#!/usr/bin/env python3
"""Prove that completing OPENING cannot contaminate the Stage-1 route."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import shutil

from verify_stage1_north_integrity import run_route


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_ROM = ROOT / "rom/working/penta_dragon_dx_FIXED.gb"
PLANES = (
    "c1a0.bin",
    "visible-tiles.bin",
    "visible-attrs.bin",
    "bg-cram.bin",
    "obj-cram.bin",
    "hardware-oam.bin",
    "shadow-oam.bin",
    "vram-low-tiles.bin",
    "vram-high-tiles.bin",
    "vram9800.bin",
    "vram9c00.bin",
    "vram9800-attrs.bin",
    "vram9c00-attrs.bin",
)
REQUIRED_PLANES = (
    "c1a0.bin",
    "visible-tiles.bin",
    "visible-attrs.bin",
    "bg-cram.bin",
    "obj-cram.bin",
)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def compare_plane(direct: Path, opening: Path) -> dict[str, object]:
    left = direct.read_bytes()
    right = opening.read_bytes()
    if len(left) != len(right):
        return {
            "bytes": [len(left), len(right)],
            "differences": max(len(left), len(right)),
            "first_difference": 0,
            "direct_sha256": sha256(direct),
            "opening_sha256": sha256(opening),
        }
    offsets = [
        index
        for index, (a, b) in enumerate(zip(left, right, strict=True))
        if a != b
    ]
    return {
        "bytes": len(left),
        "differences": len(offsets),
        "first_difference": offsets[0] if offsets else -1,
        "direct_sha256": sha256(direct),
        "opening_sha256": sha256(opening),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("rom", nargs="?", type=Path, default=DEFAULT_ROM)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--timeout", type=float, default=120.0)
    parser.add_argument("--frames", type=int, default=20000)
    parser.add_argument("--target-camera", type=lambda value: int(value, 0),
                        default=0x03A4)
    parser.add_argument("--target-room", type=lambda value: int(value, 0),
                        default=1)
    parser.add_argument("--target-settle", type=int, default=8)
    args = parser.parse_args()

    rom = args.rom.resolve()
    if not rom.is_file():
        parser.error(f"ROM not found: {rom}")
    output = args.output.resolve()
    if output.exists():
        shutil.rmtree(output)
    output.mkdir(parents=True)

    common = dict(
        rom=rom,
        frames=args.frames,
        play_frames=240,
        timeout=args.timeout,
        target_camera=args.target_camera,
        target_room=args.target_room,
        target_settle=args.target_settle,
        snap_interval=0,
        fire=False,
        trace=None,
        trace_writes=False,
    )
    direct_report = run_route(output=output / "direct",
                              via_opening=False, **common)
    opening_report = run_route(output=output / "after-opening",
                               via_opening=True, **common)

    comparisons = {
        name: compare_plane(output / "direct" / name,
                            output / "after-opening" / name)
        for name in PLANES
    }
    route_guard_ok = (
        direct_report.get("via_opening") == "0"
        and direct_report.get("opening_started") == "0"
        and opening_report.get("via_opening") == "1"
        and opening_report.get("opening_started") == "1"
        and opening_report.get("opening_completed") == "1"
        and direct_report.get("final_dcfd") == "01"
        and opening_report.get("final_dcfd") == "01"
        and direct_report.get("final_room") == opening_report.get("final_room")
        and direct_report.get("target_camera")
        == opening_report.get("target_camera")
    )
    exact = all(
        comparisons[name]["differences"] == 0
        for name in REQUIRED_PLANES
    )
    receipt = {
        "status": "pass" if route_guard_ok and exact else "fail",
        "rom": str(rom),
        "rom_sha256": sha256(rom),
        "contract": (
            "complete the default OPENING using controller input, follow its "
            "automatic Stage-1 transition, walk north to the same room/camera "
            "as a direct cold GAME START route, and require exact packed "
            "room, visible BG tile/attribute, CGB palette equality, and the "
            "live-gameplay DCFD=1 invariant on both routes"
        ),
        "target_room": args.target_room,
        "target_camera": args.target_camera,
        "direct": direct_report,
        "after_opening": opening_report,
        "route_guard_ok": route_guard_ok,
        "planes": comparisons,
        "required_planes": list(REQUIRED_PLANES),
        "physical_map_note": (
            "The untouched ROM also retains route-specific off-viewport "
            "cells in both 32x32 physical tile maps. Those full maps are "
            "recorded diagnostically. It also retains route-specific low "
            "VRAM sprite tile residue. Pass/fail requires the packed room, "
            "the exact 20x18 visible tile/attribute planes, both CGB palette "
            "banks, and live-gameplay routing at the matched north coordinate."
        ),
    }
    receipt_path = output / "receipt.json"
    receipt_path.write_text(json.dumps(receipt, indent=2) + "\n")
    print(json.dumps(receipt, indent=2))
    if not route_guard_ok:
        print("FAIL: OPENING route did not complete its natural title/game path")
        return 1
    if not exact:
        failed = [
            f"{name}:{values['differences']}"
            for name in REQUIRED_PLANES
            if (values := comparisons[name])["differences"]
        ]
        print("FAIL: OPENING contaminated Stage 1: " + ", ".join(failed))
        return 1
    print(
        "PASS: direct and completed-OPENING Stage-1 routes have identical "
        "packed terrain, visible BG tile/attribute maps, palette banks, and "
        "live-gameplay routing."
    )
    print(f"Receipt: {receipt_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
