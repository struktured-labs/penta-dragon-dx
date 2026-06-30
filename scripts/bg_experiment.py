#!/usr/bin/env python3
"""
BG Colorization Experiment Harness

Unified entrypoint for testing BG colorizer variants.
All non-BG components (OBJ, palettes, hook, DMA) are frozen.

Usage:
    uv run python scripts/bg_experiment.py --strategy ly --tiles 157 --filter on
    uv run python scripts/bg_experiment.py --strategy none --tiles 192 --filter on
    uv run python scripts/bg_experiment.py --strategy viewport --rows 5 --filter on
    uv run python scripts/bg_experiment.py --matrix  # run full comparison matrix

Strategies:
    none     - No VRAM protection. Fast but writes fail during mode 3.
    stat     - STAT register wait (mode 0/1 only). Slow but writes guaranteed.
    ly       - LY gate: skip VBK switch during rendering (LY < 144). Zero flicker.
    hybrid   - LY gate + STAT wait for tiles during VBlank only.
    viewport - Visible-row sweep: only colors the 18 visible rows (scroll-insulated).
"""
import argparse
import json
import subprocess
import sys
import time
from dataclasses import dataclass, asdict
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))
from penta_dragon_dx.display_patcher import apply_all_display_patches

# ============================================================
# FROZEN COMPONENTS (shared across all experiments)
# ============================================================

def load_palettes_from_yaml(yaml_path: Path) -> dict:
    """Load all palette data from YAML file."""
    with open(yaml_path) as f:
        data = yaml.safe_load(f)

    def pal_to_bytes(colors: list[str]) -> bytes:
        result = bytearray()
        for c in colors:
            val = int(c, 16) & 0x7FFF
            result.extend([val & 0xFF, (val >> 8) & 0xFF])
        return bytes(result)

    bg_keys = ['Dungeon', 'BG1', 'BG2', 'BG3', 'BG4', 'BG5', 'BG6', 'BG7']
    bg_data = bytearray()
    for key in bg_keys:
        if key in data.get('bg_palettes', {}):
            bg_data.extend(pal_to_bytes(data['bg_palettes'][key]['colors']))
        else:
            bg_data.extend(pal_to_bytes(["7FFF", "5294", "2108", "0000"]))

    obj_key_map = {
        0: ('EnemyProjectile', ["0000", "7C1F", "5817", "3010"]),
        1: ('SaraDragon', ["0000", "03E0", "01C0", "0000"]),
        2: ('SaraWitch', ["0000", "2EBE", "511F", "0842"]),
        3: ('SaraProjectileAndCrow', ["0000", "001F", "0017", "000F"]),
        4: ('Hornets', ["0000", "03FF", "00DF", "0000"]),
        5: ('OrcGround', ["0000", "02A0", "0160", "0000"]),
        6: ('Humanoid', ["0000", "7C1F", "4C0F", "0000"]),
        7: ('Catfish', ["0000", "7FE0", "3CC0", "0000"]),
    }
    obj_data = bytearray()
    for i in range(8):
        key, fallback = obj_key_map[i]
        if key in data.get('obj_palettes', {}):
            obj_data.extend(pal_to_bytes(data['obj_palettes'][key]['colors']))
        else:
            obj_data.extend(pal_to_bytes(fallback))

    # FFBF 1-2 = mini-bosses (mid-level), 3-8 = bosses (major/end-of-level)
    boss_keys = ['Gargoyle', 'Spider', 'Boss3_Crimson', 'Boss4_Ice',
                 'Boss5_Void', 'Boss6_Poison', 'Boss7_Knight', 'Angela']
    boss_data = data.get('boss_palettes', {})
    boss_palette_table = bytearray()
    boss_slot_table = bytearray()
    for key in boss_keys:
        entry = boss_data.get(key, {})
        colors = entry.get('colors', ["0000", "7FFF", "5294", "2108"])
        slot = entry.get('slot', 6)
        boss_palette_table.extend(pal_to_bytes(colors))
        boss_slot_table.append(slot)

    jet_data = data.get('obj_palettes', {})
    sara_witch_jet = pal_to_bytes(jet_data.get('SaraWitchJet', {}).get('colors', ["0000", "7C1F", "5817", "3010"]))
    sara_dragon_jet = pal_to_bytes(jet_data.get('SaraDragonJet', {}).get('colors', ["0000", "7FE0", "4EC0", "2D80"]))

    powerup_data = data.get('powerup_palettes', {})
    spiral_proj = pal_to_bytes(powerup_data.get('SpiralProjectile', {}).get('colors', ["0000", "7FE0", "5EC0", "3E80"]))
    shield_proj = pal_to_bytes(powerup_data.get('ShieldProjectile', {}).get('colors', ["0000", "03FF", "02BF", "019F"]))
    turbo_proj = pal_to_bytes(powerup_data.get('TurboProjectile', {}).get('colors', ["0000", "00FF", "00BF", "005F"]))

    return {
        'bg_data': bytes(bg_data), 'obj_data': bytes(obj_data),
        'boss_palette_table': bytes(boss_palette_table),
        'boss_slot_table': bytes(boss_slot_table),
        'sara_witch_jet': sara_witch_jet, 'sara_dragon_jet': sara_dragon_jet,
        'spiral_proj': spiral_proj, 'shield_proj': shield_proj, 'turbo_proj': turbo_proj,
    }


