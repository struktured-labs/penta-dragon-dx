#!/usr/bin/env python3
"""Penta Dragon DX v3.02 — Title screen cursor fix.

Fixes the title screen regression where the cursor 'A' (tile 0x73) was
missing/invisible. Preserves all teleport features (O(1) OAM intercept,
scene_detect, teleport combo, position sweep, lava override, arena tables).

Fixes:
1. **Outer FFC1 gate NOP'd** — bg_sweep now runs on title (FFC1=0) to fix
   banner showcase palette corruption. v301's outer gate in the colorize
   handler skipped bg_sweep entirely when FFC1=0.
2. **Ungated inline hook** — write tile+attr on the title screen (was tile-only
   due to D880 gate). Arena still tile-only for position sweep compatibility.
3. **OBJ palette LUT** — tiles 0x70-0x7F → pal 7 (was pal 6), matching the
   proven CP-cascade assignment. Cursor 'A' at tile 0x73 needs pal 7.
4. **bg_sweep** — re-patched to WRAM 0xCC00 with FFC1 gate NOP'd (DMG NOPs
   remain removed as intended).
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

# Ensure we run from the project root
import os as _os
_script_dir = Path(__file__).parent.parent
_os.chdir(str(_script_dir))

from build_v301_gdma import (
    build_v301, load_palettes_from_yaml, create_palette_loader,
    create_shadow_colorizer_main, create_tile_based_colorizer,
    create_tile_to_palette_subroutine, create_conditional_palette_cached,
    BG_TABLE_BYTES, _bg_table,
)
from build_v296_phantomsafe import create_bg_sweep_viewport_gated
from arena_position import (
    parse_footprint_posmaps, rle_encode_posmap, create_rle_expander,
    create_position_sweep,
)
from build_v301_teleport import (
    _table_from_dict, build_scene_detect, build_lava_override,
    build_landing_pad, build_teleport_routine, build_levelsel_attr_clear_stub,
    ARENA_TILE_PAL, ARENA_ORDER, FOOTPRINT_LOG,
    _bg_table_shalamar, _bg_table_riff, _bg_table_crystal_dragon,
    _bg_table_cameo, _bg_table_ted, _bg_table_troop,
    _bg_table_faze, _bg_table_angela, _bg_table_penta_dragon,
    SPLASH_TABLE_ADDR,
)
import yaml

BASE_OUT = Path("rom/working/penta_dragon_dx_v301.gb")
OUTPUT_PATH = Path("rom/working/penta_dragon_dx_FIXED.gb")  # Overwrite FIXED.gb

# Reuse all the same constants
BANK13 = 13 * 0x4000
BG_SWEEP_ADDR = 0x6CD0
WRAM_BG_TABLE = 0xCC00
COLORIZE_ADDR = 0x6E00
TELEPORT_ADDR = 0x6E90  # moved from 0x6E80: v301's colorize handler tail at 0x6E7E-0x6E8C (FFC1 gate + shadow_main + OAM DMA + VBK restore) must be preserved
OBJ_PAL_TABLE_ADDR = 0x6B00
WRAPPER_ADDR = 0x6F40
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
PAL_ADDR = 0x6800
BOSS_PAL_ADDR = 0x6880
BOSS_SLOT_ADDR = 0x68C0
SWJ_ADDR = 0x68D0
SDJ_ADDR = 0x68D8
SP_ADDR = 0x68E0
SHP_ADDR = 0x68E8
TP_ADDR = 0x68F0
PAL_LOADER_ADDR = 0x6900
SHADOW_MAIN_ADDR = 0x69D0
COLORIZER_ADDR = 0x6A10
TILE_PAL_ADDR = 0x6B00
COND_PAL_ADDR = 0x6C90



def main():
    # 1. Build base v3.01 production ROM
    build_v301()
    rom = bytearray(BASE_OUT.read_bytes())

    # 2. Verify v301 base has the D880 gate for banner showcase (D880=0x1B/0x1C)
    #    This was applied in build_v301_gdma.py commit df4641e.
    #    The colorize handler checks D880 first; if 0x1B or 0x1C, runs bg_sweep
    #    unconditionally (bypassing the FFC1 gate). Other D880 values still
    #    honor FFC1=0 (skip bg_sweep on menus / title idle).
    colorize_off = BANK13 + (COLORIZE_ADDR - 0x4000) + 0x6E
    assert rom[colorize_off:colorize_off+5] == bytes([0xFA, 0x80, 0xD8, 0xFE, 0x1B]), \
        f"v301 base missing D880 gate at colorize_addr+0x6E: {rom[colorize_off:colorize_off+5].hex()}"
    print(f"  banner D880 gate: verified at colorize_addr+0x6E")

    # 4. Title screen text (same as teleport)
    E = 0x9A
    def _txt(s):
        return [0x00 if c == ' ' else 0x80 + (ord(c) - 65) for c in s]
    JAM = [0xD0, 0xD7, 0xD8, 0xD9, 0x00, 0x89, 0x80, 0x8F, 0x80, 0x8D, 0x00,
           0x80, 0x91, 0x93, 0x00, 0x8C, 0x84, 0x83, 0x88, 0x80]
    title_list = bytes(
        [0x07, 0x03, 0xC1, 0xC2, 0xC3, 0xC4, 0xC5, E]
        + [0x07, 0x04, 0xD1, 0xD2, 0xD3, 0xD4, 0xD5, E]
        + [0x07, 0x05, 0xC6, 0xC7, 0xC8, 0xC9, 0xD6, E]
        + [0x03, 0x06] + _txt("PENTA DRAGON DX") + [E]
        + [0x04, 0x08] + _txt("OPENING START") + [E]
        + [0x04, 0x0A] + _txt("GAME    START") + [E]
        + [0x00, 0x0E, 0xC0, E]
        + [0x00, 0x0F] + JAM + [E]
        + [0x00, 0x11, 0x83, 0x97, 0x00, 0x95, 0xD7, 0xD8, 0xD8, 0x00] + _txt("STRUK LABS") + [E]
    )
    assert len(title_list) <= 125
    assert rom[0x4EA5:0x4EA7] == bytes([0x07, 0x03]), "title list head moved"
    rom[0x4EA5:0x4EA5 + len(title_list)] = title_list
    print(f"  title: PENTA DRAGON DX header + STRUKTURED LABS ({len(title_list)}/125 bytes @0x4EA5)")

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

    # 11. OBJ palette LUT at bank13:0x6B00 (was CP-cascade subroutine)
    # FIXED: tiles 0x70-0x7F → pal 7 (was pal 6 in teleport build).
    # The original CP-cascade assigned cursor tile 0x73 → pal 7.
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
            _obj_pal[_i] = 7      # <-- FIXED: pal 7 (was 6), cursor 'A' at tile 0x73
        elif _i <= 0x8F:
            _obj_pal[_i] = 3
        else:
            _obj_pal[_i] = 4
    _obj_pal_off = BANK13 + (OBJ_PAL_TABLE_ADDR - 0x4000)
    rom[_obj_pal_off:_obj_pal_off + 256] = _obj_pal
    _vb = sum(1 for _v in _obj_pal if _v > 7 and _v != 0xFF)
    assert _vb == 0
    print(f"  OBJ palette LUT: 256 bytes at bank13:0x{OBJ_PAL_TABLE_ADDR:04X} "
          f"(tiles 0x70-0x7F → pal 7 [cursor fix])")

    # 12. Re-patch bg_sweep to read WRAM 0xCC00 (per-scene) with FFC1 NOP'd
    sweep = bytearray(create_bg_sweep_viewport_gated(WRAM_BG_TABLE, BG_SWEEP_ADDR))
    assert sweep[:4] == bytearray([0xF0, 0xC1, 0xB7, 0xC8])
    sweep[0:4] = bytearray([0x00, 0x00, 0x00, 0x00])  # DMG NOPs removed
    off = BANK13 + (BG_SWEEP_ADDR - 0x4000)
    rom[off:off + len(sweep)] = sweep
    print(f"  bg_sweep: WRAM 0x{WRAM_BG_TABLE:04X}, FFC1 gate NOP'd ({len(sweep)} bytes)")

    # 13. Position sweep (holy-grail path for arena attrs)
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

    # 14. INLINE HOOK: UNGATED tile+attr (title writes attrs too!)
    # This is the critical fix — no title_gate means attrs are written
    # on the title screen. Arena still tile-only via arena_neutralize.
    from build_v301_gdma import create_inline_tile_copy_tileonly
    inline_code = create_inline_tile_copy_tileonly(
        arena_neutralize_d880=0x0C,
        title_gate=None)        # <-- KEY FIX: no title gate
    available = 0x436D - 0x42A7 + 1
    assert len(inline_code) <= available
    rom[0x42A7:0x42A7 + len(inline_code)] = inline_code
    if len(inline_code) < available:
        rom[0x42A7 + len(inline_code):0x436E] = bytearray(available - len(inline_code))
    assert rom[0x42A0:0x42A7] == bytearray([0x26, 0x9C, 0xC3, 0xA7, 0x42, 0x26, 0x98])
    print(f"  inline hook: UNGATED tile+attr ({len(inline_code)} bytes, "
          f"{available - len(inline_code)} free) — title=full, dungeon=full, arena=tile-only")

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

    # 16. VBlank wrapper at 0x6F30
    assert TELEPORT_ADDR + len(tp) <= WRAPPER_ADDR
    wrapper = bytearray([
        0xF5,                                 # PUSH AF  (save for sound engine compat)
        0xC5,                                 # PUSH BC
        0xD5,                                 # PUSH DE
        0xE5,                                 # PUSH HL
        0x3E, 0x20,                           # LD A, 0x20
        0xE0, 0x00,                           # LDH [FF00], A
        0xF0, 0x00,                           # LDH A, [FF00]
        0xF0, 0x00,                           # LDH A, [FF00]
        0x2F,                                 # CPL
        0xE6, 0x0F,                           # AND 0x0F
        0xCB, 0x37,                           # SWAP A
        0x47,                                 # LD B, A
        0x3E, 0x10,                           # LD A, 0x10
        0xE0, 0x00,                           # LDH [FF00], A
        0xF0, 0x00,                           # LDH A, [FF00]
        0xF0, 0x00,                           # LDH A, [FF00]
        0xF0, 0x00,                           # LDH A, [FF00]
        0xF0, 0x00,                           # LDH A, [FF00]
        0xF0, 0x00,                           # LDH A, [FF00]
        0xF0, 0x00,                           # LDH A, [FF00]
        0xF0, 0x00,                           # LDH A, [FF00]
        0xF0, 0x00,                           # LDH A, [FF00]
        0x2F,                                 # CPL
        0xE6, 0x0F,                           # AND 0x0F
        0xB0,                                 # OR B
        0xE0, 0x93,                           # LDH [FF93], A
        0x47,                                 # LD B, A
        0x3E, 0x30,                           # LD A, 0x30
        0xE0, 0x00,                           # LDH [FF00], A
        0x78,                                 # LD A, B
        0xCD, TELEPORT_ADDR & 0xFF, (TELEPORT_ADDR >> 8) & 0xFF,  # CALL teleport
        0xCD, 0x80, 0xFF,                     # CALL 0xFF80  — sound engine VBlank update
        0xE1,                                 # POP HL
        0xD1,                                 # POP DE
        0xC1,                                 # POP BC
        0xF1,                                 # POP AF
        0xC9,                                 # RET
    ])
    assert WRAPPER_ADDR + len(wrapper) <= LANDING_PAD_ROM_ADDR
    wrapper_off = BANK13 + (WRAPPER_ADDR - 0x4000)
    rom[wrapper_off:wrapper_off + len(wrapper)] = wrapper
    print(f"  VBlank wrapper: {len(wrapper)} bytes at bank13:0x{WRAPPER_ADDR:04X}")

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
    
    # Auto-launch gate: verify ROM boots before returning
    try:
        import subprocess
        _sd = Path(__file__).parent
        result = subprocess.run(
            [sys.executable, str(_sd / "launch_gate.py"), str(OUTPUT_PATH)],
            capture_output=True, text=True, timeout=60
        )
        if result.returncode == 0:
            print(f"  ✅ LAUNCH GATE PASSED: {OUTPUT_PATH.name} boots correctly")
        else:
            print(f"  ❌ LAUNCH GATE FAILED: {OUTPUT_PATH.name} white screen freeze detected")
            print(f"     {result.stdout.strip()}")
            print(f"     {result.stderr.strip()}")
    except Exception as e:
        print(f"  ⚠️  Launch gate skipped: {e}")
    
    return OUTPUT_PATH


if __name__ == "__main__":
    main()
