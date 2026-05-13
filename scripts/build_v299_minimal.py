#!/usr/bin/env python3
"""Penta Dragon DX v2.99 — minimal colorization (no wall palette).

Theory: the visible "purple/slate specks" the user reports on dungeon
floors are *correctly-placed* wall/structure tiles (per the manual
palettes/bg_tile_categories.yaml ground truth) using pal6/slate, which
visually contrasts hard with adjacent floor tiles (pal0 blue-white).

Even when classification is right, the SEAM between adjacent palettes
is the jarring artifact. Solution: minimize palette differentiation:

  - All structural tiles (floor, walls, edges, decorations, void) → pal0
  - Items (0x88-0xDF) → pal1 (light blue / item-stand-out)
  - Hazards (spike cylinders + thrusting spikes) → pal5 (red/orange warning)

Net: floor + walls look uniform (no seam), items pop, hazards warn.
Title + phantom + boss colors unchanged.

Architecture: v2.96-phantomsafe sweep + v2.95 colorize handler. Same
no-trampoline phantom-safe core, just a sparser bg_table.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from bg_experiment import (
    load_palettes_from_yaml, create_tile_based_colorizer,
    create_shadow_colorizer_main, create_palette_loader,
    create_tile_to_palette_subroutine,
)
from create_vblank_colorizer_v288 import create_conditional_palette_cached
from build_v296_phantomsafe import create_bg_sweep_viewport_gated


def _minimal_bg_table() -> bytes:
    """Default everything to pal0 except items and hazards."""
    table = bytearray(256)  # init to pal0 everywhere
    # Spike cylinder hazards
    for i in [0x2A, 0x2B, 0x2C, 0x2D, 0x2E, 0x3A, 0x3B, 0x3C, 0x3D]:
        table[i] = 5
    # Thrusting wall spikes
    table[0x47] = 5
    table[0x57] = 5
    # Items (0x88-0xDF)
    for i in range(0x88, 0xE0):
        table[i] = 1
    # Sentinel for ff_filter
    table[0xFF] = 0xFF
    return bytes(table)


BG_TABLE_BYTES = _minimal_bg_table()
assert len(BG_TABLE_BYTES) == 256


def build_v299():
    input_rom = Path("rom/Penta Dragon (J).gb")
    output_path = Path("rom/working/penta_dragon_dx_v299.gb")
    palette_yaml = Path("palettes/penta_palettes_v097.yaml")

    rom = bytearray(input_rom.read_bytes())
    palettes = load_palettes_from_yaml(palette_yaml)
    rom[0x143] = 0x80

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
    w(bg_table_addr, BG_TABLE_BYTES)
    w(cond_pal_addr, create_conditional_palette_cached(pal_loader_addr))
    sweep = create_bg_sweep_viewport_gated(bg_table_addr, bg_sweep_addr)
    assert len(sweep) <= (colorize_addr - bg_sweep_addr)
    w(bg_sweep_addr, sweep)

    code = bytearray()
    code.extend([0xF0, 0x4F, 0xF5, 0xAF, 0xE0, 0x4F])
    code.extend([0xFA, 0x02, 0xDF, 0xFE, 0x5A])
    df02 = len(code) + 1; code.extend([0x28, 0x00])
    code.extend([0x3E, 0x5A, 0xEA, 0x02, 0xDF, 0xAF, 0xEA, 0x00, 0xDF])
    code[df02] = (len(code) - df02 - 1) & 0xFF
    code.extend([0xCD, cond_pal_addr & 0xFF, (cond_pal_addr >> 8) & 0xFF])
    code.extend([0xF0, 0xC1, 0xB7])
    skip = len(code) + 1; code.extend([0x28, 0x00])
    code.extend([0xCD, bg_sweep_addr & 0xFF, (bg_sweep_addr >> 8) & 0xFF])
    code.extend([0xCD, shadow_main_addr & 0xFF, (shadow_main_addr >> 8) & 0xFF])
    code.extend([0xCD, 0x80, 0xFF])
    code[skip] = (len(code) - skip - 1) & 0xFF
    code.extend([0xF1, 0xE0, 0x4F, 0xC9])
    w(colorize_addr, bytes(code))

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
    rom[0x003B] = 0xC9

    chk = 0
    for b in rom[0x134:0x14D]:
        chk = (chk - b - 1) & 0xFF
    rom[0x14D] = chk

    output_path.write_bytes(rom)
    print(f"Wrote {output_path} ({len(rom)} bytes)")
    n_pal0 = sum(1 for b in BG_TABLE_BYTES if b == 0)
    n_pal1 = sum(1 for b in BG_TABLE_BYTES if b == 1)
    n_pal5 = sum(1 for b in BG_TABLE_BYTES if b == 5)
    print(f"  bg_table: pal0={n_pal0}  pal1={n_pal1}  pal5={n_pal5}  sentinel=1")
    return output_path


if __name__ == "__main__":
    build_v299()
