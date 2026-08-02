#!/usr/bin/env python3
"""Prove Stage-1 pickup gold is isolated from terrain in a cold live run."""

from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
import os
from pathlib import Path
import subprocess

from PIL import Image

from analyze_stage1_pickup_art import TARGETS, color_words, decode_tile


ROOT = Path(__file__).resolve().parents[2]
PROBE = Path(__file__).with_name("probe_stage1_pickup_art.lua")
DEFAULT_MGBA = ROOT / "scripts/mgba-qt-singleflight"
STAGE1_LOW_TILE_GFX_OFFSET = 0x1D000
STAGE1_HIGH_TILE_GFX_OFFSET = 0x1F000
PICKUP_GOLD = 0x03FF


def digest(path: Path) -> str:
    value = hashlib.sha256()
    value.update(path.read_bytes())
    return value.hexdigest()


def tile_indices(tile: bytes) -> set[int]:
    values: set[int] = set()
    for row in range(0, 16, 2):
        low, high = tile[row:row + 2]
        for bit in range(8):
            mask = 1 << bit
            values.add(
                (1 if low & mask else 0) | (2 if high & mask else 0)
            )
    return values


def rom_tile(rom: bytes, tile: int) -> bytes:
    source = (
        STAGE1_LOW_TILE_GFX_OFFSET + tile * 16
        if tile < 0x80
        else STAGE1_HIGH_TILE_GFX_OFFSET + tile * 16
    )
    return rom[source:source + 16]


def live_tile(vram0: bytes, tile: int) -> bytes:
    offset = tile * 16 if tile >= 0x80 else 0x1000 + tile * 16
    return vram0[offset:offset + 16]


