#!/usr/bin/env python3
"""Prove the Stage 1 rotating spike's BG/OBJ makeup and prototype its art.

This is deliberately ROM-free in effect: it reads a candidate ROM and an
mGBA PNG savestate, writes only receipts/previews, and never starts an
emulator.  The exact captured spike is classified from the active BG map and
hardware OAM.  A proposed semantic Stage-1 source-art variant is then rendered
offline without modifying the ROM or savestate. Corresponding VRAM-bank-1
slots are inventoried as a fallback for future shared-source tiles.
"""

from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import sys

from PIL import Image, ImageDraw

from verify_pickup_class_palettes import (
    BG_PALETTE_OFFSET,
    serialized_state,
)


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

from stage1_hazard_art import (  # noqa: E402
    load_stage1_hazard_config,
    load_stage1_hazard_palette,
    remap_hazard_tile,
)

DEFAULT_ROM = ROOT / "rom/working/penta_dragon_dx_FIXED.gb"
DEFAULT_STOCK_ROM = ROOT / "rom/Penta Dragon (J).gb"
DEFAULT_STATE = (
    ROOT / "save_states_for_claude" /
    "level1_cat_fish_moth_spike_hazard_orb_item.ss0"
)
DEFAULT_FIXTURES = ROOT / "save_states_for_claude"

VRAM_OFFSET = 0x400
VRAM_BANK_SIZE = 0x2000
OAM_OFFSET = 0x260
OAM_SIZE = 0xA0
IO_OFFSET = 0x300
WRAM_OFFSET = 0x4400
HAZARD = load_stage1_hazard_config()
STAGE1_TILE_SOURCE = HAZARD.source_offset
BG_TABLE_OFFSET = 13 * 0x4000 + (0x7000 - 0x4000)

SPIKE_FAMILY = HAZARD.family_tiles
VARIANT_TILES = HAZARD.tooth_tiles | HAZARD.ring_tiles
RING_TILES = HAZARD.ring_tiles
TOOTH_TILES = HAZARD.tooth_tiles
BODY_TILES = HAZARD.body_tiles
CONNECTOR_TILES = HAZARD.connector_tiles
ART_TILES = HAZARD.art_tiles
VARIANT_PALETTE = HAZARD.tooth_palette
BODY_PALETTE = HAZARD.body_palette
CONNECTOR_PALETTE = HAZARD.connector_palette
PREFERRED_ATTR = VARIANT_PALETTE
BANK1_FALLBACK_ATTR = 0x08 | VARIANT_PALETTE
# Each rotating tile is compared with the floor/shadow/rail tile it replaces.
# Matching pixels remain environment art.  Changed pixels are the moving
# hazard and receive the dedicated color index.  This avoids the rejected
# blanket remap, which correctly colored the rings but also painted their
# embedded floor and rail pixels red.
SEMANTIC_BASE_TILES = HAZARD.semantic_base_tiles
ENVIRONMENT_REMAP = dict(enumerate(HAZARD.environment_remap))
HAZARD_REMAP = dict(enumerate(HAZARD.hazard_remap))
# Ring frames contain pixels that happen to equal the stationary rail at the
# same coordinates.  Difference-only classification therefore leaves gray
# holes in the moving ring.  These small, art-audited regions cover the full
# ring arcs without entering the stationary rail rows.
RING_REGIONS = HAZARD.ring_regions
# Difference-only classification leaves a few floor/shadow-colored pixels
# inside the tooth outlines whenever the moving art happens to equal its
# semantic baseline.  These row spans were traced from the black outlines of
# all twelve animation frames.  They fill only the closed tooth/drill
# silhouettes; pixels outside the spans still use the conservative baseline
# comparison so the checkerboard and cast shadow remain untouched.
# Values are end-exclusive x ranges keyed by source-art y row.
TOOTH_ROW_SPANS = HAZARD.tooth_row_spans


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def tile_offset(tile: int, signed_indices: bool) -> int:
    if signed_indices and tile < 0x80:
        return 0x1000 + tile * 16
    return tile * 16


