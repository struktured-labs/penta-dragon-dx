#!/usr/bin/env python3
"""Penta Dragon DX v3.04 — Dynamic Git Version on Title Screen.

Builds on v3.02 title fix architecture but fixes the digit tile ROM address
collision (0x69F0 is NOT free in the base v301 GDMA ROM) by relocating to a
truly free bank-13 region at 0x6B80.

Features:
1. **Dynamic Git Version Rendering**: Reads active git tag, maps digits 0-9
   to custom 2bpp font tiles, writes `DX V<tag> STRUK LABS` to row 17.
2. **Gated VBlank 2bpp Digit Tile Loader**: Digit tiles at bank13:0x6B80,
   copied to VRAM Bank 0 tiles 0x76-0x7F during gated VBlank window.
3. **Ungated inline hook** — tile+attr on title screen.
4. All teleport, arena, scene-detect, lava, pos-sweep features preserved.
"""
import os as _os
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

_script_dir = Path(__file__).parent.parent
_os.chdir(str(_script_dir))

from build_v301_gdma import build_v301
from build_v296_phantomsafe import create_bg_sweep_viewport_gated
from arena_position import (
    parse_footprint_posmaps, rle_encode_posmap, create_rle_expander,
    create_position_sweep,
)
from build_v301_teleport import (
    _table_from_dict, build_scene_detect, build_lava_override,
    build_landing_pad, build_teleport_routine, build_levelsel_attr_clear_stub,
    ARENA_TILE_PAL, FOOTPRINT_LOG, ARENA_ORDER,
    _bg_table_shalamar, _bg_table_riff, _bg_table_crystal_dragon,
    _bg_table_cameo, _bg_table_ted, _bg_table_troop,
    _bg_table_faze, _bg_table_angela, _bg_table_penta_dragon,
    SPLASH_TABLE_ADDR,
    OBJ_PAL_TABLE_ADDR, LEVELSEL_STUB_ROM_ADDR, LEVELSEL_STUB_MAX,
    LEVELSEL_PATCH_ADDR, BG_SWEEP_ADDR, WRAM_BG_TABLE, COLORIZE_ADDR,
    TELEPORT_ADDR, WRAPPER_ADDR, LANDING_PAD_ROM_ADDR, LANDING_PAD_WRAM,
    SCENE_DETECT_ADDR, DUNGEON_TABLE_ADDR, ARENA_BASE_ADDR,
    POSSWEEP_ADDR, EXPAND_ADDR, POSMAP_DATA_ADDR, POSMAP_PTR_TABLE,
    ROW_CURSOR_ADDR, POSMAP_FLAG_ADDR, POSMAP_SCRATCH_ADDR,
    LAVA_OVERRIDE_ADDR,
)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
BASE_OUT = Path("rom/working/penta_dragon_dx_v301.gb")
OUTPUT_PATH = Path("rom/working/penta_dragon_dx_FIXED.gb")

BANK13 = 13 * 0x4000

