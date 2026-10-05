#!/usr/bin/env python3
"""#14: Sara is hidden behind the black ceiling overhang exactly as on stock.

Two cold-boot runs (original cartridge, then the candidate) go through the
fail-closed single-flight launcher with the same input recipe
(probe_sara_overhang_priority.lua): native title route, one position assist to
the pre-secret corridor (world 1240/1344 at frame 1201), Down for frames
1202..1212, then no input. Sara settles at world 1240/1356, camera $0C08,
under the black overhang.

Frame-exact acceptance, per run:
* overhang samples (frames 1240, 1260, 1300): scene $02, world 1240/1356,
  camera $0C08, all four Sara OAM entries (FE00..FE0F) at the stock positions
  with OBJ-to-BG priority (attribute bit 7) set, and every pixel of Sara's
  16x16 footprint black in the native 160x144 screenshot (she is hidden);
  the rest of the frame must not be blank.
* floor control (frame 1200, before the assist): priority clear on all four
  entries and Sara visible (non-black footprint pixels).
The stock run must satisfy the same contract, which pins the reference
behaviour (original DMG OBJ priority). Regression: db09de8d drew Sara over the
overhang (priority never set; 192 non-black footprint pixels at frame 1260).
Emulator evidence only, never hardware qualification.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

from PIL import Image

ROOT = Path(__file__).resolve().parents[2]
SELF = Path(__file__).resolve()
PROBE = SELF.parent / "probe_sara_overhang_priority.lua"
LAUNCHER = ROOT / "scripts/mgba-qt-singleflight"
STOCK = ROOT / "rom/Penta Dragon (J).gb"
STOCK_SHA = "2f32570cff62b8664bfa06b939988c3fd6a7efabf870a990a5fa65bab37eac30"
SCHEMA = "penta-sara-overhang-priority-v1"
OVERHANG = ("overhang-1240", "overhang", "overhang-1300")
FLOOR = "floor"
WORLD = [1240, 1356]
CAMERA = "0C08"


class GateError(RuntimeError):
    pass


def footprint(sample: dict) -> dict:
    """Pixel facts for Sara's four quadrants from the sample screenshot."""
    image = Image.open(sample["screenshot"]).convert("RGB")
    if image.size != (160, 144):
        raise GateError(f"{sample['tag']}: capture must keep native 160x144")
    pixels = image.load()
    covered, nonblack = set(), 0
    for y, x, _tile, _attr in sample["oam"]:
        for dy in range(8):
            for dx in range(8):
                sx, sy = x - 8 + dx, y - 16 + dy
                if 0 <= sx < 160 and 0 <= sy < 144 and (sx, sy) not in covered:
                    covered.add((sx, sy))
                    nonblack += pixels[sx, sy] != (0, 0, 0)
    total = sum(pixels[x, y] != (0, 0, 0) for y in range(144) for x in range(160))
    return dict(footprint_pixels=len(covered), footprint_nonblack=nonblack, image_nonblack=total)


def summarize(sample: dict) -> dict:
    facts = dict(frame=sample["frame"], scene=sample["scene"], world=sample["world"],
                 camera=sample["camera"], oam=sample["oam"], flags=sample["flags"])
    facts.update(footprint(sample) if "screenshot" in sample else
                 {k: sample[k] for k in ("footprint_nonblack", "image_nonblack")})
    facts.setdefault("footprint_pixels", 256)
    return facts


