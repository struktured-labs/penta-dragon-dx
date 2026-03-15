#!/usr/bin/env python3
"""
Penta Dragon Asset Extractor
=============================

Extracts tile and sprite graphics from the original Penta Dragon (J) ROM
by dumping VRAM from multiple save states using a headless mGBA emulator.

Outputs:
  - Raw .bin files (GB native 2bpp format, GBDK-compatible)
  - PNG preview images (per-tile, sprite sheets, full tileset previews)
  - C header files with tile data as const arrays (GBDK format)
  - Tilemap data (.bin and .h)

Usage:
    uv run python scripts/extract_assets.py
"""

import os
import subprocess
import sys
from pathlib import Path

import numpy as np
from PIL import Image

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

PROJECT_ROOT = Path(__file__).resolve().parent.parent
ORIGINAL_ROM = Path(
    os.environ.get(
        "PENTA_ROM",
        str(
            Path.home()
            / "projects"
            / "penta-dragon-dx-claude"
            / "rom"
            / "Penta Dragon (J).gb"
        ),
    )
)
SAVE_STATE_DIR = PROJECT_ROOT / "save_states_for_claude"
OUTPUT_DIR = PROJECT_ROOT / "assets" / "extracted"
TMP_DIR = PROJECT_ROOT / "tmp"

# GB 2bpp grayscale palette (lightest to darkest)
DMG_PALETTE = [
    (224, 248, 208),  # Color 0 - lightest
    (136, 192, 112),  # Color 1
    (52, 104, 86),    # Color 2
    (8, 24, 32),      # Color 3 - darkest
]

# Sprite tile ranges (loaded into VRAM 0x8000-0x87FF, tiles 0x00-0x7F)
SPRITE_TILE_RANGES = {
    "effects_projectiles": (0x00, 0x1F, "Effects & Projectiles"),
    "sara_witch": (0x20, 0x27, "Sara Witch"),
    "sara_dragon": (0x28, 0x2F, "Sara Dragon"),
    "crows": (0x30, 0x3F, "Crows"),
    "hornets": (0x40, 0x4F, "Hornets"),
    "orcs": (0x50, 0x5F, "Orcs"),
    "humanoids": (0x60, 0x6F, "Humanoids (soldier/moth/mage)"),
    "special_catfish": (0x70, 0x7F, "Special (catfish)"),
}

# BG tile ranges (loaded into VRAM 0x8800-0x97FF, tiles 0x00-0xFF via signed addressing)
BG_TILE_RANGES = {
    "floor_edges": (0x00, 0x3F, "Floor/edges/platforms"),
    "wall_fill": (0x40, 0x5F, "Wall fill"),
    "arches_doorways": (0x60, 0x87, "Arches/doorways"),
    "items": (0x88, 0xDF, "Items"),
    "decorative": (0xE0, 0xFD, "Decorative"),
    "void": (0xFE, 0xFF, "Void"),
}

# Save states to use for extraction (different states have different tiles loaded)
EXTRACT_STATES = [
    "level1_sara_w_4_hornets.ss0",
    "level1_sara_w_gargoyle_mini_boss.ss0",
    "level1_sara_w_crow.ss0",
    "level1_sara_w_orc.ss0",
    "level1_sara_w_moth.ss0",
    "level1_sara_w_soldier.ss0",
    "level1_sara_d_alone.ss0",
    "level1_sara_d_spider_miniboss.ss0",
    "level1_sara_w_spier_miniboss.ss0",
    "level1_cat_fish_moth_spike_hazard_orb_item.ss0",
    "level1_sara_w_in_jet_form_secret_stage.ss0",
    "level1_sara_w_flash_item.ss0",
    "level1_sara_w_dragon_powerup_item.ss0",
    "level1_sara_w_spiral_power_active.ss0",
    "level1_sara_w_alone.ss0",
]


# ---------------------------------------------------------------------------
# VRAM dumping via headless mGBA + Lua
# ---------------------------------------------------------------------------