def create_tile_based_colorizer(colorizer_base_addr: int) -> bytes:
    """Optimized tile-based OBJ colorizer (FROZEN)."""
    code = bytearray()
    labels = {}
    forward_jumps = []

    def emit(opcodes):
        code.extend(opcodes if isinstance(opcodes, (list, bytes, bytearray)) else [opcodes])

    def emit_jr(opcode, target_label):
        code.append(opcode)
        forward_jumps.append((len(code), target_label))
        code.append(0x00)

    emit([0x06, 0x28])
    labels['loop_start'] = len(code)
    emit([0x2B, 0x7E, 0x23])
    emit([0xB7])
    emit_jr(0x28, 'skip_sprite')
    emit([0x4F])
    emit([0xFE, 0x30])
    emit_jr(0x38, 'low_tiles')
    emit([0x7B, 0xB7])
    emit_jr(0x20, 'boss_palette')
    emit([0x79])
    emit([0xFE, 0x40]); emit_jr(0x38, 'pal_3')
    emit([0xFE, 0x50]); emit_jr(0x38, 'pal_4')
    emit([0xFE, 0x60]); emit_jr(0x38, 'pal_5')
    emit([0xFE, 0x70]); emit_jr(0x38, 'pal_6')
    emit([0xFE, 0x80]); emit_jr(0x38, 'pal_7')
    # Iter 278r (reverted 2026-06-30): the change `[0x7A, 0x00]` (LD A,D; NOP)
    # routed high-tile default to sara_palette to fix orange-Sara race. Broke
    # 10 enemy tests (stage4_live_render, crow, orc, etc.) because tile 0x80+
    # is legitimately used by enemy sprites. Restored original pal_4 default.
    emit([0x3E, 0x04]); emit_jr(0x18, 'apply_palette')

    labels['low_tiles'] = len(code)
    emit([0xFE, 0x20]); emit_jr(0x30, 'sara_palette')
    # Iter 31: tile 0x10-0x1F is Sara's secondary body sprites. Route to
    # sara_palette (D) so the iter-31 hwoam_recolor B=40 raise doesn't
    # paint slot 10-11 pal 4 (Sara half-orange). Iter 29 verified this
    # change is safe (sara_w_alone + all OBJ tests still pass).
    emit([0xFE, 0x10]); emit_jr(0x30, 'sara_palette')
    emit([0xFE, 0x02]); emit_jr(0x38, 'pal_3')
    emit([0xAF]); emit_jr(0x18, 'apply_palette')

    labels['pal_3'] = len(code); emit([0x3E, 0x03]); emit_jr(0x18, 'apply_palette')
    labels['pal_4'] = len(code); emit([0x3E, 0x04]); emit_jr(0x18, 'apply_palette')
    labels['pal_5'] = len(code); emit([0x3E, 0x05]); emit_jr(0x18, 'apply_palette')
    labels['pal_6'] = len(code); emit([0x3E, 0x06]); emit_jr(0x18, 'apply_palette')
    labels['pal_7'] = len(code); emit([0x3E, 0x07]); emit_jr(0x18, 'apply_palette')
    labels['sara_palette'] = len(code); emit(0x7A); emit_jr(0x18, 'apply_palette')
    labels['boss_palette'] = len(code); emit(0x7B)

    labels['apply_palette'] = len(code)
    emit([0x4F, 0x7E, 0xE6, 0xF8, 0xB1, 0x77])

    labels['skip_sprite'] = len(code)
    emit([0x23, 0x23, 0x23, 0x23, 0x05])
    loop_abs = colorizer_base_addr + labels['loop_start']
    emit([0xC2, loop_abs & 0xFF, (loop_abs >> 8) & 0xFF])
    emit([0xC9])

    for pos, label in forward_jumps:
        offset = labels[label] - (pos + 1)
        code[pos] = offset & 0xFF
    return bytes(code)


def create_shadow_colorizer_main(colorizer_addr, boss_slot_table_addr):
    """Shadow colorizer main (FROZEN)."""
    code = bytearray()
    code.extend([0xF5, 0xC5, 0xD5, 0xE5])
    code.extend([0xF0, 0xBE, 0xB7, 0x20, 0x04, 0x16, 0x02, 0x18, 0x02, 0x16, 0x01])
    code.extend([0xF0, 0xBF, 0xB7])
    no_boss = len(code); code.extend([0x28, 0x00])
    code.extend([0x3D, 0x4F, 0x06, 0x00])
    code.extend([0x21, boss_slot_table_addr & 0xFF, (boss_slot_table_addr >> 8) & 0xFF])
    code.extend([0x09, 0x5E])
    done_boss = len(code); code.extend([0x18, 0x00])
    code[no_boss + 1] = len(code) - (no_boss + 2)
    code.extend([0x1E, 0x00])
    code[done_boss + 1] = len(code) - (done_boss + 2)
    code.extend([0x21, 0x03, 0xC0])
    code.extend([0xCD, colorizer_addr & 0xFF, colorizer_addr >> 8])
    code.extend([0x21, 0x03, 0xC1])
    code.extend([0xCD, colorizer_addr & 0xFF, colorizer_addr >> 8])
    code.extend([0xE1, 0xD1, 0xC1, 0xF1, 0xC9])
    return bytes(code)


def create_palette_loader(pal_addr, boss_pal_addr, boss_slot_addr,
                          swj_addr, sdj_addr, sp_addr, shp_addr, tp_addr):
    """Palette loader (FROZEN)."""
    code = bytearray()
    code.extend([0xF0, 0xD0, 0x57])
    code.extend([0x21, pal_addr & 0xFF, (pal_addr >> 8) & 0xFF])
    code.extend([0x3E, 0x80, 0xE0, 0x68, 0x0E, 0x40])
    code.extend([0x2A, 0xE0, 0x69, 0x0D, 0x20, 0xFA])
    obj_addr = pal_addr + 64
    code.extend([0x3E, 0x80, 0xE0, 0x6A])
    code.extend([0xF0, 0xC0, 0xB7, 0x28, 23])
    code.extend([0xFE, 0x01, 0x20, 0x05])
    code.extend([0x21, sp_addr & 0xFF, (sp_addr >> 8) & 0xFF, 0x18, 17])
    code.extend([0xFE, 0x02, 0x20, 0x05])
    code.extend([0x21, shp_addr & 0xFF, (shp_addr >> 8) & 0xFF, 0x18, 8])
    code.extend([0x21, tp_addr & 0xFF, (tp_addr >> 8) & 0xFF, 0x18, 3])
    code.extend([0x21, obj_addr & 0xFF, (obj_addr >> 8) & 0xFF])
    code.extend([0x0E, 0x08, 0x2A, 0xE0, 0x6B, 0x0D, 0x20, 0xFA])
    code.extend([0x3E, 0x88, 0xE0, 0x6A])
    sd_addr = obj_addr + 8
    code.extend([0x21, sd_addr & 0xFF, (sd_addr >> 8) & 0xFF])
    code.extend([0x7A, 0xFE, 0x01, 0x20, 0x03])
    code.extend([0x21, sdj_addr & 0xFF, (sdj_addr >> 8) & 0xFF])
    code.extend([0x0E, 0x08, 0x2A, 0xE0, 0x6B, 0x0D, 0x20, 0xFA])
    code.extend([0x3E, 0x90, 0xE0, 0x6A])
    sw_addr = obj_addr + 16
    code.extend([0x21, sw_addr & 0xFF, (sw_addr >> 8) & 0xFF])
    code.extend([0x7A, 0xFE, 0x01, 0x20, 0x03])
    code.extend([0x21, swj_addr & 0xFF, (swj_addr >> 8) & 0xFF])
    code.extend([0x0E, 0x08, 0x2A, 0xE0, 0x6B, 0x0D, 0x20, 0xFA])
    code.extend([0x3E, 0x98, 0xE0, 0x6A])
    cr_addr = obj_addr + 24
    code.extend([0x21, cr_addr & 0xFF, (cr_addr >> 8) & 0xFF])
    code.extend([0x0E, 0x18, 0x2A, 0xE0, 0x6B, 0x0D, 0x20, 0xFA])
    code.extend([0x3E, 0xB0, 0xE0, 0x6A])
    hu_addr = obj_addr + 48
    code.extend([0x21, hu_addr & 0xFF, (hu_addr >> 8) & 0xFF])
    code.extend([0x0E, 0x08, 0x2A, 0xE0, 0x6B, 0x0D, 0x20, 0xFA])
    code.extend([0x3E, 0xB8, 0xE0, 0x6A])
    cf_addr = obj_addr + 56
    code.extend([0x21, cf_addr & 0xFF, (cf_addr >> 8) & 0xFF])
    code.extend([0x0E, 0x08, 0x2A, 0xE0, 0x6B, 0x0D, 0x20, 0xFA])
    code.extend([0xF0, 0xBF, 0xB7])
    bs_pos = len(code); code.extend([0x28, 0x00])
    code.extend([0x3D, 0x5F, 0x4F, 0x06, 0x00])
    code.extend([0x21, boss_slot_addr & 0xFF, (boss_slot_addr >> 8) & 0xFF])
    # ADD A,A × 3 → slot*8 (OCPS index for OBJ palette slot).
    # Was previously ADD A,A × 1 → slot*2, the wrong stride: each CGB
    # palette is 8 bytes, so OBJ palette N starts at index N*8 in OCPS.
    # The old code for Gargoyle (slot=6) wrote to OCPS=12 (palette 1
    # color 2 + auto-increment), which corrupted Sara D's palette.
    # User symptom: Sara's colors changed when a mini-boss spawned and
    # reverted after she moved (subsequent OBJ palette refreshes
    # overwrote the corruption).
    code.extend([0x09, 0x7E, 0x87, 0x87, 0x87, 0xF6, 0x80, 0xE0, 0x6A])
    code.extend([0x7B, 0x87, 0x87, 0x87, 0x4F, 0x06, 0x00])
    code.extend([0x21, boss_pal_addr & 0xFF, (boss_pal_addr >> 8) & 0xFF])
    code.extend([0x09, 0x0E, 0x08, 0x2A, 0xE0, 0x6B, 0x0D, 0x20, 0xFA])
    code[bs_pos + 1] = len(code) - (bs_pos + 2)
    code.append(0xC9)
    return bytes(code)


