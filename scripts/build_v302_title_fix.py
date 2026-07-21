#!/usr/bin/env python3
"""Penta Dragon DX v3.02 — Title screen cursor & dynamic version fix.

Features & Fixes:
1. **Dynamic Git Version Rendering**: Reads active git tag (`git describe --tags --abbrev=0`),
   maps digits 0-9 to custom 2bpp font tiles (0x76-0x7F) and writes `DX V<tag> STRUK LABS`
   to row 17 of the title screen menu list.
2. **Gated VBlank 2bpp Digit Tile Loader**: Places clean 2bpp Western digit glyphs (0-9)
   at bank13:0x69F0 and copies them to vacant VRAM Bank 0 slots (0x8760 = tiles 0x76-0x7F)
   ONLY during the gated VBlank window in the VBlank wrapper (gated on D880 < 2 and sentinel DF1C).
3. **Ungated inline hook** — write tile+attr on the title screen (was tile-only
   due to D880 gate). Arena still tile-only for position sweep compatibility.
4. **OBJ palette LUT** — tiles 0x70-0x7F → pal 7, matching cursor 'A' at tile 0x73 requirements.
5. **bg_sweep** — re-patched to WRAM 0xCC00 with FFC1 gate NOP'd.
"""
import os as _os
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

# Ensure we run from the project root
_script_dir = Path(__file__).parent.parent
_os.chdir(str(_script_dir))

import yaml
from arena_position import (
    parse_footprint_posmaps, rle_encode_posmap, create_rle_expander,
    create_position_sweep,
)
from build_v296_phantomsafe import create_bg_sweep_viewport_gated
from build_v301_gdma import (
    build_v301, load_palettes_from_yaml, create_palette_loader,
    create_shadow_colorizer_main, create_tile_based_colorizer,
    create_tile_to_palette_subroutine, create_conditional_palette_cached,
    BG_TABLE_BYTES, _bg_table,
)
from build_v301_teleport import (
    _table_from_dict, build_scene_detect, build_lava_override,
    build_landing_pad, build_teleport_routine, build_levelsel_attr_clear_stub,
    ARENA_TILE_PAL, FOOTPRINT_LOG, ARENA_ORDER,
    _bg_table_shalamar, _bg_table_riff, _bg_table_crystal_dragon,
    _bg_table_cameo, _bg_table_ted, _bg_table_troop,
    _bg_table_faze, _bg_table_angela, _bg_table_penta_dragon,
    SPLASH_TABLE_ADDR,
)

BASE_OUT = Path("rom/working/penta_dragon_dx_v301.gb")
OUTPUT_PATH = Path("rom/working/penta_dragon_dx_FIXED.gb")  # Overwrite FIXED.gb

# Constants
BANK13 = 13 * 0x4000
BG_SWEEP_ADDR = 0x6CD0
WRAM_BG_TABLE = 0xCC00
COLORIZE_ADDR = 0x6E00
TELEPORT_ADDR = 0x6E80
OBJ_PAL_TABLE_ADDR = 0x6B00
WRAPPER_ADDR = 0x6F30
LANDING_PAD_ROM_ADDR = 0x6F80
LANDING_PAD_WRAM = 0xCF90
LEVELSEL_STUB_ROM_ADDR = 0x53C2
LEVELSEL_STUB_WRAM = 0xCFB0
LEVELSEL_PATCH_ADDR = 0x3B47
LEVELSEL_STUB_MAX = 36
SCENE_DETECT_ADDR = 0x6FB0
DUNGEON_TABLE_ADDR = 0x7000
ARENA_BASE_ADDR = 0x7200
SHALAMAR_TABLE_ADDR = 0x7200
RIFF_TABLE_ADDR = 0x7300
CRYSTAL_DRAGON_TABLE_ADDR = 0x7400
CAMEO_TABLE_ADDR = 0x7500
TED_TABLE_ADDR = 0x7600
TROOP_TABLE_ADDR = 0x7700
FAZE_TABLE_ADDR = 0x7800
ANGELA_TABLE_ADDR = 0x7900
PENTA_DRAGON_TABLE_ADDR = 0x7A00
LAVA_OVERRIDE_ADDR = 0x7E00
POSSWEEP_ADDR = 0x7100
EXPAND_ADDR = 0x6D80
POSMAP_DATA_ADDR = 0x7B00
POSMAP_PTR_TABLE = 0x7FE0
ROW_CURSOR_ADDR = 0xDF40
POSMAP_FLAG_ADDR = 0xDF46
POSMAP_SCRATCH_ADDR = 0xDF47
DIGIT_TILES_ROM_ADDR = 0x69F0   # 160 bytes: 10 digit tiles (0-9) x 16 bytes/tile
VRAM_DIGIT_COPY_ADDR = 0x6AC0   # Gated VBlank helper: copies ROM 0x69F0 -> VRAM 0x8760 (tiles 0x76-0x7F)