def create_vram_dump_lua(output_path: Path, done_path: Path, wait_frames: int = 60) -> str:
    """Create a Lua script that dumps all VRAM tile data, tilemaps, and OAM.

    Waits `wait_frames` frames after state load so the game has time to
    decompress and load tile data into VRAM.

    Output format (8352 bytes total):
      - 0x0000-0x1FFF: VRAM 0x8000-0x9FFF (8192 bytes: tiles + tilemaps)
      - 0x2000-0x209F: OAM 0xFE00-0xFE9F (160 bytes: 40 sprites x 4)
    """
    return f"""\
-- Fast VRAM dumper for Penta Dragon asset extraction
local frame_count = 0
local WAIT = {wait_frames}

callbacks:add("frame", function()
    frame_count = frame_count + 1
    if frame_count == WAIT then
        local f = io.open("{output_path}", "wb")
        if not f then emu:quit(); return end

        -- Batch reads into a table then concat (much faster than per-byte write)
        local chunks = {{}}
        for addr = 0x8000, 0x9FFF do
            chunks[#chunks + 1] = string.char(emu:read8(addr))
        end
        f:write(table.concat(chunks))

        chunks = {{}}
        for addr = 0xFE00, 0xFE9F do
            chunks[#chunks + 1] = string.char(emu:read8(addr))
        end
        f:write(table.concat(chunks))

        f:close()

        local done = io.open("{done_path}", "w")
        if done then done:write("OK"); done:close() end
        emu:quit()
    end
end)
"""


def dump_vram_from_state(rom_path: Path, state_path: Path, output_path: Path) -> bool:
    """Run headless mGBA with a Lua script to dump VRAM from a save state."""
    done_path = output_path.with_suffix(".done")
    lua_path = TMP_DIR / "vram_dump.lua"
    lua_path.write_text(create_vram_dump_lua(output_path, done_path, wait_frames=60))

    # Clean previous artifacts
    for f in [output_path, done_path]:
        if f.exists():
            f.unlink()

    env = os.environ.copy()
    env.pop("DISPLAY", None)
    env.pop("WAYLAND_DISPLAY", None)
    env["QT_QPA_PLATFORM"] = "offscreen"
    env["SDL_AUDIODRIVER"] = "dummy"

    cmd = [
        "xvfb-run", "-a",
        "mgba-qt",
        str(rom_path),
        "-t", str(state_path),
        "--script", str(lua_path),
        "-l", "0",
    ]

    try:
        proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, env=env)
        try:
            proc.wait(timeout=20)
        except subprocess.TimeoutExpired:
            # mGBA often hangs after emu:quit() -- kill it
            proc.kill()
            proc.wait()
        # Check results regardless of how process ended
        if done_path.exists():
            done_path.unlink()
        return output_path.exists() and output_path.stat().st_size >= 8192
    except Exception as e:
        print(f"  ERROR: {e}")
        return False


def create_autoplay_sprite_dump_lua(output_path: Path, done_path: Path) -> str:
    """Create a Lua script that auto-plays into gameplay to capture all sprite tiles.

    The game dynamically loads sprite tiles into VRAM 0x8000-0x87FF. During
    gameplay, the full set of 128 tiles is populated (projectiles, Sara,
    enemies, etc.). This script navigates the title screen, enters gameplay,
    and dumps sprite VRAM once the tile set stabilizes.

    Output format (2208 bytes):
      - 0x0000-0x07FF: VRAM 0x8000-0x87FF (2048 bytes: 128 sprite tiles)
      - 0x0800-0x089F: OAM 0xFE00-0xFE9F (160 bytes)
    """
    return f"""\
-- Auto-play sprite dumper: navigates to gameplay, dumps when tiles loaded
local frame_count = 0
local best_count = 0
local best_data = nil

local function count_tiles()
    local n = 0
    for i = 0, 127 do
        local addr = 0x8000 + i * 16
        local sum = 0
        for j = 0, 15 do sum = sum + emu:read8(addr + j) end
        if sum > 0 then n = n + 1 end
    end
    return n
end

local function do_dump()
    local f = io.open("{output_path}", "wb")
    if not f then return end
    local chunks = {{}}
    for addr = 0x8000, 0x87FF do
        chunks[#chunks + 1] = string.char(emu:read8(addr))
    end
    f:write(table.concat(chunks))
    chunks = {{}}
    for addr = 0xFE00, 0xFE9F do
        chunks[#chunks + 1] = string.char(emu:read8(addr))
    end
    f:write(table.concat(chunks))
    f:close()
    local done = io.open("{done_path}", "w")
    if done then done:write("OK"); done:close() end
end

callbacks:add("frame", function()
    frame_count = frame_count + 1

    -- Title / menu navigation (multiple START + DOWN + A presses)
    if frame_count == 30 then emu:addKey(3) end
    if frame_count == 32 then emu:clearKey(3) end
    if frame_count == 90 then emu:addKey(3) end
    if frame_count == 92 then emu:clearKey(3) end
    if frame_count == 150 then emu:addKey(7) end
    if frame_count == 152 then emu:clearKey(7) end
    if frame_count == 180 then emu:addKey(3) end
    if frame_count == 182 then emu:clearKey(3) end
    if frame_count == 240 then emu:addKey(3) end
    if frame_count == 242 then emu:clearKey(3) end
    if frame_count == 300 then emu:addKey(0) end
    if frame_count == 302 then emu:clearKey(0) end
    if frame_count == 360 then emu:addKey(3) end
    if frame_count == 362 then emu:clearKey(3) end
    if frame_count == 420 then emu:addKey(0) end
    if frame_count == 422 then emu:clearKey(0) end
    if frame_count == 480 then emu:addKey(3) end
    if frame_count == 482 then emu:clearKey(3) end
    if frame_count == 540 then emu:addKey(3) end
    if frame_count == 542 then emu:clearKey(3) end
    if frame_count == 600 then emu:addKey(0) end
    if frame_count == 602 then emu:clearKey(0) end
    if frame_count == 660 then emu:addKey(3) end
    if frame_count == 662 then emu:clearKey(3) end

    -- In-gameplay movement (move right, attack, jump)
    if frame_count > 700 then
        if frame_count % 8 < 6 then emu:addKey(4) else emu:clearKey(4) end
        if frame_count % 20 == 0 then emu:addKey(0) end
        if frame_count % 20 == 2 then emu:clearKey(0) end
        if frame_count % 60 == 0 then emu:addKey(1) end
        if frame_count % 60 == 2 then emu:clearKey(1) end
    end

    -- Check tile count every 60 frames and dump when we have many tiles
    if frame_count > 200 and frame_count % 60 == 0 then
        local n = count_tiles()
        if n > best_count then
            best_count = n
            do_dump()  -- Save best snapshot so far
        end
    end

    -- Quit after 6000 frames (~100 sec)
    if frame_count >= 6000 then
        do_dump()
        emu:quit()
    end
end)
"""