def create_conditional_palette(palette_loader_addr):
    """Conditional palette wrapper (FROZEN)."""
    code = bytearray()
    code.extend([0xF0, 0xBE, 0x47, 0xF0, 0xBF, 0xA8, 0x47])
    code.extend([0xF0, 0xC0, 0xA8, 0x47, 0xF0, 0xD0, 0xA8, 0x3C])
    code.extend([0x47, 0xF0, 0xA9, 0xB8, 0xC8])
    code.extend([0x78, 0xE0, 0xA9])
    code.extend([0xC3, palette_loader_addr & 0xFF, palette_loader_addr >> 8])
    return bytes(code)


def create_tile_to_palette_subroutine():
    """Tile->palette subroutine for OBJ (FROZEN)."""
    code = bytearray()
    code.extend([0xFE, 0xFF, 0xC8])
    cp1 = len(code); code.extend([0xFE, 0x05, 0x38, 0x00])
    cp2 = len(code); code.extend([0xFE, 0x07, 0x38, 0x00])
    cp3 = len(code); code.extend([0xFE, 0x13, 0x38, 0x00])
    cp4 = len(code); code.extend([0xFE, 0x60, 0x38, 0x00])
    cp5 = len(code); code.extend([0xFE, 0x88, 0x38, 0x00])
    cp6 = len(code); code.extend([0xFE, 0xE0, 0x38, 0x00])
    cp7 = len(code); code.extend([0xFE, 0xFE, 0x38, 0x00])
    pal0 = len(code); code.extend([0xAF, 0xC9])
    pal1 = len(code); code.extend([0x3E, 0x01, 0xC9])
    pal6 = len(code); code.extend([0x3E, 0x06, 0xC9])
    for cp, tgt in [(cp1, pal0), (cp2, pal6), (cp3, pal0), (cp4, pal6),
                    (cp5, pal0), (cp6, pal1), (cp7, pal6)]:
        code[cp + 3] = (tgt - (cp + 4)) & 0xFF
    return bytes(code)


def create_vblank_hook(combined_addr):
    """VBlank hook with joypad (FROZEN)."""
    lo, hi = combined_addr & 0xFF, (combined_addr >> 8) & 0xFF
    joy = bytearray([
        0x3E, 0x20, 0xE0, 0x00, 0xF0, 0x00, 0x2F, 0xE6, 0x0F, 0xCB, 0x37, 0x47,
        0x3E, 0x10, 0xE0, 0x00, 0x0E, 0x08, 0xF0, 0x00, 0x0D, 0x20, 0xFB,
        0x2F, 0xE6, 0x0F, 0xB0, 0xE0, 0x93, 0x3E, 0x30, 0xE0, 0x00,
    ])
    hook = bytearray([0x3E, 0x0D, 0xEA, 0x00, 0x20, 0xCD, lo, hi,
                       0x3E, 0x01, 0xEA, 0x00, 0x20, 0xC9])
    total = joy + hook
    assert len(total) == 47, f"Hook is {len(total)} bytes, must be 47!"
    return bytes(total)


# ============================================================
# VARIABLE COMPONENT: BG Colorizer
# ============================================================

def create_bg_tile_table(ff_filter: bool) -> bytes:
    """256-byte ROM lookup table: tile_id -> BG palette number."""
    table = bytearray(256)
    for tile in range(256):
        if tile == 0xFF and ff_filter:
            table[tile] = 0xFF  # skip marker
        elif tile < 0x05:
            table[tile] = 0
        elif tile < 0x07:
            table[tile] = 0  # 0x05-0x06: floor accents, not walls
        elif tile < 0x13:
            table[tile] = 0
        elif tile < 0x60:
            table[tile] = 6
        elif tile < 0x88:
            table[tile] = 0
        elif tile < 0xE0:
            table[tile] = 1
        elif tile < 0xFE:
            table[tile] = 6
        else:
            table[tile] = 0
    return bytes(table)


