#!/usr/bin/env python3
"""Exercise deep Stage 1 states and require exact packed-source tile copies."""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import time


ROOT = Path(__file__).resolve().parents[2]
PROBE = ROOT / "scripts/diagnostics/probe_stage1_tilemap_copy.lua"
DEFAULT_STATES = (
    "level1_sara_w_alone.ss0",
)
STAGE1_SETUP_ROM_OFFSET = 0x37B13
PURE_COMPLETION_PATTERNS = (
    bytes.fromhex("F1 3D 28 03 F5 18 D1 C9"),
    # Live cache hits restore their bounded IE mask through the atomic wrap;
    # title/attract retain the trailing ordinary RET at this second pattern.
    bytes.fromhex("F1 3D 28 03 F5 18 D1 78 B7 C2 98 34 C9"),
    # Current live maps tail-call the fixed-bank hazard stamper after the
    # complete 24x24 tile plane is visible.  Break on the final RET after the
    # stamper and explicit EI; this remains the exact tile-copy completion,
    # not an implementation-internal row address.
    bytes.fromhex(
        "F1 3D 28 03 F5 18 D1 FA FD DC B7 C4 42 08 FB C9"
    ),
    # A register route token avoids even a fixed-bank CALL after ordinary
    # room-$03 and prerecorded copies while retaining hazard publication.
    bytes.fromhex("F1 3D 28 03 F5 18 D1 78 FE 05 C4 44 08 FB C9"),
)
STOCK_COPY_PREFIX = bytes.fromhex("2E 00 11 A0 C1 0E 08 06 18 F3")
STOCK_COPY_COMPLETION = 0x436D
WRAM_BG_TABLE_HIGH = 0xC6
DOUBLE_BUFFER_PREFIX = bytes.fromhex(
    "2E 00 FA 80 D8 FE 02 F3 C2"
)
DOUBLE_BUFFER_COMPLETION_PATTERN = bytes.fromhex(
    "AF E0 4F 3C E0 70 AF FB C9"
)


def parse_report(path: Path) -> dict[str, str]:
    return dict(
        line.split("=", 1)
        for line in path.read_text().splitlines()
        if "=" in line
    )