def dump_sprites_via_autoplay(rom_path: Path, output_path: Path) -> bool:
    """Run the game into gameplay to capture all sprite tiles.

    The game dynamically loads sprite tiles into VRAM during gameplay.
    This function navigates the title screen, enters a game, and captures
    the sprite tileset once it stabilizes (~6000 frames / 100 seconds).
    """
    done_path = output_path.with_suffix(".done")
    lua_path = TMP_DIR / "autoplay_sprite_dump.lua"
    lua_path.write_text(create_autoplay_sprite_dump_lua(output_path, done_path))

    for f in [output_path, done_path]:
        if f.exists():
            f.unlink()

    env = os.environ.copy()
    env.pop("DISPLAY", None)
    env.pop("WAYLAND_DISPLAY", None)
    env["QT_QPA_PLATFORM"] = "offscreen"
    env["SDL_AUDIODRIVER"] = "dummy"

    cmd = [
        "xvfb-run", "-a",
        "mgba-qt",
        str(rom_path),
        "--script", str(lua_path),
        "-l", "0",
    ]

    try:
        proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, env=env)
        try:
            proc.wait(timeout=180)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()
        if done_path.exists():
            done_path.unlink()
        return output_path.exists() and output_path.stat().st_size >= 2048
    except Exception as e:
        print(f"  ERROR: {e}")
        return False


def parse_autoplay_sprite_dump(dump_path: Path) -> dict[int, bytes]:
    """Parse the autoplay sprite dump into a tile dictionary.

    The dump contains VRAM 0x8000-0x87FF (2048 bytes, 128 tiles x 16 bytes).
    """
    data = dump_path.read_bytes()
    if len(data) < 2048:
        return {}
    sprite_tiles = {}
    for i in range(128):
        tdata = data[i * 16 : (i + 1) * 16]
        if not is_tile_empty(tdata):
            sprite_tiles[i] = tdata
    return sprite_tiles


# ---------------------------------------------------------------------------
# Tile parsing & rendering
# ---------------------------------------------------------------------------


def decode_2bpp_tile(data: bytes) -> np.ndarray:
    """Decode a single 8x8 GB 2bpp tile (16 bytes) into a pixel array.

    Returns an 8x8 numpy array with values 0-3 (palette indices).
    """
    assert len(data) == 16, f"Expected 16 bytes, got {len(data)}"
    pixels = np.zeros((8, 8), dtype=np.uint8)
    for row in range(8):
        lo = data[row * 2]
        hi = data[row * 2 + 1]
        for col in range(8):
            bit = 7 - col
            pixel = ((hi >> bit) & 1) << 1 | ((lo >> bit) & 1)
            pixels[row, col] = pixel
    return pixels