def create_bg_colorizer_viewport(bg_table_addr: int, rows_per_frame: int,
                                  ff_filter: bool, stat_safe: bool = False) -> bytes:
    """Visible-row sweep BG colorizer (scroll-insulated).

    Instead of sweeping all 1024 tiles sequentially, computes which 18 rows
    are currently visible (from SCY register) and sweeps only those.
    Each frame processes `rows_per_frame` complete rows (32 tiles each).

    Scroll insulation: when the screen scrolls, the visible rows change,
    and the colorizer automatically targets the new visible area. Since we
    color all 32 columns per row, SCX changes are handled for free.

    When stat_safe=True, adds STAT register waits before each VRAM access
    to guarantee reads/writes succeed on MiSTer FPGA hardware. Without this,
    mode 3 reads return 0xFF and writes are silently dropped.

    HRAM usage:
      FF91 = row_counter (0-17, which visible row to process next)
      FFA5 = tilemap_base_hi (0x98 or 0x9C, computed once per frame)
      FFA9 = outer row countdown (temporary, reused from conditional palette)
    """
    bg_table_hi = (bg_table_addr >> 8) & 0xFF
    code = bytearray()

    def emit(opcodes):
        code.extend(opcodes if isinstance(opcodes, (list, bytes, bytearray)) else [opcodes])

    # === PREAMBLE ===
    emit([0xF0, 0xC1])        # LDH A, [FFC1]  - gameplay check
    emit([0xB7])               # OR A
    emit([0xC8])               # RET Z           - skip on menus

    emit([0xC5, 0xD5, 0xE5])  # PUSH BC, DE, HL

    # Compute tilemap base from LCDC bit 3
    emit([0xF0, 0x40])        # LDH A, [FF40]  - LCDC
    emit([0xE6, 0x08])        # AND 0x08        - bit 3
    emit([0x0F])               # RRCA            - 0 or 4
    emit([0xC6, 0x98])        # ADD A, 0x98     - 0x98 or 0x9C
    emit([0xE0, 0xA5])        # LDH [FFA5], A   - save base_hi

    # ROM table high byte (constant through all loops)
    emit([0x26, bg_table_hi]) # LD H, table_hi

    # Ensure VBK=0
    emit([0xAF])               # XOR A
    emit([0xE0, 0x4F])        # LDH [FF4F], A

    # Outer row counter
    emit([0x3E, rows_per_frame & 0xFF])  # LD A, ROWS
    emit([0xE0, 0xA9])        # LDH [FFA9], A

    # === OUTER ROW LOOP ===
    row_loop = len(code)

    # Compute tilemap_row = (SCY/8 + row_counter) & 0x1F
    emit([0xF0, 0x42])        # LDH A, [FF42]  - SCY
    emit([0xCB, 0x3F])        # SRL A           - /2
    emit([0xCB, 0x3F])        # SRL A           - /4
    emit([0xCB, 0x3F])        # SRL A           - /8  → SCY/8
    emit([0x4F])               # LD C, A         - C = SCY/8
    emit([0xF0, 0x91])        # LDH A, [FF91]  - row_counter (0-17)
    emit([0x81])               # ADD A, C        - SCY/8 + row_counter
    emit([0xE6, 0x1F])        # AND 0x1F        - mod 32 = tilemap_row

    # Compute row start address DE
    # low byte: (tilemap_row & 7) << 5
    # high byte: base_hi + (tilemap_row >> 3)
    emit([0x4F])               # LD C, A         - save tilemap_row
    emit([0xE6, 0x07])        # AND 0x07        - low 3 bits
    emit([0xCB, 0x37])        # SWAP A          - * 16
    emit([0x87])               # ADD A, A        - * 32
    emit([0x5F])               # LD E, A         - E = row_lo

    emit([0x79])               # LD A, C         - tilemap_row
    emit([0xCB, 0x3F])        # SRL A           - /2
    emit([0xCB, 0x3F])        # SRL A           - /4
    emit([0xCB, 0x3F])        # SRL A           - /8  → 0-3
    emit([0x57])               # LD D, A
    emit([0xF0, 0xA5])        # LDH A, [FFA5]  - base_hi
    emit([0x82])               # ADD A, D
    emit([0x57])               # LD D, A         - D = hi

    # Inner counter: 32 tiles per row
    emit([0x06, 0x20])        # LD B, 32

    # === INNER TILE LOOP ===
    tile_loop = len(code)

    # STAT wait: spin until mode 0 (HBlank) or mode 1 (VBlank)
    # Blocks mode 2 (OAM scan) and mode 3 (drawing) which corrupt VRAM access
    # One wait covers both the read and write (~72T < 87T minimum HBlank)
    if stat_safe:
        stat_wait = len(code)
        emit([0xF0, 0x41])    # LDH A, [FF41]   - STAT register
        emit([0xE6, 0x02])    # AND 0x02         - bit 1: mode 2/3 flag
        stat_jr = len(code)
        emit([0x20, 0x00])    # JR NZ, stat_wait - spin if mode 2 or 3
        code[stat_jr + 1] = (stat_wait - (stat_jr + 2)) & 0xFF

    emit([0x1A])               # LD A, [DE]      - read tile (VBK=0)
    emit([0x6F])               # LD L, A
    emit([0x7E])               # LD A, [HL]      - ROM lookup → palette

    # 0xFF filter: skip write if mode 3 returned garbage
    if ff_filter:
        emit([0x3C])           # INC A           - 0xFF→0x00, Z set
        skip_fwd = len(code)
        emit([0x28, 0x00])     # JR Z, skip_write (patch later)
        emit([0x3D])           # DEC A           - restore
    else:
        skip_fwd = None

    # Write palette attribute to VRAM bank 1
    emit([0x4F])               # LD C, A         - save palette
    emit([0x3E, 0x01])        # LD A, 0x01
    emit([0xE0, 0x4F])        # LDH [FF4F], A   - VBK=1
    emit([0x79])               # LD A, C         - restore palette
    emit([0x12])               # LD [DE], A      - write attr
    emit([0xAF])               # XOR A
    emit([0xE0, 0x4F])        # LDH [FF4F], A   - VBK=0

    # skip_write target
    skip_write = len(code)
    if skip_fwd is not None:
        code[skip_fwd + 1] = (skip_write - (skip_fwd + 2)) & 0xFF

    emit([0x1C])               # INC E           - next tile in row
    emit([0x05])               # DEC B           - counter--

    # JR NZ back to tile_loop
    tile_back = len(code)
    tile_offset = tile_loop - (tile_back + 2)
    emit([0x20, tile_offset & 0xFF])

    # === ADVANCE ROW COUNTER (mod 18) ===
    emit([0xF0, 0x91])        # LDH A, [FF91]
    emit([0x3C])               # INC A
    emit([0xFE, 18])          # CP 18
    emit([0x38, 0x01])        # JR C, no_wrap  (+1 = skip XOR A)
    emit([0xAF])               # XOR A           - wrap to 0
    # no_wrap:
    emit([0xE0, 0x91])        # LDH [FF91], A

    # === OUTER LOOP CHECK ===
    emit([0xF0, 0xA9])        # LDH A, [FFA9]
    emit([0x3D])               # DEC A
    emit([0xE0, 0xA9])        # LDH [FFA9], A

    # JR NZ back to row_loop
    row_back = len(code)
    row_offset = row_loop - (row_back + 2)
    if row_offset < -128:
        raise ValueError(f"Row loop JR offset {row_offset} out of range! Code too large.")
    emit([0x20, row_offset & 0xFF])

    # === CLEANUP ===
    emit([0xAF])               # XOR A
    emit([0xE0, 0x4F])        # LDH [FF4F], A   - VBK=0

    emit([0xE1, 0xD1, 0xC1]) # POP HL, DE, BC
    emit([0xC9])               # RET

    return bytes(code)


