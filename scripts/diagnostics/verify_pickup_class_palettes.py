#!/usr/bin/env python3
"""Verify and render the complete Stage 1 pickup-class palette map.

The checked-in mGBA savestates are PNG containers. Their ``gbAs`` chunk holds
the zlib-compressed 0x11800-byte Game Boy state, including both VRAM banks.
Reading that payload directly lets this verifier bind every named pickup to
its real 2x2 tile signature without launching an emulator or trusting a
filename alone.
"""

from __future__ import annotations

import argparse
from collections import Counter
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import struct
import sys
import zlib

from PIL import Image, ImageDraw


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

from build_v301_gdma import _bg_table  # noqa: E402


DEFAULT_ROM = ROOT / "rom/working/penta_dragon_dx_FIXED.gb"
DEFAULT_STATES = ROOT / "save_states_for_claude"
BANK13 = 13 * 0x4000
BG_TABLE_OFFSET = BANK13 + (0x7000 - 0x4000)
BG_PALETTE_OFFSET = BANK13 + (0x6800 - 0x4000)
SERIALIZED_SIZE = 0x11800
VRAM_OFFSET = 0x400
VRAM_SIZE = 0x2000


@dataclass(frozen=True)
class Pickup:
    name: str
    tiles: tuple[int, int, int, int]
    palette: int
    state: str


def block(base: int) -> tuple[int, int, int, int]:
    return base, base + 1, base + 0x10, base + 0x11


PICKUPS = (
    Pickup(
        "Health 1",
        block(0x88),
        1,
        "level1_sara_w_healpotion1_poison_cure_slow_cure.ss0",
    ),
    Pickup(
        "Health 2",
        (0x88, 0x89, 0x98, 0x96),
        1,
        "level1_sara_w_health2_health1_poision_cure_wild_card.ss0",
    ),
    Pickup(
        "Poison Cure",
        block(0x8A),
        3,
        "level1_sara_w_healpotion1_poison_cure_slow_cure.ss0",
    ),
    Pickup(
        "Slow Cure",
        block(0x8C),
        3,
        "level1_sara_w_healpotion1_poison_cure_slow_cure.ss0",
    ),
    Pickup(
        "Shield",
        block(0x84),
        4,
        "level1_sara_w_shield1_item.ss0",
    ),
    Pickup(
        "Spiral",
        block(0x8E),
        5,
        "level1_sara_spiral_powerup_item.ss0",
    ),
    Pickup(
        "Fat Arrow",
        block(0xA0),
        4,
        "level1_sara_w_fat_arrow_bidirectional_arrow_half_diagnol_arrow_wild_card_item.ss0",
    ),
    Pickup(
        "Bidirectional Arrow",
        block(0xA2),
        4,
        "level1_sara_w_fat_arrow_bidirectional_arrow_half_diagnol_arrow_wild_card_item.ss0",
    ),
    Pickup(
        "Half-Diagonal Arrow",
        block(0xA4),
        4,
        "level1_sara_w_fat_arrow_bidirectional_arrow_half_diagnol_arrow_wild_card_item.ss0",
    ),
    Pickup(
        "All-Diagonals Arrow",
        block(0xA6),
        4,
        "level1_sara_w_all_diagnol_arrow_item.ss0",
    ),
    Pickup(
        "Turbo",
        block(0xA8),
        5,
        "level1_sara_d_turbo_powerup_health1_item.ss0",
    ),
    Pickup(
        "Flash",
        block(0xAA),
        5,
        "level1_sara_w_flash_item.ss0",
    ),
    Pickup(
        "Teleport",
        block(0xAC),
        4,
        "level1_sara_w_teleport.ss0",
    ),
    Pickup(
        "Extra Life",
        block(0xAE),
        2,
        "level1_sara_w_extra_life_item.ss0",
    ),
    Pickup(
        "Wild Card",
        block(0xC6),
        2,
        "level1_sara_w_health2_health1_poision_cure_wild_card.ss0",
    ),
    Pickup(
        "Rock",
        block(0xC8),
        5,
        "level1_sara_w_rock_item.ss0",
    ),
    Pickup(
        "P Item",
        block(0xCA),
        2,
        "level1_sara_w_p_item.ss0",
    ),
    Pickup(
        "Orb",
        block(0xCC),
        2,
        "level1_cat_fish_moth_spike_hazard_orb_item.ss0",
    ),
    Pickup(
        "Dragon",
        block(0xCE),
        5,
        "level1_sara_w_dragon_powerup_item.ss0",
    ),
)

