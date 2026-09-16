#!/usr/bin/env python3
"""Confirm the title-colour prototype on mGBA's accurate pixel pipeline.

PyBoy is adequate for the attribute/CRAM content checks, but it does not model
VRAM/CRAM access windows.  This gate re-renders the same title frame under
mGBA through the mandatory single-flight wrapper and reports the CRAM block,
the published BG attribute rows and the distinct rendered colours.

Exit codes: 0 = captured, 1 = capture failed, 75 = the emulator lock was busy
(a hard stop, never a reason to invoke the emulator directly).
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import tempfile
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PROJECT_TMP = ROOT / "tmp"
LUA = Path(__file__).with_name("title_color_shot.lua")
LOCK_BUSY = 75


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("rom", type=Path)
    parser.add_argument("--at-frame", type=int, default=400)
    parser.add_argument(
        "--wait-return", action="store_true",
        help="capture the title after the attract reel returns to it",
    )
    parser.add_argument("--frame-limit", type=int, default=200000)
    parser.add_argument("--timeout", type=float, default=60.0)
    parser.add_argument(
        "--out", type=Path, default=Path("tmp/title-color/mgba"),
    )
    parser.add_argument(
        "--mgba", default=str(ROOT / "scripts/mgba-qt-singleflight"),
    )
    parser.add_argument(
        "--writer-trace", action="store_true",
        help="also log every CPU write into the title attribute rows while scene $01 "
             "is live (frame, address, VBK, old/new, PC, bank, LY, STAT, DF08) to <out>-writers.tsv",
    )
    parser.add_argument(
        "--writer-trace-address",
        help="restrict --writer-trace to one VRAM CPU address (for example 0x9924)",
    )
    parser.add_argument(
        "--expect-image", action="store_true",
        help="compare BOTH maps' full 32x18 attribute rows 1..18 against the "
             "role image rebuilt from the ROM's own title list (576 cells each); "
             "exit 1 on any mismatch",
    )
    args = parser.parse_args()

    if not args.rom.is_file():
        parser.error(f"ROM not found: {args.rom}")
    if args.writer_trace_address is not None:
        if not args.writer_trace:
            parser.error("--writer-trace-address requires --writer-trace")
        try:
            trace_address = int(args.writer_trace_address, 0)
        except ValueError:
            parser.error("--writer-trace-address must be an integer")
        if not 0x8000 <= trace_address <= 0x9FFF:
            parser.error("--writer-trace-address must be a VRAM CPU address")
    else:
        trace_address = None
    out = args.out.resolve()
    scratch = PROJECT_TMP.resolve()
    if out == scratch or scratch not in out.parents:
        parser.error("--out must be a file stem below repository tmp/")
    out.parent.mkdir(parents=True, exist_ok=True)
    PROJECT_TMP.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(
        prefix="penta-title-color-", dir=PROJECT_TMP
    ) as tmp:
        stem = Path(tmp) / "result"
        env = os.environ.copy()
        env.update(
            OUT=str(stem),
            AT_FRAME=str(args.at_frame),
            WAIT_RETURN="1" if args.wait_return else "0",
            FRAME_LIMIT=str(args.frame_limit),
            TITLE_WRITER_TRACE="1" if args.writer_trace else "0",
            QT_QPA_PLATFORM="offscreen",
            SDL_AUDIODRIVER="dummy",
        )
        if trace_address is not None:
            env["TITLE_WRITER_TRACE_ADDRESS"] = hex(trace_address)
        process = subprocess.run(
            [
                args.mgba,
                "--fastforward",
                "--script",
                str(LUA),
                str(args.rom.resolve()),
            ],
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            timeout=args.timeout,
            check=False,
        )
        if process.returncode == LOCK_BUSY:
            print(
                "LOCK BUSY (exit 75): the project-wide emulator lock is held. "
                "Not bypassing it."
            )
            return LOCK_BUSY
        text = stem.with_suffix(".txt")
        shot = stem.with_suffix(".png")
        if not text.is_file() or not shot.is_file():
            print(f"FAIL: no capture (exit {process.returncode})")
            print(process.stderr.decode(errors="replace")[-2000:])
            return 1
        report = text.read_text()
        shutil.copy(text, out.with_suffix(".txt"))
        shutil.copy(shot, out.with_suffix(".png"))
        trace = Path(str(stem) + "-writers.tsv")
        if trace.is_file():
            shutil.copy(trace, Path(str(out) + "-writers.tsv"))
            print(f"writer trace: {str(out) + '-writers.tsv'}")

    print(report.strip())
    status = 0
    if args.expect_image:
        status = check_both_map_image(args.rom, report)
    try:
        from PIL import Image
    except ImportError:
        return status
    image = Image.open(out.with_suffix(".png")).convert("RGB")
    counts = Counter(image.getdata())
    print(f"distinct rendered colours: {len(counts)}")
    for colour, count in counts.most_common(8):
        print(f"  {colour} x{count}")
    print(f"artifacts: {out.with_suffix('.png')} {out.with_suffix('.txt')}")
    return status


def check_both_map_image(rom_path: Path, report: str) -> int:
    """Exact 576-cell comparison of both physical maps against the role image."""
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import build_title_color_prototype as title
    rom = rom_path.read_bytes()
    image, _coverage = title.build_attribute_image(title.parse_title_list(rom))
    expected = bytes(image)
    assert len(expected) == title.IMAGE_ROWS * title.MAP_STRIDE == 576
    dumps = {}
    for line in report.splitlines():
        for key in ("attrs9800", "attrs9C00"):
            if line.startswith(key + "="):
                dumps[key] = bytes.fromhex(line.split("=", 1)[1].strip())
    if set(dumps) != {"attrs9800", "attrs9C00"}:
        print("FAIL: capture lacks attrs9800/attrs9C00 (old probe?)")
        return 1
    bad = 0
    for key, got in dumps.items():
        if len(got) != 576:
            print(f"FAIL: {key} has {len(got)} cells, expected 576")
            bad += 1
            continue
        diff = [i for i in range(576) if got[i] != expected[i]]
        rows = sorted({title.IMAGE_FIRST_ROW + i // 32 for i in diff})
        print(f"{key}: {576 - len(diff)}/576 cells match role image"
              + (f"; mismatched rows {rows[:12]}" if diff else ""))
        bad += bool(diff)
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