def decode_tile(raw: bytes) -> list[int]:
    if len(raw) != 16:
        raise ValueError("a Game Boy tile must be exactly 16 bytes")
    pixels: list[int] = []
    for row in range(8):
        low, high = raw[row * 2:row * 2 + 2]
        for bit in range(7, -1, -1):
            pixels.append(
                ((low >> bit) & 1) | (((high >> bit) & 1) << 1)
            )
    return pixels


def encode_tile(pixels: list[int]) -> bytes:
    if len(pixels) != 64:
        raise ValueError("a Game Boy tile must contain exactly 64 pixels")
    result = bytearray(16)
    for row in range(8):
        low = high = 0
        for column in range(8):
            value = pixels[row * 8 + column]
            bit = 7 - column
            low |= (value & 1) << bit
            high |= ((value >> 1) & 1) << bit
        result[row * 2] = low
        result[row * 2 + 1] = high
    return bytes(result)


def remap_tile(tile: int, raw: bytes, baseline: bytes) -> bytes:
    return remap_hazard_tile(HAZARD, tile, raw, baseline)


def palette_rows(rom: bytes) -> list[list[tuple[int, int, int]]]:
    palettes = []
    for slot in range(8):
        start = BG_PALETTE_OFFSET + slot * 8
        words = [
            rom[start + offset] | (rom[start + offset + 1] << 8)
            for offset in range(0, 8, 2)
        ]
        palettes.append([
            (
                (word & 0x1F) * 255 // 31,
                ((word >> 5) & 0x1F) * 255 // 31,
                ((word >> 10) & 0x1F) * 255 // 31,
            )
            for word in words
        ])
    return palettes


def target_hazard_palettes(
    palettes: list[list[tuple[int, int, int]]],
) -> list[list[tuple[int, int, int]]]:
    """Load the independently tunable Stage-1 hazard row from palette YAML."""
    result = [[*palette] for palette in palettes]
    slot, payload = load_stage1_hazard_palette()
    words = [
        payload[offset] | (payload[offset + 1] << 8)
        for offset in range(0, 8, 2)
    ]
    result[slot] = [
        (
            (word & 0x1F) * 255 // 31,
            ((word >> 5) & 0x1F) * 255 // 31,
            ((word >> 10) & 0x1F) * 255 // 31,
        )
        for word in words
    ]
    return result


def screen_coordinate(world: int, scroll: int, extent: int) -> int | None:
    position = world - scroll
    while position >= 128:
        position -= 256
    while position < -128:
        position += 256
    if position >= extent or position + 8 <= 0:
        return None
    return position


def visible_cells(state: bytes) -> tuple[list[dict[str, int]], dict[str, int]]:
    io = state[IO_OFFSET:IO_OFFSET + 0x80]
    lcdc, scy, scx = io[0x40], io[0x42], io[0x43]
    map_offset = 0x1C00 if lcdc & 0x08 else 0x1800
    vram0 = state[VRAM_OFFSET:VRAM_OFFSET + VRAM_BANK_SIZE]
    vram1 = state[
        VRAM_OFFSET + VRAM_BANK_SIZE:VRAM_OFFSET + 2 * VRAM_BANK_SIZE
    ]
    cells = []
    for map_y in range(32):
        y = screen_coordinate(map_y * 8, scy, 144)
        if y is None:
            continue
        for map_x in range(32):
            x = screen_coordinate(map_x * 8, scx, 160)
            if x is None:
                continue
            offset = map_offset + map_y * 32 + map_x
            cells.append({
                "map_x": map_x,
                "map_y": map_y,
                "screen_x": x,
                "screen_y": y,
                "tile": vram0[offset],
                "attr": vram1[offset],
            })
    return cells, {
        "lcdc": lcdc,
        "scx": scx,
        "scy": scy,
        "map": 0x9C00 if lcdc & 0x08 else 0x9800,
        "signed_tile_indices": int(not bool(lcdc & 0x10)),
    }


