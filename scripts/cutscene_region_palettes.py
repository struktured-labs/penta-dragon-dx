#!/usr/bin/env python3
"""Compile the YAML-owned story-panel region palette masks.

The stock story renderer commits a 20x8 illustration above a 20x10 dialogue
area.  This module deliberately models only the illustration.  Runtime code
must keep the lower dialogue area neutral BG0.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml


ART_COLUMNS = 20
ART_ROWS = 8
STORY_ART_IDS = frozenset(range(1, 8))


@dataclass(frozen=True)
class Region:
    x0: int
    x1: int
    y0: int
    y1: int
    palette: int
    palette_name: str


@dataclass(frozen=True)
class Panel:
    name: str
    art_ids: tuple[int, ...]
    default_palette: int
    default_palette_name: str
    regions: tuple[Region, ...]


def _range(raw: object, label: str, maximum: int) -> tuple[int, int]:
    if not isinstance(raw, list) or len(raw) != 2:
        raise ValueError(f"{label} must be a two-element YAML list")
    start, end = raw
    if not isinstance(start, int) or not isinstance(end, int):
        raise ValueError(f"{label} bounds must be integers")
    if not 0 <= start <= end < maximum:
        raise ValueError(
            f"{label} range {start}..{end} is outside 0..{maximum - 1}"
        )
    return start, end


def load_cutscene_region_palettes(path: Path) -> dict[int, Panel]:
    """Return one validated panel definition for each stock art ID 1..7."""
    path = Path(path)
    document = yaml.safe_load(path.read_text())
    bg_palettes = document.get("bg_palettes")
    definitions = document.get("cutscene_region_palettes")
    if not isinstance(bg_palettes, dict) or len(bg_palettes) != 8:
        raise ValueError(f"{path}: bg_palettes must define eight ordered slots")
    if not isinstance(definitions, dict) or not definitions:
        raise ValueError(f"{path}: cutscene_region_palettes is missing")

    slots = {name: index for index, name in enumerate(bg_palettes)}
    by_art_id: dict[int, Panel] = {}
    for name, raw in definitions.items():
        if not isinstance(raw, dict):
            raise ValueError(f"{name}: panel definition must be a mapping")
        art_ids_raw = raw.get("art_ids")
        if not isinstance(art_ids_raw, list) or not art_ids_raw:
            raise ValueError(f"{name}: art_ids must be a non-empty list")
        art_ids = tuple(art_ids_raw)
        if any(not isinstance(value, int) for value in art_ids):
            raise ValueError(f"{name}: art_ids must contain integers")
        default_name = raw.get("default")
        if default_name not in slots or slots[default_name] == 0:
            raise ValueError(
                f"{name}: default must name one of the chromatic BG1..BG7 rows"
            )

        regions: list[Region] = []
        occupied: set[tuple[int, int]] = set()
        raw_regions = raw.get("regions", [])
        if not isinstance(raw_regions, list):
            raise ValueError(f"{name}: regions must be a list")
        for index, raw_region in enumerate(raw_regions):
            if not isinstance(raw_region, dict):
                raise ValueError(f"{name}: region {index} must be a mapping")
            x0, x1 = _range(
                raw_region.get("x"), f"{name} region {index} x", ART_COLUMNS
            )
            y0, y1 = _range(
                raw_region.get("y"), f"{name} region {index} y", ART_ROWS
            )
            palette_name = raw_region.get("palette")
            if palette_name not in slots or slots[palette_name] == 0:
                raise ValueError(
                    f"{name}: region {index} must name a chromatic BG1..BG7 row"
                )
            cells = {
                (x, y)
                for y in range(y0, y1 + 1)
                for x in range(x0, x1 + 1)
            }
            overlap = occupied & cells
            if overlap:
                sample = min(overlap, key=lambda cell: (cell[1], cell[0]))
                raise ValueError(
                    f"{name}: region {index} overlaps another region at {sample}"
                )
            occupied.update(cells)
            regions.append(Region(
                x0=x0,
                x1=x1,
                y0=y0,
                y1=y1,
                palette=slots[palette_name],
                palette_name=palette_name,
            ))

        panel = Panel(
            name=name,
            art_ids=art_ids,
            default_palette=slots[default_name],
            default_palette_name=default_name,
            regions=tuple(regions),
        )
        for art_id in art_ids:
            if art_id not in STORY_ART_IDS:
                raise ValueError(f"{name}: art ID {art_id} is outside 1..7")
            if art_id in by_art_id:
                raise ValueError(
                    f"art ID {art_id} is assigned to both "
                    f"{by_art_id[art_id].name} and {name}"
                )
            by_art_id[art_id] = panel

    missing = sorted(STORY_ART_IDS - by_art_id.keys())
    if missing:
        raise ValueError(f"unclassified story art IDs: {missing}")
    return by_art_id


def panel_mask(panel: Panel) -> tuple[tuple[int, ...], ...]:
    rows = [
        [panel.default_palette for _ in range(ART_COLUMNS)]
        for _ in range(ART_ROWS)
    ]
    for region in panel.regions:
        for y in range(region.y0, region.y1 + 1):
            for x in range(region.x0, region.x1 + 1):
                rows[y][x] = region.palette
    return tuple(tuple(row) for row in rows)


def masks_by_art_id(path: Path) -> dict[int, tuple[tuple[int, ...], ...]]:
    return {
        art_id: panel_mask(panel)
        for art_id, panel in load_cutscene_region_palettes(path).items()
    }