def tile_to_image(tile_pixels: np.ndarray, palette=None, scale: int = 1) -> Image.Image:
    """Convert an 8x8 tile pixel array to a PIL Image."""
    if palette is None:
        palette = DMG_PALETTE
    img = Image.new("RGB", (8, 8))
    for y in range(8):
        for x in range(8):
            img.putpixel((x, y), palette[tile_pixels[y, x]])
    if scale > 1:
        img = img.resize((8 * scale, 8 * scale), Image.NEAREST)
    return img


def is_tile_empty(tile_data: bytes) -> bool:
    """Check if a tile is all zeros (empty/blank)."""
    return all(b == 0 for b in tile_data)


def is_tile_solid(tile_data: bytes) -> bool:
    """Check if every byte pair is identical (1bpp effectively - no shading)."""
    for i in range(0, 16, 2):
        if tile_data[i] != tile_data[i + 1]:
            return False
    return True


def make_tilesheet(
    tiles: dict[int, bytes],
    cols: int = 16,
    scale: int = 4,
    palette=None,
    label: str = "",
) -> Image.Image:
    """Create a sprite/tile sheet image from a dict of tile_id -> tile_data."""
    if not tiles:
        return Image.new("RGB", (1, 1))

    max_id = max(tiles.keys())
    total = max_id + 1
    rows = (total + cols - 1) // cols

    tile_px = 8 * scale
    margin = 1 if scale >= 2 else 0
    cell = tile_px + margin

    width = cols * cell + margin
    height = rows * cell + margin

    # Dark gray background to distinguish empty tiles
    img = Image.new("RGB", (width, height), (40, 40, 40))

    for tile_id, tile_data in tiles.items():
        r = tile_id // cols
        c = tile_id % cols
        x = c * cell + margin
        y = r * cell + margin
        pixels = decode_2bpp_tile(tile_data)
        tile_img = tile_to_image(pixels, palette=palette, scale=scale)
        img.paste(tile_img, (x, y))

    return img


# ---------------------------------------------------------------------------
# Output generation
# ---------------------------------------------------------------------------


def write_raw_bin(tiles: dict[int, bytes], output_path: Path, start_id: int, end_id: int):
    """Write contiguous tile data as raw binary (2bpp, GBDK-compatible)."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "wb") as f:
        for tile_id in range(start_id, end_id + 1):
            if tile_id in tiles:
                f.write(tiles[tile_id])
            else:
                f.write(b"\x00" * 16)


def write_c_header(
    tiles: dict[int, bytes],
    output_path: Path,
    start_id: int,
    end_id: int,
    array_name: str,
    description: str,
):
    """Write tile data as a C header file with const arrays (GBDK format)."""
    output_path.parent.mkdir(parents=True, exist_ok=True)

    guard = f"__{array_name.upper()}_H__"
    lines = [
        f"#ifndef {guard}",
        f"#define {guard}",
        "",
        f"/* {description} */",
        f"/* Tiles 0x{start_id:02X} - 0x{end_id:02X} ({end_id - start_id + 1} tiles, {(end_id - start_id + 1) * 16} bytes) */",
        f"/* Extracted from Penta Dragon (J) VRAM */",
        "",
        f"#define {array_name}_TILE_COUNT {end_id - start_id + 1}",
        f"#define {array_name}_TILE_START 0x{start_id:02X}",
        "",
        f"const unsigned char {array_name}[] = {{",
    ]

    for tile_id in range(start_id, end_id + 1):
        data = tiles.get(tile_id, b"\x00" * 16)
        hex_bytes = ", ".join(f"0x{b:02X}" for b in data)
        lines.append(f"    /* Tile 0x{tile_id:02X} */ {hex_bytes},")

    lines.append("};")
    lines.append("")
    lines.append(f"#endif /* {guard} */")
    lines.append("")

    output_path.write_text("\n".join(lines))


def write_tilemap_bin(tilemap_data: bytes, output_path: Path):
    """Write raw tilemap data (1024 bytes = 32x32)."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(tilemap_data)


