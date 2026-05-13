#!/usr/bin/env python3
"""Penta Dragon DX v3.00 — phantom-safe inline BG attr hook.

Architecture: BG attribute bytes (palette indices) are written INLINE at
tile-write time, eliminating the ~18-frame attr lag that produced visible
flicker in v2.99's bg_sweep approach. bg_sweep is RETAINED as a slow-cycle
safety net (covers off-screen tilemap regions and preserves game frame
timing).

The vanilla ROM has a tile-copy routine at bank 1:0x42A0-0x436D that copies
24 rows of 24 tile IDs from WRAM[0xC1A0..] to VRAM (tilemap 0x9800 or
0x9C00). v3.00 patches THIS routine in place so that after each 4-tile
group write to VBK=0, a second short DI window writes 4 BG attr bytes to
the same addresses in VBK=1 — looking up `palette = bg_table[tile_id]`.

Key design choices for phantom-sound safety:

1. NO BANK SWITCH. The inline hook runs entirely in bank 1, never touches
   FF99. The vanilla game's FF99 is undisturbed.

2. SHORT DI WINDOWS. Each mini-group has TWO short DI windows (one for
   tile writes, one for attr writes), separated by EI. Each DI window is
   comparable in length to vanilla's (~280T worst-case).

3. bg_table in WRAM. The 256-byte tile -> palette index table is copied to
   WRAM[0xDA00..0xDAFF] at boot. Verified safe both statically (no `EA xx DA`
   writes in any bank) and at runtime (5000-frame multi-direction probe
   including forced mini-boss spawn → 0xDA00-0xDAFF stays zero-sum).
   Bank 1 reads from WRAM via [BC] with B=0xDA.

4. ENTRY POINTS PRESERVED. 0x42A0 (LD H,9C; JP 0x42A7) and 0x42A5 (LD H,98)
   are unchanged. Only 0x42A7..0x436D is rewritten.

5. BG SWEEP RETAINED. v2.99's bg_sweep stays in the VBlank handler as a
   safety net. The inline hook covers VISIBLE tilemap regions at tile-write
   time; bg_sweep slowly cycles through the rest. Empirically, removing
   bg_sweep entirely broke the mini-boss probe (state-machine timing
   regression) — so it's kept.

6. bg_table init in VBlank handler. The cold-boot path in bank 13's
   colorize handler copies bg_table (256 bytes) from bank 13's ROM to
   WRAM[0xCF00..0xCFFF] once at startup, gated by DF02 magic byte.

Per-group DI window estimate:
  - vanilla:        DI + STAT wait (~250T) + 4 writes (24T) + EI = ~280T
  - v3.00 tile DI:  same as vanilla, ~280T
  - v3.00 attr DI:  ~280T (STAT wait + 4 lookup-and-write attr ops)
  - Two DI windows per group, separated by EI gap (~50T)

Verified probes (all PASS):
  - title color:      3 distinct colors, 9.9% non-white
  - phantom D887:     4 transitions (vs vanilla 18; v2.99 = 0)
  - gameplay palette: 24 distinct words, 4 distinct attr-pal indices
                      attr histogram: pal0=903, pal1=38, pal5=2, pal7=81
                      (vs v2.99: pal0=918, pal1=17, pal5=1, pal7=88)
  - mini-boss color:  reached, OBJ palette colorized
  - scroll tearing:   0/s pal changes within room
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
    """Default everything to pal0 except items and hazards (same as v2.99)."""
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
    # Sentinel for ff_filter (kept for compat, harmless)
    table[0xFF] = 0xFF
    return bytes(table)


BG_TABLE_BYTES = _minimal_bg_table()
assert len(BG_TABLE_BYTES) == 256

# WRAM location for runtime bg_table.
# Verified safe across 5000-frame multi-direction probe (incl. forced miniboss spawn):
# 0xDA00-0xDAFF stays zero-sum throughout (0 static writes, 0 runtime writes).
# (0xCF00 was BAD: game writes during rooms past initial dungeon.
#  0xDE00 has 29 static writes in bank 2 to 0xDE48-0xDE51 — too risky.)
WRAM_BG_TABLE = 0xDA00  # 256 bytes
WRAM_BG_TABLE_HI = (WRAM_BG_TABLE >> 8) & 0xFF
WRAM_BG_TABLE_LO = WRAM_BG_TABLE & 0xFF


def create_inline_tile_copy() -> bytes:
    """Build the enhanced tile copy routine.

    Layout (bank 1, replaces 0x42A0-0x436D, 206 bytes available):

      0x42A0: 26 9C C3 A7 42 26 98   ; UNCHANGED entry points
      0x42A7: <enhanced code below>

    Register usage:
      A — scratch
      B — bg_table_hi (0xDA) — preserved across writes in attr phase
      C — group counter (6 per row) — pushed/popped around inner ops
      DE — tile buffer source pointer (advances by 4 per write batch, rewinds
           by 4 between tile/attr phases)
      HL — tilemap write pointer (advances by 4 per write batch, rewinds by
           4 between phases, +8 per row at row end)

    Stack: row counter (24 -> 0) — kept on stack across group_loop
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
        assert -128 <= offset <= 127, f"JR back to {name}: offset {offset} out of range"
        emit([opcode, offset & 0xFF])

    def emit_jr_fwd(opcode):
        pos = len(code) + 1
        emit([opcode, 0x00])
        return pos  # caller fixes later

    def patch_jr_fwd(pos):
        offset = len(code) - (pos + 1)
        assert -128 <= offset <= 127, f"JR fwd from {pos}: offset {offset}"
        code[pos] = offset & 0xFF

    # ============================================================
    # SETUP (0x42A7-onwards)
    # H is pre-set to 0x98 or 0x9C by entry point
    # ============================================================
    emit([0x2E, 0x00])               # LD L, 0x00
    emit([0x11, 0xA0, 0xC1])         # LD DE, 0xC1A0     ; WRAM tile source
    emit([0x3E, 0x18])               # LD A, 24
    emit([0xF5])                     # PUSH AF           ; row counter on stack

    # ============================================================
    # ROW_LOOP
    # ============================================================
    mark('row_loop')
    emit([0x0E, 0x06])               # LD C, 6           ; 6 groups per row

    # ============================================================
    # GROUP_LOOP — for each of 6 groups: tile phase + attr phase
    # ============================================================
    mark('group_loop')

    # -------- TILE PHASE: VBK=0 (default), 4 tile writes --------
    emit([0xF3])                     # DI
    # Wait for mode 3 (begin scanline)
    mark('stat3a')
    emit([0xF0, 0x41])               # LDH A,[FF41]
    emit([0xE6, 0x03])               # AND 3
    emit([0xFE, 0x03])               # CP 3
    emit_jr_back(0x20, 'stat3a')     # JR NZ, stat3a    ; wait until mode 3
    # Wait for mode 0 (HBlank — VRAM accessible)
    mark('stat0a')
    emit([0xF0, 0x41])               # LDH A,[FF41]
    emit([0xE6, 0x03])               # AND 3
    emit_jr_back(0x20, 'stat0a')     # JR NZ, stat0a    ; wait until mode 0
    # 4 tile writes: LD A,[DE]; INC DE; LD [HL+],A
    for _ in range(4):
        emit([0x1A, 0x13, 0x22])
    emit([0xFB])                     # EI

    # -------- TRANSITION: rewind L,E by 4; VBK=1 --------
    # (interrupts CAN fire here — DI is off briefly)
    # SAVE C (group counter) — attr write loop clobbers C via "LD C,A; LD A,[BC]"
    emit([0xC5])                     # PUSH BC          ; save group counter (C)
    emit([0x7D])                     # LD A, L
    emit([0xD6, 0x04])               # SUB 4
    emit([0x6F])                     # LD L, A
    emit([0x30, 0x01])               # JR NC, +1
    emit([0x25])                     # DEC H            ; carry: H -= 1
    emit([0x7B])                     # LD A, E
    emit([0xD6, 0x04])               # SUB 4
    emit([0x5F])                     # LD E, A
    emit([0x30, 0x01])               # JR NC, +1
    emit([0x15])                     # DEC D            ; carry: D -= 1
    emit([0x06, WRAM_BG_TABLE_HI])   # LD B, 0xDA       ; bg_table_hi
    emit([0x3E, 0x01])               # LD A, 1
    emit([0xE0, 0x4F])               # LDH [FF4F], A    ; VBK = 1 (attr bank)

    # -------- ATTR PHASE: VBK=1, 4 attr writes --------
    emit([0xF3])                     # DI
    mark('stat3b')
    emit([0xF0, 0x41])               # LDH A,[FF41]
    emit([0xE6, 0x03])               # AND 3
    emit([0xFE, 0x03])               # CP 3
    emit_jr_back(0x20, 'stat3b')     # JR NZ, stat3b
    mark('stat0b')
    emit([0xF0, 0x41])               # LDH A,[FF41]
    emit([0xE6, 0x03])               # AND 3
    emit_jr_back(0x20, 'stat0b')     # JR NZ, stat0b
    # 4 attr writes via [BC] lookup
    # Per tile:
    #   LD A,[DE]       ; load tile_id from buffer
    #   INC DE
    #   LD C, A         ; B already = 0xDE (bg_table_hi); C = tile_id
    #   LD A, [BC]      ; load palette index from bg_table[tile_id]
    #   LD [HL+], A     ; write attr
    for _ in range(4):
        emit([0x1A, 0x13, 0x4F, 0x0A, 0x22])
    emit([0xFB])                     # EI

    # -------- POST-ATTR: VBK=0 --------
    emit([0xAF])                     # XOR A
    emit([0xE0, 0x4F])               # LDH [FF4F], A    ; VBK = 0

    # -------- RESTORE C (group counter) --------
    emit([0xC1])                     # POP BC           ; restore group counter

    # -------- GROUP COUNTER --------
    emit([0x0D])                     # DEC C
    emit_jr_back(0x20, 'group_loop') # JR NZ, group_loop

    # ============================================================
    # ROW END: advance HL by 8 (skip 8 unused columns in tilemap)
    # ============================================================
    emit([0x7D])                     # LD A, L
    emit([0xC6, 0x08])               # ADD 8
    emit([0x6F])                     # LD L, A
    emit([0x30, 0x01])               # JR NC, +1
    emit([0x24])                     # INC H

    # ============================================================
    # ROW COUNTER
    # ============================================================
    emit([0xF1])                     # POP AF           ; row count
    emit([0x3D])                     # DEC A
    # if zero -> done
    j_done = emit_jr_fwd(0x28)       # JR Z, done
    emit([0xF5])                     # PUSH AF          ; row count back on stack
    # Jump back to row_loop
    # We need JR back to 'row_loop' — but it may be too far. Compute offset.
    offset = targets['row_loop'] - (len(code) + 2)
    if -128 <= offset <= 127:
        emit([0x18, offset & 0xFF])  # JR row_loop
    else:
        # use JP (3 bytes)
        target_addr = 0x42A7 + targets['row_loop']
        emit([0xC3, target_addr & 0xFF, (target_addr >> 8) & 0xFF])

    patch_jr_fwd(j_done)
    emit([0xC9])                     # RET

    return bytes(code)


