#!/usr/bin/env python3
"""Penta Dragon DX v3.01 — GDMA-based BG attr transfer.

Replaces v3.00's dual-STAT-wait inline hook with:
  1. Tile-only inline hook (single STAT wait, vanilla speed)
  2. VBlank attr computation: read tiles from C1A0, lookup bg_table,
     write 1024-byte attr buffer to WRAM bank 2 (D000-D3FF)
  3. GDMA transfer: hardware DMA 1024 bytes from WRAM bank 2 to
     VRAM tilemap VBK=1 every VBlank (~2048T)

WRAM bank 2 confirmed safe — game never writes FF70 in code.
bg_sweep retained as safety net (mini-boss probe timing dependency).

Palette mapping (bg_table):
  - pal0 (floor/default):  floor, void, structure/transitions, hazards
  - pal1 (items):          0x88-0xDF (pickups, powerups)
  - pal6 (walls):          0x14-0x1E, 0x25-0x26, 0x34-0x38, 0x41-0x49,
                           0x54-0x57, 0x59 (slate blue-gray)
  - pal7 overridden to pal0 colors (hides stale CGB boot-ROM attrs)
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


def _bg_table() -> bytes:
    """Tile-to-palette lookup table (256 bytes, one per tile ID)."""
    table = bytearray(256)
    for i in [0x14, 0x16, 0x17, 0x18, 0x19, 0x1A, 0x1C, 0x1E]:
        table[i] = 6
    for i in [0x25, 0x26, 0x34, 0x35, 0x36, 0x37, 0x38]:
        table[i] = 6
    for i in [0x41, 0x42, 0x44, 0x45, 0x46, 0x47, 0x48, 0x49,
              0x54, 0x55, 0x56, 0x57, 0x59]:
        table[i] = 6
    for i in range(0x88, 0xE0):
        table[i] = 1
    table[0xFF] = 0xFF
    return bytes(table)


BG_TABLE_BYTES = _bg_table()
WRAM_BG_TABLE = 0xDA00
WRAM_BG_TABLE_HI = (WRAM_BG_TABLE >> 8) & 0xFF
ATTR_BUFFER = 0xD000  # WRAM bank 2 (DA00 alternative tested, made no difference)


def create_inline_tile_copy_tileonly() -> bytes:
    """Tile-only inline copy — single STAT wait per group, vanilla speed.

    Replaces 0x42A7..0x436D. H pre-set to 0x98 or 0x9C by entry point.
    24 rows × 6 groups × 4 tiles = 576 tiles.
    """
    code = bytearray()
    targets = {}

    def emit(opcodes):
        if isinstance(opcodes, (list, bytes, bytearray)):
            code.extend(opcodes)
        else:
            code.append(opcodes)

    def mark(name):
        targets[name] = len(code)

    def emit_jr_back(opcode, name):
        offset = targets[name] - (len(code) + 2)
        assert -128 <= offset <= 127
        emit([opcode, offset & 0xFF])

    def emit_jr_fwd(opcode):
        pos = len(code) + 1
        emit([opcode, 0x00])
        return pos

    def patch_jr_fwd(pos):
        offset = len(code) - (pos + 1)
        assert -128 <= offset <= 127
        code[pos] = offset & 0xFF

    # Setup
    emit([0x2E, 0x00])               # LD L, 0x00
    emit([0x11, 0xA0, 0xC1])         # LD DE, 0xC1A0
    emit([0x3E, 0x18])               # LD A, 24
    emit([0xF5])                     # PUSH AF  (row counter)

    mark('row_loop')
    emit([0x0E, 0x06])               # LD C, 6  (groups per row)

    mark('group_loop')
    # STAT wait: mode 3 then mode 0
    emit([0xF3])                     # DI
    mark('stat3')
    emit([0xF0, 0x41])               # LDH A,[FF41]
    emit([0xE6, 0x03])               # AND 3
    emit([0xFE, 0x03])               # CP 3
    emit_jr_back(0x20, 'stat3')      # JR NZ, stat3
    mark('stat0')
    emit([0xF0, 0x41])               # LDH A,[FF41]
    emit([0xE6, 0x03])               # AND 3
    emit_jr_back(0x20, 'stat0')      # JR NZ, stat0
    # 4 tile writes
    for _ in range(4):
        emit([0x1A, 0x13, 0x22])     # LD A,[DE]; INC DE; LD [HL+],A
    emit([0xFB])                     # EI

    # Group counter
    emit([0x0D])                     # DEC C
    emit_jr_back(0x20, 'group_loop') # JR NZ, group_loop

    # Row end: HL += 8
    emit([0x7D])                     # LD A, L
    emit([0xC6, 0x08])               # ADD 8
    emit([0x6F])                     # LD L, A
    emit([0x30, 0x01])               # JR NC, +1
    emit([0x24])                     # INC H

    # Row counter
    emit([0xF1])                     # POP AF
    emit([0x3D])                     # DEC A
    j_done = emit_jr_fwd(0x28)       # JR Z, done
    emit([0xF5])                     # PUSH AF
    offset = targets['row_loop'] - (len(code) + 2)
    if -128 <= offset <= 127:
        emit([0x18, offset & 0xFF])
    else:
        target_addr = 0x42A7 + targets['row_loop']
        emit([0xC3, target_addr & 0xFF, (target_addr >> 8) & 0xFF])

    patch_jr_fwd(j_done)
    emit([0xC9])                     # RET

    return bytes(code)


def create_gdma_transfer() -> bytes:
    """GDMA 1024 bytes from WRAM bank 2:D000 to displayed tilemap VBK=1.

    Must run during VBlank. ~2048T. DI around FF70 switch.
    Checks LCDC bit 3 for tilemap base (0x9800 or 0x9C00).
    """
    code = bytearray()

    # VBK=1
    code.extend([0x3E, 0x01, 0xE0, 0x4F])

    # DI — protect FF70 switch from Timer ISR
    code.extend([0xF3])

    # FF70=2 (WRAM bank 2)
    code.extend([0x3E, 0x02, 0xE0, 0x70])

    # HDMA source = D000
    code.extend([0x3E, 0xD0, 0xE0, 0x51])   # HDMA1 = 0xD0
    code.extend([0xAF, 0xE0, 0x52])          # HDMA2 = 0x00

    # HDMA dest = tilemap base (check LCDC bit 3)
    code.extend([0xF0, 0x40])               # LDH A,[LCDC]
    code.extend([0xE6, 0x08])               # AND 0x08
    code.extend([0x28, 0x04])               # JR Z, +4 (use 0x98)
    code.extend([0x3E, 0x9C])               # LD A, 0x9C
    code.extend([0x18, 0x02])               # JR +2
    code.extend([0x3E, 0x98])               # LD A, 0x98
    code.extend([0xE0, 0x53])               # HDMA3 = dest high
    code.extend([0xAF, 0xE0, 0x54])         # HDMA4 = 0x00

    # Start HDMA in HBlank mode (64 blocks, 16 bytes per HBlank).
    # General mode (HDMA5 = 0x3F) halts CPU for ~2048T per call, which
    # was breaking the game's STAGE LOAD → dungeon transition.
    # HBlank mode (HDMA5 = 0xBF, bit 7 set) spreads the work across
    # ~64 HBlanks using HBlank-only CPU time. Doesn't halt CPU.
    code.extend([0x3E, 0xBF, 0xE0, 0x55])   # HDMA5 = 0xBF → HBlank mode

    # GDMA done. Restore FF70=1, EI, VBK=0
    code.extend([0x3E, 0x01, 0xE0, 0x70])   # FF70=1
    code.extend([0xFB])                     # EI
    code.extend([0xAF, 0xE0, 0x4F])         # VBK=0
    code.extend([0xC9])                     # RET

    return bytes(code)


def create_attr_computation(bg_table_addr: int) -> bytes:
    """Compute 1024-byte attr buffer in WRAM bank 2 from tile buffer.

    Reads tiles from WRAM 0xC1A0 (bank 0, always accessible).
    Looks up bg_table from ROM bank 13 (active during VBlank handler).
    Writes to WRAM bank 2:D000-D3FF.

    18 rows × 24 tiles + 8 padding cols. Each ROW gets its own DI window.

    Row count is 18 (not 24) to fit the visible viewport height — the
    off-screen rows 19-24 never need attr writes. Going past 22 rows
    starves the game's main loop of CPU time per frame (each row adds
    ~2050T to the handler; >22 rows leaves <25K T for game logic and
    the STAGE LOAD→dungeon transition can't complete). See
    `docs/v301_regression_stage_load_stuck.md` for the binary-search
    cliff data.

    Why one DI per row (not per chunk): the empirical safe DI budget on this
    ROM is ~2000-3000T, NOT the 7000T originally assumed. The chunked design
    (3 rows in one ~6100T DI) freezes at the FFC1=0→1 transition; one-row
    DI (~2000T) does not. Total runtime is similar to the 8-chunk design
    (~50K T) but per-DI stays safe and the EI gaps service Timer ISR.

    Register plan inside DI:
      B  = bg_table high byte (0x70)
      C  = scratch (tile ID for [BC] lookup)
      HL = tile source (C1A0+, bank 0 — unaffected by FF70)
      DE = attr dest (D000+, bank 2 — requires FF70=2)
      FFE0 (HRAM scratch) = row counter (avoids DI-internal PUSH/POP nesting)
    """
    bg_table_hi = (bg_table_addr >> 8) & 0xFF
    code = bytearray()

    code.extend([0xC5, 0xD5, 0xE5, 0xF5])  # PUSH BC, DE, HL, AF
    code.extend([0x21, 0xA0, 0xC1])         # LD HL, 0xC1A0
    code.extend([0x11, 0x00, 0xD0])         # LD DE, 0xD000 (attr buffer)
    code.extend([0x3E, 0x14])               # LD A, 20 (under 22-row cliff; cold-boot zero may unlock this)
    code.extend([0xE0, 0xE0])               # LDH [FFE0], A (row counter in HRAM)

    row_loop = len(code)
    code.extend([0xF3])                     # DI
    code.extend([0x3E, 0x02, 0xE0, 0x70])   # FF70 = 2
    code.extend([0x06, bg_table_hi])        # LD B, bg_table_hi
    code.extend([0x3E, 0x18])               # LD A, 24 (tile counter)

    tile_loop = len(code)
    code.extend([0xF5])                     # PUSH AF (tile counter)
    code.extend([0x2A])                     # LD A, [HL+]
    code.extend([0x4F])                     # LD C, A
    code.extend([0x0A])                     # LD A, [BC]
    code.extend([0x12])                     # LD [DE], A
    code.extend([0x13])                     # INC DE
    code.extend([0xF1])                     # POP AF
    code.extend([0x3D])                     # DEC A
    code.extend([0x20, (tile_loop - (len(code) + 2)) & 0xFF])

    code.extend([0x3E, 0x01, 0xE0, 0x70])   # FF70 = 1
    code.extend([0xFB])                     # EI

    # DE += 8 (skip padding cols) — outside DI
    code.extend([0x7B, 0xC6, 0x08, 0x5F, 0x30, 0x01, 0x14])

    # Row counter via HRAM
    code.extend([0xF0, 0xE0])               # LDH A, [FFE0]
    code.extend([0x3D])                     # DEC A
    code.extend([0xE0, 0xE0])               # LDH [FFE0], A
    code.extend([0x20, (row_loop - (len(code) + 2)) & 0xFF])

    code.extend([0xF1, 0xE1, 0xD1, 0xC1])  # POP AF, HL, DE, BC
    code.extend([0xC9])
    return bytes(code)


def build_v301():
    input_rom = Path("rom/Penta Dragon (J).gb")
    output_path = Path("rom/working/penta_dragon_dx_v301.gb")
    palette_yaml = Path("palettes/penta_palettes_v097.yaml")

    rom = bytearray(input_rom.read_bytes())
    palettes = load_palettes_from_yaml(palette_yaml)

    # pal7 ← pal0 (hide stale CGB boot-ROM attrs)
    bg_data = bytearray(palettes['bg_data'])
    bg_data[56:64] = bg_data[0:8]
    palettes = {**palettes, 'bg_data': bytes(bg_data)}

    rom[0x143] = 0x80  # CGB flag

    # Bank 13 layout
    bank13 = 13 * 0x4000
    pal_addr = 0x6800
    boss_pal_addr = 0x6880
    boss_slot_addr = 0x68C0
    swj_addr = 0x68D0; sdj_addr = 0x68D8
    sp_addr = 0x68E0; shp_addr = 0x68E8; tp_addr = 0x68F0
    pal_loader_addr = 0x6900
    shadow_main_addr = 0x69D0
    colorizer_addr = 0x6A10
    tile_pal_addr = 0x6B00
    cond_pal_addr = 0x6C90
    bg_sweep_addr = 0x6CD0
    gdma_addr = 0x6D80
    colorize_addr = 0x6E00
    bg_table_addr = 0x7000
    attr_comp_addr = 0x7100

    def w(addr, data):
        off = bank13 + (addr - 0x4000)
        rom[off:off + len(data)] = data

    # Palette data + tables (same as v3.00)
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

    # bg_sweep safety net. Strip the internal FFC1 gate (first 4 bytes
    # `F0 C1 B7 C8` = LDH A,[FFC1]; OR A; RET Z) so it runs on title too.
    sweep = bytearray(create_bg_sweep_viewport_gated(bg_table_addr, bg_sweep_addr))
    assert sweep[:4] == bytearray([0xF0, 0xC1, 0xB7, 0xC8]), \
        f"bg_sweep prefix changed: {sweep[:4].hex()}"
    sweep[0:4] = bytearray([0x00, 0x00, 0x00, 0x00])  # NOPs
    w(bg_sweep_addr, bytes(sweep))

    # GDMA transfer routine
    gdma_code = create_gdma_transfer()
    assert gdma_addr + len(gdma_code) <= colorize_addr, \
        f"GDMA overflows: {gdma_addr + len(gdma_code):#X} > {colorize_addr:#X}"
    w(gdma_addr, gdma_code)
    print(f"  GDMA transfer: {len(gdma_code)} bytes at 0x{gdma_addr:04X}")

    # Attr computation routine
    attr_comp = create_attr_computation(bg_table_addr)
    w(attr_comp_addr, attr_comp)
    print(f"  attr computation: {len(attr_comp)} bytes at 0x{attr_comp_addr:04X}")

    # ============================================================
    # COLORIZE HANDLER
    #
    # Order: FF99 save+set → VBK save → cold-boot init → cond_pal → GDMA
    #        → FFC1 gate { DMA, bg_sweep, OBJ colorizer, attr computation }
    #        → VBK restore → FF99 restore
    #
    # FF99 fix (essential): the game's STAT handler at 0x0853 and Timer ISR
    # at 0x06B3 both restore the ROM bank from FF99 at exit. The hook at
    # 0x0824 writes 0x0D to 0x2100 but DOES NOT update FF99 (47-byte budget).
    # If an ISR fires during our colorize handler (after any EI), it would
    # restore bank from FF99 (stale game value, e.g. bank 1) and our
    # subsequent PC fetches would come from the wrong bank — garbage exec,
    # game freeze. Updating FF99 here makes ISRs restore bank 13 correctly.
    # ============================================================
    code = bytearray()
    code.extend([0xF0, 0x99, 0xF5])           # LDH A,[FF99]; PUSH AF (save FF99)
    code.extend([0x3E, 0x0D, 0xE0, 0x99])     # LD A,0x0D; LDH [FF99],A (FF99=bank13)
    code.extend([0xF0, 0x4F, 0xF5])           # save VBK
    code.extend([0xAF, 0xE0, 0x4F])           # VBK = 0

    # DF02 magic byte cold-boot check
    code.extend([0xFA, 0x02, 0xDF, 0xFE, 0x5A])
    df02_jr = len(code) + 1
    code.extend([0x28, 0x00])                 # JR Z, skip_cold

    # ---- COLD-BOOT PATH ----
    code.extend([0x3E, 0x5A, 0xEA, 0x02, 0xDF])  # DF02 = 0x5A
    code.extend([0xAF, 0xEA, 0x00, 0xDF])         # DF00 = 0 (hash)
    code.extend([0xAF, 0xEA, 0x03, 0xDF])         # DF03 = 0 (GDMA-ready flag)

    # Copy bg_table ROM → WRAM 0xDA00 (for inline hook compatibility — not
    # strictly needed for v3.01 since inline hook no longer reads it, but
    # keeping it doesn't hurt and allows fallback)
    code.extend([0x21, bg_table_addr & 0xFF, (bg_table_addr >> 8) & 0xFF])
    code.extend([0x11, WRAM_BG_TABLE & 0xFF, (WRAM_BG_TABLE >> 8) & 0xFF])
    code.extend([0x06, 0x00])                 # B = 0 (256 iters)
    bg_copy = len(code)
    code.extend([0x2A, 0x12, 0x13, 0x05])    # [HL+]→[DE]; INC DE; DEC B
    offset = bg_copy - (len(code) + 2)
    code.extend([0x20, offset & 0xFF])

    # Cold-boot bank-2 zero — with the FF99 fix in place, the previous
    # "white screens on title" issue should no longer happen. Try zeroing
    # the attr buffer so subsequent HDMA copies a known-clean state to
    # VRAM bank 1 instead of garbage.
    code.extend([0xF3])                       # DI
    code.extend([0x3E, 0x02, 0xE0, 0x70])     # FF70 = 2
    code.extend([0x21, 0x00, 0xD0])           # HL = D000
    code.extend([0xAF])                       # A = 0
    code.extend([0x06, 0x00])                 # B = 0 (256 iters)
    zero_loop1 = len(code)
    code.extend([0x22, 0x05])                 # LD [HL+],A; DEC B
    code.extend([0x20, (zero_loop1 - (len(code) + 2)) & 0xFF])
    code.extend([0x06, 0x00])                 # B = 0 again
    zero_loop2 = len(code)
    code.extend([0x22, 0x05])
    code.extend([0x20, (zero_loop2 - (len(code) + 2)) & 0xFF])
    code.extend([0x06, 0x00])
    zero_loop3 = len(code)
    code.extend([0x22, 0x05])
    code.extend([0x20, (zero_loop3 - (len(code) + 2)) & 0xFF])
    code.extend([0x06, 0x00])
    zero_loop4 = len(code)
    code.extend([0x22, 0x05])
    code.extend([0x20, (zero_loop4 - (len(code) + 2)) & 0xFF])
    code.extend([0x3E, 0x01, 0xE0, 0x70])     # FF70 = 1
    code.extend([0xFB])                       # EI

    # ---- skip_cold target ----
    code[df02_jr] = (len(code) - df02_jr - 1) & 0xFF

    # ---- WARM PATH ----
    # 1. cond_pal
    code.extend([0xCD, cond_pal_addr & 0xFF, (cond_pal_addr >> 8) & 0xFF])

    # 2. bg_sweep — runs ALWAYS (title too). The simplified inline hook
    # no longer writes attrs, so bg_sweep is the only mechanism that colors
    # title-screen tiles. Full coverage in ~18 frames.
    code.extend([0xCD, bg_sweep_addr & 0xFF, (bg_sweep_addr >> 8) & 0xFF])

    # 3. GDMA (if buffer ready). Skipped on title since attr_computation
    # never runs there (gated by FFC1), so DF03 stays 0.
    code.extend([0xFA, 0x03, 0xDF, 0xB7])
    gdma_skip = len(code) + 1
    code.extend([0x28, 0x00])
    code.extend([0xCD, gdma_addr & 0xFF, (gdma_addr >> 8) & 0xFF])
    code[gdma_skip] = (len(code) - gdma_skip - 1) & 0xFF

    # 4. FFC1 gate: game-only work (DMA + OBJ colorizer ONLY).
    # attr_computation + GDMA/HDMA SKIPPED. EXHAUSTIVE testing confirmed
    # every combination breaks gameplay:
    #   - attr_comp ≤22 rows alone: WORKS
    #   - attr_comp 23+ rows alone: BREAKS
    #   - GDMA general-mode alone: BREAKS
    #   - HDMA HBlank-mode alone: D880 progresses, visual garbage
    #   - attr_comp + GDMA at any row count: BREAKS
    #   - attr_comp + HDMA at any row count: BREAKS
    #   - attr buffer at DA00 (alternate to D000): STILL BREAKS
    #   - cold-boot zero + attr_comp + HDMA: STILL BREAKS
    # Production ships with bg_sweep alone (functional, slow attr coverage).
    code.extend([0xF0, 0xC1, 0xB7])
    ffc1_skip = len(code) + 1
    code.extend([0x28, 0x00])
    code.extend([0xCD, 0x80, 0xFF])           # OAM DMA
    code.extend([0xCD, shadow_main_addr & 0xFF, (shadow_main_addr >> 8) & 0xFF])
    code[ffc1_skip] = (len(code) - ffc1_skip - 1) & 0xFF

    # Restore VBK, restore FF99, return
    code.extend([0xF1, 0xE0, 0x4F])           # POP AF; LDH [VBK], A
    code.extend([0xF1, 0xE0, 0x99])           # POP AF; LDH [FF99], A (restore FF99)
    code.extend([0xC9])

    assert colorize_addr + len(code) <= bg_table_addr, \
        f"colorize handler overflow: {colorize_addr + len(code):#X} > {bg_table_addr:#X}"
    w(colorize_addr, bytes(code))
    print(f"  colorize handler: {len(code)} bytes at 0x{colorize_addr:04X}")

    # ============================================================
    # VBLANK HOOK at 0x0824
    # ============================================================
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

    # NOP game DMA
    rom[0x06D5:0x06D8] = bytearray([0x00, 0x00, 0x00])

    # RST $38 RETI → RET
    rom[0x003B] = 0xC9

    # ============================================================
    # INLINE TILE-ONLY HOOK at bank1:0x42A7
    # ============================================================
    inline_code = create_inline_tile_copy_tileonly()
    available = 0x436D - 0x42A7 + 1  # 199 bytes
    assert len(inline_code) <= available, \
        f"inline tile copy too big: {len(inline_code)} > {available}"

    rom[0x42A7:0x42A7 + len(inline_code)] = inline_code
    if len(inline_code) < available:
        rom[0x42A7 + len(inline_code):0x436E] = bytearray(available - len(inline_code))

    assert rom[0x42A0:0x42A7] == bytearray([0x26, 0x9C, 0xC3, 0xA7, 0x42, 0x26, 0x98])

    print(f"  inline tile copy: {len(inline_code)} bytes (tile-only, {available - len(inline_code)} free)")

    # Header checksum
    chk = 0
    for b in rom[0x134:0x14D]:
        chk = (chk - b - 1) & 0xFF
    rom[0x14D] = chk

    output_path.write_bytes(rom)
    print(f"Wrote {output_path} ({len(rom)} bytes)")
    return output_path


if __name__ == "__main__":
    build_v301()
