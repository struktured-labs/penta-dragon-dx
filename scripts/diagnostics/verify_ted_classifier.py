#!/usr/bin/env python3
"""Execute Ted's real classifier against canonical and measured duplicate cells."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import uuid
import zlib

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

from build_v302_title_fix import (
    TED_SANITIZER_RUNTIME_ADDR,
    build_ted_group_sanitizer_wram,
)
from normalize_mgba_state_pc import (
    CPU_EXECUTION_STATE, CPU_FLAGS, CPU_PC, CPU_SP, GB_STATE_SIZE,
    MBC1_BANK_HI, MBC1_BANK_LO, MEMORY_CURRENT_BANK, MEMORY_FLAGS,
    png_chunks, state_offset, write_png,
)
from verify_ted_determinism import TED_NUMBERED_TILE_POSITION

MGBA = ROOT / "scripts/mgba-headless-singleflight"
PROBE = Path(__file__).with_name("probe_ted_classifier.lua")
SCHEMA = "penta-ted-classifier-v1"
HARNESS, SOURCE, RESULTS, MARKER, STACK = 0xC720, 0xC700, 0xCC00, 0xCD00, 0xDFE0
ANCHOR = (8, 12)
DUPLICATES = (
    (0x13, (12, 8)), (0x14, (12, 9)), (0x1C, (13, 9)),
    (0x1F, (14, 10)), (0x20, (14, 11)),
    (0x27, (15, 10)), (0x28, (15, 11)),
)


def floor_tile(row: int, col: int) -> int:
    return 0x77 + 2 * (row & 1) + (col & 1)


def tests() -> list[tuple[str, int, tuple[int, int]]]:
    result = [("duplicate", tile, relative) for tile, relative in DUPLICATES]
    result.extend(
        ("canonical", tile, TED_NUMBERED_TILE_POSITION[tile])
        for tile, _relative in DUPLICATES
    )
    result.append(("partial-initial-crown", 0x02, (0, 0)))
    return result


def harness_code() -> tuple[bytes, list[tuple[int, ...]]]:
    code = bytearray([0xF3])
    expected_rows: list[tuple[int, ...]] = []
    for index, (kind, tile, relative) in enumerate(tests()):
        if kind == "partial-initial-crown":
            row, col = 4, 12
        else:
            row = (ANCHOR[0] + relative[0]) & 31
            col = (ANCHOR[1] + relative[1]) & 31
        group_col = col - col % 3
        slot = col - group_col
        source = [floor_tile(row, group_col + i) for i in range(3)]
        if kind == "partial-initial-crown":
            source = [0x02, 0x03, floor_tile(row, group_col + 2)]
        else:
            source[slot] = tile
        expected = source.copy()
        if kind == "duplicate":
            expected[slot] = floor_tile(row, col)
        expected_rows.append(tuple(expected))
        for offset, value in enumerate(source):
            code.extend((0x3E, value, 0xEA, (SOURCE + offset) & 0xFF,
                         (SOURCE + offset) >> 8))
        for address, value in (
            (0xC4FA, ANCHOR[0]), (0xC4FB, ANCHOR[1]),
            (0xFFA9, 0 if kind == "partial-initial-crown" else 1),
        ):
            if address >= 0xFF00:
                code.extend((0x3E, value, 0xE0, address & 0xFF))
            else:
                code.extend((0x3E, value, 0xEA, address & 0xFF, address >> 8))
        destination = 0x9800 + row * 32 + group_col
        output = RESULTS + index * 3
        code.extend((
            0x21, destination & 0xFF, destination >> 8,
            0x11, SOURCE & 0xFF, SOURCE >> 8,
            0x31, STACK & 0xFF, STACK >> 8,
            0xCD, TED_SANITIZER_RUNTIME_ADDR & 0xFF,
            TED_SANITIZER_RUNTIME_ADDR >> 8,
            0x78, 0xEA, output & 0xFF, output >> 8,
            0x79, 0xEA, (output + 1) & 0xFF, (output + 1) >> 8,
            0xF0, 0xA8, 0xEA, (output + 2) & 0xFF, (output + 2) >> 8,
        ))
    code.extend((0x3E, 0xA5, 0xEA, MARKER & 0xFF, MARKER >> 8, 0x18, 0xFE))
    return bytes(code), expected_rows


def patched_state(source: Path, destination: Path, rom: Path) -> list[tuple[int, ...]]:
    chunks = png_chunks(source.read_bytes())
    indices = [i for i, (kind, _payload) in enumerate(chunks) if kind == b"gbAs"]
    if len(indices) != 1:
        raise RuntimeError(f"expected one gbAs chunk, found {len(indices)}")
    index = indices[0]
    raw = bytearray(zlib.decompress(chunks[index][1]))
    if len(raw) != GB_STATE_SIZE:
        raise RuntimeError(f"unexpected Game Boy state size 0x{len(raw):X}")
    raw[0x0004:0x0008] = (zlib.crc32(rom.read_bytes()) & 0xFFFFFFFF).to_bytes(4, "little")
    raw[CPU_SP:CPU_SP + 2] = STACK.to_bytes(2, "little")
    raw[CPU_PC:CPU_PC + 2] = HARNESS.to_bytes(2, "little")
    raw[CPU_EXECUTION_STATE] = 3
    raw[CPU_FLAGS:CPU_FLAGS + 4] = bytes(4)
    raw[MEMORY_CURRENT_BANK:MEMORY_CURRENT_BANK + 2] = (13).to_bytes(2, "little")
    raw[MBC1_BANK_LO], raw[MBC1_BANK_HI] = 13, 0
    flags = int.from_bytes(raw[MEMORY_FLAGS:MEMORY_FLAGS + 2], "little")
    raw[MEMORY_FLAGS:MEMORY_FLAGS + 2] = (flags | 0x0008).to_bytes(2, "little")
    raw[state_offset(0xFF99)] = 13
    raw[state_offset(0xFFFF)] = 0
    runtime = build_ted_group_sanitizer_wram()
    raw[state_offset(TED_SANITIZER_RUNTIME_ADDR):
        state_offset(TED_SANITIZER_RUNTIME_ADDR) + len(runtime)] = runtime
    program, expected = harness_code()
    raw[state_offset(HARNESS):state_offset(HARNESS) + len(program)] = program
    raw[state_offset(RESULTS):state_offset(RESULTS) + 15 * 3] = bytes(15 * 3)
    raw[state_offset(MARKER)] = 0
    # At direct entry, CALL owns SP+0..1 and the classifier expects stacked A
    # bytes at entry SP+5/+7/+9. CALL begins from STACK, so entry SP=STACK-2.
    for address in (STACK + 3, STACK + 5, STACK + 7):
        raw[state_offset(address)] = 0
    chunks[index] = (b"gbAs", zlib.compress(bytes(raw), level=9))
    write_png(destination, chunks)
    return expected


def run(rom: Path, state: Path, output: Path, timeout: float) -> tuple[list[str], list[tuple[int, ...]]]:
    trace_dir = output.parent / "classifier" / uuid.uuid4().hex
    trace_dir.mkdir(parents=True, exist_ok=True)
    prefix, fixture = trace_dir / "trace", trace_dir / "classifier.ss0"
    expected = patched_state(state, fixture, rom)
    env = os.environ.copy()
    env.update(QT_QPA_PLATFORM="offscreen", SDL_AUDIODRIVER="dummy",
               TED_CLASSIFIER_OUT=str(prefix))
    process = subprocess.Popen(
        [str(MGBA), "-t", str(fixture), "--script", str(PROBE), str(rom.resolve())],
        cwd=ROOT, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True,
    )
    marker, deadline = Path(str(prefix) + ".done"), time.monotonic() + timeout
    try:
        while time.monotonic() < deadline:
            if marker.is_file():
                status = marker.read_text().strip()
                lines = prefix.read_text().splitlines()
                if status == "status=ok tests=15" and len(lines) == 15:
                    return lines, expected
                if status and status != "status=ok tests=15":
                    raise RuntimeError(status)
                time.sleep(0.02); continue
            if process.poll() is not None:
                raise RuntimeError((process.stderr.read() if process.stderr else "").strip())
            time.sleep(0.02)
        raise TimeoutError(f"Ted classifier timed out after {timeout:.1f}s")
    finally:
        if process.poll() is None:
            process.terminate()
            try: process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                process.kill(); process.wait(timeout=2)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("rom", type=Path)
    parser.add_argument("--state", type=Path,
                        default=ROOT / "save_states_for_claude/level1_sara_d_alone.ss0")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--timeout", type=float, default=30)
    args = parser.parse_args()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    lines, expected = run(args.rom, args.state, args.output, args.timeout)
    failures = []
    seen = set()
    for line in lines:
        fields = line.split()
        if len(fields) != 4:
            failures.append({"kind": "malformed", "line": line}); continue
        index = int(fields[0]); actual = tuple(int(value, 16) for value in fields[1:])
        seen.add(index)
        if actual != expected[index]:
            failures.append({"kind": "wrong-classification", "index": index,
                             "case": tests()[index][0], "tile": tests()[index][1],
                             "expected": expected[index], "actual": actual})
    missing = sorted(set(range(15)) - seen)
    if missing: failures.append({"kind": "missing-tests", "indices": missing})
    receipt = {"schema": SCHEMA,
               "rom_sha256": hashlib.sha256(args.rom.read_bytes()).hexdigest(),
               "state_sha256": hashlib.sha256(args.state.read_bytes()).hexdigest(),
               "status": "pass" if not failures else "fail",
               "tests": len(seen), "duplicate_cases": 7, "canonical_cases": 7,
               "partial_initial_crown_cases": 1,
               "failures": failures}
    args.output.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n")
    print(json.dumps(receipt, indent=2, sort_keys=True))
    return 0 if receipt["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