def create_bg_colorizer(bg_table_addr: int, strategy: str, tiles: int,
                         ff_filter: bool) -> bytes:
    """BG colorizer with configurable strategy.

    strategy: 'none', 'stat', 'ly', 'hybrid'
    tiles: tiles per frame
    ff_filter: whether to skip writes on 0xFF lookup result

    For LY/hybrid strategies, LY-skipped tiles do NOT advance the counter
    (they'll be retried next VBlank). 0xFF-filtered tiles DO advance
    (they're genuinely empty/unused).
    """
    bg_table_hi = (bg_table_addr >> 8) & 0xFF
    use_ly = strategy in ('ly', 'hybrid')
    code = bytearray()
    forward_jumps = []
    labels = {}

    def emit(opcodes):
        code.extend(opcodes if isinstance(opcodes, (list, bytes, bytearray)) else [opcodes])

    def emit_jr(opcode, target_label):
        code.append(opcode)
        forward_jumps.append((len(code), target_label))
        code.append(0x00)

    # === CHECK GAME MODE ===
    emit([0xF0, 0xC1])        # LDH A, [FFC1]
    emit([0xB7])              # OR A
    emit([0xC8])              # RET Z

    emit([0xC5, 0xD5, 0xE5])  # PUSH BC, DE, HL

    # === COMPUTE ADDRESS ===
    emit([0xF0, 0xA5])        # counter high
    emit([0xE6, 0x03])
    emit([0xC6, 0x98])
    emit([0x57])
    emit([0xF0, 0x40])        # LCDC
    emit([0xE6, 0x08])
    emit([0x0F])
    emit([0x82])
    emit([0x57])
    emit([0xF0, 0x91])        # counter low
    emit([0x5F])

    emit([0x06, tiles & 0xFF])
    emit([0x26, bg_table_hi])

    emit([0xAF])              # VBK = 0
    emit([0xE0, 0x4F])

    # === SWEEP LOOP ===
    labels['sweep_loop'] = len(code)

    # --- LY-first gate (strategies: ly, hybrid) ---
    # Check LY FIRST: if VBlank is over, exit loop immediately.
    # This avoids wasted VRAM reads + ROM lookups during rendering.
    if use_ly:
        emit([0xF0, 0x44])    # LDH A, [FF44]
        emit([0xFE, 0x90])    # CP 144
        emit_jr(0x38, 'done_loop')  # JR C, done (rendering started, exit)

    # --- STAT wait (strategies: stat, hybrid) ---
    if strategy in ('stat', 'hybrid'):
        labels['stat_wait'] = len(code)
        emit([0xF0, 0x41])    # LDH A, [FF41]
        emit([0xE6, 0x02])    # AND 0x02
        stat_jr = len(code)
        emit([0x20, 0x00])    # JR NZ, stat_wait
        code[stat_jr + 1] = (labels['stat_wait'] - (stat_jr + 2)) & 0xFF

    # Read tile
    emit([0x1A])              # LD A, [DE]
    emit([0x6F])              # LD L, A
    emit([0x7E])              # LD A, [HL]  (ROM lookup)

    # --- 0xFF filter ---
    if ff_filter:
        emit([0x3C])          # INC A (0xFF -> 0x00, Z set)
        emit_jr(0x28, 'advance_only')  # skip write, advance counter
        emit([0x3D])          # DEC A (restore)

    emit([0x4F])              # LD C, A (save palette)

    # Write attr (VBK=1)
    emit([0x3E, 0x01])
    emit([0xE0, 0x4F])        # VBK = 1
    emit([0x79])              # LD A, C
    emit([0x12])              # LD [DE], A
    emit([0xAF])
    emit([0xE0, 0x4F])        # VBK = 0

    # === Advance counter (successful write + 0xFF filter fall through here) ===
    labels['advance_only'] = len(code)

    emit([0x1C])              # INC E
    emit_jr(0x20, 'no_wrap')

    emit([0x14])              # INC D
    emit([0x7A])
    emit([0xE6, 0x03])
    emit([0xC6, 0x98])
    emit([0x57])
    emit([0xF0, 0x40])
    emit([0xE6, 0x08])
    emit([0x0F])
    emit([0x82])
    emit([0x57])

    labels['no_wrap'] = len(code)

    emit([0x05])              # DEC B
    sweep_end = len(code)
    sweep_offset = labels['sweep_loop'] - (sweep_end + 2)
    if sweep_offset < -128 or sweep_offset > 127:
        raise ValueError(f"Sweep loop offset {sweep_offset} out of range!")
    emit([0x20, sweep_offset & 0xFF])

    labels['done_loop'] = len(code)

    # === SAVE COUNTER ===
    emit([0x7A])
    emit([0xE6, 0x03])
    emit([0xE0, 0xA5])
    emit([0x7B])
    emit([0xE0, 0x91])

    # === CLEANUP: guarantee VBK=0 ===
    emit([0xAF])
    emit([0xE0, 0x4F])

    emit([0xE1, 0xD1, 0xC1])
    emit([0xC9])

    # Patch forward jumps
    for pos, label in forward_jumps:
        target = labels[label]
        offset = target - (pos + 1)
        if offset < -128 or offset > 127:
            raise ValueError(f"JR to {label} out of range: {offset}")
        code[pos] = offset & 0xFF

    return bytes(code)


# ============================================================
# ROM BUILDER
# ============================================================