def run_state(
    mgba: Path,
    rom: Path,
    state: Path | None,
    report: Path,
    frames: int,
    timeout: float,
    warm_reset: bool,
    force_pure: bool,
    trace_hash: str,
) -> dict[str, str]:
    runtime = report.parent / report.stem
    runtime.mkdir(exist_ok=True)
    report.unlink(missing_ok=True)
    runtime_rom = runtime / "candidate.gb"
    shutil.copy2(rom, runtime_rom)
    rom_bytes = runtime_rom.read_bytes()
    stock_copy = rom_bytes[
        0x42A7:0x42A7 + len(STOCK_COPY_PREFIX)
    ] == STOCK_COPY_PREFIX
    double_buffer = rom_bytes[
        0x42A7:0x42A7 + len(DOUBLE_BUFFER_PREFIX)
    ] == DOUBLE_BUFFER_PREFIX
    if stock_copy or double_buffer:
        # The unmodified game finishes its 24x24 copy at the RET at $436D.
        # Supporting it here lets the same long-running gate prove that a
        # production candidate restored the timing-sensitive stock routine.
        pure_completion = (
            STOCK_COPY_COMPLETION if stock_copy else 0xFFFF
        )
    else:
        pure_matches = [
            (index, pattern)
            for pattern in PURE_COMPLETION_PATTERNS
            for index in range(
                0x42A7, 0x436E - len(pattern) + 1
            )
            if rom_bytes[index:index + len(pattern)] == pattern
        ]
        if len(pure_matches) != 1:
            raise RuntimeError("candidate pure-copy completion is not unique")
        pure_index, pure_pattern = pure_matches[0]
        pure_completion = pure_index + len(pure_pattern) - 1
    atomic_wrap_mode = "stock-order"
    if stock_copy:
        # A stock-copier isolation build intentionally has neither an atomic
        # row nor its exit. Keep inert breakpoint addresses so the same probe
        # can still prove every native tile-only completion byte-for-byte.
        atomic_wrap = atomic_row = atomic_first_tile_write = 0xFFFF
        atomic_wrap_mode = "disabled"
    elif double_buffer:
        completion_matches = [
            index
            for index in range(
                0x42A7,
                0x436E - len(DOUBLE_BUFFER_COMPLETION_PATTERN) + 1,
            )
            if rom_bytes[
                index:index + len(DOUBLE_BUFFER_COMPLETION_PATTERN)
            ] == DOUBLE_BUFFER_COMPLETION_PATTERN
        ]
        if len(completion_matches) != 1:
            raise RuntimeError(
                "double-buffer completion is not unique"
            )
        # Break on EI after both GDMA planes have completed. Unlike the
        # row-wise atomic copier, H is already the exact $98/$9C map base.
        atomic_wrap = completion_matches[0] + 7
        atomic_row = atomic_first_tile_write = 0xFFFF
        atomic_wrap_mode = "direct-map"
    else:
        # The completed map is already stable on entry to the atomic wrapper.
        # Break before its hazard publisher can legitimately use H as scratch;
        # the older EI/RET/RETI fallback remains for historical candidates.
        atomic_wrap_entries = [
            index
            for index in range(0x3482, 0x34A3)
            if rom_bytes[index:index + 4] in (
                bytes.fromhex("CD 42 08 F3"),
                bytes.fromhex("C4 42 08 F3"),
            )
        ]
        atomic_wrap_returns = [
            index
            for index in range(0x3482, 0x34A3)
            if (
                rom_bytes[index:index + 2] == bytes.fromhex("FB C9")
                or rom_bytes[index] == 0xD9
            )
        ]
        atomic_wrap_matches = atomic_wrap_entries or atomic_wrap_returns
        if len(atomic_wrap_matches) != 1:
            raise RuntimeError(
                "candidate atomic wrapper completion is not unique"
            )
        atomic_wrap = atomic_wrap_matches[0]

        atomic_row_matches = [
            index
            for index in range(0x42A7, pure_completion)
            if rom_bytes[index:index + 6]
            in (
                bytes([0x06, WRAM_BG_TABLE_HIGH, 0x3E, 0x06, 0xE0, 0xE0]),
                bytes([0x06, WRAM_BG_TABLE_HIGH, 0x3E, 0x08, 0xE0, 0xE0]),
            )
        ]
        if len(atomic_row_matches) != 1:
            raise RuntimeError("candidate atomic-row entry is not unique")
        atomic_row = atomic_row_matches[0]
        atomic_first_tile_write = rom_bytes.find(
            bytes.fromhex("1A 13 22"), atomic_row + 6, pure_completion
        )
        if atomic_first_tile_write < 0:
            raise RuntimeError("candidate atomic tile writer is missing")

    setup_path = ""
    if state is not None:
        if rom_bytes[
            STAGE1_SETUP_ROM_OFFSET:STAGE1_SETUP_ROM_OFFSET + 4
        ] in (bytes.fromhex("78 E0 A5 F3"), bytes.fromhex("78 E0 E1 F3")):
            # Current route-caching setup: preserve the caller's B token in
            # verified-free FFA5 before entering the bounded interrupt window.
            setup_length = 14
        elif rom_bytes[
            STAGE1_SETUP_ROM_OFFSET:STAGE1_SETUP_ROM_OFFSET + 2
        ] == bytes.fromhex("F3 C9"):
            setup_length = 2
        elif (
            rom_bytes[STAGE1_SETUP_ROM_OFFSET] == 0xF3
            and rom_bytes[STAGE1_SETUP_ROM_OFFSET + 10] == 0xC9
        ):
            setup_length = 11
        elif rom_bytes[STAGE1_SETUP_ROM_OFFSET] == 0xF3:
            # The compact FFBA setup and former FFE0/direct-D880 variants all
            # begin with DI; their terminal RET distinguishes 13/14/15 bytes.
            if rom_bytes[STAGE1_SETUP_ROM_OFFSET + 12] == 0xC9:
                setup_length = 13
            elif rom_bytes[STAGE1_SETUP_ROM_OFFSET + 13] == 0xC9:
                setup_length = 14
            else:
                setup_length = 15
        else:
            setup_length = 14
        setup = rom_bytes[
            STAGE1_SETUP_ROM_OFFSET:
            STAGE1_SETUP_ROM_OFFSET + setup_length
        ]
        if len(setup) != setup_length or setup[0] not in (0x11, 0x78, 0xF3):
            raise RuntimeError("candidate Stage 1 setup is missing or malformed")
        setup_file = runtime / "stage1_atomic_setup.bin"
        setup_file.write_bytes(setup)
        setup_path = str(setup_file)

    env = os.environ.copy()
    env.update(
        {
            "QT_QPA_PLATFORM": "offscreen",
            "SDL_AUDIODRIVER": "dummy",
            "STAGE1_TILEMAP_OUT": str(report),
            "STAGE1_TILEMAP_FRAMES": str(frames),
            "STAGE1_TILEMAP_WARM_RESET": "1" if warm_reset else "0",
            "STAGE1_TILEMAP_SETUP": setup_path,
            "STAGE1_TILEMAP_FORCE_PURE": "1" if force_pure else "0",
            "STAGE1_TILEMAP_TRACE_HASH": trace_hash,
            "STAGE1_TILEMAP_PURE_COMPLETION": f"{pure_completion:04X}",
            "STAGE1_TILEMAP_ATOMIC_WRAP": f"{atomic_wrap:04X}",
            "STAGE1_TILEMAP_ATOMIC_ROW": f"{atomic_row:04X}",
            "STAGE1_TILEMAP_ATOMIC_FIRST_WRITE": (
                f"{atomic_first_tile_write:04X}"
            ),
            "STAGE1_TILEMAP_ATOMIC_WRAP_MODE": atomic_wrap_mode,
        }
    )
    command = [str(mgba), "--fastforward"]
    if state is not None:
        command.extend(["-t", str(state)])
    command.extend(
        [
            str(runtime_rom),
            "--script",
            str(PROBE),
            "-C",
            f"savegamePath={runtime}",
        ]
    )
    log = (runtime / "mgba.log").open("w")
    process = subprocess.Popen(
        command,
        cwd=ROOT,
        env=env,
        stdout=log,
        stderr=subprocess.STDOUT,
    )
    deadline = time.monotonic() + timeout
    try:
        while time.monotonic() < deadline:
            if report.is_file() and report.stat().st_size:
                return parse_report(report)
            if process.poll() is not None:
                break
            time.sleep(0.05)
        raise RuntimeError(f"no report within {timeout:.1f}s")
    finally:
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=1)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()
        log.close()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("rom", type=Path)
    parser.add_argument(
        "--states", type=Path, default=ROOT / "save_states_for_claude"
    )
    parser.add_argument(
        "--state", action="append", dest="state_names", default=[]
    )
    parser.add_argument("--frames", type=int, default=900)
    parser.add_argument("--timeout", type=float, default=12.0)
    parser.add_argument("--warm-reset", action="store_true")
    parser.add_argument("--force-pure", action="store_true")
    parser.add_argument("--trace-hash", default="")
    parser.add_argument("--output", type=Path)
    parser.add_argument(
        "--mgba", type=Path,
        default=ROOT / "scripts/mgba-qt-singleflight",
    )
    args = parser.parse_args()

    names = tuple(args.state_names) or DEFAULT_STATES
    failures: list[str] = []
    total_completions = 0
    owned_temp = None
    if args.output:
        output = args.output.resolve()
        output.mkdir(parents=True, exist_ok=True)
    else:
        owned_temp = tempfile.TemporaryDirectory(prefix="penta-stage1-tilemap-")
        output = Path(owned_temp.name)
    try:
        for name in names:
            state = None if name == "cold" else (args.states / name).resolve()
            if state is not None and not state.is_file():
                failures.append(f"{name}: missing state")
                continue
            stem = "cold" if state is None else state.stem
            report_path = output / f"{stem}.report"
            try:
                report = run_state(
                    args.mgba.resolve(), args.rom.resolve(), state,
                    report_path, args.frames, args.timeout, args.warm_reset,
                    args.force_pure, args.trace_hash,
                )
                atomic = int(report["atomic_completions"])
                pure = int(report["pure_completions"])
                completions = atomic + pure
                mismatches = int(report["mismatch_cells"])
                total_completions += completions
                print(
                    f"{name}: entries={report['copy_entries']} "
                    f"atomic={atomic} pure={pure} "
                    f"wrap_hits={report['wrap_hits']} "
                    f"exact={report['exact_copies']} "
                    f"mismatches={mismatches} "
                    f"maps={report['destinations']} "
                    f"scene={report['final_scene']} "
                    f"active={report['final_active']} "
                    f"warm_reset={report['warm_reset']} "
                    f"setup={report['runtime_setup']}"
                    f" force_pure={report['force_pure']}"
                )
                print(
                    f"  entry_h={report['entry_h_values']} "
                    f"wrap_a={report['wrap_a_values']} "
                    f"wrap_h={report['wrap_h_values']}"
                )
                if mismatches:
                    failures.append(f"{name}: {report['first_mismatch']}")
            except Exception as exc:
                failures.append(f"{name}: {exc}")
    finally:
        if owned_temp is not None:
            owned_temp.cleanup()

    if total_completions == 0:
        failures.append("no Stage 1 atomic copy completed")
    if failures:
        print("\nFAIL:")
        for failure in failures:
            print(f"  - {failure}")
        return 1
    print(
        f"\nPASS: {total_completions} completed Stage 1 tilemap copies "
        "matched the packed 24x24 room source exactly."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