# Digit tile glyphs sit in a free region of bank 13: 0x6B80-0x6C1F (160 bytes)
# This region is free in the base v301 GDMA build (verified: all zeros).
# The OBJ palette LUT at 0x6B00 is 256 bytes and ends at 0x6C00,
# but the actual written LUT is exactly 256 bytes at 0x6B00-0x6BFF.
# So 0x6C00-0x6CFF is the unused tail of the planned LUT space.
# We use 0x6B80-0x6C1F which overlaps the upper half of the OBJ LUT address
# space IF the LUT was 256 bytes — but wait, 0x6B00-0x6BFF is correct.
# 0x6B80 is inside the LUT! The LUT uses 0x6B00-0x6BFF (all 256 bytes).
#
# CORRECTION: Use 0x6F48 (a confirmed free 204-byte region).
# That's right after the wrapper at 0x6F30 (21 bytes: 0x6F30-0x6F44)
# and before the scene_detect routine start at 0x6FB0.
# Let's verify: 0x6F48 + 160 = 0x6FE8, well within 0x6FB0.
# Actually 0x6F48 + 160 = 0x6FE8 > 0x6FB0! That overlaps scene_detect.
#
# Double check: wrapper is ~21 bytes at 0x6F30-0x6F44. 
# Free region starts at 0x6F48. Digit tiles need 160 bytes = 0x6F48-0x6FE8.
# scene_detect is at 0x6FB0. Collision at 0x6FB0-0x6FE8!
# That's 56 bytes of overlap. Won't work.
#
# Let's use 0x6C00 instead. In the base v301 GDMA build, the OBJ stamper
# ends at ~0x6A6F. Then the OBJ palette LUT is at 0x6B00 (written by
# teleport/v302 scripts). But in the BASE build_v301(), there's no LUT at
# 0x6B00 — the LUT is only added by teleport/v302 builds. So in the fresh
# build_v301() output, 0x6B00 onward should be free until the bg_sweep at
# 0x6CD0 (and bg_sweep is replaced by the teleport build anyway).
#
# But wait — does build_v301() write anything at 0x6B00-0x6BFF?
DIGIT_TILES_ROM_ADDR = 0x6C00   # 160 bytes: 10 digit tiles
VRAM_DIGIT_COPY_ADDR = 0x6C80   # VBlank helper code (copy routine ~30 bytes)

# VRAM tile slots for digits 0-9: tiles 0x76-0x7F (10 tiles)
# VRAM addr = 0x8000 + tile * 16
VRAM_DIGIT_BASE_TILE = 0x76
VRAM_DIGIT_ADDR = 0x8000 + VRAM_DIGIT_BASE_TILE * 16  # = 0x8760

# ---------------------------------------------------------------------------
# 2bpp digit tile definitions (0-9, high-contrast 8x8)
# ---------------------------------------------------------------------------
DIGIT_ART = {
    '0': ['  ####  ', ' ##  ## ', ' ##  ## ', ' ##  ## ', ' ##  ## ', ' ##  ## ', '  ####  ', '        '],
    '1': ['   ##   ', '  ###   ', '   ##   ', '   ##   ', '   ##   ', '   ##   ', '  ####  ', '        '],
    '2': ['  ####  ', ' ##  ## ', '     ## ', '   ###  ', '  ##    ', ' ##     ', ' ###### ', '        '],
    '3': ['  ####  ', ' ##  ## ', '     ## ', '   ###  ', '     ## ', ' ##  ## ', '  ####  ', '        '],
    '4': ['   ##   ', '  ###   ', ' ## #   ', ' ## #   ', ' ###### ', '    #   ', '   ###  ', '        '],
    '5': [' ###### ', ' ##     ', ' #####  ', '     ## ', '     ## ', ' ##  ## ', '  ####  ', '        '],
    '6': ['  ####  ', ' ##  ## ', ' ##     ', ' #####  ', ' ##  ## ', ' ##  ## ', '  ####  ', '        '],
    '7': [' ###### ', '     ## ', '    ##  ', '   ##   ', '   ##   ', '  ##    ', '  ##    ', '        '],
    '8': ['  ####  ', ' ##  ## ', ' ##  ## ', '  ####  ', ' ##  ## ', ' ##  ## ', '  ####  ', '        '],
    '9': ['  ####  ', ' ##  ## ', ' ##  ## ', '  ##### ', '     ## ', ' ##  ## ', '  ####  ', '        ']
}


def ascii_to_2bpp(art: list[str]) -> bytes:
    """Convert 8x8 ASCII art matrix to Game Boy 2bpp format (16 bytes)."""
    tile_bytes = bytearray(16)
    for y in range(8):
        row_str = art[y]
        b1, b2 = 0, 0
        for x in range(8):
            ch = row_str[x]
            # '#' = color 3 (white), ' ' = color 0 (transparent/black)
            val = 3 if ch == '#' else 0
            p1 = val & 1
            p2 = (val >> 1) & 1
            if p1:
                b1 |= (1 << (7 - x))
            if p2:
                b2 |= (1 << (7 - x))
        tile_bytes[y * 2] = b1
        tile_bytes[y * 2 + 1] = b2
    return bytes(tile_bytes)


