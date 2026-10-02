"""Per-boss-arena BG palette rows (`arena_bg_palettes` in the palette YAML).

Every boss arena has its own tile->palette-number table
(`arena_tables_data.ARENA_TILE_PAL`), but all arenas historically shared one
global BG0-BG7 color block (`bg_palettes`).  The optional YAML section

    arena_bg_palettes:
      Shalamar:
        BG4: ["7FFF", "7FE0", "3D80", "0000"]
      Ted:
        BG1: ["7FFF", "001F", "294A", "0000"]

overrides individual rows for one arena only.  Any row or arena that is not
listed falls back to the global `bg_palettes` row, so a YAML without this
section (or with an empty mapping) means exactly today's behavior.

The runtime identifies stage-boss arenas by the master scene byte D880,
which is $0C + FFBA ($0C Shalamar ... $14 Penta Dragon).

This module is deliberately dependency-light (PyYAML is only needed by the
caller) so the live editor, its tests, and the builder share one parser.
"""
from __future__ import annotations

import re
from typing import Mapping

SECTION = "arena_bg_palettes"

# (YAML key, UI label, D880 scene id, arena_tables_data key)
ARENAS: tuple[tuple[str, str, int, str], ...] = (
    ("Shalamar", "Boss 1 — Shalamar", 0x0C, "shalamar"),
    ("Riff", "Boss 2 — Riff", 0x0D, "riff"),
    ("CrystalDragon", "Boss 3 — Crystal Dragon", 0x0E, "crystal_dragon"),
    ("Cameo", "Boss 4 — Cameo", 0x0F, "cameo"),
    ("Ted", "Boss 5 — Ted", 0x10, "ted"),
    ("Troop", "Boss 6 — Troop", 0x11, "troop"),
    ("Faze", "Boss 7 — Faze", 0x12, "faze"),
    ("Angela", "Boss 8 — Angela", 0x13, "angela"),
    ("PentaDragon", "Final Boss — Penta Dragon", 0x14, "penta_dragon"),
)
ARENA_KEYS = tuple(key for key, _label, _d880, _table in ARENAS)
ARENA_D880 = {key: d880 for key, _label, d880, _table in ARENAS}
ARENA_LABEL = {key: label for key, label, _d880, _table in ARENAS}
ARENA_TABLE_KEY = {key: table for key, _label, _d880, table in ARENAS}

ROW_KEYS = tuple(f"BG{index}" for index in range(8))
# `Dungeon` is the global YAML name of BG0; accept it as an alias on input.
ROW_ALIASES = {"Dungeon": 0, **{name: index for index, name in enumerate(ROW_KEYS)}}
_COLOR_RE = re.compile(r"[0-7][0-9A-Fa-f]{3}")

Overrides = dict[str, dict[int, list[str]]]


class ArenaPaletteError(ValueError):
    """Raised for a malformed `arena_bg_palettes` section."""


def normalize_color(value: object, where: str) -> str:
    if not isinstance(value, str) or not _COLOR_RE.fullmatch(value):
        raise ArenaPaletteError(
            f"{where}: expected a 4-digit BGR555 string 0000-7FFF, got {value!r}"
        )
    return value.upper()


def parse_arena_bg_palettes(document: Mapping | None) -> Overrides:
    """Validate and normalize the optional section.

    Returns {arena_key: {row_index: [4 uppercase BGR555 strings]}} containing
    only arenas with at least one row.  A missing/None/empty section returns
    an empty dict.  Unknown arenas, unknown rows, or bad colors raise
    ArenaPaletteError instead of silently falling back (the builder must never
    ship a typo as "no override").
    """
    if not document:
        return {}
    section = document.get(SECTION)
    if section is None:
        return {}
    if not isinstance(section, Mapping):
        raise ArenaPaletteError(f"{SECTION} must be a mapping of boss arenas")
    result: Overrides = {}
    for arena, rows in section.items():
        if arena not in ARENA_D880:
            raise ArenaPaletteError(
                f"{SECTION}: unknown arena {arena!r}; expected one of "
                + ", ".join(ARENA_KEYS)
            )
        if rows is None:
            continue
        if not isinstance(rows, Mapping):
            raise ArenaPaletteError(f"{SECTION}.{arena} must map BG rows to colors")
        parsed: dict[int, list[str]] = {}
        for row_name, colors in rows.items():
            if row_name not in ROW_ALIASES:
                raise ArenaPaletteError(
                    f"{SECTION}.{arena}: unknown row {row_name!r}; use BG0..BG7"
                )
            row = ROW_ALIASES[row_name]
            if row in parsed:
                raise ArenaPaletteError(f"{SECTION}.{arena}: BG{row} given twice")
            if isinstance(colors, Mapping):
                colors = colors.get("colors")
            where = f"{SECTION}.{arena}.{row_name}"
            if not isinstance(colors, (list, tuple)) or len(colors) != 4:
                raise ArenaPaletteError(f"{where}: expected exactly four colors")
            parsed[row] = [normalize_color(c, f"{where}[{i}]") for i, c in enumerate(colors)]
        if parsed:
            result[arena] = dict(sorted(parsed.items()))
    return {key: result[key] for key in ARENA_KEYS if key in result}


