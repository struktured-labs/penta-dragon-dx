#!/usr/bin/env python3
"""Install the complete current Ted material table in an expanded candidate."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

from arena_tables_data import TED_BODY_TILE_PAL, TED_FLOOR_TILE_PAL


BANK_SIZE = 0x4000
TED_TABLE_ADDR = 0x7600
TABLE_SIZE = 0x87


def header_checksum(rom: bytes) -> int:
    value = 0
    for byte in rom[0x0134:0x014D]:
        value = (value - byte - 1) & 0xFF
    return value


def global_checksum(rom: bytes) -> int:
    return (sum(rom) - rom[0x014E] - rom[0x014F]) & 0xFFFF


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    rom = bytearray(args.source.read_bytes())
    if len(rom) != 0x80000:
        parser.error(f"expected 512 KiB expanded candidate, got {len(rom)} bytes")
    palette_map = TED_BODY_TILE_PAL | TED_FLOOR_TILE_PAL
    for bank in (13, 16):
        table = bank * BANK_SIZE + TED_TABLE_ADDR - 0x4000
        values = bytes(palette_map.get(tile, 0) for tile in range(TABLE_SIZE))
        rom[table:table + TABLE_SIZE] = values
    rom[0x014D] = header_checksum(rom)
    checksum = global_checksum(rom)
    rom[0x014E:0x0150] = checksum.to_bytes(2, "big")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(rom)
    print(args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