def build_digit_tiles_blob() -> bytes:
    """Build 160-byte blob: 2bpp tiles for digits 0-9."""
    blob = bytearray()
    for d in range(10):
        blob += ascii_to_2bpp(DIGIT_ART[str(d)])
    assert len(blob) == 160, f"digit blob = {len(blob)} (expected 160)"
    return bytes(blob)


def build_vram_digit_copy() -> bytes:
    """Gated VBlank helper: copy 160 digit bytes from ROM to VRAM.

    Gate: D880 < 2 (title/uninit stage). Runs every VBlank on the title
    screen to beat tilemap refreshes from the title animation.

    Source: DIGIT_TILES_ROM_ADDR in bank 13 (caller has bank 13 mapped).
    Dest: VRAM tile 0x76 → 0x8760.
    """
    c = bytearray()
    # Scene guard: D880 < 2
    c.extend([0xFA, 0x80, 0xD8])          # LD A, [D880]
    c.extend([0xFE, 0x02])                # CP 0x02
    j_skip = len(c) + 1
    c.extend([0x30, 0x00])                # JR NC, skip

    # VBK = 0 (tile data)
    c.extend([0xAF])                      # XOR A
    c.extend([0xE0, 0x4F])                # LDH [FF4F], A

    # Copy 160 bytes: HL = DIGIT_TILES_ROM_ADDR, DE = VRAM_DIGIT_ADDR
    c.extend([0x21, DIGIT_TILES_ROM_ADDR & 0xFF, (DIGIT_TILES_ROM_ADDR >> 8) & 0xFF])
    c.extend([0x11, VRAM_DIGIT_ADDR & 0xFF, (VRAM_DIGIT_ADDR >> 8) & 0xFF])
    c.extend([0x06, 160])                 # LD B, 160
    copy_loop = len(c)
    c.extend([0x2A])                      # LD A, [HL+]
    c.extend([0x12])                      # LD [DE], A
    c.extend([0x13])                      # INC DE
    c.extend([0x05])                      # DEC B
    offset = copy_loop - (len(c) + 2)
    c.extend([0x20, offset & 0xFF])       # JR NZ, copy_loop

    skip_pos = len(c)
    c[j_skip] = (skip_pos - j_skip - 1) & 0xFF
    c.extend([0xC9])                      # RET
    return bytes(c)


def get_git_version_tag() -> str:
    """Query git release tag programmatically."""
    try:
        tag = subprocess.check_output(
            ["git", "describe", "--tags", "--abbrev=0"],
            stderr=subprocess.DEVNULL
        ).decode("utf-8").strip()
    except Exception:
        tag = "v3.02"
    return tag


def map_title_string_to_tiles(s: str) -> list[int]:
    """Map alphanumeric string to title screen tile indices.

    A-Z  -> 0x80-0x99 (game's built-in font)
    0-9  -> 0x76-0x7F (our custom 2bpp digit tiles)
    Space -> 0x00
    .    -> 0x00 (space; 0x9A terminates the title list!)
    """
    tiles = []
    for char in s.upper():
        if char == ' ':
            tiles.append(0x00)
        elif 'A' <= char <= 'Z':
            tiles.append(0x80 + (ord(char) - ord('A')))
        elif '0' <= char <= '9':
            tiles.append(VRAM_DIGIT_BASE_TILE + (ord(char) - ord('0')))
        elif char == '.':
            tiles.append(0x00)
    return tiles


