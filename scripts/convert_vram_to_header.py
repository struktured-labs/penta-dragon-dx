#!/usr/bin/env python3
"""Convert extracted VRAM binary dump to C header file and PNG preview.

Reads a raw VRAM dump (0x8000-0x87FF, 2048 bytes = 128 tiles) and extracts
specific tile ranges into C header arrays and PNG preview sheets.
"""

import struct
import sys
from pathlib import Path

try:
    from PIL import Image
except ImportError:
    Image = None


def vram_tile_to_pixels(tile_data: bytes) -> list[list[int]]:
    """Convert 16 bytes of Game Boy tile data to 8x8 pixel grid (0-3 values)."""
    pixels = []
    for row in range(8):
        lo = tile_data[row * 2]
        hi = tile_data[row * 2 + 1]
        row_pixels = []
        for bit in range(7, -1, -1):
            color = ((hi >> bit) & 1) << 1 | ((lo >> bit) & 1)
            row_pixels.append(color)
        pixels.append(row_pixels)
    return pixels


def render_tile_sheet(tiles: list[bytes], cols: int = 16, scale: int = 4) -> "Image.Image":
    """Render tiles as a PNG sheet."""
    if Image is None:
        return None

    num_tiles = len(tiles)
    rows = (num_tiles + cols - 1) // cols

    # GB palette: white, light gray, dark gray, black
    palette = [(255, 255, 255), (170, 170, 170), (85, 85, 85), (0, 0, 0)]

    width = cols * 8 * scale
    height = rows * 8 * scale
    img = Image.new("RGB", (width, height), (200, 200, 200))

    for idx, tile_data in enumerate(tiles):
        tx = (idx % cols) * 8 * scale
        ty = (idx // cols) * 8 * scale
        pixels = vram_tile_to_pixels(tile_data)

        for py in range(8):
            for px in range(8):
                color = palette[pixels[py][px]]
                for sy in range(scale):
                    for sx in range(scale):
                        img.putpixel((tx + px * scale + sx, ty + py * scale + sy), color)

    return img


def write_c_header(
    output_path: Path,
    array_name: str,
    tiles: list[bytes],
    tile_start_id: int,
    description: str,
) -> None:
    """Write tiles as a C header file."""
    total_bytes = len(tiles) * 16
    guard = array_name.upper() + "_H"

    with open(output_path, "w") as f:
        f.write(f"/**\n")
        f.write(f" * {description}\n")
        f.write(f" *\n")
        f.write(f" * Extracted from Penta Dragon VRAM during gameplay.\n")
        f.write(f" * Tile IDs 0x{tile_start_id:02X}-0x{tile_start_id + len(tiles) - 1:02X}\n")
        f.write(f" * {len(tiles)} tiles, {total_bytes} bytes (16 bytes per 8x8 tile)\n")
        f.write(f" *\n")
        f.write(f" * Game Boy tile format: 2 bytes per row, 8 rows per tile\n")
        f.write(f" *   byte0 = low bitplane, byte1 = high bitplane\n")
        f.write(f" *   pixel color = (hi_bit << 1) | lo_bit  (0-3)\n")
        f.write(f" */\n\n")
        f.write(f"#ifndef {guard}\n")
        f.write(f"#define {guard}\n\n")
        f.write(f"#include <stdint.h>\n\n")
        f.write(f"#define {array_name}_NUM_TILES {len(tiles)}\n")
        f.write(f"#define {array_name}_BYTES_PER_TILE 16\n")
        f.write(f"#define {array_name}_TOTAL_BYTES {total_bytes}\n")
        f.write(f"#define {array_name}_FIRST_TILE_ID 0x{tile_start_id:02X}\n\n")

        f.write(f"static const uint8_t {array_name}[{total_bytes}] = {{\n")

        for i, tile_data in enumerate(tiles):
            tile_id = tile_start_id + i
            f.write(f"    /* Tile 0x{tile_id:02X} (VRAM 0x{0x8000 + tile_id * 16:04X}) */\n")
            f.write("    ")
            for j, byte in enumerate(tile_data):
                f.write(f"0x{byte:02X}")
                if i < len(tiles) - 1 or j < 15:
                    f.write(",")
                if j == 7:
                    f.write("\n    ")
                elif j < 15:
                    f.write(" ")
            f.write("\n")
            if i < len(tiles) - 1:
                f.write("\n")

        f.write(f"}};\n\n")
        f.write(f"#endif /* {guard} */\n")


def main():
    project_dir = Path("/home/struktured/projects/penta-dragon-remake")
    vram_bin = project_dir / "tmp" / "extraction" / "vram_dragon_sprites.bin"
    header_dir = project_dir / "assets" / "extracted" / "sprites" / "include"
    preview_dir = project_dir / "tmp" / "extraction" / "screenshots"

    header_dir.mkdir(parents=True, exist_ok=True)
    preview_dir.mkdir(parents=True, exist_ok=True)

    if not vram_bin.exists():
        print(f"ERROR: VRAM dump not found: {vram_bin}")
        sys.exit(1)

    data = vram_bin.read_bytes()
    if len(data) != 2048:
        print(f"ERROR: Expected 2048 bytes, got {len(data)}")
        sys.exit(1)

    print(f"Read {len(data)} bytes from {vram_bin}")

    # Parse into 128 tiles of 16 bytes each
    all_tiles = [data[i * 16 : (i + 1) * 16] for i in range(128)]

    # === Sara Dragon character tiles (0x20-0x2F) ===
    sara_dragon_tiles = all_tiles[0x20:0x30]
    header_path = header_dir / "sprites_sara_dragon_real.h"
    write_c_header(
        header_path,
        "SPRITE_SARA_DRAGON_REAL",
        sara_dragon_tiles,
        0x20,
        "Sara Dragon form sprite tiles - extracted from live VRAM",
    )
    print(f"Wrote Sara Dragon header: {header_path} ({len(sara_dragon_tiles)} tiles, {len(sara_dragon_tiles)*16} bytes)")

    # Verify non-empty
    total_sum = sum(sum(t) for t in sara_dragon_tiles)
    print(f"  Data verification: total byte sum = {total_sum} ({'OK - has data' if total_sum > 0 else 'WARNING - all zeros!'})")
    for i, tile in enumerate(sara_dragon_tiles):
        tile_sum = sum(tile)
        tile_id = 0x20 + i
        status = "data" if tile_sum > 0 else "EMPTY"
        print(f"  Tile 0x{tile_id:02X}: sum={tile_sum:5d} [{status}]")

    # === Projectile/effect tiles (0x00-0x1F) ===
    projectile_tiles = all_tiles[0x00:0x20]
    proj_header_path = header_dir / "sprites_dragon_projectiles.h"
    write_c_header(
        proj_header_path,
        "SPRITE_DRAGON_PROJECTILES",
        projectile_tiles,
        0x00,
        "Projectile/effect tiles during Dragon form - may differ from Witch form",
    )
    print(f"\nWrote projectile header: {proj_header_path} ({len(projectile_tiles)} tiles, {len(projectile_tiles)*16} bytes)")

    # === PNG previews ===
    if Image is not None:
        # Sara Dragon tiles
        img = render_tile_sheet(sara_dragon_tiles, cols=16, scale=4)
        if img:
            png_path = preview_dir / "sara_dragon_tiles_0x20_0x2F.png"
            img.save(png_path)
            print(f"\nWrote tile preview: {png_path}")

        # Projectile tiles
        img2 = render_tile_sheet(projectile_tiles, cols=16, scale=4)
        if img2:
            png_path2 = preview_dir / "dragon_projectile_tiles_0x00_0x1F.png"
            img2.save(png_path2)
            print(f"Wrote projectile preview: {png_path2}")

        # Full VRAM dump
        img3 = render_tile_sheet(all_tiles, cols=16, scale=4)
        if img3:
            png_path3 = preview_dir / "full_vram_0x8000_0x87FF.png"
            img3.save(png_path3)
            print(f"Wrote full VRAM preview: {png_path3}")
    else:
        print("\nNote: PIL/Pillow not available, skipping PNG previews")

    print("\nDone!")


if __name__ == "__main__":
    main()