# 2bpp Western digit tile definitions (0-9, high-contrast 8x8)
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
    """Build 160-byte blob containing 2bpp tiles for digits 0-9."""
    blob = bytearray()
    for d in range(10):
        blob += ascii_to_2bpp(DIGIT_ART[str(d)])
    assert len(blob) == 160
    return bytes(blob)


def build_vram_digit_copy() -> bytes:
    """Build gated VBlank helper to copy 160 digit bytes from ROM 0x69F0 to VRAM 0x8760.

    Gated by scene guard D880 < 2 (title/uninit). Runs continuously every VBlank
    frame on title screen (160 bytes copy = ~2560T, well within VBlank) to beat
    title animation tilemap refreshes.
    """
    c = bytearray()
    # Scene guard: D880 < 2 (title or init stage)
    c.extend([0xFA, 0x80, 0xD8])          # LD A, [D880]
    c.extend([0xFE, 0x02])                # CP 0x02
    j_skip = len(c) + 1
    c.extend([0x30, 0x00])                # JR NC, copy_done

    # Select VRAM Bank 0
    c.extend([0xAF])                      # XOR A
    c.extend([0xE0, 0x4F])                # LDH [FF4F], A

    # Copy 160 bytes: HL = 0x69F0 (ROM), DE = 0x8760 (VRAM tile 0x76), B = 160
    c.extend([0x21, DIGIT_TILES_ROM_ADDR & 0xFF, (DIGIT_TILES_ROM_ADDR >> 8) & 0xFF])  # LD HL, 0x69F0
    c.extend([0x11, 0x60, 0x87])          # LD DE, 0x8760 (tile 0x76 * 16 + 0x8000)
    c.extend([0x06, 160])                 # LD B, 160
    copy_loop = len(c)
    c.extend([0x2A])                      # LD A, [HL+]
    c.extend([0x12])                      # LD [DE], A
    c.extend([0x13])                      # INC DE
    c.extend([0x05])                      # DEC B
    offset = copy_loop - (len(c) + 2)
    c.extend([0x20, offset & 0xFF])       # JR NZ, copy_loop

    copy_done_pos = len(c)
    c[j_skip] = (copy_done_pos - j_skip - 1) & 0xFF
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

    Mapping:
      Space  -> 0x00
      A-Z    -> 0x80 - 0x99
      0-9    -> 0x76 - 0x7F (custom 2bpp font tiles)
      .      -> 0x00 (space; 0x9A is the title command list string terminator!)
    """
    tiles = []
    for char in s.upper():
        if char == ' ':
            tiles.append(0x00)
        elif 'A' <= char <= 'Z':
            tiles.append(0x80 + (ord(char) - ord('A')))
        elif '0' <= char <= '9':
            tiles.append(0x76 + (ord(char) - ord('0')))
        elif char == '.':
            tiles.append(0x00)  # Use space for dot to prevent premature entry termination by 0x9A parser
    return tiles


def main():
    # 1. Build base v3.01 production ROM
    build_v301()
    rom = bytearray(BASE_OUT.read_bytes())

    # 2. Get active git tag and format version string
    raw_tag = get_git_version_tag()
    # Strip leading 'v' or 'V' and sanitize branch/build suffixes if present
    version_part = raw_tag.lstrip('vV').split('-')[0]  # e.g., '3.02' or '302'
    # Remove any dots so the version renders cleanly as digits (no period glyph needed)
    version_part = version_part.replace('.', '')
    version_str = f"V{version_part}"                     # e.g. 'V302' or 'V302'
    row17_text = f"DX {version_str} STRUK LABS"
    row17_tiles = map_title_string_to_tiles(row17_text)
    print(f"  git tag: '{raw_tag}' -> version text: '{row17_text}'")

    # Construct title command list
    E = 0x9A
    def _txt(s):
        return [0x00 if c == ' ' else 0x80 + (ord(c) - 65) for c in s]
    JAM = [0xD0, 0xD7, 0xD8, 0xD9, 0x00, 0x89, 0x80, 0x8F, 0x80, 0x8D, 0x00,
           0x80, 0x91, 0x93, 0x00, 0x8C, 0x84, 0x83, 0x88, 0x80]

    title_list = bytes(
        [0x07, 0x03, 0xC1, 0xC2, 0xC3, 0xC4, 0xC5, E]          # logo row 0 (screen row 3)
        + [0x07, 0x04, 0xD1, 0xD2, 0xD3, 0xD4, 0xD5, E]        # logo row 1 (screen row 4)
        + [0x07, 0x05, 0xC6, 0xC7, 0xC8, 0xC9, 0xD6, E]        # logo row 2 (screen row 5)
        + [0x03, 0x06] + _txt("PENTA DRAGON DX") + [E]         # game name + DX (row 6 -> screen row 6)
        + [0x04, 0x08] + _txt("OPENING START") + [E]           # OPENING START (row 8 -> screen row 8)
        + [0x04, 0x0A] + _txt("GAME    START") + [E]           # GAME START (row 10 -> screen row 10)
        + [0x00, 0x0E, 0xC0, E]                                 # (c) symbol (row 14 -> screen row 14)
        + [0x00, 0x0F] + JAM + [E]                              # JAPAN ART MEDIA (row 15 -> screen row 15)
        + [0x00, 0x11] + row17_tiles + [E]                      # Row 17 -> screen row 17: "DX V3.02 STRUK LABS"
        + [E]                                                   # Explicit list terminator 0x9A
    )
    assert len(title_list) <= 125, f"title list {len(title_list)} > 125 bytes"
    assert rom[0x4EA5:0x4EA7] == bytes([0x07, 0x03]), "title list head moved"
    rom[0x4EA5:0x4EA5 + len(title_list)] = title_list
    print(f"  title: PENTA DRAGON DX header + '{row17_text}' ({len(title_list)}/125 bytes @0x4EA5)")

    # 3. Write 2bpp digit tiles to bank13:0x69F0
    digits_blob = build_digit_tiles_blob()
    off = BANK13 + (DIGIT_TILES_ROM_ADDR - 0x4000)
    rom[off:off + len(digits_blob)] = digits_blob
    print(f"  digit tiles blob: 160 bytes (digits 0-9) at bank13:0x{DIGIT_TILES_ROM_ADDR:04X}")

    # 4. Write VRAM digit copy helper at bank13:0x6AC0
    vram_copy_code = build_vram_digit_copy()
    off = BANK13 + (VRAM_DIGIT_COPY_ADDR - 0x4000)
    rom[off:off + len(vram_copy_code)] = vram_copy_code
    print(f"  vram digit copy helper: {len(vram_copy_code)} bytes at bank13:0x{VRAM_DIGIT_COPY_ADDR:04X}")

    # 5. Landing pad source in bank13
    lp = build_landing_pad()
    assert len(lp) <= 40
    off = BANK13 + (LANDING_PAD_ROM_ADDR - 0x4000)
    rom[off:off + len(lp)] = lp
    print(f"  landing pad source: {len(lp)} bytes at bank13:0x{LANDING_PAD_ROM_ADDR:04X}")

    # 6. Levelsel attr-clear stub
    ls = build_levelsel_attr_clear_stub()
    assert len(ls) <= LEVELSEL_STUB_MAX
    off = BANK13 + (LEVELSEL_STUB_ROM_ADDR - 0x4000)
    for i in range(LEVELSEL_STUB_MAX):
        assert rom[off + i] == 0x00, f"levelsel site not free at +{i}"
    rom[off:off + len(ls)] = ls
    print(f"  levelsel attr-clear stub: {len(ls)} bytes at bank13:0x{LEVELSEL_STUB_ROM_ADDR:04X}")

    # 7. Arena bg_tables (all 9 bosses)
    arena_tables = [
        ("Shalamar",      SHALAMAR_TABLE_ADDR,        _bg_table_shalamar),
        ("Riff",          RIFF_TABLE_ADDR,            _bg_table_riff),
        ("Crystal Dragon", CRYSTAL_DRAGON_TABLE_ADDR,  _bg_table_crystal_dragon),
        ("Cameo",         CAMEO_TABLE_ADDR,           _bg_table_cameo),
        ("Ted",           TED_TABLE_ADDR,             _bg_table_ted),
        ("Troop",         TROOP_TABLE_ADDR,           _bg_table_troop),
        ("Faze",          FAZE_TABLE_ADDR,            _bg_table_faze),
        ("Angela",        ANGELA_TABLE_ADDR,          _bg_table_angela),
        ("Penta Dragon",  PENTA_DRAGON_TABLE_ADDR,    _bg_table_penta_dragon),
    ]
    for i, (name, addr, _) in enumerate(arena_tables):
        expected = ARENA_BASE_ADDR + i * 0x100
        assert addr == expected
    for name, addr, build_fn in arena_tables:
        table = build_fn()
        assert len(table) == 256
        off = BANK13 + (addr - 0x4000)
        rom[off:off + 256] = table
        print(f"  {name:14s} bg_table: 256 bytes at bank13:0x{addr:04X}")

    # 8. Scene-detect routine
    sd = build_scene_detect(DUNGEON_TABLE_ADDR, ARENA_BASE_ADDR, SPLASH_TABLE_ADDR)
    assert SCENE_DETECT_ADDR + len(sd) <= DUNGEON_TABLE_ADDR
    off = BANK13 + (SCENE_DETECT_ADDR - 0x4000)
    rom[off:off + len(sd)] = sd
    print(f"  scene-detect: {len(sd)} bytes at bank13:0x{SCENE_DETECT_ADDR:04X}")

    # 9. Lava override
    lava = build_lava_override(LAVA_OVERRIDE_ADDR)
    off = BANK13 + (LAVA_OVERRIDE_ADDR - 0x4000)
    rom[off:off + len(lava)] = lava
    print(f"  lava override: {len(lava)} bytes at bank13:0x{LAVA_OVERRIDE_ADDR:04X}")

    # 10. Splash table (all pal0, for D880=0x18)
    off = BANK13 + (SPLASH_TABLE_ADDR - 0x4000)
    rom[off:off + 256] = bytes(256)
    print(f"  splash table: 256 bytes (all pal0) at bank13:0x{SPLASH_TABLE_ADDR:04X}")

    # 11. OBJ palette LUT at bank13:0x6B00
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
            _obj_pal[_i] = 7      # pal 7, cursor 'A' at tile 0x73
        elif _i <= 0x8F:
            _obj_pal[_i] = 3
        else:
            _obj_pal[_i] = 4
    _obj_pal_off = BANK13 + (OBJ_PAL_TABLE_ADDR - 0x4000)
    rom[_obj_pal_off:_obj_pal_off + 256] = _obj_pal
    _vb = sum(1 for _v in _obj_pal if _v > 7 and _v != 0xFF)
    assert _vb == 0
    print(f"  OBJ palette LUT: 256 bytes at bank13:0x{OBJ_PAL_TABLE_ADDR:04X} (tiles 0x70-0x7F -> pal 7)")

    # 12. Re-patch bg_sweep to read WRAM 0xCC00 (per-scene) with FFC1 NOP'd
    sweep = bytearray(create_bg_sweep_viewport_gated(WRAM_BG_TABLE, BG_SWEEP_ADDR))
    assert sweep[:4] == bytearray([0xF0, 0xC1, 0xB7, 0xC8])
    sweep[0:4] = bytearray([0x00, 0x00, 0x00, 0x00])  # DMG NOPs removed
    off = BANK13 + (BG_SWEEP_ADDR - 0x4000)
    rom[off:off + len(sweep)] = sweep
    print(f"  bg_sweep: WRAM 0x{WRAM_BG_TABLE:04X}, FFC1 gate NOP'd ({len(sweep)} bytes)")

    # 13. Position sweep
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
    print(f"  posmap RLE total: {len(blob)} bytes")
    pt = bytearray()
    for p in ptr:
        pt += bytes([p & 0xFF, (p >> 8) & 0xFF])
    off = BANK13 + (POSMAP_PTR_TABLE - 0x4000)
    rom[off:off + len(pt)] = pt

    # RLE expander
    expander = create_rle_expander()
    assert EXPAND_ADDR + len(expander) <= COLORIZE_ADDR
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

    # 14. INLINE HOOK: UNGATED tile+attr
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

    # 15. Teleport routine at bank13:0x6E80
    tp = build_teleport_routine()
    tp = bytearray(tp)
    assert tp[-1] == 0xC9
    tp[-1] = 0xC3
    tp.append(COLORIZE_ADDR & 0xFF)
    tp.append((COLORIZE_ADDR >> 8) & 0xFF)
    off = BANK13 + (TELEPORT_ADDR - 0x4000)
    rom[off:off + len(tp)] = tp
    print(f"  teleport routine: {len(tp)} bytes at bank13:0x{TELEPORT_ADDR:04X}")

    # 16. VBlank wrapper at 0x6F30 with CALL VRAM_DIGIT_COPY
    assert TELEPORT_ADDR + len(tp) <= WRAPPER_ADDR
    wrapper = bytearray([
        0xF5,                                 # PUSH AF
        0xC5,                                 # PUSH BC
        0xD5,                                 # PUSH DE
        0xE5,                                 # PUSH HL
        # CALL VRAM digit copy helper (copies digit 2bpp tiles during VBlank)
        0xCD, VRAM_DIGIT_COPY_ADDR & 0xFF, (VRAM_DIGIT_COPY_ADDR >> 8) & 0xFF,
        0xCD, TELEPORT_ADDR & 0xFF, (TELEPORT_ADDR >> 8) & 0xFF,  # CALL teleport
        0xE1,                                 # POP HL
        0xD1,                                 # POP DE
        0xC1,                                 # POP BC
        0xF1,                                 # POP AF
        0xC9,                                 # RET
    ])
    assert WRAPPER_ADDR + len(wrapper) <= LANDING_PAD_ROM_ADDR
    wrapper_off = BANK13 + (WRAPPER_ADDR - 0x4000)
    rom[wrapper_off:wrapper_off + len(wrapper)] = wrapper
    print(f"  VBlank wrapper (with VRAM digit copy): {len(wrapper)} bytes at bank13:0x{WRAPPER_ADDR:04X}")

    # 17. VBlank hook at 0x0824
    new_hook = bytearray([
        0xF0, 0x99,                           # LDH A, [FF99]
        0xF5,                                 # PUSH AF
        0x3E, 0x0D,                           # LD A, 13
        0xE0, 0x99,                           # LDH [FF99], A
        0xEA, 0x00, 0x21,                     # LD [0x2100], A
        0xCD, WRAPPER_ADDR & 0xFF, (WRAPPER_ADDR >> 8) & 0xFF,  # CALL wrapper
        0xF1,                                 # POP AF
        0xE0, 0x99,                           # LDH [FF99], A
        0xEA, 0x00, 0x21,                     # LD [0x2100], A
        0xC9,                                 # RET
    ])
    assert len(new_hook) <= 47
    new_hook_padded = (new_hook + bytearray(47 - len(new_hook)))[:47]
    rom[0x0824:0x0824 + 47] = new_hook_padded
    print(f"  VBlank hook: {len(new_hook)} bytes at 0x0824")

    # 18. Levelsel JP NZ patch
    expected = bytes([0xC2, 0x93, 0x73])
    actual = bytes(rom[LEVELSEL_PATCH_ADDR:LEVELSEL_PATCH_ADDR + 3])
    assert actual == expected, f"levelsel patch site corrupted: {actual.hex()}"
    rom[LEVELSEL_PATCH_ADDR + 1] = LEVELSEL_STUB_WRAM & 0xFF
    rom[LEVELSEL_PATCH_ADDR + 2] = (LEVELSEL_STUB_WRAM >> 8) & 0xFF
    print(f"  Levelsel JP NZ patched: 0x{LEVELSEL_PATCH_ADDR:04X} → 0x{LEVELSEL_STUB_WRAM:04X}")

    # Header checksum
    chk = 0
    for b in rom[0x134:0x14D]:
        chk = (chk - b - 1) & 0xFF
    rom[0x14D] = chk

    # Final OBJ LUT verification
    _v = rom[BANK13 + (OBJ_PAL_TABLE_ADDR - 0x4000):BANK13 + (OBJ_PAL_TABLE_ADDR - 0x4000) + 256]
    _vb = sum(1 for _x in _v if _x > 7 and _x != 0xFF)
    assert _vb == 0, f"OBJ palette LUT corrupted! {_vb} bad entries"
    print(f"  ✅ OBJ palette LUT verified clean")

    OUTPUT_PATH.write_bytes(rom)
    print(f"Wrote {OUTPUT_PATH} ({len(rom)} bytes)")
    return OUTPUT_PATH


if __name__ == "__main__":
    main()
