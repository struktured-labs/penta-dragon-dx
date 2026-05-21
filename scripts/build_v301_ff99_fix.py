#!/usr/bin/env python3
"""Test the FF99-fix hypothesis: keep IRQs enabled, but update FF99 too.

Our hook switches bank to 13 via `LD [0x2100], A` but DOESN'T update FF99.
The game's STAT (0x0853) and Timer (0x06B3) ISRs both restore bank from
FF99 at exit. If they fire during our handler, they put bank back to the
game's stale FF99 value (e.g., bank 1), and our code execution corrupts.

Fix: also write 0x0D to FF99 when we map bank 13 in the hook, and restore
FF99 to the saved value at hook exit. Then ISRs restore bank 13 correctly.

Uses the freezing 2-rows-unroll attr_comp as the test workload — if FF99
fix is sufficient, this passes WITHOUT IE masking.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from bg_experiment import (load_palettes_from_yaml, create_tile_based_colorizer,
    create_shadow_colorizer_main, create_palette_loader, create_tile_to_palette_subroutine)
from create_vblank_colorizer_v288 import create_conditional_palette_cached
from build_v296_phantomsafe import create_bg_sweep_viewport_gated
from build_v301_gdma import BG_TABLE_BYTES, WRAM_BG_TABLE, create_inline_tile_copy_tileonly
from build_v301_iemask import create_2rows_unroll
# Also import the original 8-chunk attr_comp for the full-load test
import build_v301_attr_enabled as full_mod
import importlib.util as _u
_spec = _u.spec_from_file_location("ag_old", str(Path(__file__).parent / "build_v301_gdma.py"))
_orig_v301 = _u.module_from_spec(_spec); _spec.loader.exec_module(_orig_v301)


def build():
    rom = bytearray(Path("rom/Penta Dragon (J).gb").read_bytes())
    palettes = load_palettes_from_yaml(Path("palettes/penta_palettes_v097.yaml"))
    bg_data = bytearray(palettes['bg_data']); bg_data[56:64] = bg_data[0:8]
    palettes = {**palettes, 'bg_data': bytes(bg_data)}
    rom[0x143] = 0x80
    bank13 = 13 * 0x4000
    A = {'pal':0x6800,'bp':0x6880,'bs':0x68C0,'swj':0x68D0,'sdj':0x68D8,
         'sp':0x68E0,'shp':0x68E8,'tp':0x68F0,'pl':0x6900,'shm':0x69D0,
         'co':0x6A10,'tps':0x6B00,'cp':0x6C90,'sw':0x6CD0,'cz':0x6E00,
         'bt':0x7000,'ac':0x7100}
    def w(a,d): rom[bank13+(a-0x4000):bank13+(a-0x4000)+len(d)] = d
    w(A['pal'], palettes['bg_data']); w(A['pal']+64, palettes['obj_data'])
    w(A['bp'], palettes['boss_palette_table']); w(A['bs'], palettes['boss_slot_table'])
    w(A['swj'], palettes['sara_witch_jet']); w(A['sdj'], palettes['sara_dragon_jet'])
    w(A['sp'], palettes['spiral_proj']); w(A['shp'], palettes['shield_proj'])
    w(A['tp'], palettes['turbo_proj'])
    w(A['pl'], create_palette_loader(A['pal'], A['bp'], A['bs'], A['swj'], A['sdj'], A['sp'], A['shp'], A['tp']))
    w(A['shm'], create_shadow_colorizer_main(A['co'], A['bs']))
    colz = bytearray(create_tile_based_colorizer(A['co'])); colz[1] = 0x0A
    w(A['co'], bytes(colz))
    w(A['tps'], create_tile_to_palette_subroutine())
    w(A['bt'], BG_TABLE_BYTES)
    w(A['cp'], create_conditional_palette_cached(A['pl']))
    sw = bytearray(create_bg_sweep_viewport_gated(A['bt'], A['sw'])); sw[0:4] = bytes(4)
    w(A['sw'], bytes(sw))
    # Use the CURRENT per-row attr_comp (production design from build_v301_gdma.py)
    # to verify FF99 fix is compatible with the production path.
    # For variant testing, swap to create_2rows_unroll or attr_enabled's full 8-chunk.
    import sys as _s
    test_variant = _s.argv[1] if len(_s.argv) > 1 else "perrow"
    if test_variant == "perrow":
        w(A['ac'], _orig_v301.create_attr_computation(A['bt']))
        print(f"  using PRODUCTION per-row attr_comp")
    elif test_variant == "2rows":
        w(A['ac'], create_2rows_unroll(A['bt']))
        print(f"  using freezing 2-rows-unroll attr_comp")
    else:
        raise ValueError(f"unknown variant {test_variant}")

    # Colorize handler with FF99 fix: save FF99, set FF99=0x0D, do work,
    # restore FF99. Now any ISR that fires during our handler will see
    # FF99=0x0D and restore bank 13 correctly.
    code = bytearray()
    code.extend([0xF0, 0x99, 0xF5])             # LDH A, [FF99]; PUSH AF (save FF99)
    code.extend([0x3E, 0x0D, 0xE0, 0x99])       # LD A, 0x0D; LDH [FF99], A
    code.extend([0xF0, 0x4F, 0xF5, 0xAF, 0xE0, 0x4F])   # save VBK; VBK=0
    code.extend([0xFA, 0x02, 0xDF, 0xFE, 0x5A])
    df02 = len(code) + 1
    code.extend([0x28, 0x00])
    code.extend([0x3E, 0x5A, 0xEA, 0x02, 0xDF])
    code.extend([0xAF, 0xEA, 0x00, 0xDF, 0xAF, 0xEA, 0x03, 0xDF])
    code.extend([0x21, A['bt'] & 0xFF, (A['bt'] >> 8) & 0xFF])
    code.extend([0x11, WRAM_BG_TABLE & 0xFF, (WRAM_BG_TABLE >> 8) & 0xFF])
    code.extend([0x06, 0x00])
    bg = len(code)
    code.extend([0x2A, 0x12, 0x13, 0x05])
    code.extend([0x20, (bg - (len(code) + 2)) & 0xFF])
    code[df02] = (len(code) - df02 - 1) & 0xFF
    code.extend([0xCD, A['cp'] & 0xFF, (A['cp'] >> 8) & 0xFF])
    code.extend([0xCD, A['sw'] & 0xFF, (A['sw'] >> 8) & 0xFF])
    code.extend([0xF0, 0xC1, 0xB7])
    fg = len(code) + 1
    code.extend([0x28, 0x00])
    code.extend([0xCD, 0x80, 0xFF])
    code.extend([0xCD, A['shm'] & 0xFF, (A['shm'] >> 8) & 0xFF])
    code.extend([0xCD, A['ac'] & 0xFF, (A['ac'] >> 8) & 0xFF])
    code[fg] = (len(code) - fg - 1) & 0xFF
    code.extend([0xF1, 0xE0, 0x4F])              # restore VBK
    code.extend([0xF1, 0xE0, 0x99])              # POP AF; LDH [FF99], A (restore FF99)
    code.extend([0xC9])
    w(A['cz'], bytes(code))

    # Standard hook (unchanged). FF99 fix lives inside colorize_handler now.
    cz = A['cz']
    hook = bytes([0xF0, 0x99, 0xF5, 0x3E, 0x20, 0xE0, 0x00, 0xF0, 0x00, 0x2F, 0xE6, 0x0F,
                  0xCB, 0x37, 0x47, 0x3E, 0x10, 0xE0, 0x00, 0xF0, 0x00, 0xF0, 0x00,
                  0x2F, 0xE6, 0x0F, 0xB0, 0xE0, 0x93, 0x3E, 0x30, 0xE0, 0x00,
                  0x3E, 0x0D, 0xEA, 0x00, 0x20, 0xCD, cz & 0xFF, (cz >> 8) & 0xFF,
                  0xF1, 0xEA, 0x00, 0x20, 0xC9])
    assert len(hook) <= 47, f"hook too big: {len(hook)} > 47"
    rom[0x0824:0x0824 + 47] = hook + bytes(47 - len(hook))
    rom[0x06D5:0x06D8] = bytes(3)
    rom[0x003B] = 0xC9
    inline_code = create_inline_tile_copy_tileonly()
    rom[0x42A7:0x42A7 + len(inline_code)] = inline_code
    rom[0x42A7 + len(inline_code):0x436E] = bytes(0x436D - 0x42A7 + 1 - len(inline_code))
    chk = 0
    for b in rom[0x134:0x14D]: chk = (chk - b - 1) & 0xFF
    rom[0x14D] = chk
    out = Path("rom/working/penta_dragon_dx_v301_ff99_fix.gb")
    out.write_bytes(rom)
    print(f"Wrote {out}  (hook len={len(hook)})")


if __name__ == "__main__":
    build()
