"""Shared diagnostic contract for all nine animated boss arenas.

This module deliberately owns no runtime addresses.  It gives receipt tools a
single boss order, expected material, scene number, and measured footprint
without coupling the production ROM builder to an experimental WRAM layout.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
POSITION_LOG = ROOT / "scripts/diagnostics/posmap_maps.log"


@dataclass(frozen=True)
class BossContract:
    name: str
    material: str
    scene: int
    neutral_rectangles: tuple[tuple[int, int, int, int], ...] = ()
    neutral_tile_ids: frozenset[int] = frozenset()


BOSSES = (
    BossContract(
        "shalamar", "ice cyan", 0x0C,
        ((8, 12, 20, 24), (12, 18, 0, 24)),
        frozenset({0x00, 0x01}),
    ),
    BossContract("riff", "purple", 0x0D),
    BossContract("crystal_dragon", "ice cyan", 0x0E),
    BossContract("cameo", "cherry red/crimson", 0x0F),
    BossContract(
        "ted",
        "staggered crimson/gold shell + vertically continuous dark tendrils",
        0x10,
    ),
    BossContract("troop", "steel/navy", 0x11),
    BossContract("faze", "purple", 0x12),
    BossContract("angela", "purple", 0x13),
    BossContract(
        "penta_dragon", "cherry red body + multicolor heads", 0x14,
    ),
)
NAMES = tuple(boss.name for boss in BOSSES)


# Crystal Dragon's portal reuses animated tile IDs across differently colored
# material cells. Its body is OBJ4-OBJ7, so the production path intentionally
# caches the portal's two physical BG attribute maps instead of recoloring each
# tile publish. These are the exact visible 18x20 entry layouts. Later native
# camera wraps atomically advance both layouts. Row 4, column 15 is the one
# measured phase seam: depending on which physical map was serialized first,
# one entry-layout cell can already contain either side of the next native
# wrap. The strict verifier allows one such entry cell anywhere, but still
# rejects two cells, partial publishes, or rapid layout alternation.
CRYSTAL_ENTRY_PHASE_CELLS = frozenset({(4, 15)})
CRYSTAL_ENTRY_ATTR_ROWS = {
    0x9800: (
        "44444444000000040004", "44444444000000040004",
        "44000044044000040004", "44000004400444404440",
        "44000004000000040004", "44000044000000040004",
        "44444444044000040004", "44444444400444404440",
        "00004000000000040004", "00004000000000040004",
        "00004000044000040004", "00000444400444404440",
        "00000000000000040000", "00000000000000040000",
        "00000000044000044444", "00000000400444404004",
        "44400004000000440000", "00040040000000400000",
    ),
    0x9C00: (
        "44444444000000040004", "44444444000000040004",
        "44000044044000040004", "44000004400444404440",
        "44000004000000000004", "44000044000000040004",
        "44444444044000040004", "44444444400444404440",
        "00004000000000040004", "00004000000000040004",
        "00004000044000040004", "00000444400444404440",
        "00000000000000040000", "00000000000000040000",
        "00000000044000044444", "00000000400444404004",
        "44400004000000440000", "00040040000000400000",
    ),
}


def crystal_entry_attr_map() -> dict[tuple[int, int, int], int]:
    """Return the exact clean-entry physical maps for Crystal's portal."""
    result: dict[tuple[int, int, int], int] = {}
    for base, rows in CRYSTAL_ENTRY_ATTR_ROWS.items():
        if len(rows) != 18:
            raise ValueError(f"Crystal map {base:04X} has {len(rows)} rows")
        for row, digits in enumerate(rows):
            if len(digits) != 20 or set(digits) - set("04"):
                raise ValueError(
                    f"invalid Crystal cached row {base:04X}:{row}: {digits}"
                )
            for col, digit in enumerate(digits):
                result[(base, row, col)] = int(digit)
    differences = [
        (row, col)
        for row in range(18)
        for col in range(20)
        if result[(0x9800, row, col)] != result[(0x9C00, row, col)]
    ]
    if set(differences) - CRYSTAL_ENTRY_PHASE_CELLS:
        raise ValueError(
            f"Crystal cached-map seam changed: {differences}"
        )
    return result


def load_position_maps(path: Path = POSITION_LOG) -> dict[str, bytes]:
    """Load and validate every measured 18x20 footprint in a 32-column map."""
    rows: dict[str, dict[int, str]] = {}
    for line in path.read_text().splitlines():
        fields = line.split()
        if len(fields) == 4 and fields[0] == "ROW":
            name, row, digits = fields[1], int(fields[2]), fields[3]
            rows.setdefault(name, {})[row] = digits

    maps: dict[str, bytes] = {}
    for boss in BOSSES:
        result = bytearray(18 * 32)
        for row in range(18):
            digits = rows.get(boss.name, {}).get(row)
            if digits is None or len(digits) != 20:
                raise ValueError(
                    f"invalid footprint row {boss.name}:{row} in {path}"
                )
            for col, value in enumerate(digits):
                result[row * 32 + col] = int(value) & 7
        maps[boss.name] = bytes(result)
    return maps


def group_clear_flags(
    position_map: bytes,
    *,
    rows: int = 24,
    columns: int = 24,
    group_width: int = 3,
) -> bytes:
    """Describe wholly unoccupied atomic groups without prescribing storage."""
    if len(position_map) != 18 * 32:
        raise ValueError(f"expected 576 footprint bytes, got {len(position_map)}")
    flags = bytearray()
    for row in range(rows):
        for start in range(0, columns, group_width):
            occupied = any(
                row < 18
                and col < 20
                and position_map[row * 32 + col] != 0
                for col in range(start, start + group_width)
            )
            flags.append(not occupied)
    return bytes(flags)