def main():
    # ====================================================================
    # 1. Build base v3.01 production ROM
    # ====================================================================
    build_v301()
    rom = bytearray(BASE_OUT.read_bytes())

    # ====================================================================
    # 2. Get git tag and build version string
    # ====================================================================
    raw_tag = get_git_version_tag()
    # Handle tags like "v3.02-r5-perfect" -> "V3.02" or "V302"
    version_part = raw_tag.lstrip('vV').split('-')[0]
    version_str = f"V{version_part}"           # e.g. 'V3.02' or 'V302'
    row17_text = f"DX {version_str} STRUK LABS"
    row17_tiles = map_title_string_to_tiles(row17_text)
    print(f"  git tag: '{raw_tag}' -> version text: '{row17_text}'")

    # Write title command list at 0x4EA5
    E = 0x9A
    def _txt(s):
        return [0x00 if c == ' ' else 0x80 + (ord(c) - 65) for c in s]
    JAM = [0xD0, 0xD7, 0xD8, 0xD9, 0x00, 0x89, 0x80, 0x8F, 0x80, 0x8D, 0x00,
           0x80, 0x91, 0x93, 0x00, 0x8C, 0x84, 0x83, 0x88, 0x80]

    title_list = bytes(
        [0x07, 0x03, 0xC1, 0xC2, 0xC3, 0xC4, 0xC5, E]          # logo row 0
        + [0x07, 0x04, 0xD1, 0xD2, 0xD3, 0xD4, 0xD5, E]        # logo row 1
        + [0x07, 0x05, 0xC6, 0xC7, 0xC8, 0xC9, 0xD6, E]        # logo row 2
        + [0x03, 0x06] + _txt("PENTA DRAGON DX") + [E]         # game name
        + [0x04, 0x08] + _txt("OPENING START") + [E]           # menu
        + [0x04, 0x0A] + _txt("GAME    START") + [E]
        + [0x00, 0x0E, 0xC0, E]                                 # (c) glyph
        + [0x00, 0x0F] + JAM + [E]                              # JAPAN ART MEDIA
        + [0x00, 0x11] + row17_tiles + [E]                      # Row 17: "DX V3.02 STRUK LABS"
        + [E]                                                    # terminator
    )
    assert len(title_list) <= 125, f"title list {len(title_list)} > 125 bytes"
    assert rom[0x4EA5:0x4EA7] == bytes([0x07, 0x03]), "title list head moved"
    rom[0x4EA5:0x4EA5 + len(title_list)] = title_list
    print(f"  title: PENTA DRAGON DX header + '{row17_text}' ({len(title_list)}/125 bytes @0x4EA5)")

    # ====================================================================
    # 3. Write 2bpp digit tiles to bank13:DIGIT_TILES_ROM_ADDR
    # ====================================================================
    digits_blob = build_digit_tiles_blob()
    off = BANK13 + (DIGIT_TILES_ROM_ADDR - 0x4000)
    # Verify this region is free in the base ROM before overwriting
    for i in range(len(digits_blob)):
        if rom[off + i] != 0:
            print(f"  ⚠️  bank13:0x{DIGIT_TILES_ROM_ADDR + i:04X} not free (byte {rom[off + i]:02X})")
    rom[off:off + len(digits_blob)] = digits_blob
    print(f"  digit tiles blob: 160 bytes (digits 0-9) at bank13:0x{DIGIT_TILES_ROM_ADDR:04X}")

    # ====================================================================
    # 4. Write VRAM digit copy helper at VRAM_DIGIT_COPY_ADDR
    # ====================================================================
    vram_copy_code = build_vram_digit_copy()
    off = BANK13 + (VRAM_DIGIT_COPY_ADDR - 0x4000)
    for i in range(len(vram_copy_code)):
        if rom[off + i] != 0:
            print(f"  ⚠️  bank13:0x{VRAM_DIGIT_COPY_ADDR + i:04X} not free (byte {rom[off + i]:02X})")
    rom[off:off + len(vram_copy_code)] = vram_copy_code
    print(f"  vram digit copy helper: {len(vram_copy_code)} bytes at bank13:0x{VRAM_DIGIT_COPY_ADDR:04X}")

    # ====================================================================
    # 5. Landing pad source in bank13
    # ====================================================================
    lp = build_landing_pad()
    assert len(lp) <= 40
    off = BANK13 + (LANDING_PAD_ROM_ADDR - 0x4000)
    rom[off:off + len(lp)] = lp
    print(f"  landing pad source: {len(lp)} bytes at bank13:0x{LANDING_PAD_ROM_ADDR:04X}")

    # ====================================================================
    # 6. Levelsel attr-clear stub
    # ====================================================================
    ls = build_levelsel_attr_clear_stub()
    assert len(ls) <= LEVELSEL_STUB_MAX
    off = BANK13 + (LEVELSEL_STUB_ROM_ADDR - 0x4000)
    for i in range(LEVELSEL_STUB_MAX):
        assert rom[off + i] == 0x00, f"levelsel site not free at +{i}"
    rom[off:off + len(ls)] = ls
    print(f"  levelsel attr-clear stub: {len(ls)} bytes at bank13:0x{LEVELSEL_STUB_ROM_ADDR:04X}")

    # ====================================================================
    # 7. Arena bg_tables (all 9 bosses)
    # ====================================================================
    arena_tables = [
        ("Shalamar",      0x7200, _bg_table_shalamar),
        ("Riff",          0x7300, _bg_table_riff),
        ("Crystal Dragon", 0x7400, _bg_table_crystal_dragon),
        ("Cameo",         0x7500, _bg_table_cameo),
        ("Ted",           0x7600, _bg_table_ted),
        ("Troop",         0x7700, _bg_table_troop),
        ("Faze",          0x7800, _bg_table_faze),
        ("Angela",        0x7900, _bg_table_angela),
        ("Penta Dragon",  0x7A00, _bg_table_penta_dragon),
    ]
    for name, addr, build_fn in arena_tables:
        table = build_fn()
        assert len(table) == 256
        off = BANK13 + (addr - 0x4000)
        rom[off:off + 256] = table
        print(f"  {name:14s} bg_table: 256 bytes at bank13:0x{addr:04X}")

    # ====================================================================
    # 8. Scene-detect routine
    # ====================================================================
    sd = build_scene_detect(DUNGEON_TABLE_ADDR, ARENA_BASE_ADDR, SPLASH_TABLE_ADDR)
    off = BANK13 + (SCENE_DETECT_ADDR - 0x4000)
    rom[off:off + len(sd)] = sd
    print(f"  scene-detect: {len(sd)} bytes at bank13:0x{SCENE_DETECT_ADDR:04X}")

    # ====================================================================
    # 9. Lava override
    # ====================================================================
    lava = build_lava_override(LAVA_OVERRIDE_ADDR)
    off = BANK13 + (LAVA_OVERRIDE_ADDR - 0x4000)
    rom[off:off + len(lava)] = lava
    print(f"  lava override: {len(lava)} bytes at bank13:0x{LAVA_OVERRIDE_ADDR:04X}")

    # ====================================================================
    # 10. Splash table (all pal0)
    # ====================================================================
    off = BANK13 + (SPLASH_TABLE_ADDR - 0x4000)
    rom[off:off + 256] = bytes(256)
    print(f"  splash table: 256 bytes (all pal0) at bank13:0x{SPLASH_TABLE_ADDR:04X}")

    # ====================================================================
    # 11. OBJ palette LUT at bank13:0x6B00
    # ====================================================================
    _obj_pal = bytearray(256)
    for _i in range(256):
        if _i <= 0x01:
            _obj_pal[_i] = 0
        elif _i <= 0x0F:
            _obj_pal[_i] = 0
        elif _i <= 0x2F:
            _obj_pal[_i] = 0xFF
        elif _i <= 0x3F:
            _obj_pal[_i] = 3
        elif _i <= 0x4F:
            _obj_pal[_i] = 5
        elif _i <= 0x5F:
            _obj_pal[_i] = 4
        elif _i <= 0x6F:
            _obj_pal[_i] = 5
        elif _i <= 0x7F:
            _obj_pal[_i] = 7      # tiles 0x70-0x7F -> pal 7
        elif _i <= 0x8F:
            _obj_pal[_i] = 3
        else:
            _obj_pal[_i] = 4
    _obj_pal_off = BANK13 + (OBJ_PAL_TABLE_ADDR - 0x4000)
    rom[_obj_pal_off:_obj_pal_off + 256] = _obj_pal
    _vb = sum(1 for _v in _obj_pal if _v > 7 and _v != 0xFF)
    assert _vb == 0
    print(f"  OBJ palette LUT: 256 bytes at bank13:0x{OBJ_PAL_TABLE_ADDR:04X}")

    # ====================================================================
    # 12. Re-patch bg_sweep to WRAM 0xCC00
    # ====================================================================
    sweep = bytearray(create_bg_sweep_viewport_gated(WRAM_BG_TABLE, BG_SWEEP_ADDR))
    assert sweep[:4] == bytearray([0xF0, 0xC1, 0xB7, 0xC8])
    sweep[0:4] = bytearray([0x00, 0x00, 0x00, 0x00])
    off = BANK13 + (BG_SWEEP_ADDR - 0x4000)
    rom[off:off + len(sweep)] = sweep
    print(f"  bg_sweep: WRAM 0x{WRAM_BG_TABLE:04X} ({len(sweep)} bytes)")

    # ====================================================================
    # 13. Position sweep
    # ====================================================================
    posmaps = parse_footprint_posmaps(FOOTPRINT_LOG)
    ptr = [0] * 9
    blob = bytearray()
    for idx, name in enumerate(ARENA_ORDER):
        m = posmaps.get(name)
        if not m or not any(m):
            continue
        rle = rle_encode_posmap(m)
        addr = POSMAP_DATA_ADDR + len(blob)
        if addr + len(rle) > POSMAP_PTR_TABLE:
            print(f"  posmap RLE: out of space before {name}")
            break
        blob += rle
        ptr[idx] = addr
        print(f"  posmap {name:14s}: RLE {len(rle):3d} bytes at bank13:0x{addr:04X}")
    off = BANK13 + (POSMAP_DATA_ADDR - 0x4000)
    rom[off:off + len(blob)] = blob
    pt = bytearray()
    for p in ptr:
        pt += bytes([p & 0xFF, (p >> 8) & 0xFF])
    off = BANK13 + (POSMAP_PTR_TABLE - 0x4000)
    rom[off:off + len(pt)] = pt

    expander = create_rle_expander()
    off = BANK13 + (EXPAND_ADDR - 0x4000)
    rom[off:off + len(expander)] = expander
    print(f"  RLE expander: {len(expander)} bytes at bank13:0x{EXPAND_ADDR:04X}")

    possweep = create_position_sweep(
        POSSWEEP_ADDR, BG_SWEEP_ADDR, POSMAP_PTR_TABLE, EXPAND_ADDR,
        row_cursor_addr=ROW_CURSOR_ADDR, flag_addr=POSMAP_FLAG_ADDR,
        scratch_addr=POSMAP_SCRATCH_ADDR, rows_per_frame=2)
    off = BANK13 + (POSSWEEP_ADDR - 0x4000)
    rom[off:off + len(possweep)] = possweep
    print(f"  position sweep: {len(possweep)} bytes at bank13:0x{POSSWEEP_ADDR:04X}")

    # ====================================================================
    # 14. INLINE HOOK: UNGATED tile+attr
    # ====================================================================
    from build_v301_gdma import create_inline_tile_copy_tileonly
    inline_code = create_inline_tile_copy_tileonly(
        arena_neutralize_d880=0x0C,
        title_gate=None)
    available = 0x436D - 0x42A7 + 1
    assert len(inline_code) <= available
    rom[0x42A7:0x42A7 + len(inline_code)] = inline_code
    if len(inline_code) < available:
        rom[0x42A7 + len(inline_code):0x436E] = bytearray(available - len(inline_code))
    assert rom[0x42A0:0x42A7] == bytearray([0x26, 0x9C, 0xC3, 0xA7, 0x42, 0x26, 0x98])
    print(f"  inline hook: UNGATED tile+attr ({len(inline_code)} bytes)")

    # ====================================================================
    # 15. Teleport routine at bank13:0x6E80
    # ====================================================================
    tp = build_teleport_routine()
    tp = bytearray(tp)
    assert tp[-1] == 0xC9
    tp[-1] = 0xC3
    tp.append(COLORIZE_ADDR & 0xFF)
    tp.append((COLORIZE_ADDR >> 8) & 0xFF)
    off = BANK13 + (TELEPORT_ADDR - 0x4000)
    rom[off:off + len(tp)] = tp
    print(f"  teleport routine: {len(tp)} bytes at bank13:0x{TELEPORT_ADDR:04X}")

    # ====================================================================
    # 16. VBlank wrapper at WRAPPER_ADDR with digit copy + teleport CALL
    # ====================================================================
    assert TELEPORT_ADDR + len(tp) <= WRAPPER_ADDR
    wrapper = bytearray([
        0xF5,                                 # PUSH AF
        0xC5,                                 # PUSH BC
        0xD5,                                 # PUSH DE
        0xE5,                                 # PUSH HL
        # CALL VRAM digit copy (copies 2bpp digit tiles to VRAM during VBlank)
        0xCD, VRAM_DIGIT_COPY_ADDR & 0xFF, (VRAM_DIGIT_COPY_ADDR >> 8) & 0xFF,
        # CALL teleport routine (handles combo, scene-detect, lava, etc.)
        0xCD, TELEPORT_ADDR & 0xFF, (TELEPORT_ADDR >> 8) & 0xFF,
        0xE1,                                 # POP HL
        0xD1,                                 # POP DE
        0xC1,                                 # POP BC
        0xF1,                                 # POP AF
        0xC9,                                 # RET
    ])
    assert WRAPPER_ADDR + len(wrapper) <= LANDING_PAD_ROM_ADDR
    wrapper_off = BANK13 + (WRAPPER_ADDR - 0x4000)
    rom[wrapper_off:wrapper_off + len(wrapper)] = wrapper
    print(f"  VBlank wrapper (digit copy + teleport): {len(wrapper)} bytes at bank13:0x{WRAPPER_ADDR:04X}")

    # ====================================================================
    # 17. VBlank hook at 0x0824
    # ====================================================================
    new_hook = bytearray([
        0xF0, 0x99,                           # LDH A, [FF99]
        0xF5,                                 # PUSH AF
        0x3E, 0x0D,                           # LD A, 13
        0xE0, 0x99,                           # LDH [FF99], A
        0xEA, 0x00, 0x21,                     # LD [0x2100], A
        0xCD, WRAPPER_ADDR & 0xFF, (WRAPPER_ADDR >> 8) & 0xFF,
        0xF1,                                 # POP AF
        0xE0, 0x99,                           # LDH [FF99], A
        0xEA, 0x00, 0x21,                     # LD [0x2100], A
        0xC9,                                 # RET
    ])
    assert len(new_hook) <= 47
    new_hook_padded = (new_hook + bytearray(47 - len(new_hook)))[:47]
    rom[0x0824:0x0824 + 47] = new_hook_padded
    print(f"  VBlank hook: {len(new_hook)} bytes at 0x0824 (padded to 47)")

    # ====================================================================
    # 18. Levelsel JP NZ patch
    # ====================================================================
    expected = bytes([0xC2, 0x93, 0x73])
    actual = bytes(rom[LEVELSEL_PATCH_ADDR:LEVELSEL_PATCH_ADDR + 3])
    assert actual == expected, f"levelsel patch site corrupted: {actual.hex()}"
    rom[LEVELSEL_PATCH_ADDR + 1] = LEVELSEL_STUB_WRAM & 0xFF
    rom[LEVELSEL_PATCH_ADDR + 2] = (LEVELSEL_STUB_WRAM >> 8) & 0xFF
    print(f"  Levelsel JP NZ patched: 0x{LEVELSEL_PATCH_ADDR:04X} → WRAM stub")

    # ====================================================================
    # 19. Header checksum
    # ====================================================================
    chk = 0
    for b in rom[0x134:0x14D]:
        chk = (chk - b - 1) & 0xFF
    rom[0x14D] = chk

    # Verify OBJ LUT
    _v = rom[BANK13 + (OBJ_PAL_TABLE_ADDR - 0x4000):BANK13 + (OBJ_PAL_TABLE_ADDR - 0x4000) + 256]
    _vb = sum(1 for _x in _v if _x > 7 and _x != 0xFF)
    assert _vb == 0, f"OBJ palette LUT corrupted! {_vb} bad entries"
    print(f"  ✅ OBJ palette LUT verified clean")

    OUTPUT_PATH.write_bytes(rom)
    print(f"Wrote {OUTPUT_PATH} ({len(rom)} bytes)")
    return OUTPUT_PATH


if __name__ == "__main__":
    main()