def state_fields(path: Path) -> dict[str, str]:
    return dict(
        line.split("=", 1)
        for line in path.read_text().splitlines()
        if "=" in line
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("rom", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--mgba", type=Path, default=DEFAULT_MGBA)
    parser.add_argument("--timeout", type=float, default=30.0)
    args = parser.parse_args()

    rom_path = args.rom.resolve()
    mgba = args.mgba.resolve()
    output = args.output.resolve()
    if not rom_path.is_file():
        parser.error(f"ROM not found: {rom_path}")
    if not mgba.is_file():
        parser.error(f"guarded mGBA frontend not found: {mgba}")
    output.mkdir(parents=True, exist_ok=True)
    prefix = output / "stage1-pickup-art"
    suffixes = (
        ".vram0.bin", ".vram1.bin", ".bg-cram.bin", ".state.txt",
        ".png", ".done",
    )
    for suffix in suffixes:
        Path(str(prefix) + suffix).unlink(missing_ok=True)

    environment = os.environ.copy()
    environment.update({
        "PICKUP_ART_OUT": str(prefix),
        "QT_QPA_PLATFORM": "offscreen",
        "SDL_AUDIODRIVER": "dummy",
    })
    log_path = output / "mgba.log"
    with log_path.open("w") as stream:
        completed = subprocess.run(
            [
                str(mgba), "--fastforward", "--script", str(PROBE),
                str(rom_path),
            ],
            cwd=ROOT,
            env=environment,
            stdout=stream,
            stderr=subprocess.STDOUT,
            timeout=args.timeout,
            check=False,
        )

    required = [Path(str(prefix) + suffix) for suffix in suffixes]
    missing = [path.name for path in required if not path.is_file()]
    if completed.returncode != 0 or missing:
        print(
            f"FAIL: cold pickup probe status={completed.returncode} "
            f"missing={missing}; see {log_path}"
        )
        return 1

    rom = rom_path.read_bytes()
    vram0 = Path(str(prefix) + ".vram0.bin").read_bytes()
    vram1 = Path(str(prefix) + ".vram1.bin").read_bytes()
    cram = Path(str(prefix) + ".bg-cram.bin").read_bytes()
    state = state_fields(Path(str(prefix) + ".state.txt"))
    screenshot = Path(str(prefix) + ".png")
    if len(rom) != 0x40000 or len(vram0) != 0x2000 \
            or len(vram1) != 0x2000 or len(cram) != 64:
        print("FAIL: incomplete ROM/VRAM/CRAM payload")
        return 1

    pickup_source_failures = []
    terrain_source_failures = []
    live_source_mismatches = []
    for tile in range(0x100):
        source = rom_tile(rom, tile)
        indices = tile_indices(source)
        if tile in TARGETS:
            if 1 not in indices or 2 in indices:
                pickup_source_failures.append(f"{tile:02X}")
        elif 1 in indices:
            terrain_source_failures.append(f"{tile:02X}")
        if live_tile(vram0, tile) != source:
            live_source_mismatches.append(f"{tile:02X}")

    lcdc = int(state["LCDC"], 16)
    signed_indices = not bool(lcdc & 0x10)
    map_base = 0x1C00 if lcdc & 0x08 else 0x1800
    tilemap = vram0[map_base:map_base + 0x400]
    attrs = vram1[map_base:map_base + 0x400]
    visible_targets: Counter[int] = Counter()
    visible_terrain: Counter[int] = Counter()
    vram = vram0 + vram1
    for tile, attr in zip(tilemap, attrs):
        pixels = decode_tile(
            vram, tile, (attr >> 3) & 1,
            signed_indices=signed_indices,
        )
        (visible_targets if tile in TARGETS else visible_terrain).update(
            pixels
        )

    bg0 = color_words(cram, 0)
    with Image.open(screenshot) as source:
        image = source.convert("RGB")
    pixels = list(image.getdata())
    chromatic_pixels = sum(max(pixel) - min(pixel) >= 24 for pixel in pixels)
    checks = {
        "cold route reached stable Stage 1 gameplay": (
            state.get("D880") == "02" and state.get("FFC1") == "01"
        ),
        "canonical pickup class contains 73 unique tile IDs": (
            len(TARGETS) == 73
        ),
        "all pickup source tiles reserve index 1 and exclude index 2": (
            not pickup_source_failures
        ),
        "all 183 ordinary source tiles exclude reserved index 1": (
            len(TARGETS) == 73 and not terrain_source_failures
        ),
        "all 256 live tiles exactly match the candidate ROM source": (
            not live_source_mismatches
        ),
        "live BG0 index 1 is bright gold": bg0[1] == PICKUP_GOLD,
        "live map renders pickup pixels through reserved index 1": (
            visible_targets[1] > 0
        ),
        "live map renders zero ordinary-terrain pixels through index 1": (
            visible_terrain[1] == 0
        ),
        "cold screenshot is 160x144 and chromatic": (
            image.size == (160, 144) and chromatic_pixels > 100
        ),
    }
    failures = [name for name, passed in checks.items() if not passed]
    receipt = {
        "schema": "penta-dragon-dx-stage1-pickup-art-v1",
        "status": "pass" if not failures else "fail",
        "rom": str(rom_path),
        "rom_sha256": digest(rom_path),
        "checks": checks,
        "state": state,
        "bg0": [f"{word:04X}" for word in bg0],
        "pickup_tile_count": len(TARGETS),
        "ordinary_tile_count": 0x100 - len(TARGETS),
        "visible_pickup_pixel_indices": dict(sorted(visible_targets.items())),
        "visible_terrain_pixel_indices": dict(sorted(visible_terrain.items())),
        "pickup_source_failures": pickup_source_failures,
        "terrain_source_failures": terrain_source_failures,
        "live_source_mismatches": live_source_mismatches,
        "screenshot": {
            "path": str(screenshot),
            "sha256": digest(screenshot),
            "size": list(image.size),
            "chromatic_pixels": chromatic_pixels,
        },
        "failures": failures,
    }
    receipt_path = output / "receipt.json"
    receipt_path.write_text(json.dumps(receipt, indent=2) + "\n")
    for name, passed in checks.items():
        print(f"{'PASS' if passed else 'FAIL'}: {name}")
    print(f"Receipt: {receipt_path}")
    if failures:
        return 1
    print(
        "PASS: Stage-1 pickup gold is live and isolated from every ordinary "
        "terrain pixel."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
