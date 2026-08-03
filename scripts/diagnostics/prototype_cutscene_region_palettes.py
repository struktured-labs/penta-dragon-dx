#!/usr/bin/env python3
"""Render a ROM-free multi-palette spike for the eight story art panels.

The production ROM currently assigns one CGB BG palette to all 160 artwork
cells in each committed story panel and leaves the 200 dialogue cells on BG0.
This prototype keeps the proven scene boundary but tries position-aware,
tile-aligned palette masks inside the artwork.  It reads exact mGBA savestate
VRAM and renders the result offline, so it never competes with a headed play
session and cannot mutate a ROM or savestate.

The colors are deliberately the existing tuneable BG1..BG7 ramps.  This spike
is about proving useful regions and safe containment; final colors can still
be selected in the live palette editor with the audience.
"""

from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import struct
import sys
import zlib

from PIL import Image, ImageDraw
import yaml

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

from cutscene_region_palettes import (  # noqa: E402
    ART_COLUMNS as VISIBLE_COLUMNS,
    ART_ROWS,
    load_cutscene_region_palettes,
    panel_mask,
)

DEFAULT_STATES = ROOT / "tmp/palette_session/story_states"
DEFAULT_PALETTES = ROOT / "palettes/penta_palettes_v097.yaml"
DEFAULT_OUTPUT = Path("/tmp/penta-cutscene-region-spike")
SERIALIZED_SIZE = 0x11800
VISIBLE_ROWS = 18

STATE_ART_IDS = {
    "opening_book": 1,
    "opening_sara": 2,
    "opening_dragon_eye": 3,
    "pre_final": 4,
    "pre_final_sara": 7,
    "post_final": 5,
    "post_final_lisa": 6,
    "post_final_sara": 7,
}


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def serialized_state(path: Path) -> bytes:
    data = path.read_bytes()
    if data[:8] != b"\x89PNG\r\n\x1a\n":
        raise RuntimeError(f"not an mGBA PNG savestate: {path}")
    position = 8
    while position + 12 <= len(data):
        size = struct.unpack(">I", data[position:position + 4])[0]
        kind = data[position + 4:position + 8]
        payload = data[position + 8:position + 8 + size]
        if kind == b"gbAs":
            state = zlib.decompress(payload)
            if len(state) != SERIALIZED_SIZE:
                raise RuntimeError(
                    f"{path} serialized {len(state):#x} bytes, "
                    f"expected {SERIALIZED_SIZE:#x}"
                )
            return state
        position += size + 12
    raise RuntimeError(f"mGBA gbAs chunk missing: {path}")


def load_palettes(path: Path) -> list[list[tuple[int, int, int]]]:
    document = yaml.safe_load(path.read_text())
    entries = list(document["bg_palettes"].values())
    if len(entries) != 8:
        raise RuntimeError(f"{path} defines {len(entries)} BG palettes")
    palettes = []
    for entry in entries:
        palette = []
        for value in entry["colors"]:
            color = int(value, 16)
            red = (color & 0x1F) * 255 // 31
            green = ((color >> 5) & 0x1F) * 255 // 31
            blue = ((color >> 10) & 0x1F) * 255 // 31
            palette.append((red, green, blue))
        if len(palette) != 4:
            raise RuntimeError("every BG palette must define four colors")
        palettes.append(palette)
    return palettes


def visible_cells(state: bytes) -> tuple[list[list[int]], dict[str, int]]:
    io = state[0x300:0x380]
    lcdc, scy, scx = io[0x40], io[0x42], io[0x43]
    if lcdc & 0x20:
        raise RuntimeError("story spike does not support a visible window")
    if scx & 7 or scy & 7:
        raise RuntimeError(f"story viewport is not tile-aligned: {scx=}, {scy=}")
    map_offset = 0x1C00 if lcdc & 0x08 else 0x1800
    vram = state[0x400:0x4400]
    attrs = []
    for row in range(VISIBLE_ROWS):
        map_row = ((scy >> 3) + row) & 31
        attrs.append([
            vram[0x2000 + map_offset + map_row * 32
                 + (((scx >> 3) + column) & 31)]
            for column in range(VISIBLE_COLUMNS)
        ])
    return attrs, {
        "lcdc": lcdc,
        "scx": scx,
        "scy": scy,
        "map": 0x9C00 if lcdc & 0x08 else 0x9800,
    }


def render(
    state: bytes,
    palettes: list[list[tuple[int, int, int]]],
    art_mask: tuple[tuple[int, ...], ...],
) -> Image.Image:
    io = state[0x300:0x380]
    lcdc, scy, scx = io[0x40], io[0x42], io[0x43]
    map_offset = 0x1C00 if lcdc & 0x08 else 0x1800
    vram = state[0x400:0x4400]
    image = Image.new("RGB", (160, 144))
    pixels = image.load()
    for screen_y in range(144):
        world_y = (scy + screen_y) & 0xFF
        tile_y, inner_y = (world_y >> 3) & 31, world_y & 7
        visible_row = screen_y >> 3
        for screen_x in range(160):
            world_x = (scx + screen_x) & 0xFF
            tile_x, inner_x = (world_x >> 3) & 31, world_x & 7
            tile = vram[map_offset + tile_y * 32 + tile_x]
            if lcdc & 0x10:
                tile_offset = tile * 16
            else:
                tile_offset = tile * 16 if tile >= 0x80 else 0x1000 + tile * 16
            low = vram[tile_offset + inner_y * 2]
            high = vram[tile_offset + inner_y * 2 + 1]
            bit = 7 - inner_x
            color = ((high >> bit) & 1) * 2 + ((low >> bit) & 1)
            visible_column = screen_x >> 3
            palette = (
                art_mask[visible_row][visible_column]
                if visible_row < ART_ROWS else 0
            )
            pixels[screen_x, screen_y] = palettes[palette][color]
    return image


