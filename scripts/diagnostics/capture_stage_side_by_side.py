#!/usr/bin/env python3
"""Build OG-versus-DX per-stage playthrough contact sheets for visual review.

For each requested stage, boots BOTH ROMs from power-on through the identical
scripted route (title -> level select -> stage), screenshots every STEP play
frames, and assembles a two-row contact sheet (OG on top, DX below) with
room/scroll annotations. The ~6% speed difference means late panels drift in
position between rows; the review target is palette/bleed/material
regressions, which do not require pixel alignment.

Runs everything through the guarded single-flight wrapper, one emulator at a
time. Announce on the intercom before running; the Ted lane has slot priority.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import time

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[2]
MGBA = ROOT / "scripts" / "mgba-qt-singleflight"
PROBE = Path(__file__).with_name("probe_stage_side_by_side.lua")
DEFAULT_ORIGINAL = ROOT / "rom/Penta Dragon (J).gb"

SHOT = re.compile(
    r"shot frame=(?P<frame>\d+) room=(?P<room>[0-9A-F]{2}) "
    r"scx=(?P<scx>[0-9A-F]{2}) scy=(?P<scy>[0-9A-F]{2}) d880=(?P<scene>[0-9A-F]{2})"
)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def terminate(process: subprocess.Popen[bytes]) -> None:
    if process.poll() is not None:
        return
    process.terminate()
    try:
        process.wait(timeout=3)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=3)


def capture(rom: Path, target: int, frames: int, step: int, mode: str,
            prefix: Path, timeout: float) -> list[dict]:
    prefix.parent.mkdir(parents=True, exist_ok=True)
    marker = Path(str(prefix) + ".done")
    trace = Path(str(prefix) + ".trace")
    marker.unlink(missing_ok=True)
    trace.unlink(missing_ok=True)
    env = os.environ.copy()
    env.update(
        SSS_OUT=str(prefix),
        SSS_TARGET=str(target),
        SSS_FRAMES=str(frames),
        SSS_STEP=str(step),
        SSS_MODE=mode,
        QT_QPA_PLATFORM="offscreen",
        SDL_AUDIODRIVER="dummy",
    )
    process = subprocess.Popen(
        [str(MGBA), "--fastforward",
         "-C", f"savegamePath={prefix.parent}",
         "-C", f"savestatePath={prefix.parent}",
         str(rom), "--script", str(PROBE)],
        cwd=ROOT, env=env,
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    try:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if marker.is_file() and marker.read_text().strip():
                break
            if process.poll() is not None:
                raise RuntimeError(f"mGBA exited {process.returncode}")
            time.sleep(0.05)
        else:
            raise TimeoutError(f"stage capture timed out: {prefix.name}")
    finally:
        terminate(process)
    status = marker.read_text().strip()
    if status != "ok":
        raise RuntimeError(f"stage capture rejected {prefix.name}: {status}")
    rows = []
    for line in trace.read_text().splitlines():
        m = SHOT.fullmatch(line.strip())
        if m:
            shot_path = Path(f"{prefix}.f{int(m.group('frame')):04d}.png")
            if shot_path.is_file():
                rows.append({
                    "frame": int(m.group("frame")),
                    "room": m.group("room"),
                    "scx": m.group("scx"),
                    "scy": m.group("scy"),
                    "png": shot_path,
                })
    if not rows:
        raise RuntimeError(f"no screenshots captured for {prefix.name}")
    return rows


def build_sheet(og: list[dict], dx: list[dict], out: Path, stage: int) -> None:
    frames = sorted({r["frame"] for r in og} & {r["frame"] for r in dx})
    og_by = {r["frame"]: r for r in og}
    dx_by = {r["frame"]: r for r in dx}
    if not frames:
        raise RuntimeError("no aligned frames between OG and DX")
    w, h = Image.open(og_by[frames[0]]["png"]).size
    label_h = 14
    cols = len(frames)
    sheet = Image.new("RGB", (cols * w, 2 * (h + label_h) + label_h), "black")
    draw = ImageDraw.Draw(sheet)
    draw.text((4, 2 * (h + label_h)),
              f"stage {stage + 1}: top=OG bottom=DX, panels labeled frame/room/scx",
              fill="white")
    for col, frame in enumerate(frames):
        for row, src in ((0, og_by[frame]), (1, dx_by[frame])):
            y = row * (h + label_h)
            sheet.paste(Image.open(src["png"]).convert("RGB"), (col * w, y))
            draw.text((col * w + 2, y + h + 1),
                      f"f{frame} r{src['room']} x{src['scx']}",
                      fill="yellow" if row else "cyan")
    sheet.save(out)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("dx_rom", type=Path)
    parser.add_argument("--original", type=Path, default=DEFAULT_ORIGINAL)
    parser.add_argument("--stage", action="append", type=int, choices=range(7),
                        help="FFBA target(s); default all 7")
    parser.add_argument("--frames", type=int, default=1200)
    parser.add_argument("--step", type=int, default=60)
    parser.add_argument("--mode", choices=("right", "patrol"), default="patrol")
    parser.add_argument("--timeout", type=float, default=300.0)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    stages = args.stage if args.stage is not None else list(range(7))
    args.output.mkdir(parents=True, exist_ok=True)
    manifest = {
        "schema": "penta-stage-side-by-side-v1",
        "original_rom_sha256": sha256(args.original.resolve()),
        "dx_rom_sha256": sha256(args.dx_rom.resolve()),
        "frames": args.frames, "step": args.step, "mode": args.mode,
        "stages": {},
    }
    for target in stages:
        stage_dir = args.output / f"stage{target + 1}"
        og = capture(args.original.resolve(), target, args.frames, args.step,
                     args.mode, stage_dir / "og" / "run", args.timeout)
        dx = capture(args.dx_rom.resolve(), target, args.frames, args.step,
                     args.mode, stage_dir / "dx" / "run", args.timeout)
        sheet = args.output / f"stage{target + 1}-side-by-side.png"
        build_sheet(og, dx, sheet, target)
        manifest["stages"][f"stage{target + 1}"] = {
            "og_shots": len(og), "dx_shots": len(dx), "sheet": str(sheet),
        }
        print(f"stage {target + 1}: og={len(og)} dx={len(dx)} shots -> {sheet}")
    (args.output / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print(f"Manifest: {args.output / 'manifest.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