def visible_oam(state: bytes, lcdc: int) -> list[dict[str, int]]:
    height = 16 if lcdc & 0x04 else 8
    result = []
    oam = state[OAM_OFFSET:OAM_OFFSET + OAM_SIZE]
    for slot in range(40):
        y, x, tile, attr = oam[slot * 4:slot * 4 + 4]
        left, top = x - 8, y - 16
        if left >= 160 or left + 8 <= 0 or top >= 144 or top + height <= 0:
            continue
        result.append({
            "slot": slot,
            "x": x,
            "y": y,
            "left": left,
            "top": top,
            "right": left + 8,
            "bottom": top + height,
            "tile": tile,
            "attr": attr,
            "palette": attr & 7,
            "vram_bank": (attr >> 3) & 1,
        })
    return result


def intersects(first: dict[str, int], second: dict[str, int]) -> bool:
    return not (
        first["right"] <= second["left"]
        or second["right"] <= first["left"]
        or first["bottom"] <= second["top"]
        or second["bottom"] <= first["top"]
    )


def cell_rect(cell: dict[str, int]) -> dict[str, int]:
    return {
        "left": cell["screen_x"],
        "top": cell["screen_y"],
        "right": cell["screen_x"] + 8,
        "bottom": cell["screen_y"] + 8,
    }


def render_bg(
    state: bytes,
    rom: bytes,
    cells: list[dict[str, int]],
    metadata: dict[str, int],
    *,
    proposed: bool,
    target_palette: bool = False,
) -> Image.Image:
    palettes = palette_rows(rom)
    if target_palette:
        palettes = target_hazard_palettes(palettes)
    vram = state[VRAM_OFFSET:VRAM_OFFSET + 2 * VRAM_BANK_SIZE]
    signed_indices = bool(metadata["signed_tile_indices"])
    image = Image.new("RGB", (160, 144), "black")
    pixels = image.load()
    for cell in cells:
        tile, attr = cell["tile"], cell["attr"]
        if proposed and tile in ART_TILES:
            source_offset = tile_offset(tile, signed_indices)
            baseline_tile = SEMANTIC_BASE_TILES.get(tile, tile)
            baseline_offset = tile_offset(baseline_tile, signed_indices)
            raw = remap_tile(
                tile,
                vram[source_offset:source_offset + 16],
                vram[baseline_offset:baseline_offset + 16],
            )
            attr = (
                CONNECTOR_PALETTE
                if tile in CONNECTOR_TILES
                else BODY_PALETTE
                if tile in RING_TILES or tile in BODY_TILES
                else PREFERRED_ATTR
            )
        else:
            bank = (attr >> 3) & 1
            offset = bank * VRAM_BANK_SIZE + tile_offset(
                tile, signed_indices
            )
            raw = vram[offset:offset + 16]
        decoded = decode_tile(raw)
        for inner_y in range(8):
            for inner_x in range(8):
                screen_x = cell["screen_x"] + inner_x
                screen_y = cell["screen_y"] + inner_y
                if not (0 <= screen_x < 160 and 0 <= screen_y < 144):
                    continue
                source_x = 7 - inner_x if attr & 0x20 else inner_x
                source_y = 7 - inner_y if attr & 0x40 else inner_y
                color = decoded[source_y * 8 + source_x]
                pixels[screen_x, screen_y] = palettes[attr & 7][color]
    return image


def preview_sheet(
    current: Image.Image,
    safe_blue: Image.Image,
    target_gold: Image.Image,
    path: Path,
) -> None:
    scale, label_height, gap = 3, 28, 12
    width, height = 160 * scale, 144 * scale
    sheet = Image.new(
        "RGB", (width * 3 + gap * 2, height + label_height), "#202020"
    )
    draw = ImageDraw.Draw(sheet)
    draw.text((8, 7), "current BG plane", fill="white")
    draw.text(
        (width + gap + 8, 7),
        "semantic art + current BG7 (no CRAM change)",
        fill="white",
    )
    draw.text(
        (2 * (width + gap) + 8, 7),
        "gold rings/teeth + fire-colored cylinder body",
        fill="white",
    )
    sheet.paste(
        current.resize((width, height), Image.Resampling.NEAREST),
        (0, label_height),
    )
    sheet.paste(
        safe_blue.resize((width, height), Image.Resampling.NEAREST),
        (width + gap, label_height),
    )
    sheet.paste(
        target_gold.resize((width, height), Image.Resampling.NEAREST),
        (2 * (width + gap), label_height),
    )
    sheet.save(path)