def uniform_mask(palette: int) -> tuple[tuple[int, ...], ...]:
    return tuple(
        tuple(palette for _ in range(VISIBLE_COLUMNS))
        for _ in range(ART_ROWS)
    )


def labelled_pair(name: str, uniform: Image.Image, prototype: Image.Image) -> Image.Image:
    scale = 2
    width = 160 * scale
    label_height = 24
    pair = Image.new("RGB", (width * 2 + 12, 144 * scale + label_height), "#202020")
    draw = ImageDraw.Draw(pair)
    left = uniform.resize((width, 144 * scale), Image.Resampling.NEAREST)
    right = prototype.resize((width, 144 * scale), Image.Resampling.NEAREST)
    pair.paste(left, (0, label_height))
    pair.paste(right, (width + 12, label_height))
    draw.text((4, 5), f"{name}: current uniform", fill="white")
    draw.text((width + 16, 5), "region-mask spike", fill="white")
    return pair


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--states", type=Path, default=DEFAULT_STATES)
    parser.add_argument("--palettes", type=Path, default=DEFAULT_PALETTES)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)

    palettes = load_palettes(args.palettes)
    region_panels = load_cutscene_region_palettes(args.palettes)
    receipts = {}
    pairs = []
    for name, art_id in STATE_ART_IDS.items():
        panel = region_panels[art_id]
        state_path = args.states / f"{name}.ss0"
        state = serialized_state(state_path)
        source_attrs, registers = visible_cells(state)
        art_source = [value for row in source_attrs[:ART_ROWS] for value in row]
        dialogue_source = [
            value for row in source_attrs[ART_ROWS:] for value in row
        ]
        if any(value != 0 for value in dialogue_source):
            raise RuntimeError(f"{name}: source dialogue attributes are not neutral")

        proposed = panel_mask(panel)
        current = uniform_mask(art_id)
        uniform = render(state, palettes, current)
        prototype = render(state, palettes, proposed)
        if uniform.crop((0, 64, 160, 144)).tobytes() != \
                prototype.crop((0, 64, 160, 144)).tobytes():
            raise RuntimeError(f"{name}: prototype changed dialogue pixels")

        uniform_path = args.output / f"{name}-uniform.png"
        prototype_path = args.output / f"{name}-prototype.png"
        uniform.save(uniform_path)
        prototype.save(prototype_path)
        pairs.append(labelled_pair(name, uniform, prototype))
        mask_values = [value for row in proposed for value in row]
        receipts[name] = {
            "state": str(state_path.resolve()),
            "state_sha256": digest(state_path.read_bytes()),
            "registers": {key: f"0x{value:02X}" for key, value in registers.items()},
            "yaml_panel": panel.name,
            "art_id": art_id,
            "default_palette": panel.default_palette_name,
            "current_uniform_palette": art_id,
            "proposed_art_histogram": dict(sorted(Counter(mask_values).items())),
            "art_cells": len(art_source),
            "dialogue_cells": len(dialogue_source),
            "source_dialogue_nonzero_attrs": sum(value != 0 for value in dialogue_source),
            "prototype_dialogue_changed_pixels": 0,
            "unsafe_proposed_attrs": sum(value & 0xF8 != 0 for value in mask_values),
        }

    sheet_width = max(pair.width for pair in pairs)
    sheet_height = sum(pair.height for pair in pairs) + 12 * (len(pairs) - 1)
    sheet = Image.new("RGB", (sheet_width, sheet_height), "#101010")
    top = 0
    for pair in pairs:
        sheet.paste(pair, (0, top))
        top += pair.height + 12
    sheet.save(args.output / "contact-sheet.png")

    receipt = {
        "status": "prototype-only",
        "mutates_rom": False,
        "mutates_savestates": False,
        "palette_source": str(args.palettes.resolve()),
        "palette_source_sha256": digest(args.palettes.read_bytes()),
        "containment": "top 8x20 art cells only; lower 10x20 dialogue cells BG0",
        "panels": receipts,
    }
    (args.output / "receipt.json").write_text(
        json.dumps(receipt, indent=2, sort_keys=True) + "\n"
    )
    print(
        "PASS: rendered 8 offline cutscene region-mask prototypes; "
        "1,280 art cells classified and all 1,600 dialogue cells unchanged."
    )
    print(f"Contact sheet: {args.output / 'contact-sheet.png'}")
    print(f"Receipt: {args.output / 'receipt.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