EXPECTED_TABLE = bytes(_bg_table())
EXPECTED_TABLE_HISTOGRAM = dict(sorted(Counter(EXPECTED_TABLE).items()))


def digest(path: Path, algorithm: str = "sha256") -> str:
    value = hashlib.new(algorithm)
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            value.update(chunk)
    return value.hexdigest()


def serialized_state(path: Path) -> bytes:
    data = path.read_bytes()
    if data[:8] != b"\x89PNG\r\n\x1a\n":
        raise RuntimeError(f"not an mGBA PNG savestate: {path}")
    position = 8
    while position + 12 <= len(data):
        size = struct.unpack(">I", data[position:position + 4])[0]
        kind = data[position + 4:position + 8]
        payload = data[position + 8:position + 8 + size]
        if len(payload) != size:
            break
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


def find_signature(
    tilemap: bytes,
    tiles: tuple[int, int, int, int],
) -> list[tuple[int, int]]:
    found = []
    for row in range(23):
        for column in range(23):
            offset = row * 32 + column
            actual = (
                tilemap[offset],
                tilemap[offset + 1],
                tilemap[offset + 32],
                tilemap[offset + 33],
            )
            if actual == tiles:
                found.append((column, row))
    return found


def decode_tile(vram: bytes, tile: int) -> list[int]:
    # Stage 1 uses LCDC's signed tile-data mode. Item IDs >= 0x80 therefore
    # map directly to VRAM offsets tile*16 in the $8800-$8FFF half.
    offset = tile * 16 if tile >= 0x80 else 0x1000 + tile * 16
    pixels = []
    for row in range(8):
        low, high = vram[offset + row * 2:offset + row * 2 + 2]
        for bit in range(7, -1, -1):
            pixels.append(((high >> bit) & 1) * 2 + ((low >> bit) & 1))
    return pixels


def bgr555_to_rgb(word: int) -> tuple[int, int, int]:
    red = (word & 0x1F) * 255 // 31
    green = ((word >> 5) & 0x1F) * 255 // 31
    blue = ((word >> 10) & 0x1F) * 255 // 31
    return red, green, blue


def palette_words(rom: bytes, palette: int) -> list[int]:
    start = BG_PALETTE_OFFSET + palette * 8
    data = rom[start:start + 8]
    return [
        data[index] | (data[index + 1] << 8)
        for index in range(0, 8, 2)
    ]


