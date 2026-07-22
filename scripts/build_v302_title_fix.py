#!/usr/bin/env python3
"""Penta Dragon DX — title cursor and v3.01 release footer fix.

Features & Fixes:
1. **Exact release footer**: writes `DX V3.01 STRUK LABS` to row 17.
2. **Native title digits**: reuses the title's built-in 3, 0, and 1 glyphs.
3. **Reversible period tile**: temporarily replaces unused title digit 9 with
   a period via GDMA, then restores 9 when leaving the title.
4. **Title-safe inline hook** — keeps the proven tile-only path on the title
   screen and full tile+attr writes in gameplay. Arena remains tile-only for
   position-sweep compatibility.
5. **OBJ palette LUT** — tiles 0x70-0x7F → pal 7, matching cursor 'A' at tile 0x73 requirements.
6. **Title bg_sweep** — reads the per-scene WRAM table with its FFC1 gate
   removed so the title receives initialized attributes.
"""
import os as _os
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
    SPLASH_TABLE_ADDR, LANDING_PAD_ROM_ADDR, LANDING_PAD_WRAM,
    LEVELSEL_STUB_ROM_ADDR, LEVELSEL_STUB_WRAM, LEVELSEL_PATCH_ADDR,
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
TITLE_GLYPH_DATA_ADDR = 0x6D50  # period + native digit-9 restore tiles
VRAM_GLYPH_COPY_ADDR = 0x6DA7   # gap: end of RLE expander -> COLORIZE_ADDR
TITLE_FOOTER = "DX V3.01 STRUK LABS"
CUSTOM_TITLE_TILES = {
    # 0x75 is swallowed by the title command parser as a control value.
    ".": 0x7F,
    "0": 0x76,
    "1": 0x77,
    "3": 0x79,
}

PERIOD_TILE = bytes.fromhex("00 00 00 00 00 00 00 00 00 00 00 00 18 18 00 00")
NATIVE_DIGIT_9_TILE = bytes.fromhex(
    "00 00 7C 7C C6 C6 C6 C6 7E 7E 06 06 C6 C6 7C 7C"
)


def build_title_glyph_blob() -> bytes:
    """Period tile plus the CGB boot-font 9 tile restored after the title."""
    return PERIOD_TILE + NATIVE_DIGIT_9_TILE


def build_vram_glyph_copy() -> bytes:
    """Build the gated VBlank helper for the exact v3.01 footer glyphs.

    LCDC uses signed BG tile addressing on the title, so IDs 0x76-0x7F are at
    VRAM 0x9760-0x97FF, not 0x8760. Native tiles already provide 0, 1, and 3.
    Tile 0x7F is temporarily replaced with a period, then its native 9 glyph is
    restored after leaving the title. Both writes use one-block CGB GDMA.
    """
    c = bytearray()
    c.extend([0xF0, 0x4F, 0xF5])          # LDH A,[FF4F]; PUSH AF

    # Select VRAM Bank 0 for the tilemap signature and tile data.
    c.extend([0xAF, 0xE0, 0x4F])

    # Title path for D880 0/1; all other scenes restore the native digit 9.
    c.extend([0xFA, 0x80, 0xD8, 0xFE, 0x02])
    j_restore_nine = len(c) + 1
    c.extend([0x30, 0x00])                # JR NC, restore_nine

    # Wait until the footer's native 3 has been placed in the active tilemap.
    c.extend([0xFA, 0x45, 0x9A])          # LD A, [0x9A45]
    c.extend([0xFE, CUSTOM_TITLE_TILES["3"]])
    j_skip_footer = len(c) + 1
    c.extend([0x20, 0x00])                # JR NZ, copy_done
    c.extend([0xFA, 0xFC, 0x97])          # LD A, [0x97FC] (tile 0x7F row 6)
    c.extend([0xFE, 0x18])
    j_skip_loaded = len(c) + 1
    c.extend([0x28, 0x00])                # JR Z, copy_done

    def emit_gdma(source_addr: int) -> None:
        for register, value in (
            (0x51, (source_addr >> 8) & 0xFF),
            (0x52, source_addr & 0xF0),
            (0x53, 0x17),                  # destination 0x9700 page
            (0x54, 0xF0),                  # destination 0x97F0
            (0x55, 0x00),                  # one 16-byte block, GDMA mode
        ):
            c.extend([0x3E, value, 0xE0, register])

    emit_gdma(TITLE_GLYPH_DATA_ADDR)
    j_title_done = len(c) + 1
    c.extend([0x18, 0x00])                # JR copy_done

    restore_nine_pos = len(c)
    c.extend([0xFA, 0xFC, 0x97, 0xFE, 0x18])
    j_skip_restore = len(c) + 1
    c.extend([0x20, 0x00])                # JR NZ, copy_done
    emit_gdma(TITLE_GLYPH_DATA_ADDR + 0x10)

    copy_done_pos = len(c)
    c[j_restore_nine] = (restore_nine_pos - j_restore_nine - 1) & 0xFF
    for jump_pos in (j_skip_footer, j_skip_loaded, j_title_done, j_skip_restore):
        c[jump_pos] = (copy_done_pos - jump_pos - 1) & 0xFF
    c.extend([0xF1, 0xE0, 0x4F])          # POP AF; LDH [FF4F], A (restore VBK)
    c.extend([0xC9])                      # RET
    return bytes(c)


