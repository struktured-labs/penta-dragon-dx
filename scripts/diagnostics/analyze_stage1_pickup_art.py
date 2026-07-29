#!/usr/bin/env python3
"""Analyze live pickup/background pixel-index overlap from an mGBA dump."""

from __future__ import annotations

import argparse
from collections import Counter
import json
from pathlib import Path


TARGET_RANGES = (
    range(0x88, 0x90),
    range(0x98, 0xA0),
    range(0xA8, 0xB0),
    range(0xB8, 0xC0),
    range(0xC8, 0xD0),
    range(0xD8, 0xE0),
)
TARGETS = frozenset(tile for group in TARGET_RANGES for tile in group)


def decode_tile(vram: bytes, tile: int, bank: int) -> list[int]:
    base = bank * 0x2000 + tile * 16
    pixels = []
    for row in range(8):
        low, high = vram[base + row * 2:base + row * 2 + 2]
        for bit in range(7, -1, -1):
            pixels.append(((high >> bit) & 1) * 2 + ((low >> bit) & 1))
    return pixels


def color_words(cram: bytes, slot: int) -> list[int]:
    data = cram[slot * 8:(slot + 1) * 8]
    return [
        data[index] | (data[index + 1] << 8)
        for index in range(0, 8, 2)
    ]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("prefix", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    prefix = args.prefix.resolve()
    vram0 = Path(str(prefix) + ".vram0.bin").read_bytes()
    vram1 = Path(str(prefix) + ".vram1.bin").read_bytes()
    cram = Path(str(prefix) + ".bg-cram.bin").read_bytes()
    if len(vram0) != 0x2000 or len(vram1) != 0x2000 or len(cram) != 64:
        raise SystemExit("incomplete mGBA dump")
    vram = vram0 + vram1

    lcdc = int(dict(
        line.split("=", 1)
        for line in Path(str(prefix) + ".state.txt").read_text().splitlines()
    )["LCDC"], 16)
    map_base = 0x1C00 if lcdc & 0x08 else 0x1800
    tilemap = vram0[map_base:map_base + 0x400]
    attrs = vram1[map_base:map_base + 0x400]
    visible_targets = Counter()
    visible_non_targets = Counter()
    for tile, attr in zip(tilemap, attrs):
        bank = (attr >> 3) & 1
        pixels = decode_tile(vram, tile, bank)
        counter = visible_targets if tile in TARGETS else visible_non_targets
        counter.update(pixels)

    pickup_tiles = {
        f"{tile:02X}": {
            "bank0_index_histogram": dict(
                sorted(Counter(decode_tile(vram, tile, 0)).items())
            ),
            "bank1_index_histogram": dict(
                sorted(Counter(decode_tile(vram, tile, 1)).items())
            ),
        }
        for tile in sorted(TARGETS)
    }
    bg0, bg1 = color_words(cram, 0), color_words(cram, 1)
    safe_indices = [
        index for index in range(4) if bg0[index] == bg1[index]
    ]
    changed_indices = [
        index for index in range(4) if bg0[index] != bg1[index]
    ]
    receipt = {
        "prefix": str(prefix),
        "lcdc": f"{lcdc:02X}",
        "bg0": [f"{word:04X}" for word in bg0],
        "bg1": [f"{word:04X}" for word in bg1],
        "palette_equal_indices": safe_indices,
        "palette_changed_indices": changed_indices,
        "visible_target_pixel_indices": dict(sorted(visible_targets.items())),
        "visible_non_target_pixel_indices": dict(
            sorted(visible_non_targets.items())
        ),
        "pickup_tiles": pickup_tiles,
    }
    output = args.output or Path(str(prefix) + ".receipt.json")
    output.write_text(json.dumps(receipt, indent=2) + "\n")
    print(json.dumps({
        key: receipt[key] for key in (
            "bg0", "bg1", "palette_equal_indices",
            "palette_changed_indices", "visible_target_pixel_indices",
            "visible_non_target_pixel_indices",
        )
    }, indent=2))
    print(f"Receipt: {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