@dataclass
class BGConfig:
    strategy: str = 'ly'
    tiles: int = 157
    ff_filter: bool = True
    tilemap_mode: str = 'active'  # 'active' only for now
    rows_per_frame: int = 5  # for viewport strategy only
    stat_safe: bool = False  # STAT waits for MiSTer FPGA safety

    @property
    def label(self):
        ff = "ff" if self.ff_filter else "noff"
        stat = "_stat" if self.stat_safe else ""
        if self.strategy == 'viewport':
            return f"viewport_{self.rows_per_frame}r_{ff}{stat}"
        return f"{self.strategy}_{self.tiles}t_{ff}{stat}"


def build_rom(config: BGConfig, output_path: Path = None) -> Path:
    """Build ROM with given BG config. Returns output path."""
    input_rom = Path("rom/Penta Dragon (J).gb")
    if output_path is None:
        output_path = Path(f"tmp/experiment_{config.label}.gb")
    palette_yaml = Path("palettes/penta_palettes_v097.yaml")

    with open(input_rom, "rb") as f:
        rom = bytearray(f.read())

    apply_all_display_patches(rom)
    palettes = load_palettes_from_yaml(palette_yaml)

    # Data layout
    pal_addr = 0x6800
    boss_pal_addr = 0x6880
    boss_slot_addr = 0x68C0
    swj_addr = 0x68D0; sdj_addr = 0x68D8
    sp_addr = 0x68E0; shp_addr = 0x68E8; tp_addr = 0x68F0

    # Code layout
    pal_loader_addr = 0x6900
    shadow_main_addr = 0x69D0
    colorizer_addr = 0x6A10
    tile_pal_addr = 0x6B00
    bg_colorizer_addr = 0x6C00
    cond_pal_addr = 0x6C80
    combined_addr = 0x6D00
    bg_table_addr = 0x6E00

    # Generate code
    pal_loader = create_palette_loader(pal_addr, boss_pal_addr, boss_slot_addr,
                                       swj_addr, sdj_addr, sp_addr, shp_addr, tp_addr)
    cond_pal = create_conditional_palette(pal_loader_addr)
    shadow_main = create_shadow_colorizer_main(colorizer_addr, boss_slot_addr)
    colorizer = create_tile_based_colorizer(colorizer_addr)
    tile_pal = create_tile_to_palette_subroutine()
    bg_table = create_bg_tile_table(config.ff_filter)
    if config.strategy == 'viewport':
        bg_colorizer = create_bg_colorizer_viewport(bg_table_addr, config.rows_per_frame, config.ff_filter, config.stat_safe)
    else:
        bg_colorizer = create_bg_colorizer(bg_table_addr, config.strategy, config.tiles, config.ff_filter)

    # Combined function ordering:
    # For unsafe strategies ('none', viewport without stat): Palette first, BG last
    #   BG extends past VBlank but 0xFF filter prevents mode 3 corruption
    # For safe strategies (stat_safe viewport, 'ly', 'hybrid', 'stat'): BG first
    #   STAT waits guarantee VRAM access safety regardless of execution order
    combined = bytearray()
    is_safe = config.stat_safe or config.strategy in ('ly', 'hybrid', 'stat')
    if not is_safe:
        # Palette -> OBJ -> DMA -> BG (palette writes safe in VBlank, BG extends into rendering)
        combined.extend([0xCD, cond_pal_addr & 0xFF, cond_pal_addr >> 8])
        combined.extend([0xCD, shadow_main_addr & 0xFF, shadow_main_addr >> 8])
        combined.extend([0xCD, 0x80, 0xFF])  # DMA
        combined.extend([0xCD, bg_colorizer_addr & 0xFF, bg_colorizer_addr >> 8])
        combined.extend([0xC9])
    else:
        # BG -> Palette -> OBJ -> DMA (BG runs first while STAT waits handle safety)
        combined.extend([0xCD, bg_colorizer_addr & 0xFF, bg_colorizer_addr >> 8])
        combined.extend([0xCD, cond_pal_addr & 0xFF, cond_pal_addr >> 8])
        combined.extend([0xCD, shadow_main_addr & 0xFF, shadow_main_addr >> 8])
        combined.extend([0xCD, 0x80, 0xFF, 0xC9])

    hook = create_vblank_hook(combined_addr)

    # Verify no overlaps
    regions = [
        ('pal_loader', pal_loader_addr, len(pal_loader)),
        ('cond_pal', cond_pal_addr, len(cond_pal)),
        ('shadow_main', shadow_main_addr, len(shadow_main)),
        ('colorizer', colorizer_addr, len(colorizer)),
        ('tile_pal', tile_pal_addr, len(tile_pal)),
        ('bg_colorizer', bg_colorizer_addr, len(bg_colorizer)),
        ('combined', combined_addr, len(combined)),
        ('bg_table', bg_table_addr, len(bg_table)),
    ]
    for i, (na, sa, sza) in enumerate(regions):
        for nb, sb, szb in regions[i+1:]:
            if sa < sb + szb and sb < sa + sza:
                raise ValueError(f"OVERLAP: {na} and {nb}")

    # Write to ROM
    bank13 = 13 * 0x4000
    def w(addr, data):
        off = bank13 + (addr - 0x4000)
        rom[off:off+len(data)] = data

    w(pal_addr, palettes['bg_data'])
    w(pal_addr + 64, palettes['obj_data'])
    w(boss_pal_addr, palettes['boss_palette_table'])
    w(boss_slot_addr, palettes['boss_slot_table'])
    w(swj_addr, palettes['sara_witch_jet'])
    w(sdj_addr, palettes['sara_dragon_jet'])
    w(sp_addr, palettes['spiral_proj'])
    w(shp_addr, palettes['shield_proj'])
    w(tp_addr, palettes['turbo_proj'])
    w(pal_loader_addr, pal_loader)
    w(cond_pal_addr, cond_pal)
    w(shadow_main_addr, shadow_main)
    w(colorizer_addr, colorizer)
    w(tile_pal_addr, tile_pal)
    w(bg_colorizer_addr, bg_colorizer)
    w(bg_table_addr, bg_table)
    w(combined_addr, combined)

    rom[0x06D5:0x06D5+3] = bytearray([0x00, 0x00, 0x00])
    rom[0x0824:0x0824+len(hook)] = hook
    rom[0x143] = 0x80

    # Header checksum
    x = 0
    for i in range(0x134, 0x14D):
        x = (x - rom[i] - 1) & 0xFF
    rom[0x14D] = x

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "wb") as f:
        f.write(rom)

    return output_path


# ============================================================
# TEST RUNNER
# ============================================================

