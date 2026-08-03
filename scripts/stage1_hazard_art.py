#!/usr/bin/env python3
"""Compile the YAML-owned Stage 1 rotating-spike art and palette contract."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

import yaml


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_ART_YAML = ROOT / "palettes/bg_tile_categories.yaml"
DEFAULT_PALETTE_YAML = ROOT / "palettes/penta_palettes_v097.yaml"


@dataclass(frozen=True)
class Stage1HazardConfig:
    source_offset: int
    tooth_tiles: frozenset[int]
    ring_tiles: frozenset[int]
    body_tiles: frozenset[int]
    connector_tiles: frozenset[int]
    support_tiles: frozenset[int]
    tooth_palette: int
    ring_palette: int
    body_palette: int
    connector_palette: int
    support_palette: int
    semantic_base_tiles: Mapping[int, int]
    environment_remap: tuple[int, int, int, int]
    hazard_remap: tuple[int, int, int, int]
    ring_regions: Mapping[int, tuple[int, int, int, int]]
    tooth_row_spans: Mapping[int, Mapping[int, tuple[int, int]]]
    body_row_spans: Mapping[int, Mapping[int, tuple[int, int]]]
    connector_row_spans: Mapping[int, Mapping[int, tuple[int, int]]]

    @property
    def art_tiles(self) -> frozenset[int]:
        return (
            self.tooth_tiles
            | self.ring_tiles
            | self.body_tiles
            | self.connector_tiles
        )

    @property
    def family_tiles(self) -> frozenset[int]:
        return self.art_tiles | self.support_tiles


def _category_tiles(category: dict, size: int = 256) -> frozenset[int]:
    result = {int(tile) for tile in category.get("tiles", [])}
    for low, high in category.get("tile_ranges", []):
        low, high = int(low), int(high)
        if not 0 <= low <= high < size:
            raise ValueError(f"invalid tile range {low:02X}-{high:02X}")
        result.update(range(low, high + 1))
    if any(not 0 <= tile < size for tile in result):
        raise ValueError("tile category contains an out-of-range ID")
    return frozenset(result)


def _row_spans(value: dict) -> dict[int, dict[int, tuple[int, int]]]:
    result: dict[int, dict[int, tuple[int, int]]] = {}
    for raw_tile, raw_rows in value.items():
        tile = int(raw_tile)
        rows: dict[int, tuple[int, int]] = {}
        for raw_row, raw_span in raw_rows.items():
            row = int(raw_row)
            left, right = (int(item) for item in raw_span)
            if not 0 <= row < 8 or not 0 <= left < right <= 8:
                raise ValueError(
                    f"invalid row span tile={tile:02X} row={row}: "
                    f"{left}..{right}"
                )
            rows[row] = (left, right)
        result[tile] = rows
    return result


def load_stage1_hazard_config(
    path: Path | str = DEFAULT_ART_YAML,
) -> Stage1HazardConfig:
    """Load and cross-check the canonical art and attribute declaration."""
    data = yaml.safe_load(Path(path).read_text())
    bg = data["bg_table"]
    named = {category["name"]: category for category in bg["categories"]}
    raw = data["stage1_hazard_art"]["rotating_spike"]
    roles = raw["palette_categories"]

    def role(name: str) -> tuple[frozenset[int], int]:
        category = named[roles[name]]
        palette = int(category["palette"])
        if not 0 <= palette <= 7:
            raise ValueError(f"{category['name']} has invalid palette {palette}")
        return _category_tiles(category), palette

    tooth_tiles, tooth_palette = role("tooth")
    fire_tiles, fire_palette = role("fire_body")
    connector_tiles, connector_palette = role("wall_connector")
    support_tiles, support_palette = role("support")
    ring_tiles = frozenset(int(tile) for tile in raw["ring_tiles"])
    body_tiles = frozenset(int(tile) for tile in raw["body_tiles"])
    if fire_tiles != ring_tiles | body_tiles:
        raise ValueError("fire-body category does not equal ring + body IDs")

    semantic = {
        int(tile): int(baseline)
        for tile, baseline in raw["semantic_base_tiles"].items()
    }
    ring_regions = {
        int(tile): tuple(int(item) for item in region)
        for tile, region in raw["ring_regions"].items()
    }
    tooth_spans = _row_spans(raw["tooth_row_spans"])
    body_spans = _row_spans(raw["body_row_spans"])
    connector_spans = _row_spans(raw["connector_row_spans"])
    config = Stage1HazardConfig(
        source_offset=int(raw["source_offset"]),
        tooth_tiles=tooth_tiles,
        ring_tiles=ring_tiles,
        body_tiles=body_tiles,
        connector_tiles=connector_tiles,
        support_tiles=support_tiles,
        tooth_palette=tooth_palette,
        ring_palette=fire_palette,
        body_palette=fire_palette,
        connector_palette=connector_palette,
        support_palette=support_palette,
        semantic_base_tiles=semantic,
        environment_remap=tuple(int(item) for item in raw["environment_remap"]),
        hazard_remap=tuple(int(item) for item in raw["hazard_remap"]),
        ring_regions=ring_regions,
        tooth_row_spans=tooth_spans,
        body_row_spans=body_spans,
        connector_row_spans=connector_spans,
    )
    if config.family_tiles != frozenset(range(0x60, 0x80)):
        raise ValueError("rotating-spike roles must partition tiles 60-7F")
    if config.art_tiles & config.support_tiles:
        raise ValueError("art and support tile roles overlap")
    if set(config.semantic_base_tiles) != config.tooth_tiles | config.ring_tiles:
        raise ValueError("semantic baselines must cover every tooth and ring")
    if set(config.ring_regions) != config.ring_tiles:
        raise ValueError("ring regions must cover every ring tile")
    if set(config.tooth_row_spans) != config.tooth_tiles:
        raise ValueError("tooth silhouettes must cover every tooth tile")
    if set(config.body_row_spans) != config.ring_tiles | config.body_tiles:
        raise ValueError("body silhouettes must cover every fire-body tile")
    if set(config.connector_row_spans) != config.connector_tiles:
        raise ValueError("connector silhouettes must cover every connector tile")
    for mapping in (config.environment_remap, config.hazard_remap):
        if len(mapping) != 4 or any(not 0 <= value <= 3 for value in mapping):
            raise ValueError(f"invalid 2bpp remap {mapping}")
    return config


def _color_words(colors: list[str | int]) -> tuple[int, int, int, int]:
    values = tuple(
        int(color, 16) if isinstance(color, str) else int(color)
        for color in colors
    )
    if len(values) != 4 or any(not 0 <= value <= 0x7FFF for value in values):
        raise ValueError("a CGB palette must contain four BGR555 colors")
    return values


def load_stage1_hazard_palette(
    palette_path: Path | str = DEFAULT_PALETTE_YAML,
    art_path: Path | str = DEFAULT_ART_YAML,
) -> tuple[int, bytes]:
    """Return the Stage-1-only tooth palette slot and its little-endian row."""
    config = load_stage1_hazard_config(art_path)
    data = yaml.safe_load(Path(palette_path).read_text())
    raw = data["stage1_hazard_palettes"]["RotatingSpikeTeeth"]
    slot = int(raw["slot"])
    if slot != config.tooth_palette:
        raise ValueError(
            f"tooth palette slot {slot} disagrees with BG category "
            f"{config.tooth_palette}"
        )
    payload = bytearray()
    for word in _color_words(raw["colors"]):
        payload.extend((word & 0xFF, word >> 8))
    return slot, bytes(payload)


def decode_tile(raw: bytes) -> list[int]:
    if len(raw) != 16:
        raise ValueError("a Game Boy tile must be exactly 16 bytes")
    pixels: list[int] = []
    for row in range(8):
        low, high = raw[row * 2:row * 2 + 2]
        for bit in range(7, -1, -1):
            pixels.append(((low >> bit) & 1) | (((high >> bit) & 1) << 1))
    return pixels


def encode_tile(pixels: list[int]) -> bytes:
    if len(pixels) != 64:
        raise ValueError("a Game Boy tile must contain exactly 64 pixels")
    result = bytearray(16)
    for row in range(8):
        for column in range(8):
            value = pixels[row * 8 + column]
            bit = 7 - column
            result[row * 2] |= (value & 1) << bit
            result[row * 2 + 1] |= ((value >> 1) & 1) << bit
    return bytes(result)


def _inside_span(
    rows: Mapping[int, tuple[int, int]], x: int, y: int,
) -> bool:
    span = rows.get(y)
    return bool(span and span[0] <= x < span[1])


def remap_hazard_tile(
    config: Stage1HazardConfig,
    tile: int,
    raw: bytes,
    baseline: bytes,
) -> bytes:
    """Apply the reviewed material mask to one Stage 1 source tile."""
    source_pixels = decode_tile(raw)
    baseline_pixels = decode_tile(baseline)
    result: list[int] = []
    ring_region = config.ring_regions.get(tile)
    body_rows = config.body_row_spans.get(tile, {})
    tooth_rows = config.tooth_row_spans.get(tile, {})
    connector_rows = config.connector_row_spans.get(tile, {})
    for index, (source, background) in enumerate(
        zip(source_pixels, baseline_pixels)
    ):
        x, y = index & 7, index >> 3
        if tile in config.connector_tiles:
            if _inside_span(connector_rows, x, y):
                result.append(3 if source == 3 else (1 if source == 0 else 2))
            else:
                result.append(3 if source == 3 else 0)
            continue
        inside_ring = bool(
            ring_region
            and ring_region[0] <= x < ring_region[2]
            and ring_region[1] <= y < ring_region[3]
        )
        if tile in config.ring_tiles or tile in config.body_tiles:
            if source == 3:
                result.append(3)
            elif inside_ring:
                result.append(1)
            elif _inside_span(body_rows, x, y):
                result.append(1 if source == 0 else 2)
            else:
                result.append(0)
            continue
        if _inside_span(tooth_rows, x, y):
            result.append(3 if source == 3 else 2)
            continue
        mapping = (
            config.environment_remap
            if source == background
            else config.hazard_remap
        )
        result.append(mapping[source])
    return encode_tile(result)


def compile_stage1_hazard_variants(
    source_rom: bytes,
    config: Stage1HazardConfig | None = None,
) -> dict[int, bytes]:
    config = config or load_stage1_hazard_config()
    variants: dict[int, bytes] = {}
    for tile in sorted(config.art_tiles):
        start = config.source_offset + tile * 16
        raw = source_rom[start:start + 16]
        baseline_tile = config.semantic_base_tiles.get(tile, tile)
        baseline_start = config.source_offset + baseline_tile * 16
        baseline = source_rom[baseline_start:baseline_start + 16]
        if len(raw) != 16 or len(baseline) != 16:
            raise ValueError("Stage 1 tile source falls outside the ROM")
        variants[tile] = remap_hazard_tile(config, tile, raw, baseline)
    return variants


def apply_stage1_hazard_variants(
    rom: bytearray,
    stock_rom: bytes,
    config: Stage1HazardConfig | None = None,
) -> dict[str, int]:
    """Write only the approved Stage 1 source-art variants into a build."""
    config = config or load_stage1_hazard_config()
    variants = compile_stage1_hazard_variants(stock_rom, config)
    changed_bytes = 0
    for tile, variant in variants.items():
        start = config.source_offset + tile * 16
        stock = stock_rom[start:start + 16]
        if bytes(rom[start:start + 16]) != stock:
            raise ValueError(f"Stage 1 hazard tile {tile:02X} changed before remap")
        changed_bytes += sum(before != after for before, after in zip(stock, variant))
        rom[start:start + 16] = variant
    return {
        "tiles": len(variants),
        "raw_bytes": len(variants) * 16,
        "changed_bytes": changed_bytes,
    }