def layer_map(
    screenshot: Image.Image,
    hazards: list[dict[str, int]],
    sprites: list[dict[str, int]],
    path: Path,
) -> None:
    scale, label_height = 4, 30
    image = screenshot.resize((160 * scale, 144 * scale), Image.Resampling.NEAREST)
    sheet = Image.new("RGB", (image.width, image.height + label_height), "#202020")
    sheet.paste(image, (0, label_height))
    draw = ImageDraw.Draw(sheet)
    draw.text((8, 8), "orange = BG spike cells; cyan = hardware OAM", fill="white")
    for cell in hazards:
        x, y = cell["screen_x"] * scale, cell["screen_y"] * scale + label_height
        draw.rectangle((x, y, x + 8 * scale - 1, y + 8 * scale - 1), outline="#ff8c00", width=2)
    for sprite in sprites:
        draw.rectangle((
            sprite["left"] * scale,
            sprite["top"] * scale + label_height,
            sprite["right"] * scale - 1,
            sprite["bottom"] * scale + label_height - 1,
        ), outline="#00ffff", width=2)
    sheet.save(path)


def tile_sheet(
    originals: dict[int, bytes],
    variants: dict[int, bytes],
    rom: bytes,
    path: Path,
) -> None:
    palettes = target_hazard_palettes(palette_rows(rom))
    scale, cell_width, cell_height = 5, 116, 76
    ordered = sorted(originals)
    rows = (len(ordered) + 3) // 4
    sheet = Image.new("RGB", (4 * cell_width, rows * cell_height), "white")
    draw = ImageDraw.Draw(sheet)
    for index, tile in enumerate(ordered):
        x0 = (index % 4) * cell_width
        y0 = (index // 4) * cell_height
        for side, raw in enumerate((originals[tile], variants[tile])):
            colors = palettes[
                CONNECTOR_PALETTE
                if tile in CONNECTOR_TILES
                else BODY_PALETTE
                if tile in RING_TILES or tile in BODY_TILES
                else VARIANT_PALETTE
            ]
            decoded = decode_tile(raw)
            for y in range(8):
                for x in range(8):
                    color = colors[decoded[y * 8 + x]]
                    draw.rectangle((
                        x0 + side * 44 + x * scale,
                        y0 + 18 + y * scale,
                        x0 + side * 44 + (x + 1) * scale - 1,
                        y0 + 18 + (y + 1) * scale - 1,
                    ), fill=color)
        draw.text(
            (x0 + 2, y0 + 2), f"{tile:02X} stock / semantic", fill="black"
        )
    sheet.save(path)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("rom", nargs="?", type=Path, default=DEFAULT_ROM)
    parser.add_argument("--stock-rom", type=Path, default=DEFAULT_STOCK_ROM)
    parser.add_argument("--state", type=Path, default=DEFAULT_STATE)
    parser.add_argument("--fixtures", type=Path, default=DEFAULT_FIXTURES)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    rom_path = args.rom.resolve()
    stock_path = args.stock_rom.resolve()
    state_path = args.state.resolve()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    rom = rom_path.read_bytes()
    stock = stock_path.read_bytes()
    state = serialized_state(state_path)
    if len(rom) < 0x40000 or len(rom) % 0x4000:
        raise SystemExit(
            f"FAIL: ROM is {len(rom)} bytes; expected at least 262144 "
            "and a whole number of 16 KiB banks"
        )
    if len(stock) != 0x40000:
        raise SystemExit(
            f"FAIL: stock ROM is {len(stock)} bytes, expected 262144"
        )

    cells, metadata = visible_cells(state)
    hazards = [cell for cell in cells if cell["tile"] in SPIKE_FAMILY]
    sprites = visible_oam(state, metadata["lcdc"])
    overlaps = []
    for cell in hazards:
        rectangle = cell_rect(cell)
        for sprite in sprites:
            if intersects(rectangle, sprite):
                overlaps.append({"cell": cell, "sprite": sprite})

    signed_indices = bool(metadata["signed_tile_indices"])
    vram = state[VRAM_OFFSET:VRAM_OFFSET + 2 * VRAM_BANK_SIZE]
    originals: dict[int, bytes] = {}
    variants: dict[int, bytes] = {}
    family_matches = []
    candidate_matches = []
    for tile in sorted(SPIKE_FAMILY):
        offset = tile_offset(tile, signed_indices)
        live = vram[offset:offset + 16]
        source = stock[
            STAGE1_TILE_SOURCE + tile * 16:
            STAGE1_TILE_SOURCE + (tile + 1) * 16
        ]
        family_matches.append(live == source)
        if tile in ART_TILES:
            originals[tile] = source
            baseline_tile = SEMANTIC_BASE_TILES.get(tile, tile)
            baseline = stock[
                STAGE1_TILE_SOURCE + baseline_tile * 16:
                STAGE1_TILE_SOURCE + (baseline_tile + 1) * 16
            ]
            variants[tile] = remap_tile(tile, source, baseline)
            candidate = rom[
                STAGE1_TILE_SOURCE + tile * 16:
                STAGE1_TILE_SOURCE + (tile + 1) * 16
            ]
            candidate_matches.append(candidate == variants[tile])

    fixture_paths = sorted(args.fixtures.resolve().glob("*.ss*"))
    parsed_fixtures = 0
    occupied_fixtures = []
    for path in fixture_paths:
        try:
            fixture = serialized_state(path)
        except RuntimeError:
            continue
        parsed_fixtures += 1
        fixture_vram1 = fixture[
            VRAM_OFFSET + VRAM_BANK_SIZE:VRAM_OFFSET + 2 * VRAM_BANK_SIZE
        ]
        if any(
            fixture_vram1[
                tile_offset(tile, signed_indices):
                tile_offset(tile, signed_indices) + 16
            ] != bytes(16)
            for tile in ART_TILES
        ):
            occupied_fixtures.append(path.name)

    raw_original = b"".join(originals[tile] for tile in sorted(originals))
    raw_variant = b"".join(variants[tile] for tile in sorted(variants))
    changed_bytes = sum(
        before != after for before, after in zip(raw_original, raw_variant)
    )
    histograms = {
        f"{tile:02X}": {
            "stock": dict(sorted(Counter(decode_tile(originals[tile])).items())),
            "variant": dict(sorted(Counter(decode_tile(variants[tile])).items())),
        }
        for tile in sorted(originals)
    }
    tooth_mask_boundaries_are_black = True
    tooth_mask_interiors_are_complete = True
    tooth_mask_exteriors_are_conservative = True
    for tile in sorted(TOOTH_TILES):
        source_pixels = decode_tile(originals[tile])
        variant_pixels = decode_tile(variants[tile])
        for y in range(8):
            span = TOOTH_ROW_SPANS[tile].get(y)
            if span:
                left, right = span
                tooth_mask_boundaries_are_black &= (
                    source_pixels[y * 8 + left] == 3
                    and source_pixels[y * 8 + right - 1] == 3
                )
            for x in range(8):
                index = y * 8 + x
                inside = bool(span and span[0] <= x < span[1])
                source = source_pixels[index]
                if inside:
                    expected = 3 if source == 3 else 2
                    tooth_mask_interiors_are_complete &= (
                        variant_pixels[index] == expected
                    )
                else:
                    tooth_mask_exteriors_are_conservative &= (
                        variant_pixels[index] == ENVIRONMENT_REMAP[source]
                    )

    current_image = render_bg(state, rom, cells, metadata, proposed=False)
    safe_blue_image = render_bg(
        state, rom, cells, metadata, proposed=True
    )
    target_gold_image = render_bg(
        state, rom, cells, metadata, proposed=True, target_palette=True
    )
    preview_path = output / "current-vs-semantic-art.png"
    layers_path = output / "bg-vs-oam-layer-map.png"
    tiles_path = output / "hazard-variant-tiles.png"
    preview_sheet(
        current_image, safe_blue_image, target_gold_image, preview_path
    )
    layer_map(Image.open(state_path).convert("RGB"), hazards, sprites, layers_path)
    tile_sheet(originals, variants, rom, tiles_path)
    (output / "hazard-variants.bin").write_bytes(raw_variant)

    scene = state[WRAM_OFFSET + (0xD880 - 0xC000)]
    visible_variant_ids = sorted({
        cell["tile"] for cell in hazards if cell["tile"] in VARIANT_TILES
    })
    visible_body_ids = sorted({
        cell["tile"] for cell in hazards if cell["tile"] in BODY_TILES
    })
    current_table = rom[BG_TABLE_OFFSET:BG_TABLE_OFFSET + 256]
    checks = {
        "captured state is ordinary Stage 1 gameplay": scene == 0x02,
        "active map contains a substantial rotating spike assembly": len(hazards) >= 20,
        "visible assembly exercises rings and teeth": (
            bool(set(visible_variant_ids) & RING_TILES)
            and bool(set(visible_variant_ids) & TOOTH_TILES)
        ),
        "hardware OAM does not overlap the captured spike assembly": not overlaps,
        "all 32 captured spike-family tiles equal stock Stage 1 art": (
            all(family_matches)
        ),
        "all candidate source-art tiles equal the YAML variants": (
            all(candidate_matches)
        ),
        "all proposed tiles differ from their stock art": all(
            variants[tile] != originals[tile] for tile in originals
        ),
        "semantic remap keeps environmental white/blue and black available": (
            ENVIRONMENT_REMAP == {0: 0, 1: 1, 2: 1, 3: 3}
        ),
        "semantic remap gives changed non-black pixels one hazard index": (
            HAZARD_REMAP == {0: 2, 1: 2, 2: 2, 3: 3}
        ),
        "preferred rotating-art attribute is scene-local BG7 with no unsafe bits": (
            PREFERRED_ATTR == 0x07
        ),
        "bank-1 fallback is exactly BG7 plus pattern-bank bit": (
            BANK1_FALLBACK_ATTR == 0x0F
        ),
        "selected bank-1 pattern slots are blank in every parsed fixture": (
            parsed_fixtures > 0 and not occupied_fixtures
        ),
        "current LUT does not already select VRAM bank 1": all(
            current_table[tile] & 0x08 == 0 for tile in ART_TILES
        ),
        "BG7 is selected only by the 12 tooth animation IDs": (
            {
                tile for tile, palette in enumerate(current_table)
                if palette == VARIANT_PALETTE
            } == TOOTH_TILES
        ),
        "captured cylinder body exercises all four approved core IDs": (
            {0x62, 0x6E, 0x72, 0x7E}.issubset(visible_body_ids)
        ),
        "vertical end-shadow column stays outside the fire body": (
            not ({0x63, 0x73} & BODY_TILES)
        ),
        "every tooth animation frame has an explicit silhouette mask": (
            set(TOOTH_ROW_SPANS) == TOOTH_TILES
            and all(TOOTH_ROW_SPANS.values())
        ),
        "every tooth silhouette row is bounded by original black art": (
            tooth_mask_boundaries_are_black
        ),
        "every enclosed non-black tooth pixel receives the gold index": (
            tooth_mask_interiors_are_complete
        ),
        "pixels outside tooth silhouettes always retain neutral classification": (
            tooth_mask_exteriors_are_conservative
        ),
    }
    failures = [name for name, passed in checks.items() if not passed]
    receipt = {
        "schema": "penta-dragon-dx-stage1-hazard-layers-v1",
        "status": "pass" if not failures else "fail",
        "rom": str(rom_path),
        "rom_sha256": digest(rom_path),
        "stock_rom": str(stock_path),
        "stock_rom_sha256": digest(stock_path),
        "state": str(state_path),
        "state_sha256": digest(state_path),
        "scene": f"{scene:02X}",
        "display": {
            "lcdc": f"{metadata['lcdc']:02X}",
            "scx": metadata["scx"],
            "scy": metadata["scy"],
            "active_map": f"{metadata['map']:04X}",
            "signed_tile_indices": bool(metadata["signed_tile_indices"]),
        },
        "visible_spike_cells": hazards,
        "visible_spike_cell_count": len(hazards),
        "visible_hardware_oam": sprites,
        "oam_overlap_count": len(overlaps),
        "oam_overlaps": overlaps,
        "rom_source_matches": sum(family_matches),
        "rom_source_family_size": len(family_matches),
        "candidate_variant_matches": sum(candidate_matches),
        "proposal": {
            "tiles": [f"{tile:02X}" for tile in sorted(ART_TILES)],
            "visible_tiles": [f"{tile:02X}" for tile in visible_variant_ids],
            "palette": VARIANT_PALETTE,
            "tooth_palette": VARIANT_PALETTE,
            "ring_palette": BODY_PALETTE,
            "preferred_vram_bank": 0,
            "preferred_attribute": f"{PREFERRED_ATTR:02X}",
            "bank1_fallback_attribute": f"{BANK1_FALLBACK_ATTR:02X}",
            "body_tiles": [f"{tile:02X}" for tile in sorted(BODY_TILES)],
            "connector_tiles": [
                f"{tile:02X}" for tile in sorted(CONNECTOR_TILES)
            ],
            "visible_body_tiles": [f"{tile:02X}" for tile in visible_body_ids],
            "body_palette": BODY_PALETTE,
            "semantic_base_tiles": {
                f"{key:02X}": f"{value:02X}"
                for key, value in sorted(SEMANTIC_BASE_TILES.items())
            },
            "ring_regions": {
                f"{key:02X}": list(value)
                for key, value in sorted(RING_REGIONS.items())
            },
            "tooth_row_spans": {
                f"{tile:02X}": {
                    str(row): list(span)
                    for row, span in sorted(rows.items())
                }
                for tile, rows in sorted(TOOTH_ROW_SPANS.items())
            },
            "environment_remap": {
                str(key): value for key, value in ENVIRONMENT_REMAP.items()
            },
            "hazard_remap": {
                str(key): value for key, value in HAZARD_REMAP.items()
            },
            "target_palette_sources": [
                "penta_palettes_v097.yaml:",
                "stage1_hazard_palettes.RotatingSpikeTeeth.colors",
            ],
            "raw_bytes": len(raw_variant),
            "changed_bytes": changed_bytes,
            "histograms": histograms,
        },
        "fixture_inventory": {
            "directory": str(args.fixtures.resolve()),
            "parsed_states": parsed_fixtures,
            "occupied_variant_slots": occupied_fixtures,
        },
        "artifacts": {
            "preview": preview_path.name,
            "preview_sha256": digest(preview_path),
            "layer_map": layers_path.name,
            "layer_map_sha256": digest(layers_path),
            "tile_sheet": tiles_path.name,
            "tile_sheet_sha256": digest(tiles_path),
            "variant_bytes": "hazard-variants.bin",
            "variant_bytes_sha256": hashlib.sha256(raw_variant).hexdigest(),
        },
        "checks": checks,
        "failures": failures,
    }
    receipt_path = output / "receipt.json"
    receipt_path.write_text(json.dumps(receipt, indent=2) + "\n")
    for name, passed in checks.items():
        print(f"{'PASS' if passed else 'FAIL'}: {name}")
    print(f"Layer map: {layers_path}")
    print(f"Semantic-art preview: {preview_path}")
    print(f"Receipt: {receipt_path}")
    if failures:
        print("FAIL: " + "; ".join(failures))
        return 1
    print(
        "PASS: captured rotating spike is BG-only; "
        f"{len(ART_TILES)} Stage-1 source-art variants differ in "
        f"{changed_bytes}/{len(ART_TILES) * 16} bytes (bank 1 stays free)."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