LUA_TEST_TEMPLATE = r"""
local frame = 0
local TOTAL_FRAMES = {total_frames}
local vbk_during_render = 0

-- Sample VBK state during rendering on multiple scanlines each frame
callbacks:add("scanline", function()
    local ly = emu:read8(0xFF44)
    if ly >= 0 and ly < 144 then
        local vbk = emu:read8(0xFF4F) & 0x01
        if vbk == 1 then
            vbk_during_render = vbk_during_render + 1
        end
    end
end)

callbacks:add("frame", function()
    frame = frame + 1
    if frame == TOTAL_FRAMES then
        local lcdc = emu:read8(0xFF40)
        local base = (lcdc & 0x08) ~= 0 and 0x9C00 or 0x9800
        local correct = 0
        for i = 0, 1023 do
            emu:write8(0xFF4F, 0); local t = emu:read8(base + i)
            emu:write8(0xFF4F, 1); local a = emu:read8(base + i) & 0x07
            local exp
            if t == 0xFF then exp = a
            elseif t < 0x05 then exp = 0
            elseif t < 0x07 then exp = 6
            elseif t < 0x13 then exp = 0
            elseif t < 0x60 then exp = 6
            elseif t < 0x88 then exp = 0
            elseif t < 0xE0 then exp = 1
            elseif t < 0xFE then exp = 6
            else exp = 0 end
            if a == exp then correct = correct + 1 end
        end
        emu:write8(0xFF4F, 0)
        local vbk = emu:read8(0xFF4F) & 0x01
        local f = io.open("{output}", "w")
        if f then
            f:write(string.format("%d %d %02X %02X %02X %d\n",
                correct, vbk, emu:read8(0xFFC1), emu:read8(0xFF93),
                emu:read8(0xFF44), vbk_during_render))
            f:close()
        end
        local d = io.open("DONE", "w"); if d then d:write("OK"); d:close() end
    end
end)
"""


@dataclass
class TestResult:
    config_label: str
    state_name: str
    accuracy: int
    total: int
    vbk_at_end: int
    ffc1: int
    ly_at_end: int
    vbk_render_count: int  # VBK=1 during rendering (0 = MiSTer-safe)
    crashed: bool
    bg_size: int  # bytes


def run_single_test(rom_path: Path, state_path: Path, test_frames: int = 300) -> TestResult:
    """Run one test: boot ROM with savestate, check accuracy at test_frames."""
    lua_out = Path("tmp/_exp_result.txt")
    lua_script = Path("tmp/_exp_test.lua")
    lua_out.unlink(missing_ok=True)
    Path("DONE").unlink(missing_ok=True)

    lua_code = LUA_TEST_TEMPLATE.format(total_frames=test_frames, output=str(lua_out))
    lua_script.write_text(lua_code)

    import os
    env = os.environ.copy()
    env.pop('DISPLAY', None)
    env.pop('WAYLAND_DISPLAY', None)
    env['QT_QPA_PLATFORM'] = 'offscreen'
    env['SDL_AUDIODRIVER'] = 'dummy'

    try:
        subprocess.run(
            ['xvfb-run', '-a', 'mgba-qt', str(rom_path), '-t', str(state_path),
             '--script', str(lua_script), '-l', '0'],
            timeout=30, capture_output=True, env=env
        )
    except subprocess.TimeoutExpired:
        pass  # Expected - mGBA doesn't exit after Lua script finishes

    if lua_out.exists():
        parts = lua_out.read_text().strip().split()
        vbk_render = int(parts[5]) if len(parts) > 5 else -1
        return TestResult(
            config_label="", state_name=state_path.stem,
            accuracy=int(parts[0]), total=1024,
            vbk_at_end=int(parts[1]),
            ffc1=int(parts[2], 16),
            ly_at_end=int(parts[4], 16),
            vbk_render_count=vbk_render,
            crashed=False, bg_size=0
        )
    else:
        return TestResult(
            config_label="", state_name=state_path.stem,
            accuracy=0, total=1024, vbk_at_end=-1, ffc1=-1, ly_at_end=-1,
            vbk_render_count=-1,
            crashed=True, bg_size=0
        )


# ============================================================
# EXPERIMENT MATRIX
# ============================================================

CORE_STATES = [
    "level1_sara_w_4_hornets",
    "level1_sara_d_alone",
    "level1_sara_w_gargoyle_mini_boss",
    "level1_sara_w_orc",
    "level1_sara_w_in_jet_form_secret_stage",
]

DEFAULT_MATRIX = [
    BGConfig(strategy='none', tiles=109, ff_filter=True),
    BGConfig(strategy='none', tiles=157, ff_filter=True),
    BGConfig(strategy='none', tiles=192, ff_filter=True),
    BGConfig(strategy='stat', tiles=48, ff_filter=False),
    BGConfig(strategy='stat', tiles=71, ff_filter=False),
    BGConfig(strategy='ly', tiles=40, ff_filter=True),
    BGConfig(strategy='ly', tiles=60, ff_filter=True),
    BGConfig(strategy='ly', tiles=100, ff_filter=True),
    BGConfig(strategy='ly', tiles=157, ff_filter=True),
]


def run_matrix(configs=None, states=None, test_frames=300):
    """Run experiment matrix and output results."""
    if configs is None:
        configs = DEFAULT_MATRIX
    if states is None:
        states = CORE_STATES

    state_dir = Path("save_states_for_claude")
    all_results = []

    for config in configs:
        print(f"\n{'='*60}")
        print(f"Building: {config.label}")
        try:
            rom_path = build_rom(config)
        except Exception as e:
            print(f"  BUILD FAILED: {e}")
            continue

        # Get BG colorizer size
        bg_code = create_bg_colorizer(0x6E00, config.strategy, config.tiles, config.ff_filter)
        bg_size = len(bg_code)
        print(f"  BG colorizer: {bg_size} bytes")

        for state_name in states:
            state_path = state_dir / f"{state_name}.ss0"
            if not state_path.exists():
                print(f"  SKIP {state_name} (not found)")
                continue

            result = run_single_test(rom_path, state_path, test_frames)
            result.config_label = config.label
            result.bg_size = bg_size
            all_results.append(result)

            status = "CRASH" if result.crashed else f"{result.accuracy}/{result.total}"
            print(f"  {state_name}: {status}")

    # Output summary
    output_results(all_results, configs, test_frames, states)
    return all_results


