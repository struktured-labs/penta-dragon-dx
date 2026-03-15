#!/usr/bin/env python3
"""Convert raw VRAM tile dumps to C headers for GBDK.

The game uses LCDC bit 4 = 0 (signed addressing):
  - Tile 0x00 = VRAM 0x9000
  - Tile 0x7F = VRAM 0x97F0
  - Tile 0x80 = VRAM 0x8800
  - Tile 0xFF = VRAM 0x8FF0

For GBDK's set_bkg_data(), we need tiles in unsigned order (0x00-0xFF)
where tile N data = 16 bytes at offset N*16.

During gameplay:
  - 0x9000-0x97FF contains tiles 0x00-0x7F (dungeon architecture)
  - 0x8800-0x8FFF contains tiles 0x80-0xFF (items, HUD, etc.)
"""

from pathlib import Path

PROJ = Path(__file__).parent.parent
TMP = PROJ / "tmp"
OUT = PROJ / "assets" / "extracted" / "bg" / "include"


def read_bin(path: Path) -> bytes:
    return path.read_bytes()


def tiles_to_c_header(data: bytes, name: str, tile_start: int, tile_count: int) -> str:
    lines = [
        f"#ifndef __{name.upper()}_H__",
        f"#define __{name.upper()}_H__",
        "",
        f"/* {name} - extracted from VRAM during gameplay */",
        f"/* Tiles 0x{tile_start:02X} - 0x{tile_start + tile_count - 1:02X} "
        f"({tile_count} tiles, {tile_count * 16} bytes) */",
        "",
        f"#define {name.upper()}_TILE_COUNT {tile_count}",
        f"#define {name.upper()}_TILE_START 0x{tile_start:02X}",
        "",
        f"const unsigned char {name.upper()}[] = {{",
    ]

    for tile_idx in range(tile_count):
        offset = tile_idx * 16
        tile_bytes = data[offset : offset + 16]
        hex_str = ", ".join(f"0x{b:02X}" for b in tile_bytes)
        lines.append(f"    /* Tile 0x{tile_start + tile_idx:02X} */ {hex_str},")

    lines.append("};")
    lines.append("")
    lines.append(f"#endif /* __{name.upper()}_H__ */")
    lines.append("")

    return "\n".join(lines)


def make_combined_header(tiles_lo: bytes, tiles_hi: bytes) -> str:
    """Combine tiles 0x00-0x7F (from 0x9000) and 0x80-0xFF (from 0x8800)
    into a single 256-tile array for set_bkg_data(0, 256, ...)."""

    # tiles_hi = VRAM 0x9000-0x97FF = tiles 0x00-0x7F (128 tiles)
    # tiles_lo = VRAM 0x8800-0x8FFF = tiles 0x80-0xFF (128 tiles)
    # Combined: tiles 0x00-0xFF in order

    combined = tiles_hi + tiles_lo  # 0x00-0x7F then 0x80-0xFF
    assert len(combined) == 4096, f"Expected 4096 bytes, got {len(combined)}"

    return tiles_to_c_header(combined, "BG_GAMEPLAY_TILES", 0x00, 256)


def make_dungeon_header(tiles_hi: bytes) -> str:
    """Just the dungeon architecture tiles (0x00-0x7F)."""
    return tiles_to_c_header(tiles_hi, "BG_DUNGEON_TILES", 0x00, 128)


def main():
    tiles_9000 = read_bin(TMP / "vram_tiles_9000.bin")  # tiles 0x00-0x7F
    tiles_8800 = read_bin(TMP / "vram_tiles_8800.bin")  # tiles 0x80-0xFF

    print(f"Read {len(tiles_9000)} bytes from vram_tiles_9000.bin (tiles 0x00-0x7F)")
    print(f"Read {len(tiles_8800)} bytes from vram_tiles_8800.bin (tiles 0x80-0xFF)")

    OUT.mkdir(parents=True, exist_ok=True)

    # Combined 256-tile header (replaces bg_all.h)
    combined = make_combined_header(tiles_8800, tiles_9000)
    out_path = OUT / "bg_gameplay.h"
    out_path.write_text(combined)
    print(f"Wrote {out_path} (256 tiles, 4096 bytes)")

    # Dungeon-only header (tiles 0x00-0x7F)
    dungeon = make_dungeon_header(tiles_9000)
    out_path2 = OUT / "bg_dungeon.h"
    out_path2.write_text(dungeon)
    print(f"Wrote {out_path2} (128 tiles, 2048 bytes)")

    # Also convert tilemap for reference
    tm_9c00 = read_bin(TMP / "vram_tilemap_9C00.bin")
    tm_header = "/* Gameplay tilemap dump (0x9C00, active during gameplay) */\n"
    tm_header += "/* 32x32 tile indices */\n\n"
    for row in range(32):
        offset = row * 32
        row_bytes = tm_9c00[offset : offset + 32]
        hex_row = " ".join(f"{b:02X}" for b in row_bytes)
        tm_header += f"/* Row {row:2d} */ {hex_row}\n"

    tm_path = OUT.parent / "tilemaps" / "gameplay_tilemap.txt"
    tm_path.parent.mkdir(parents=True, exist_ok=True)
    tm_path.write_text(tm_header)
    print(f"Wrote {tm_path}")

    # Preview: show non-empty tile count
    nonempty = sum(
        1
        for i in range(256)
        for off in [i * 16]
        if any(b != 0 for b in (tiles_9000 + tiles_8800)[off : off + 16])
    )
    print(f"\nNon-empty tiles: {nonempty}/256")


if __name__ == "__main__":
    main()