def map_title_string_to_tiles(s: str) -> list[int]:
    """Map alphanumeric string to title screen tile indices.

    Mapping:
      Space  -> 0x00
      A-Z    -> 0x80 - 0x99
      0,1,3  -> 0x76, 0x77, 0x79 (native title digit tiles)
      .      -> 0x7F (temporary period; 0x75 is a parser control value)
    """
    tiles = []
    for char in s.upper():
        if char == ' ':
            tiles.append(0x00)
        elif 'A' <= char <= 'Z':
            tiles.append(0x80 + (ord(char) - ord('A')))
        elif char in CUSTOM_TITLE_TILES:
            tiles.append(CUSTOM_TITLE_TILES[char])
        else:
            raise ValueError(f"unsupported title character: {char!r}")
    return tiles


def main():
    # 1. Build base v3.01 production ROM
    build_v301()
    rom = bytearray(BASE_OUT.read_bytes())

    # 2. Encode the exact release identity. This intentionally does not depend
    # on the current git tag: detached/debug tags must not rename the ROM.
    row17_text = TITLE_FOOTER
    row17_tiles = map_title_string_to_tiles(row17_text)
    assert len(row17_tiles) == 19
    print(f"  release footer: '{row17_text}'")

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
        + [0x00, 0x11] + row17_tiles + [E]                      # "DX V3.01 STRUK LABS"
        + [E]                                                   # Explicit list terminator 0x9A
    )
    assert len(title_list) <= 125, f"title list {len(title_list)} > 125 bytes"
    assert rom[0x4EA5:0x4EA7] == bytes([0x07, 0x03]), "title list head moved"
    rom[0x4EA5:0x4EA5 + len(title_list)] = title_list
    print(f"  title: PENTA DRAGON DX header + '{row17_text}' ({len(title_list)}/125 bytes @0x4EA5)")

    # 3. Store the period and native digit-9 restore tiles in the aligned gap
    # between bg_sweep and the RLE expander.
    glyph_blob = build_title_glyph_blob()
    assert len(glyph_blob) == 32
    assert TITLE_GLYPH_DATA_ADDR + len(glyph_blob) <= EXPAND_ADDR
    off = BANK13 + (TITLE_GLYPH_DATA_ADDR - 0x4000)
    assert rom[off:off + len(glyph_blob)] == bytes(len(glyph_blob)), \
        "title glyph data region is no longer free"
    rom[off:off + len(glyph_blob)] = glyph_blob
    print(f"  period + digit-9 restore: {len(glyph_blob)} bytes at bank13:0x{TITLE_GLYPH_DATA_ADDR:04X}")

    # 4. Store the glyph loader immediately after the RLE expander's reserved
    # range. A later boundary assertion verifies the generated expander fits.
    vram_copy_code = build_vram_glyph_copy()
    assert VRAM_GLYPH_COPY_ADDR + len(vram_copy_code) <= COLORIZE_ADDR
    off = BANK13 + (VRAM_GLYPH_COPY_ADDR - 0x4000)
    assert rom[off:off + len(vram_copy_code)] == bytes(len(vram_copy_code)), \
        "VRAM glyph-copy region is no longer free"
    rom[off:off + len(vram_copy_code)] = vram_copy_code
    print(f"  VRAM glyph loader: {len(vram_copy_code)} bytes at bank13:0x{VRAM_GLYPH_COPY_ADDR:04X}")

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

    # 12. Re-patch bg_sweep to read WRAM 0xCC00 (per-scene), including on the
    # title. The title-safe inline hook avoids the input corruption; this
    # sweep is still required to replace all-white boot attributes.
    sweep = bytearray(create_bg_sweep_viewport_gated(WRAM_BG_TABLE, BG_SWEEP_ADDR))
    assert sweep[:4] == bytearray([0xF0, 0xC1, 0xB7, 0xC8])
    sweep[0:4] = bytearray([0x00, 0x00, 0x00, 0x00])
    assert BG_SWEEP_ADDR + len(sweep) <= TITLE_GLYPH_DATA_ADDR, \
        "bg_sweep collides with title glyph data"
    off = BANK13 + (BG_SWEEP_ADDR - 0x4000)
    rom[off:off + len(sweep)] = sweep
    print(f"  bg_sweep: WRAM 0x{WRAM_BG_TABLE:04X}, title-enabled ({len(sweep)} bytes)")

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
    assert EXPAND_ADDR + len(expander) <= VRAM_GLYPH_COPY_ADDR, \
        "RLE expander collides with VRAM glyph loader"
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

    # 14. INLINE HOOK: title-safe tile-only path. The ungated variant corrupts
    # title-menu input state; the independent BG sweep still owns title attrs.
    from build_v301_gdma import create_inline_tile_copy_tileonly
    inline_code = create_inline_tile_copy_tileonly(
        arena_neutralize_d880=0x0C,
        title_gate=0x02)
    available = 0x436D - 0x42A7 + 1
    assert len(inline_code) <= available
    rom[0x42A7:0x42A7 + len(inline_code)] = inline_code
    if len(inline_code) < available:
        rom[0x42A7 + len(inline_code):0x436E] = bytearray(available - len(inline_code))
    assert rom[0x42A0:0x42A7] == bytearray([0x26, 0x9C, 0xC3, 0xA7, 0x42, 0x26, 0x98])
    print(f"  inline hook: title-gated tile+attr ({len(inline_code)} bytes)")

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

    # 16. VBlank wrapper at 0x6F30. Preserve the proven v3.01 cold-boot timing:
    # joypad -> teleport/colorizer first, then the one-shot footer helper.
    # Sound remains owned by the original game; a second call here churns it.
    assert TELEPORT_ADDR + len(tp) <= WRAPPER_ADDR
    wrapper = bytearray([
        0xC5,                                 # PUSH BC
        0xD5,                                 # PUSH DE
        0xE5,                                 # PUSH HL
        # Robust joypad sampler inherited from the proven v3.01 wrapper.
        # FF93 is consumed by the game and by the teleport combo detector.
        0x3E, 0x20,                           # LD A, 0x20 (directions)
        0xE0, 0x00,                           # LDH [FF00], A
        0xF0, 0x00, 0xF0, 0x00,              # settle reads
        0x2F, 0xE6, 0x0F, 0xCB, 0x37, 0x47,  # CPL; AND 0x0F; SWAP A; LD B,A
        0x3E, 0x10,                           # LD A, 0x10 (buttons)
        0xE0, 0x00,                           # LDH [FF00], A
        0xF0, 0x00, 0xF0, 0x00,              # eight settle reads
        0xF0, 0x00, 0xF0, 0x00,
        0xF0, 0x00, 0xF0, 0x00,
        0xF0, 0x00, 0xF0, 0x00,
        0x2F, 0xE6, 0x0F, 0xB0,              # CPL; AND 0x0F; OR B
        0xE0, 0x93,                           # LDH [FF93], A
        0x47,                                 # LD B, A
        0x3E, 0x30, 0xE0, 0x00, 0x78,        # deselect; restore buttons in A
        # CALL teleport (includes scene_detect + lava + colorize JP)
        0xCD, TELEPORT_ADDR & 0xFF, (TELEPORT_ADDR >> 8) & 0xFF,
        # One-shot period + v3.01 digits + footer attributes. Keeping this
        # after colorize prevents it from delaying first-VBlank CRAM writes.
        0xCD, VRAM_GLYPH_COPY_ADDR & 0xFF, (VRAM_GLYPH_COPY_ADDR >> 8) & 0xFF,
        # Restore registers
        0xE1,                                 # POP HL
        0xD1,                                 # POP DE
        0xC1,                                 # POP BC
        0xC9,                                 # RET
    ])
    assert WRAPPER_ADDR + len(wrapper) <= LANDING_PAD_ROM_ADDR
    wrapper_off = BANK13 + (WRAPPER_ADDR - 0x4000)
    rom[wrapper_off:wrapper_off + len(wrapper)] = wrapper
    print(f"  VBlank wrapper (with VRAM glyph copy): {len(wrapper)} bytes at bank13:0x{WRAPPER_ADDR:04X}")

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