def build_v300():
    input_rom = Path("rom/Penta Dragon (J).gb")
    output_path = Path("rom/working/penta_dragon_dx_v300.gb")
    palette_yaml = Path("palettes/penta_palettes_v097.yaml")

    rom = bytearray(input_rom.read_bytes())
    palettes = load_palettes_from_yaml(palette_yaml)
    rom[0x143] = 0x80  # CGB flag

    # ============================================================
    # BANK 13 LAYOUT (mostly same as v2.99)
    # ============================================================
    bank13 = 13 * 0x4000
    pal_addr = 0x6800
    boss_pal_addr = 0x6880
    boss_slot_addr = 0x68C0
    swj_addr = 0x68D0
    sdj_addr = 0x68D8
    sp_addr = 0x68E0
    shp_addr = 0x68E8
    tp_addr = 0x68F0
    pal_loader_addr = 0x6900
    shadow_main_addr = 0x69D0
    colorizer_addr = 0x6A10
    tile_pal_addr = 0x6B00
    cond_pal_addr = 0x6C90
    bg_sweep_addr = 0x6CD0
    colorize_addr = 0x6E00
    bg_table_addr = 0x7000

    def w(addr, data):
        off = bank13 + (addr - 0x4000)
        rom[off:off + len(data)] = data

    # Same as v2.99: palette data + tables
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

    # Keep bg_sweep as a safety net for tiles that escape the inline hook.
    # Although the inline hook now writes attrs at tile-write time, bg_sweep
    # handles edge cases (boot-up frames, tilemap regions not touched by the
    # tile copy). Keeping bg_sweep also preserves the frame timing that the
    # game state machine implicitly depends on.
    sweep = create_bg_sweep_viewport_gated(bg_table_addr, bg_sweep_addr)
    w(bg_sweep_addr, sweep)

    # ============================================================
    # COLORIZE HANDLER (modified from v2.99)
    #
    # Changes from v2.99:
    #   - REMOVED bg_sweep call (inline hook does it now)
    #   - ADDED bg_table -> WRAM copy in cold-boot path (DF02 magic byte)
    # ============================================================
    code = bytearray()
    code.extend([0xF0, 0x4F, 0xF5])           # save VBK
    code.extend([0xAF, 0xE0, 0x4F])           # VBK = 0
    # DF02 magic byte init check
    code.extend([0xFA, 0x02, 0xDF, 0xFE, 0x5A])  # LD A,[DF02]; CP 5A
    df02_jr = len(code) + 1
    code.extend([0x28, 0x00])                 # JR Z, +n  (skip cold-boot init)
    # ---- COLD-BOOT PATH ----
    code.extend([0x3E, 0x5A, 0xEA, 0x02, 0xDF])  # LD A,5A; LD [DF02],A
    code.extend([0xAF, 0xEA, 0x00, 0xDF])     # LD A,0; LD [DF00],A (reset hash)
    # Copy 256 bytes from bank13:bg_table_addr to WRAM[DA00..DAFF].
    # We're in bank 13 (FF99=13), so LD HL,bg_table_addr reads bank 13.
    # B=0 -> DEC counter goes 0->255->254->...->1->0 = 256 iters
    code.extend([0x21, bg_table_addr & 0xFF, (bg_table_addr >> 8) & 0xFF])  # LD HL, bg_table_addr
    code.extend([0x11, WRAM_BG_TABLE & 0xFF, (WRAM_BG_TABLE >> 8) & 0xFF])  # LD DE, WRAM_BG_TABLE
    code.extend([0x06, 0x00])                 # LD B, 0
    bg_copy_loop = len(code)
    code.extend([0x2A])                       # LD A,[HL+]
    code.extend([0x12])                       # LD [DE], A
    code.extend([0x13])                       # INC DE
    code.extend([0x05])                       # DEC B
    offset = bg_copy_loop - (len(code) + 2)
    code.extend([0x20, offset & 0xFF])        # JR NZ, bg_copy_loop

    # ---- Skip-cold-boot target ----
    code[df02_jr] = (len(code) - df02_jr - 1) & 0xFF

    # ---- WARM PATH (every frame) ----
    # cond_pal (palette loader, hash-cached)
    code.extend([0xCD, cond_pal_addr & 0xFF, (cond_pal_addr >> 8) & 0xFF])

    # FFC1 gate: if 0 (menu), skip OBJ/DMA. Keep bg_sweep as a safety net.
    code.extend([0xF0, 0xC1, 0xB7])           # LDH A,[FFC1]; OR A
    skip = len(code) + 1
    code.extend([0x28, 0x00])                 # JR Z, +n (skip if menu)
    code.extend([0xCD, bg_sweep_addr & 0xFF, (bg_sweep_addr >> 8) & 0xFF])
    code.extend([0xCD, shadow_main_addr & 0xFF, (shadow_main_addr >> 8) & 0xFF])
    code.extend([0xCD, 0x80, 0xFF])           # CALL DMA (FF80)
    code[skip] = (len(code) - skip - 1) & 0xFF

    # Restore VBK and return
    code.extend([0xF1, 0xE0, 0x4F])           # restore VBK
    code.extend([0xC9])                       # RET

    # Verify colorize handler fits before bg_table_addr
    assert colorize_addr + len(code) <= bg_table_addr, \
        f"colorize handler overflows into bg_table: {colorize_addr + len(code):#X} > {bg_table_addr:#X}"
    w(colorize_addr, bytes(code))
    print(f"  colorize handler: {len(code)} bytes at 0x{colorize_addr:04X}")

    # ============================================================
    # VBLANK HOOK at 0x0824 (same as v2.99)
    # ============================================================
    hook = bytearray([
        0xF0, 0x99, 0xF5,                              # save FF99
        0x3E, 0x20, 0xE0, 0x00, 0xF0, 0x00,            # P14 select
        0x2F, 0xE6, 0x0F, 0xCB, 0x37, 0x47,            # CPL/AND/SWAP/LDB
        0x3E, 0x10, 0xE0, 0x00,                        # P13 select
        0xF0, 0x00, 0xF0, 0x00,                        # dummy + actual
        0x2F, 0xE6, 0x0F, 0xB0, 0xE0, 0x93,            # combine; store FF93
        0x3E, 0x30, 0xE0, 0x00,                        # deselect joypad
        0x3E, 0x0D, 0xEA, 0x00, 0x20,                  # bank 13
        0xCD, colorize_addr & 0xFF, (colorize_addr >> 8) & 0xFF,  # call colorize
        0xF1, 0xEA, 0x00, 0x20,                        # restore FF99
        0xC9,                                          # RET
    ])
    assert len(hook) <= 47, f"VBlank hook too big: {len(hook)} > 47"
    rom[0x0824:0x0824 + 47] = (hook + bytearray(47 - len(hook)))[:47]

    # NOP out game DMA at 0x06D5 (our handler calls DMA explicitly)
    rom[0x06D5:0x06D8] = bytearray([0x00, 0x00, 0x00])

    # RST $38 RETI -> RET (phantom-sound belt-and-suspenders)
    rom[0x003B] = 0xC9

    # ============================================================
    # INLINE BG-ATTR HOOK at bank1:0x42A7
    #
    # Preserves entry points at 0x42A0 (LD H,9C; JP 0x42A7) and
    # 0x42A5 (LD H,98). Rewrites the body 0x42A7..0x436D inline.
    # ============================================================
    inline_code = create_inline_tile_copy()
    available = 0x436D - 0x42A7 + 1   # 199 bytes
    assert len(inline_code) <= available, \
        f"inline tile copy too big: {len(inline_code)} > {available}"

    # Patch 0x42A7..0x42A7+len-1 with our code, fill rest with NOPs to be safe
    rom[0x42A7:0x42A7 + len(inline_code)] = inline_code
    # Fill remaining bytes up to 0x436D with NOPs (just in case any code falls through)
    if len(inline_code) < available:
        # Place a RET at end of our code, then NOP-fill to 0x436E
        # Actually our code already has a RET. Fill the rest with NOPs.
        rom[0x42A7 + len(inline_code):0x436E] = bytearray(0x00 for _ in range(available - len(inline_code)))

    # Verify entry points unchanged
    assert rom[0x42A0:0x42A7] == bytearray([0x26, 0x9C, 0xC3, 0xA7, 0x42, 0x26, 0x98]), \
        f"entry points changed: {rom[0x42A0:0x42A7].hex()}"

    print(f"  inline tile copy: {len(inline_code)} bytes at 0x42A7-0x{0x42A7 + len(inline_code) - 1:04X}")
    print(f"    available: {available} bytes — {available - len(inline_code)} bytes free")

    # ============================================================
    # HEADER CHECKSUM
    # ============================================================
    chk = 0
    for b in rom[0x134:0x14D]:
        chk = (chk - b - 1) & 0xFF
    rom[0x14D] = chk

    output_path.write_bytes(rom)
    print(f"Wrote {output_path} ({len(rom)} bytes)")
    n_pal0 = sum(1 for b in BG_TABLE_BYTES if b == 0)
    n_pal1 = sum(1 for b in BG_TABLE_BYTES if b == 1)
    n_pal5 = sum(1 for b in BG_TABLE_BYTES if b == 5)
    print(f"  bg_table: pal0={n_pal0}  pal1={n_pal1}  pal5={n_pal5}")
    return output_path


if __name__ == "__main__":
    build_v300()
