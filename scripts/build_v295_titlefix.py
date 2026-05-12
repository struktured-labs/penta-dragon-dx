#!/usr/bin/env python3
"""Penta Dragon DX v2.95 — narrower fix than v2.94.

v2.94 fixed the white title and BG colorization but introduced a visible
"green ball" / weird-rectangle artifact on the title (and stray-color
flashes during gameplay). Root cause: with OBJ palette loaded AND
DMA always-on, OAM data that previously rendered "white-on-white invisible"
in v2.90 now renders colored. And running bg_sweep on title applied the
in-game bg_tile_table palette mapping to title tiles whose IDs happen to
fall in colored-palette ranges → wrong colors on title art.

v2.95 keeps the cond_pal-before-FFC1 change (so palette RAM actually loads
on title) but reverts:

  - bg_sweep stays gated by FFC1=1 (no BG-attr writes on title; title tiles
    keep default palette 0, which has color 0 = white → looks like vanilla
    grayscale title)
  - DMA gated by FFC1=1 (no spurious OAM updates while on title; sprite
    data stays whatever boot ROM left it as)

Net effect:
  - Title: BG palette gets loaded (so colors are present), but BG attrs
    stay at default (pal 0), so title looks like vanilla DMG grayscale
    rendered through pal0 — color 0 = white. That's an improvement over
    v2.90 (which was pure FFFFFF white) and better than v2.94 (which had
    visible artifacts).
  - Gameplay: identical to v2.90 (proven working BG colorization).
  - Phantom sound: identical to v2.90 (proven 2 transitions, beats vanilla 12).
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from bg_experiment import (
    load_palettes_from_yaml, create_tile_based_colorizer,
    create_shadow_colorizer_main, create_palette_loader,
    create_tile_to_palette_subroutine, create_bg_tile_table,
)
from create_vblank_colorizer_v288 import create_conditional_palette_cached
from build_v290_final import create_bg_sweep_v8


def build_v295():
    input_rom = Path("rom/Penta Dragon (J).gb")
    output_path = Path("rom/working/penta_dragon_dx_v295.gb")
    palette_yaml = Path("palettes/penta_palettes_v097.yaml")

    rom = bytearray(input_rom.read_bytes())
    palettes = load_palettes_from_yaml(palette_yaml)

    rom[0x143] = 0x80  # CGB flag

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
    colorizer[1] = 0x0A
    w(colorizer_addr, bytes(colorizer))

    w(tile_pal_addr, create_tile_to_palette_subroutine())
    w(bg_table_addr, create_bg_tile_table(ff_filter=False))
    w(cond_pal_addr, create_conditional_palette_cached(pal_loader_addr))

    # Standard v290 bg_sweep — still has internal FFC1=0 RET Z, so it does
    # nothing on title screens. That's intentional in v295.
    sweep = create_bg_sweep_v8(bg_table_addr, bg_sweep_addr)
    w(bg_sweep_addr, sweep)

    # COLORIZE HANDLER (v295 layout):
    #   VBK save → DF02 cold-boot init → cond_pal (always, fixes title white)
    #   → FFC1 gate { bg_sweep, OBJ colorizer, DMA } → VBK restore
    #
    # The CRITICAL fix vs v2.94: bg_sweep + OBJ + DMA all gated together on
    # FFC1=1. So title (FFC1=0) just gets palette RAM loaded and nothing
    # else — no stray tile attrs, no stray OAM updates. Sprite data stays
    # whatever the boot ROM / game placed there.
    code = bytearray()
    code.extend([0xF0, 0x4F, 0xF5, 0xAF, 0xE0, 0x4F])  # VBK save + VBK=0
    # DF02 cold-boot init (zero DF00 so first cond_pal hash differs)
    code.extend([0xFA, 0x02, 0xDF, 0xFE, 0x5A])
    df02 = len(code) + 1; code.extend([0x28, 0x00])
    code.extend([0x3E, 0x5A, 0xEA, 0x02, 0xDF,
                 0xAF, 0xEA, 0x00, 0xDF])
    code[df02] = (len(code) - df02 - 1) & 0xFF
    # cond_pal ALWAYS — fixes title-screen white
    code.extend([0xCD, cond_pal_addr & 0xFF, (cond_pal_addr >> 8) & 0xFF])
    # FFC1 gate — everything below is gameplay-only
    code.extend([0xF0, 0xC1, 0xB7])
    skip = len(code) + 1; code.extend([0x28, 0x00])
    code.extend([0xCD, bg_sweep_addr & 0xFF, (bg_sweep_addr >> 8) & 0xFF])
    code.extend([0xCD, shadow_main_addr & 0xFF, (shadow_main_addr >> 8) & 0xFF])
    code.extend([0xCD, 0x80, 0xFF])                     # DMA (gameplay only)
    code[skip] = (len(code) - skip - 1) & 0xFF
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
    assert len(hook) <= 47
    rom[0x0824:0x0824 + 47] = (hook + bytearray(47 - len(hook)))[:47]
    rom[0x06D5:0x06D8] = bytearray([0x00, 0x00, 0x00])

    rom[0x003B] = 0xC9  # RETI → RET (phantom-sound belt-and-suspenders)

    chk = 0
    for b in rom[0x134:0x14D]:
        chk = (chk - b - 1) & 0xFF
    rom[0x14D] = chk

    output_path.write_bytes(rom)
    print(f"Wrote {output_path} ({len(rom)} bytes)")
    return output_path


if __name__ == "__main__":
    build_v295()
