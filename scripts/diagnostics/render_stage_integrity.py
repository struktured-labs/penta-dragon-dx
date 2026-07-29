#!/usr/bin/env python3
"""Render a probe_stage_integrity.lua capture directly from CGB VRAM dumps."""

from __future__ import annotations

import argparse
import re
from pathlib import Path

from PIL import Image


def artifact(prefix: Path, suffix: str) -> Path:
    """Append an artifact suffix without discarding dotted room identifiers."""
    return Path(f"{prefix}{suffix}")


def parse_meta(path: Path) -> dict[str, int]:
    values: dict[str, int] = {}
    for key, raw in re.findall(r"([A-Za-z0-9_]+)=([0-9A-Fa-f]+)", path.read_text().splitlines()[0]):
        base = 16 if key in {"expected_scene", "D880", "FFC1", "FFBA", "LCDC", "SCX", "SCY", "active_map"} else 10
        values[key] = int(raw, base)
    return values


def gbc_channel(value: int) -> int:
    return (value << 3) | (value >> 2)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("prefix", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()

    meta = parse_meta(artifact(args.prefix, ".meta"))
    vram = [
        artifact(args.prefix, ".vram0.bin").read_bytes(),
        artifact(args.prefix, ".vram1.bin").read_bytes(),
    ]
    tilemap = artifact(args.prefix, ".map0.bin").read_bytes()
    attrs = artifact(args.prefix, ".attr.bin").read_bytes()
    bgp = artifact(args.prefix, ".bgp.bin").read_bytes()

    palettes: list[list[tuple[int, int, int]]] = []
    for palette in range(8):
        colors = []
        for color in range(4):
            offset = palette * 8 + color * 2
            word = bgp[offset] | (bgp[offset + 1] << 8)
            colors.append((
                gbc_channel(word & 0x1F),
                gbc_channel((word >> 5) & 0x1F),
                gbc_channel((word >> 10) & 0x1F),
            ))
        palettes.append(colors)

    lcdc = meta["LCDC"]
    map_offset = 0x400 if meta["active_map"] == 0x9C00 else 0
    signed_tiles = (lcdc & 0x10) == 0
    scx, scy = meta["SCX"], meta["SCY"]
    image = Image.new("RGB", (160, 144))
    pixels = image.load()

    for screen_y in range(144):
        world_y = (scy + screen_y) & 0xFF
        map_row, pixel_y = world_y >> 3, world_y & 7
        for screen_x in range(160):
            world_x = (scx + screen_x) & 0xFF
            map_col, pixel_x = world_x >> 3, world_x & 7
            cell = map_offset + map_row * 32 + map_col
            tile_id, attr = tilemap[cell], attrs[cell]
            tile_bank = (attr >> 3) & 1
            tile_x, tile_y = pixel_x, pixel_y
            if attr & 0x20: tile_x = 7 - tile_x
            if attr & 0x40: tile_y = 7 - tile_y
            tile_index = tile_id
            if signed_tiles and tile_id < 0x80:
                tile_index = 0x100 + tile_id
            tile_base = tile_index * 16 + tile_y * 2
            lo, hi = vram[tile_bank][tile_base:tile_base + 2]
            bit = 7 - tile_x
            color = ((hi >> bit) & 1) * 2 + ((lo >> bit) & 1)
            pixels[screen_x, screen_y] = palettes[attr & 7][color]

    image.save(args.output)


if __name__ == "__main__":
    main()