def output_results(results, configs, test_frames=300, states=None):
    """Write results as markdown table."""
    if states is None:
        states = CORE_STATES
    out_path = Path("tmp/experiment_results.md")

    # Group by config
    by_config = {}
    for r in results:
        by_config.setdefault(r.config_label, []).append(r)

    lines = ["# BG Experiment Results\n"]
    lines.append(f"Test frames: {test_frames} | States: {len(states)}\n")
    lines.append("| Config | BG bytes | Avg Acc | Min Acc | VBK renders | MiSTer-safe | Settle est |")
    lines.append("|--------|----------|---------|---------|-------------|-------------|------------|")

    ranked = []
    for config in configs:
        label = config.label
        group = by_config.get(label, [])
        if not group:
            continue

        accs = [r.accuracy for r in group if not r.crashed]
        crashes = sum(1 for r in group if r.crashed)
        vbk_renders = [r.vbk_render_count for r in group if not r.crashed and r.vbk_render_count >= 0]
        total_vbk = sum(vbk_renders) if vbk_renders else -1
        # MiSTer safety is based on STRATEGY, not measurement (scanline sampling
        # can't catch brief VBK=1 windows within a single scanline)
        # - ly/hybrid: zero VBK during rendering (LY gate guarantees VBlank-only writes)
        # - none: VBK switches during rendering (2 per tile per frame)
        # - stat: VBK during HBlank only, but STAT timing unreliable on FPGA
        mister_safe = config.strategy in ('ly', 'hybrid')
        bg_size = group[0].bg_size

        avg_acc = sum(accs) / len(accs) if accs else 0
        min_acc = min(accs) if accs else 0

        # Estimate settle: ~25 tiles/frame for LY (VBlank window only)
        if config.strategy == 'ly':
            writes_per_frame = 25  # ~25 tiles fit in VBlank window
        elif config.strategy == 'stat':
            writes_per_frame = config.tiles
        else:
            writes_per_frame = config.tiles * 0.5  # ~50% succeed on MiSTer

        settle_frames = int(1024 / max(writes_per_frame, 1))
        settle_s = settle_frames / 60

        vbk_str = f"{total_vbk}" if total_vbk >= 0 else "?"
        safe_str = "YES" if mister_safe else f"NO ({total_vbk} hits)"
        lines.append(f"| {label} | {bg_size} | {avg_acc:.0f}/1024 | {min_acc}/1024 | {vbk_str} | {safe_str} | ~{settle_s:.2f}s |")

        ranked.append({
            'label': label, 'avg_acc': avg_acc, 'min_acc': min_acc,
            'crashes': crashes, 'mister_safe': mister_safe,
            'total_vbk': total_vbk, 'settle_s': settle_s,
            'bg_size': bg_size, 'strategy': config.strategy,
        })

    # Rank: no crash > MiSTer-safe (0 VBK renders) > highest avg_acc > fastest settle
    ranked.sort(key=lambda x: (-x['crashes'], not x['mister_safe'], -x['avg_acc'], x['settle_s']))

    lines.append("\n## Ranking (best first)\n")
    for i, r in enumerate(ranked):
        mister = "MiSTer-safe (0 VBK)" if r['mister_safe'] else f"FLICKER ({r['total_vbk']} VBK during render)"
        lines.append(f"{i+1}. **{r['label']}** - avg {r['avg_acc']:.0f}, settle ~{r['settle_s']:.2f}s, {mister}")

    if ranked:
        best_mister = next((r for r in ranked if r['mister_safe'] and r['crashes'] == 0), None)
        best_emu = ranked[0] if ranked[0]['crashes'] == 0 else None
        lines.append(f"\n## Recommendations\n")
        if best_mister:
            lines.append(f"**MiSTer best**: `{best_mister['label']}` (settle {best_mister['settle_s']:.2f}s, 0 VBK during render)")
        else:
            lines.append("**MiSTer best**: NONE - all strategies have VBK during rendering!")
        if best_emu:
            lines.append(f"**Emulator best**: `{best_emu['label']}` (avg {best_emu['avg_acc']:.0f}/1024)")

    out_path.write_text("\n".join(lines))
    print(f"\nResults written to {out_path}")

    # Also JSON
    json_path = Path("tmp/experiment_results.json")
    json_data = [asdict(r) for r in results if hasattr(r, '__dataclass_fields__')]
    # Use simple dicts
    json_data = []
    for r in results:
        json_data.append({
            'config': r.config_label, 'state': r.state_name,
            'accuracy': r.accuracy, 'crashed': r.crashed,
            'vbk': r.vbk_at_end, 'vbk_render': r.vbk_render_count,
            'bg_size': r.bg_size,
        })
    json_path.write_text(json.dumps(json_data, indent=2))
    print(f"JSON written to {json_path}")


# ============================================================
# CLI
# ============================================================

def main():
    parser = argparse.ArgumentParser(description='BG Colorization Experiment Harness')
    parser.add_argument('--strategy', choices=['none', 'stat', 'ly', 'hybrid', 'viewport'],
                        default='ly', help='BG write protection strategy')
    parser.add_argument('--tiles', type=int, default=157, help='Tiles per frame')
    parser.add_argument('--filter', choices=['on', 'off'], default='on',
                        help='0xFF anti-flicker filter')
    parser.add_argument('--matrix', action='store_true', help='Run full experiment matrix')
    parser.add_argument('--rows', type=int, default=5, help='Rows per frame (viewport strategy)')
    parser.add_argument('--build-only', action='store_true', help='Only build, no test')
    parser.add_argument('--output', type=str, default=None, help='Output ROM path')
    parser.add_argument('--frames', type=int, default=300, help='Test frames')

    args = parser.parse_args()

    if args.matrix:
        print("=== Running BG Experiment Matrix ===")
        run_matrix(test_frames=args.frames)
        return

    config = BGConfig(
        strategy=args.strategy,
        tiles=args.tiles,
        ff_filter=(args.filter == 'on'),
        rows_per_frame=args.rows,
    )

    out = Path(args.output) if args.output else None
    rom_path = build_rom(config, out)
    if config.strategy == 'viewport':
        bg_code = create_bg_colorizer_viewport(0x6E00, config.rows_per_frame, config.ff_filter)
    else:
        bg_code = create_bg_colorizer(0x6E00, config.strategy, config.tiles, config.ff_filter)
    print(f"Built: {rom_path} ({config.label}, BG={len(bg_code)} bytes)")

    if args.build_only:
        return

    # Quick test on first core state
    state = Path("save_states_for_claude/level1_sara_w_4_hornets.ss0")
    if state.exists():
        result = run_single_test(rom_path, state, args.frames)
        result.config_label = config.label
        status = "CRASH" if result.crashed else f"{result.accuracy}/{result.total}"
        print(f"Quick test ({state.stem}): {status}, VBK={result.vbk_at_end}")


if __name__ == "__main__":
    main()