def write_tilemap_header(
    tilemap_data: bytes, output_path: Path, name: str, description: str
):
    """Write tilemap as C header."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    guard = f"__{name.upper()}_H__"
    lines = [
        f"#ifndef {guard}",
        f"#define {guard}",
        "",
        f"/* {description} */",
        f"/* 32x32 tile indices (1024 bytes) */",
        "",
        f"#define {name}_WIDTH 32",
        f"#define {name}_HEIGHT 32",
        "",
        f"const unsigned char {name}[] = {{",
    ]

    for row in range(32):
        offset = row * 32
        row_data = tilemap_data[offset : offset + 32]
        hex_bytes = ", ".join(f"0x{b:02X}" for b in row_data)
        lines.append(f"    /* Row {row:2d} */ {hex_bytes},")

    lines.append("};")
    lines.append("")
    lines.append(f"#endif /* {guard} */")
    lines.append("")

    output_path.write_text("\n".join(lines))


def write_oam_header(oam_data: bytes, output_path: Path):
    """Write OAM sprite data as C header for reference."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    guard = "__OAM_SNAPSHOT_H__"
    lines = [
        f"#ifndef {guard}",
        f"#define {guard}",
        "",
        "/* OAM Sprite Data Snapshot */",
        "/* 40 sprites x 4 bytes (Y, X, Tile, Flags) */",
        "",
        "typedef struct {",
        "    unsigned char y;",
        "    unsigned char x;",
        "    unsigned char tile;",
        "    unsigned char flags;",
        "} OAMEntry;",
        "",
    ]

    active = []
    for i in range(40):
        y = oam_data[i * 4]
        x = oam_data[i * 4 + 1]
        tile = oam_data[i * 4 + 2]
        flags = oam_data[i * 4 + 3]
        if y > 0 and y < 160:
            active.append((i, y, x, tile, flags))

    lines.append(f"/* {len(active)} active sprites in this snapshot */")
    lines.append("/*")
    for idx, y, x, tile, flags in active:
        pal = flags & 0x07
        xflip = "X" if flags & 0x20 else " "
        yflip = "Y" if flags & 0x40 else " "
        pri = "B" if flags & 0x80 else " "
        lines.append(
            f"   Sprite {idx:2d}: Y={y:3d} X={x:3d} Tile=0x{tile:02X} "
            f"Pal={pal} {xflip}{yflip}{pri}"
        )
    lines.append("*/")
    lines.append("")
    lines.append(f"#endif /* {guard} */")
    lines.append("")

    output_path.write_text("\n".join(lines))


# ---------------------------------------------------------------------------
# Main extraction pipeline
# ---------------------------------------------------------------------------


def merge_tile_dicts(base: dict[int, bytes], new: dict[int, bytes]) -> dict[int, bytes]:
    """Merge tile dictionaries, preferring non-empty tiles."""
    result = dict(base)
    for tile_id, data in new.items():
        if tile_id not in result or is_tile_empty(result[tile_id]):
            if not is_tile_empty(data):
                result[tile_id] = data
    return result


def parse_vram_dump(dump_path: Path) -> tuple[dict, dict, bytes, bytes, bytes]:
    """Parse a VRAM dump file into sprite tiles, BG tiles, tilemaps, and OAM.

    Dump format (8352 bytes):
      - 0x0000-0x1FFF: VRAM 0x8000-0x9FFF (8192 bytes)
      - 0x2000-0x209F: OAM 0xFE00-0xFE9F (160 bytes)

    Returns: (sprite_tiles, bg_tiles, tilemap0, tilemap1, oam_data)
    """
    data = dump_path.read_bytes()
    if len(data) < 8192:
        print(f"  WARN: dump too small ({len(data)} bytes), expected >= 8352")
        return {}, {}, b"", b"", b""

    # VRAM layout within the dump (offsets from start of file):
    #   0x0000-0x07FF: VRAM 0x8000-0x87FF (sprite tile data, 128 tiles)
    #   0x0800-0x0FFF: VRAM 0x8800-0x8FFF (shared tile block)
    #   0x1000-0x17FF: VRAM 0x9000-0x97FF (BG tile data)
    #   0x1800-0x1BFF: VRAM 0x9800-0x9BFF (tilemap 0)
    #   0x1C00-0x1FFF: VRAM 0x9C00-0x9FFF (tilemap 1)

    # Sprite tiles: VRAM 0x8000-0x87FF (128 tiles x 16 bytes = 2048 bytes)
    sprite_tiles = {}
    for i in range(128):
        offset = i * 16
        tdata = data[offset : offset + 16]
        if not is_tile_empty(tdata):
            sprite_tiles[i] = tdata

    # BG tiles: use signed addressing mode (0x8800 method)
    #   Tile IDs 0x00-0x7F -> VRAM 0x9000-0x97FF (dump offset 0x1000)
    #   Tile IDs 0x80-0xFF -> VRAM 0x8800-0x8FFF (dump offset 0x0800)
    bg_tiles = {}
    for i in range(256):
        if i < 128:
            vram_offset = 0x1000 + i * 16  # VRAM 0x9000 + i*16
        else:
            vram_offset = 0x0800 + (i - 128) * 16  # VRAM 0x8800 + (i-128)*16
        tdata = data[vram_offset : vram_offset + 16]
        if not is_tile_empty(tdata):
            bg_tiles[i] = tdata

    # Tilemaps: tilemap 0 at VRAM 0x9800 (dump offset 0x1800), 1024 bytes
    tilemap0 = data[0x1800 : 0x1800 + 1024]
    # tilemap 1 at VRAM 0x9C00 (dump offset 0x1C00), 1024 bytes
    tilemap1 = data[0x1C00 : 0x1C00 + 1024]

    # OAM: after VRAM data, at dump offset 0x2000 (8192), 160 bytes
    oam_data = b""
    if len(data) >= 8352:
        oam_data = data[0x2000 : 0x2000 + 160]

    return sprite_tiles, bg_tiles, tilemap0, tilemap1, oam_data