def check_run(label: str, samples: dict) -> None:
    for tag in OVERHANG:
        s = samples.get(tag)
        if s is None:
            raise GateError(f"{label}: missing sample {tag}")
        if s["scene"] != 2 or list(s["world"]) != WORLD or s["camera"] != CAMERA:
            raise GateError(f"{label} {tag}: not the reviewed overhang position "
                            f"(scene {s['scene']}, world {s['world']}, camera {s['camera']})")
        if not all(attr & 0x80 for _y, _x, _t, attr in s["oam"]):
            raise GateError(f"{label} {tag}: Sara OBJ priority not set {s['oam']}")
        if s["footprint_pixels"] != 256 or s["image_nonblack"] <= 256:
            raise GateError(f"{label} {tag}: footprint/frame cannot qualify occlusion")
        if s["footprint_nonblack"]:
            raise GateError(f"{label} {tag}: {s['footprint_nonblack']} Sara pixels drawn over the overhang")
    s = samples.get(FLOOR)
    if s is None:
        raise GateError(f"{label}: missing floor control")
    if s["scene"] != 2 or any(attr & 0x80 for _y, _x, _t, attr in s["oam"]):
        raise GateError(f"{label} floor: priority set on open floor {s['oam']}")
    if not s["footprint_nonblack"]:
        raise GateError(f"{label} floor: Sara not visible on open floor")


def evaluate(stock: dict, candidate: dict) -> dict:
    """Pure acceptance logic over summarized samples keyed by tag."""
    check_run("stock", stock)
    check_run("candidate", candidate)
    for tag in OVERHANG:
        if [o[:2] for o in candidate[tag]["oam"]] != [o[:2] for o in stock[tag]["oam"]]:
            raise GateError(f"{tag}: Sara OAM positions differ from stock")
    return dict(status="pass", overhang_frames=[stock[t]["frame"] for t in OVERHANG],
                covered_pixels=sum(candidate[t]["footprint_pixels"] for t in OVERHANG))


def run(rom: Path, label: str, output: Path, timeout: float) -> dict:
    work = output / label
    if work.exists():
        shutil.rmtree(work)
    work.mkdir(parents=True)
    shutil.copyfile(rom, work / "rom.gb")
    shutil.copyfile(PROBE, work / "probe.lua")
    environment = dict(os.environ)
    for name in ("PENTA_MGBA_LOCK", "PENTA_MGBA_QT_BIN"):
        environment.pop(name, None)
    environment.update(PSO_OUT=str(work),
                       QT_QPA_PLATFORM=environment.get("QT_QPA_PLATFORM", "offscreen"),
                       SDL_AUDIODRIVER="dummy")
    command = [str(LAUNCHER), "--fastforward", "--script", str(work / "probe.lua"), str(work / "rom.gb")]
    with (work / "emulator.log").open("w") as log:
        try:
            result = subprocess.run(command, cwd=ROOT, env=environment, stdout=log,
                                    stderr=subprocess.STDOUT, timeout=timeout, check=False)
        except subprocess.TimeoutExpired as error:
            raise GateError(f"{label}: emulator timed out") from error
    if result.returncode == 75:
        raise GateError("single-flight emulator lock is busy")
    path = work / "events.jsonl"
    if not path.is_file():
        raise GateError(f"{label}: probe produced no events (exit {result.returncode})")
    events = [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
    if not events or events[-1]["kind"] != "done":
        raise GateError(f"{label}: probe did not finish")
    return {e["tag"]: summarize(e) for e in events if e["kind"] == "sample"}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("rom", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--stock", type=Path, default=STOCK)
    parser.add_argument("--timeout", type=float, default=180.0)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    report = dict(schema=SCHEMA, rom=str(args.rom.resolve()),
                  rom_sha256=hashlib.sha256(args.rom.read_bytes()).hexdigest(), status="fail")
    try:
        if hashlib.sha256(args.stock.read_bytes()).hexdigest() != STOCK_SHA:
            raise GateError("reference is not the original cartridge")
        stock = run(args.stock.resolve(), "stock", args.output, args.timeout)
        candidate = run(args.rom.resolve(), "candidate", args.output, args.timeout)
        report.update(stock=stock, candidate=candidate)
        report.update(evaluate(stock, candidate))
    except GateError as error:
        report["error"] = str(error)
    (args.output / "report.json").write_text(json.dumps(report, indent=2) + "\n")
    if report["status"] != "pass":
        print(f"FAIL: {report['error']}")
        return 1
    print("PASS: Sara hidden under the black ceiling overhang (frames 1240/1260/1300, "
          "768 footprint pixels black, OBJ priority set) and visible on open floor, as on stock")
    return 0


if __name__ == "__main__":
    sys.exit(main())