def render_section(overrides: Overrides) -> str:
    """Render the editor-managed YAML block (ends with a newline)."""
    lines = [f"{SECTION}:" + ("" if any(overrides.values()) else " {}")]
    lines.append(
        "  # Editor-managed per-boss-arena BG rows (live_palette_editor.py Save)."
    )
    lines.append(
        "  # Missing arenas/rows fall back to bg_palettes. Applied only while D880"
    )
    lines.append(
        "  # is that arena's scene id ($0C Shalamar .. $14 PentaDragon)."
    )
    if not any(overrides.values()):
        # A comment cannot follow a flow mapping on the same logical block, so
        # keep the comments but leave the mapping empty and valid.
        return "\n".join(lines) + "\n"
    for arena in ARENA_KEYS:
        rows = overrides.get(arena) or {}
        if not rows:
            continue
        lines.append(f"  {arena}:")
        for row in sorted(rows):
            colors = ", ".join(f'"{normalize_color(c, arena)}"' for c in rows[row])
            lines.append(f"    BG{row}: [{colors}]")
    return "\n".join(lines) + "\n"


def replace_section(text: str, overrides: Overrides) -> str:
    """Return YAML text with the arena section replaced/added/emptied.

    Everything outside the section is preserved byte-for-byte. If the section
    is absent and there are no overrides, the text is returned unchanged so a
    global-only save stays identical to the historical editor.
    """
    lines = text.splitlines(keepends=True)
    start = None
    for index, line in enumerate(lines):
        if re.match(rf"^{SECTION}:(\s|$)", line):
            start = index
            break
    has_overrides = any(overrides.values())
    if start is None:
        if not has_overrides:
            return text
        prefix = text
        if prefix and not prefix.endswith("\n"):
            prefix += "\n"
        if prefix and not prefix.endswith("\n\n"):
            prefix += "\n"
        return prefix + render_section(overrides)
    end = start + 1
    while end < len(lines):
        line = lines[end]
        if line.strip() == "" or line[0] in " \t":
            end += 1
            continue
        break
    # Keep blank lines that separate the block from the next section.
    tail_blank = end
    while tail_blank > start + 1 and lines[tail_blank - 1].strip() == "":
        tail_blank -= 1
    block = render_section(overrides)
    return "".join(lines[:start]) + block + "".join(lines[tail_blank:])


def arena_rows_used(arena: str) -> list[int]:
    """BG rows the arena's tile table can produce (BG0 is always the backdrop).

    Derived from `arena_tables_data.ARENA_TILE_PAL` with the same masking as
    `build_v301_teleport._table_from_dict` (tile $FF is force-cleared to 0).
    """
    from arena_tables_data import ARENA_TILE_PAL  # local import: scripts/ on path

    table = ARENA_TILE_PAL[ARENA_TABLE_KEY[arena]]
    rows = {0}
    rows.update(pal & 7 for tile, pal in table.items() if (tile & 0xFF) != 0xFF)
    return sorted(rows)


def effective_rows(
    global_rows: Mapping[int, list[str]], overrides: Overrides, arena: str
) -> dict[int, list[str]]:
    """Global rows with one arena's overrides applied (for previews/builders)."""
    rows = {row: list(global_rows[row]) for row in range(8)}
    for row, colors in (overrides.get(arena) or {}).items():
        rows[row] = list(colors)
    return rows


def colors_to_bytes(colors: list[str]) -> bytes:
    out = bytearray()
    for color in colors:
        value = int(color, 16) & 0x7FFF
        out += value.to_bytes(2, "little")
    return bytes(out)