def run_extraction():
    """Main extraction pipeline."""
    print("=" * 60)
    print("Penta Dragon Asset Extractor")
    print("=" * 60)

    # Validate ROM
    if not ORIGINAL_ROM.exists():
        print(f"ERROR: ROM not found at {ORIGINAL_ROM}")
        print("Set PENTA_ROM env var or place ROM at expected location.")
        sys.exit(1)
    print(f"ROM: {ORIGINAL_ROM}")
    print(f"ROM size: {ORIGINAL_ROM.stat().st_size} bytes")

    # Create output directories
    for d in [OUTPUT_DIR, TMP_DIR]:
        d.mkdir(parents=True, exist_ok=True)

    dirs = {
        "sprites_bin": OUTPUT_DIR / "sprites" / "bin",
        "sprites_png": OUTPUT_DIR / "sprites" / "png",
        "sprites_h": OUTPUT_DIR / "sprites" / "include",
        "bg_bin": OUTPUT_DIR / "bg" / "bin",
        "bg_png": OUTPUT_DIR / "bg" / "png",
        "bg_h": OUTPUT_DIR / "bg" / "include",
        "tilemaps_bin": OUTPUT_DIR / "tilemaps" / "bin",
        "tilemaps_h": OUTPUT_DIR / "tilemaps" / "include",
        "tilemaps_png": OUTPUT_DIR / "tilemaps" / "png",
        "sheets": OUTPUT_DIR / "sheets",
    }
    for d in dirs.values():
        d.mkdir(parents=True, exist_ok=True)

    # ---------------------------------------------------------------
    # Phase 1a: Dump BG tiles from save states
    # ---------------------------------------------------------------
    print("\n--- Phase 1a: Dumping BG tiles from save states ---")
    print("(Save states load BG tiles from DX ROM; sprite tiles need autoplay)")

    all_sprite_tiles: dict[int, bytes] = {}
    all_bg_tiles: dict[int, bytes] = {}
    best_tilemap0 = b"\x00" * 1024
    best_tilemap1 = b"\x00" * 1024
    best_oam = b"\x00" * 160
    best_oam_count = 0

    available_states = [
        s for s in EXTRACT_STATES if (SAVE_STATE_DIR / s).exists()
    ]

    # Use just one save state for BG tiles (they're all the same for level 1)
    state_dumps: dict[str, Path] = {}
    if available_states:
        state_name = available_states[0]
        state_path = SAVE_STATE_DIR / state_name
        dump_path = TMP_DIR / f"vram_{state_name}.bin"
        print(f"  Dumping BG tiles from {state_name}...", end=" ", flush=True)

        if dump_vram_from_state(ORIGINAL_ROM, state_path, dump_path):
            if dump_path.exists() and dump_path.stat().st_size >= 8192:
                state_dumps[state_name] = dump_path
                sprite_tiles, bg_tiles, tm0, tm1, oam = parse_vram_dump(dump_path)
                all_bg_tiles = merge_tile_dicts(all_bg_tiles, bg_tiles)

                tm0_count = sum(1 for b in tm0 if b != 0) if tm0 else 0
                tm1_count = sum(1 for b in tm1 if b != 0) if tm1 else 0
                if tm0_count > sum(1 for b in best_tilemap0 if b != 0):
                    best_tilemap0 = tm0
                if tm1_count > sum(1 for b in best_tilemap1 if b != 0):
                    best_tilemap1 = tm1

                print(f"OK ({len(bg_tiles)} BG tiles)")
            else:
                print("WARN: dump too small")
        else:
            print("FAILED")
    else:
        print("  No save states found, skipping BG tile dump from states.")

    # ---------------------------------------------------------------
    # Phase 1b: Dump ALL sprite tiles via autoplay
    # ---------------------------------------------------------------
    print("\n--- Phase 1b: Dumping sprite tiles via autoplay ---")
    print("  Running game through opening sequence (~50 sec)...")

    autoplay_dump = TMP_DIR / "autoplay_sprites.bin"
    if dump_sprites_via_autoplay(ORIGINAL_ROM, autoplay_dump):
        autoplay_sprites = parse_autoplay_sprite_dump(autoplay_dump)
        all_sprite_tiles = merge_tile_dicts(all_sprite_tiles, autoplay_sprites)
        print(f"  OK: {len(autoplay_sprites)} sprite tiles captured via autoplay")
    else:
        print("  WARN: Autoplay sprite dump failed, using save state data only")

    print(f"\nTotal unique tiles: {len(all_sprite_tiles)} sprite, {len(all_bg_tiles)} BG")

    # ---------------------------------------------------------------
    # Phase 2: Export sprite tiles
    # ---------------------------------------------------------------
    print("\n--- Phase 2: Exporting sprite tiles ---")

    # Full sprite tileset
    write_raw_bin(all_sprite_tiles, dirs["sprites_bin"] / "sprites_all.bin", 0, 0x7F)
    write_c_header(
        all_sprite_tiles,
        dirs["sprites_h"] / "sprites_all.h",
        0,
        0x7F,
        "SPRITE_TILES",
        "All sprite tiles (0x00-0x7F)",
    )

    # Sprite sheet preview
    sheet = make_tilesheet(all_sprite_tiles, cols=16, scale=4, label="All Sprites")
    sheet.save(dirs["sheets"] / "sprites_all.png")
    print(f"  Sprite sheet: {dirs['sheets'] / 'sprites_all.png'}")

    # Per-range exports
    for range_name, (start, end, desc) in SPRITE_TILE_RANGES.items():
        range_tiles = {
            tid: data
            for tid, data in all_sprite_tiles.items()
            if start <= tid <= end
        }
        non_empty = len(range_tiles)

        # Raw binary
        write_raw_bin(
            all_sprite_tiles,
            dirs["sprites_bin"] / f"sprites_{range_name}.bin",
            start,
            end,
        )

        # C header
        arr_name = f"SPRITE_{range_name.upper()}"
        write_c_header(
            all_sprite_tiles,
            dirs["sprites_h"] / f"sprites_{range_name}.h",
            start,
            end,
            arr_name,
            desc,
        )

        # PNG sheet for this range
        if range_tiles:
            # Remap to 0-based for the sheet
            remapped = {tid - start: data for tid, data in range_tiles.items()}
            range_sheet = make_tilesheet(remapped, cols=8, scale=6)
            range_sheet.save(dirs["sprites_png"] / f"sprites_{range_name}.png")

        # Individual tile PNGs
        for tid in range(start, end + 1):
            if tid in all_sprite_tiles:
                pixels = decode_2bpp_tile(all_sprite_tiles[tid])
                img = tile_to_image(pixels, scale=8)
                img.save(dirs["sprites_png"] / f"sprite_0x{tid:02X}.png")

        print(f"  {range_name}: {non_empty}/{end - start + 1} tiles ({desc})")

    # ---------------------------------------------------------------
    # Phase 3: Export BG tiles
    # ---------------------------------------------------------------
    print("\n--- Phase 3: Exporting BG tiles ---")

    # Full BG tileset
    write_raw_bin(all_bg_tiles, dirs["bg_bin"] / "bg_all.bin", 0, 0xFF)
    write_c_header(
        all_bg_tiles,
        dirs["bg_h"] / "bg_all.h",
        0,
        0xFF,
        "BG_TILES",
        "All BG tiles (0x00-0xFF)",
    )

    # BG sheet preview
    bg_sheet = make_tilesheet(all_bg_tiles, cols=16, scale=4, label="All BG Tiles")
    bg_sheet.save(dirs["sheets"] / "bg_all.png")
    print(f"  BG tile sheet: {dirs['sheets'] / 'bg_all.png'}")

    # Per-range exports
    for range_name, (start, end, desc) in BG_TILE_RANGES.items():
        range_tiles = {
            tid: data for tid, data in all_bg_tiles.items() if start <= tid <= end
        }
        non_empty = len(range_tiles)

        write_raw_bin(
            all_bg_tiles,
            dirs["bg_bin"] / f"bg_{range_name}.bin",
            start,
            end,
        )

        arr_name = f"BG_{range_name.upper()}"
        write_c_header(
            all_bg_tiles,
            dirs["bg_h"] / f"bg_{range_name}.h",
            start,
            end,
            arr_name,
            desc,
        )

        if range_tiles:
            remapped = {tid - start: data for tid, data in range_tiles.items()}
            range_sheet = make_tilesheet(remapped, cols=16, scale=4)
            range_sheet.save(dirs["bg_png"] / f"bg_{range_name}.png")

        for tid in range(start, end + 1):
            if tid in all_bg_tiles:
                pixels = decode_2bpp_tile(all_bg_tiles[tid])
                img = tile_to_image(pixels, scale=8)
                img.save(dirs["bg_png"] / f"bg_0x{tid:02X}.png")

        print(f"  {range_name}: {non_empty}/{end - start + 1} tiles ({desc})")

    # ---------------------------------------------------------------
    # Phase 4: Export tilemaps
    # ---------------------------------------------------------------
    print("\n--- Phase 4: Exporting tilemaps ---")

    write_tilemap_bin(best_tilemap0, dirs["tilemaps_bin"] / "tilemap0.bin")
    write_tilemap_header(
        best_tilemap0,
        dirs["tilemaps_h"] / "tilemap0.h",
        "TILEMAP_0",
        "BG tilemap at 0x9800 (best snapshot)",
    )

    write_tilemap_bin(best_tilemap1, dirs["tilemaps_bin"] / "tilemap1.bin")
    write_tilemap_header(
        best_tilemap1,
        dirs["tilemaps_h"] / "tilemap1.h",
        "TILEMAP_1",
        "BG tilemap at 0x9C00 (best snapshot)",
    )

    # Tilemap visualization
    for tm_idx, (tm_data, tm_name) in enumerate(
        [(best_tilemap0, "tilemap0"), (best_tilemap1, "tilemap1")]
    ):
        if not tm_data or len(tm_data) < 1024:
            continue
        non_zero = sum(1 for b in tm_data if b != 0)
        print(f"  {tm_name}: {non_zero}/1024 non-zero entries")

        # Render tilemap preview using BG tiles
        tm_img = Image.new("RGB", (32 * 8, 32 * 8), (40, 40, 40))
        for row in range(32):
            for col in range(32):
                tile_id = tm_data[row * 32 + col]
                if tile_id in all_bg_tiles:
                    pixels = decode_2bpp_tile(all_bg_tiles[tile_id])
                    tile_img = tile_to_image(pixels)
                    tm_img.paste(tile_img, (col * 8, row * 8))
        tm_img_scaled = tm_img.resize((32 * 8 * 2, 32 * 8 * 2), Image.NEAREST)
        tm_img_scaled.save(dirs["tilemaps_png"] / f"{tm_name}_preview.png")

    # ---------------------------------------------------------------
    # Phase 5: Export OAM snapshot
    # ---------------------------------------------------------------
    print("\n--- Phase 5: Exporting OAM snapshot ---")
    if best_oam and len(best_oam) >= 160:
        write_oam_header(best_oam, dirs["sprites_h"] / "oam_snapshot.h")
        print(f"  OAM: {best_oam_count} active sprites in best snapshot")

    # ---------------------------------------------------------------
    # Summary
    # ---------------------------------------------------------------
    print("\n" + "=" * 60)
    print("EXTRACTION COMPLETE")
    print("=" * 60)
    print(f"Output directory: {OUTPUT_DIR}")
    print(f"  Sprite tiles: {len(all_sprite_tiles)}/128 non-empty")
    print(f"  BG tiles:     {len(all_bg_tiles)}/256 non-empty")
    print()
    print("Files generated:")
    print(f"  {dirs['sprites_bin']}/*.bin  (raw 2bpp binary)")
    print(f"  {dirs['sprites_h']}/*.h     (C headers)")
    print(f"  {dirs['sprites_png']}/*.png  (individual tile PNGs)")
    print(f"  {dirs['bg_bin']}/*.bin       (raw 2bpp binary)")
    print(f"  {dirs['bg_h']}/*.h          (C headers)")
    print(f"  {dirs['bg_png']}/*.png       (individual tile PNGs)")
    print(f"  {dirs['tilemaps_bin']}/*.bin (tilemap binary)")
    print(f"  {dirs['tilemaps_h']}/*.h    (tilemap C headers)")
    print(f"  {dirs['sheets']}/*.png       (sprite/tile sheets)")

    # Cleanup stray Xvfb procs (per CLAUDE.md guidance)
    subprocess.run(["pkill", "-9", "-f", "Xvfb :"], capture_output=True)

    return all_sprite_tiles, all_bg_tiles


if __name__ == "__main__":
    run_extraction()