def render_pickup(
    vram: bytes,
    tiles: tuple[int, int, int, int],
    colors: list[tuple[int, int, int]],
) -> Image.Image:
    image = Image.new("RGB", (16, 16))
    for index, tile in enumerate(tiles):
        pixels = decode_tile(vram, tile)
        x0, y0 = (index % 2) * 8, (index // 2) * 8
        for y in range(8):
            for x in range(8):
                image.putpixel((x0 + x, y0 + y), colors[pixels[y * 8 + x]])
    return image


def create_contact_sheet(
    entries: list[dict],
    output: Path,
) -> None:
    scale = 5
    columns = 5
    cell_width, cell_height = 170, 126
    rows = (len(entries) + columns - 1) // columns
    sheet = Image.new("RGB", (columns * cell_width, rows * cell_height), "white")
    draw = ImageDraw.Draw(sheet)
    for index, entry in enumerate(entries):
        x = (index % columns) * cell_width
        y = (index // columns) * cell_height
        icon = entry.pop("_image").resize(
            (16 * scale, 16 * scale), Image.Resampling.NEAREST
        )
        sheet.paste(icon, (x + 6, y + 6))
        draw.text((x + 6, y + 91), entry["name"], fill="black")
        draw.text(
            (x + 6, y + 106),
            f"BG{entry['palette']}  {entry['tile_signature']}",
            fill="black",
        )
    sheet.save(output)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("rom", nargs="?", type=Path, default=DEFAULT_ROM)
    parser.add_argument("--states", type=Path, default=DEFAULT_STATES)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    rom_path = args.rom.resolve()
    states = args.states.resolve()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    rom = rom_path.read_bytes()
    if len(rom) < 0x40000 or len(rom) % 0x4000:
        raise SystemExit(
            f"FAIL: ROM is {len(rom)} bytes; expected at least 262144 "
            "and a whole number of 16 KiB banks"
        )

    table = rom[BG_TABLE_OFFSET:BG_TABLE_OFFSET + 256]
    table_histogram = dict(sorted(Counter(table).items()))
    expected_tiles: dict[int, int] = {}
    for pickup in PICKUPS:
        for tile in pickup.tiles:
            previous = expected_tiles.setdefault(tile, pickup.palette)
            if previous != pickup.palette:
                raise RuntimeError(
                    f"tile {tile:02X} assigned to both BG{previous} "
                    f"and BG{pickup.palette}"
                )

    checks = {
        "73 unique pickup tile IDs": len(expected_tiles) == 73,
        "complete Stage 1 table equals its YAML compilation": (
            table == EXPECTED_TABLE
        ),
        "exact Stage 1 table histogram": (
            table_histogram == EXPECTED_TABLE_HISTOGRAM
        ),
        "every pickup tile maps to its semantic class": all(
            table[tile] == palette
            for tile, palette in expected_tiles.items()
        ),
        "all five pickup palette classes are present": (
            set(expected_tiles.values()) == {1, 2, 3, 4, 5}
        ),
    }

    entries = []
    state_cache: dict[str, bytes] = {}
    missing_signatures = []
    for pickup in PICKUPS:
        path = states / pickup.state
        state = state_cache.setdefault(pickup.state, serialized_state(path))
        vram = state[VRAM_OFFSET:VRAM_OFFSET + VRAM_SIZE]
        locations = {}
        for map_name, map_offset in (("9800", 0x1800), ("9C00", 0x1C00)):
            positions = find_signature(
                vram[map_offset:map_offset + 0x400], pickup.tiles
            )
            locations[map_name] = [list(position) for position in positions]
        if not any(locations.values()):
            missing_signatures.append(pickup.name)
        words = palette_words(rom, pickup.palette)
        entries.append(
            {
                "name": pickup.name,
                "palette": pickup.palette,
                "tiles": list(pickup.tiles),
                "tile_signature": "/".join(
                    f"{tile:02X}" for tile in pickup.tiles
                ),
                "savestate": pickup.state,
                "locations": locations,
                "palette_words": [f"{word:04X}" for word in words],
                "_image": render_pickup(
                    vram,
                    pickup.tiles,
                    [bgr555_to_rgb(word) for word in words],
                ),
            }
        )

    checks["all 19 labeled signatures exist in savestate VRAM"] = (
        not missing_signatures and len(entries) == 19
    )
    pickup_rows = {
        palette: tuple(palette_words(rom, palette))
        for palette in range(1, 6)
    }
    checks["five class color rows are byte-distinct"] = (
        len(set(pickup_rows.values())) == 5
    )

    contact_sheet = output / "pickup-class-palettes.png"
    create_contact_sheet(entries, contact_sheet)
    failures = [name for name, passed in checks.items() if not passed]
    receipt = {
        "schema": "penta-dragon-dx-pickup-class-palettes-v1",
        "status": "pass" if not failures else "fail",
        "rom": str(rom_path),
        "rom_md5": digest(rom_path, "md5"),
        "rom_sha256": digest(rom_path),
        "stage1_table_histogram": {
            str(key): value for key, value in table_histogram.items()
        },
        "pickup_palette_rows": {
            str(key): [f"{word:04X}" for word in value]
            for key, value in pickup_rows.items()
        },
        "checks": checks,
        "missing_signatures": missing_signatures,
        "pickups": entries,
        "contact_sheet": contact_sheet.name,
        "contact_sheet_sha256": digest(contact_sheet),
        "failures": failures,
    }
    receipt_path = output / "receipt.json"
    receipt_path.write_text(json.dumps(receipt, indent=2) + "\n")
    for name, passed in checks.items():
        print(f"{'PASS' if passed else 'FAIL'}: {name}")
    print(f"Contact sheet: {contact_sheet}")
    print(f"Receipt: {receipt_path}")
    if failures:
        print("FAIL: " + "; ".join(failures))
        return 1
    print(
        "PASS: all 19 labeled pickup forms use five distinct semantic "
        "palette classes."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
