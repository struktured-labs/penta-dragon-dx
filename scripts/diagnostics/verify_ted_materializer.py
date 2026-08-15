#!/usr/bin/env python3
"""Execute and verify Ted's real three-cell rejection-mask materializer."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import time
import uuid
import zlib

from normalize_mgba_state_pc import (
    CPU_EXECUTION_STATE,
    CPU_FLAGS,
    CPU_PC,
    CPU_SP,
    GB_STATE_SIZE,
    MBC1_BANK_HI,
    MBC1_BANK_LO,
    MEMORY_CURRENT_BANK,
    MEMORY_FLAGS,
    png_chunks,
    state_offset,
    write_png,
)

ROOT = Path(__file__).resolve().parents[2]
MGBA = ROOT / "scripts/mgba-headless-singleflight"
PROBE = Path(__file__).with_name("probe_ted_materializer.lua")
SCHEMA = "penta-ted-materializer-v1"
HARNESS = 0xC720
SOURCE = 0xC700
RESULTS = 0xCC00
MARKER = 0xCD00
STACK = 0xDFF0
MATERIALIZER = 0x5CDA


def floor_tile(row: int, col: int) -> int:
    return 0x77 + 2 * (row & 1) + (col & 1)


def harness_code() -> bytes:
    code = bytearray([0xF3])                # DI
    for index in range(32):
        mask = index & 7
        parity = index >> 3
        row, col = (parity >> 1) & 1, parity & 1
        address = 0x9800 + row * 32 + col
        destination = RESULTS + index * 3
        code.extend((
            0x11, SOURCE & 0xFF, SOURCE >> 8,
            0x21, address & 0xFF, address >> 8,
            0x3E, mask << 5, 0xE0, 0xA7,
            0xCD, MATERIALIZER & 0xFF, MATERIALIZER >> 8,
            0x78, 0xEA, destination & 0xFF, destination >> 8,
            0x79, 0xEA, (destination + 1) & 0xFF, (destination + 1) >> 8,
            0xF0, 0xA8, 0xEA,
            (destination + 2) & 0xFF, (destination + 2) >> 8,
        ))
    code.extend((
        0x3E, 0xA5, 0xEA, MARKER & 0xFF, MARKER >> 8,
        0x18, 0xFE,                         # stable terminal loop
    ))
    return bytes(code)


def patched_state(source: Path, destination: Path, rom: Path) -> None:
    chunks = png_chunks(source.read_bytes())
    indices = [i for i, (kind, _payload) in enumerate(chunks) if kind == b"gbAs"]
    if len(indices) != 1:
        raise RuntimeError(f"expected one gbAs chunk, found {len(indices)}")
    index = indices[0]
    raw = bytearray(zlib.decompress(chunks[index][1]))
    if len(raw) != GB_STATE_SIZE:
        raise RuntimeError(f"unexpected Game Boy state size 0x{len(raw):X}")
    raw[0x0004:0x0008] = (
        zlib.crc32(rom.read_bytes()) & 0xFFFFFFFF
    ).to_bytes(4, "little")
    raw[CPU_SP:CPU_SP + 2] = STACK.to_bytes(2, "little")
    raw[CPU_PC:CPU_PC + 2] = HARNESS.to_bytes(2, "little")
    raw[CPU_EXECUTION_STATE] = 3
    raw[CPU_FLAGS:CPU_FLAGS + 4] = bytes(4)
    raw[MEMORY_CURRENT_BANK:MEMORY_CURRENT_BANK + 2] = (13).to_bytes(2, "little")
    raw[MBC1_BANK_LO] = 13
    raw[MBC1_BANK_HI] = 0
    flags = int.from_bytes(raw[MEMORY_FLAGS:MEMORY_FLAGS + 2], "little")
    raw[MEMORY_FLAGS:MEMORY_FLAGS + 2] = (flags | 0x0008).to_bytes(2, "little")
    raw[state_offset(0xFF99)] = 13
    raw[state_offset(0xFFFF)] = 0
    program = harness_code()
    start = state_offset(HARNESS)
    raw[start:start + len(program)] = program
    raw[state_offset(SOURCE):state_offset(SOURCE) + 3] = bytes((0x11, 0x22, 0x33))
    raw[state_offset(RESULTS):state_offset(RESULTS) + 32 * 3] = bytes(32 * 3)
    raw[state_offset(MARKER)] = 0
    chunks[index] = (b"gbAs", zlib.compress(bytes(raw), level=9))
    write_png(destination, chunks)


def run(rom: Path, state: Path, output: Path, timeout: float) -> list[str]:
    trace_dir = output.parent / "materializer" / uuid.uuid4().hex
    trace_dir.mkdir(parents=True, exist_ok=True)
    prefix = trace_dir / "trace"
    fixture = trace_dir / "materializer.ss0"
    patched_state(state, fixture, rom)
    env = os.environ.copy()
    env.update(
        QT_QPA_PLATFORM="offscreen",
        SDL_AUDIODRIVER="dummy",
        TED_MATERIALIZER_OUT=str(prefix),
    )
    process = subprocess.Popen(
        [str(MGBA), "-t", str(fixture), "--script", str(PROBE),
         str(rom.resolve())],
        cwd=ROOT, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
        text=True,
    )
    marker = Path(str(prefix) + ".done")
    deadline = time.monotonic() + timeout
    try:
        while time.monotonic() < deadline:
            if marker.is_file():
                status = marker.read_text().strip()
                if not status:
                    time.sleep(0.02)
                    continue
                if status != "status=ok tests=32":
                    raise RuntimeError(status)
                lines = prefix.read_text().splitlines()
                if len(lines) == 32:
                    return lines
                # mGBA's Lua file and marker closes can become visible in
                # opposite order on a fast isolated release run. Completion
                # requires both artifacts, never the marker alone.
                time.sleep(0.02)
                continue
            if process.poll() is not None:
                raise RuntimeError(
                    (process.stderr.read() if process.stderr else "").strip()
                )
            time.sleep(0.02)
        raise TimeoutError(f"Ted materializer timed out after {timeout:.1f}s")
    finally:
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=2)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("rom", type=Path)
    parser.add_argument(
        "--state", type=Path,
        default=ROOT / "save_states_for_claude/level1_sara_d_alone.ss0",
    )
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--timeout", type=float, default=30)
    args = parser.parse_args()
    args.output.parent.mkdir(parents=True, exist_ok=True)

    lines = run(args.rom, args.state, args.output, args.timeout)
    failures: list[dict[str, object]] = []
    seen: set[int] = set()
    source = (0x11, 0x22, 0x33)
    for line in lines:
        fields = line.split()
        if len(fields) != 4:
            failures.append({"kind": "malformed", "line": line})
            continue
        index, out0, out1, out2 = (
            int(fields[0]), int(fields[1], 16), int(fields[2], 16),
            int(fields[3], 16),
        )
        mask = index & 7
        seen.add(index)
        parity = index >> 3
        row, col = (parity >> 1) & 1, parity & 1
        expected = tuple(
            floor_tile(row, col + slot) if mask & (1 << slot)
            else source[slot]
            for slot in range(3)
        )
        actual = (out0, out1, out2)
        if actual != expected:
            failures.append({
                "kind": "wrong-materialization", "index": index,
                "mask": mask, "row_parity": row, "col_parity": col,
                "expected": expected, "actual": actual,
            })
    missing = sorted(set(range(32)) - seen)
    if missing:
        failures.append({"kind": "missing-tests", "indices": missing})
    receipt = {
        "schema": SCHEMA,
        "rom_sha256": hashlib.sha256(args.rom.read_bytes()).hexdigest(),
        "state_sha256": hashlib.sha256(args.state.read_bytes()).hexdigest(),
        "status": "pass" if not failures else "fail",
        "tests": len(seen),
        "masks": 8,
        "checker_parities": 4,
        "failures": failures,
    }
    args.output.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n")
    print(json.dumps(receipt, indent=2, sort_keys=True))
    return 0 if receipt["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
