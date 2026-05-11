#!/usr/bin/env python3
"""Penta Dragon DX v2.92 — title-screen palette fix on top of v2.90.

Bug in v2.90: combined handler checks FFC1 BEFORE calling cond_pal. When
FFC1=0 (title screen / menus), cond_pal is skipped entirely. CGB boot ROM
defaults BG palette RAM to all-white → 100% white title.

Fix: Move cond_pal call BEFORE the FFC1 check. Pattern matches v2.88's
create_combined_minimal where cond_pal is unconditional and only the OBJ
colorizer + bg_sweep are gated on FFC1=1.

Verification: scripts/probes/verify_title_color.py — must show 3+ distinct
colors in captured title-screen screenshot. v2.90 / FIXED show 1; this
build should show 4+.

This script is otherwise IDENTICAL to build_v290_final.py — only the
colorize_addr handler bytes change.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from bg_experiment import (
    load_palettes_from_yaml, create_tile_based_colorizer,
    create_shadow_colorizer_main, create_palette_loader,
    create_tile_to_palette_subroutine, create_bg_tile_table,
)
from create_vblank_colorizer_v288 import create_conditional_palette_cached
from build_v290_final import create_bg_sweep_v8


def build_v292():
    input_rom = Path("rom/Penta Dragon (J).gb")
    output_path = Path("rom/working/penta_dragon_dx_v292.gb")
    palette_yaml = Path("palettes/penta_palettes_v097.yaml")

    rom = bytearray(input_rom.read_bytes())
    palettes = load_palettes_from_yaml(palette_yaml)

    # CGB flag (same as v290)
    rom[0x143] = 0x80

    # Bank 13 layout — identical to v290
    bank13 = 13 * 0x4000
    pal_addr = 0x6800; boss_pal_addr = 0x6880; boss_slot_addr = 0x68C0
    swj_addr = 0x68D0; sdj_addr = 0x68D8
    sp_addr = 0x68E0; shp_addr = 0x68E8; tp_addr = 0x68F0
    pal_loader_addr = 0x6900
    shadow_main_addr = 0x69D0
    colorizer_addr = 0x6A10
    tile_pal_addr = 0x6B00
    bg_table_addr = 0x7000
    cond_pal_addr = 0x6C90
    bg_sweep_addr = 0x6CD0
    colorize_addr = 0x6E00

    def w(addr, data):
        off = bank13 + (addr - 0x4000)
        rom[off:off + len(data)] = data

    # Palette + function data (identical to v290)
    w(pal_addr, palettes['bg_data'])
    w(pal_addr + 64, palettes['obj_data'])
    w(boss_pal_addr, palettes['boss_palette_table'])
    w(boss_slot_addr, palettes['boss_slot_table'])
    w(swj_addr, palettes['sara_witch_jet'])
    w(sdj_addr, palettes['sara_dragon_jet'])
    w(sp_addr, palettes['spiral_proj'])
    w(shp_addr, palettes['shield_proj'])
    w(tp_addr, palettes['turbo_proj'])

    w(pal_loader_addr, create_palette_loader(
        pal_addr, boss_pal_addr, boss_slot_addr,
        swj_addr, sdj_addr, sp_addr, shp_addr, tp_addr))
    w(shadow_main_addr, create_shadow_colorizer_main(colorizer_addr, boss_slot_addr))

    colorizer = bytearray(create_tile_based_colorizer(colorizer_addr))
    colorizer[1] = 0x0A  # 10 sprites per page
    w(colorizer_addr, bytes(colorizer))

    w(tile_pal_addr, create_tile_to_palette_subroutine())
    w(bg_table_addr, create_bg_tile_table(ff_filter=False))
    w(cond_pal_addr, create_conditional_palette_cached(pal_loader_addr))

    sweep = create_bg_sweep_v8(bg_table_addr, bg_sweep_addr)
    w(bg_sweep_addr, sweep)

    # ----- COLORIZE HANDLER (THE FIX) -----
    # v290 order:    VBK save → FFC1 check → DF02 init → cond_pal → bg_sweep → OBJ → DMA
    # v292 fix:      VBK save → DF02 init → cond_pal (always) → FFC1 check → bg_sweep → OBJ → DMA
    #
    # The DF02-init block forces a clean DF00=0 on cold boot so cond_pal's
    # internal hash check definitely fires the palette load. Without this,
    # DF00 is whatever random WRAM value was there, which can match the
    # first computed hash and cause the load to be skipped.
    #
    # cond_pal CALL itself moves BEFORE the FFC1 check (was the actual bug).
    code = bytearray()
    code.extend([0xF0, 0x4F, 0xF5, 0xAF, 0xE0, 0x4F])  # VBK save + VBK=0
    # DF02 cold-boot init (zero DF00 so first cond_pal hash differs → load fires)
    code.extend([0xFA, 0x02, 0xDF, 0xFE, 0x5A])        # LD A,[DF02]; CP 0x5A
    df02 = len(code) + 1; code.extend([0x28, 0x00])    # JR Z → cond_pal call
    code.extend([0x3E, 0x5A, 0xEA, 0x02, 0xDF,         # LD A,0x5A; LD [DF02],A
                 0xAF, 0xEA, 0x00, 0xDF])              # XOR A; LD [DF00],A
    code[df02] = (len(code) - df02 - 1) & 0xFF
    # cond_pal is UNCONDITIONAL — fixes title-screen white
    code.extend([0xCD, cond_pal_addr & 0xFF, (cond_pal_addr >> 8) & 0xFF])
    # Now check FFC1 to gate the heavier work (bg_sweep + OBJ colorizer)
    code.extend([0xF0, 0xC1, 0xB7])                    # LDH A,[FFC1]; OR A
    skip = len(code) + 1; code.extend([0x28, 0x00])    # JR Z → DMA
    code.extend([0xCD, bg_sweep_addr & 0xFF, (bg_sweep_addr >> 8) & 0xFF])
    code.extend([0xCD, shadow_main_addr & 0xFF, (shadow_main_addr >> 8) & 0xFF])
    code[skip] = (len(code) - skip - 1) & 0xFF
    code.extend([0xCD, 0x80, 0xFF])                    # DMA
    code.extend([0xF1, 0xE0, 0x4F, 0xC9])              # VBK restore + RET
    w(colorize_addr, bytes(code))

    # VBlank hook (identical to v290)
    hook = bytearray([
        0xF0, 0x99, 0xF5,
        0x3E, 0x20, 0xE0, 0x00, 0xF0, 0x00,
        0x2F, 0xE6, 0x0F, 0xCB, 0x37, 0x47,
        0x3E, 0x10, 0xE0, 0x00,
        0xF0, 0x00, 0xF0, 0x00,
        0x2F, 0xE6, 0x0F, 0xB0, 0xE0, 0x93,
        0x3E, 0x30, 0xE0, 0x00,
        0x3E, 0x0D, 0xEA, 0x00, 0x20,
        0xCD, colorize_addr & 0xFF, (colorize_addr >> 8) & 0xFF,
        0xF1, 0xEA, 0x00, 0x20,
        0xC9,
    ])
    assert len(hook) <= 47, f"Hook is {len(hook)} bytes, max 47"
    rom[0x0824:0x0824 + 47] = (hook + bytearray(47 - len(hook)))[:47]

    # NOP original DMA
    rom[0x06D5:0x06D8] = bytearray([0x00, 0x00, 0x00])

    # Phantom-sound fix (identical to v288+)
    rom[0x003B] = 0xC9  # RETI → RET at RST $38

    # Fix header checksum
    chk = 0
    for b in rom[0x0134:0x014D]:
        chk = (chk - b - 1) & 0xFF
    rom[0x014D] = chk

    output_path.write_bytes(rom)
    print(f"Wrote {output_path} ({len(rom)} bytes)")
    return output_path


if __name__ == "__main__":
    build_v292()
