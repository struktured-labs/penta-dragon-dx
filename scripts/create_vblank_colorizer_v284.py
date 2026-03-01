#!/usr/bin/env python3
"""
v2.84: Scroll-Edge VBlank Pre-Coloring + VBK Safety

Changes from v2.83:
1. VBK Safety: Save/restore VBK (FF4F) around all VBlank handler work.
   Insurance against edge cases where VBlank fires while enhanced copy has VBK=1.

2. Scroll-Edge Pre-Coloring: During VBlank (before LCD starts), detect scroll
   direction change and pre-color the right-edge column of the active tilemap.
   This prevents the LCD from rendering newly visible columns with stale palette
   attributes during the ~2 frames before the enhanced copy reaches them.

3. FFA9 Repurposed: Previously used as conditional palette hash cache + sweep
   palette temp. Now holds "previous SCX/8" for scroll detection. Trade-off:
   cond_pal hash check will almost always mismatch → palettes load every frame
   (~150M extra). Acceptable.

HRAM assignments:
  FF91: Hook flag (0x5A = copy active, checked but NOT cleared by VBlank)
  FFA5: Sweep state counter (0-23=Phase1, 24-47=Phase2)
  FFA9: Previous SCX/8 for scroll detection (was hash cache in v2.83)
  FFEE: Base hi temp (protected by hook flag during enhanced copy)
"""
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).parent))
from bg_experiment import (
    load_palettes_from_yaml, create_tile_based_colorizer,
    create_shadow_colorizer_main, create_palette_loader,
    create_tile_to_palette_subroutine,
    create_bg_tile_table,
)
from penta_dragon_dx.display_patcher import apply_all_display_patches

HOOK_FLAG = 0x5A  # Magic value: "hook just ran"


def create_conditional_palette_always(palette_loader_addr: int) -> bytes:
    """Always-load palette wrapper — no FFA9 hash cache.

    In v2.84, FFA9 is repurposed for scroll detection (prev SCX/8).
    The original cond_pal read/wrote FFA9 as a hash cache, which would
    corrupt the scroll state. This version simply jumps to the palette
    loader unconditionally. Cost: ~150M extra per VBlank frame (acceptable).
    """
    code = bytearray()
    code.extend([0xC3, palette_loader_addr & 0xFF, (palette_loader_addr >> 8) & 0xFF])
    return bytes(code)


def create_bank_aware_vblank_hook(combined_addr: int) -> bytes:
    """VBlank hook with joypad + bank-aware save/restore via FF99.
    Must be exactly 47 bytes (0x0824-0x0852).
    """
    lo, hi = combined_addr & 0xFF, (combined_addr >> 8) & 0xFF
    joy = bytearray([
        0x3E, 0x20,  # LD A, 0x20
        0xE0, 0x00,  # LDH [FF00], A
        0xF0, 0x00,  # LDH A, [FF00]
        0x2F,        # CPL
        0xE6, 0x0F,  # AND 0x0F
        0xCB, 0x37,  # SWAP A
        0x47,        # LD B, A
        0x3E, 0x10,  # LD A, 0x10
        0xE0, 0x00,  # LDH [FF00], A
        0xF0, 0x00,  # LDH A, [FF00] (dummy)
        0xF0, 0x00,  # LDH A, [FF00] (actual)
        0x2F,        # CPL
        0xE6, 0x0F,  # AND 0x0F
        0xB0,        # OR B
        0xE0, 0x93,  # LDH [FF93], A
        0x3E, 0x30,  # LD A, 0x30
        0xE0, 0x00,  # LDH [FF00], A
    ])
    hook = bytearray([
        0xF0, 0x99,        # LDH A, [FF99]
        0xF5,              # PUSH AF
        0x3E, 0x0D,        # LD A, 0x0D
        0xEA, 0x00, 0x20,  # LD [0x2000], A
        0xCD, lo, hi,      # CALL combined
        0xF1,              # POP AF
        0xEA, 0x00, 0x20,  # LD [0x2000], A
        0xC9,              # RET
    ])
    total = joy + hook
    while len(total) < 47:
        total.append(0x00)
    assert len(total) == 47, f"Hook is {len(total)} bytes, must be 47!"
    return bytes(total)


def create_fast_menu_copy(base_addr: int, return_addr: int) -> bytes:
    """Fast tile-only copy for menus (FFC1=0).

    Replicates original game's tilemap copy: 24 rows × 24 tiles from C1A0
    to VRAM with STAT waits, but NO palette attribute writes. Same speed
    as the vanilla game.

    Uses full DI for the entire copy — matches original game's behavior where
    EI→DI between groups cancels the pending EI, so VBlank NEVER fires during
    the copy. This preserves the game's HALT-based frame sync timing.

    Entry: H = tilemap base hi (0x98 or 0x9C), set by caller.
    """
    code = bytearray()
    targets = {}

    def emit(opcodes):
        code.extend(opcodes if isinstance(opcodes, (list, bytes, bytearray)) else [opcodes])

    def mark(name):
        targets[name] = len(code)

    def emit_jr_back(opcode, name):
        offset = targets[name] - (len(code) + 2)
        assert -128 <= offset <= 127, f"JR to {name}: offset {offset}"
        emit([opcode, offset & 0xFF])

    # DI once at start — VBlank never fires during the entire copy
    emit([0xF3])               # DI

    # Init pointers (H already set by caller)
    emit([0x2E, 0x00])        # LD L, 0x00
    emit([0x11, 0xA0, 0xC1]) # LD DE, 0xC1A0        ; WRAM tile source
    emit([0x0E, 24])          # LD C, 24             ; 24 rows

    mark('fast_row')
    emit([0x06, 6])            # LD B, 6              ; 6 groups per row

    mark('fast_group')
    # STAT wait: AND 0x02 blocks modes 2+3
    mark('fast_stat')
    emit([0xF0, 0x41])        # LDH A,[FF41]
    emit([0xE6, 0x02])        # AND 0x02
    emit_jr_back(0x20, 'fast_stat')  # JR NZ → wait

    # Copy 4 tiles: LD A,[DE]; INC DE; LD [HL+],A × 4
    for _ in range(4):
        emit([0x1A, 0x13, 0x22])  # LD A,[DE]; INC DE; LD [HL+],A

    emit([0x05])               # DEC B
    emit_jr_back(0x20, 'fast_group')  # JR NZ → next group

    # Skip 8 unused columns: HL += 8
    emit([0x7D])               # LD A, L
    emit([0xC6, 0x08])        # ADD 8
    emit([0x6F])               # LD L, A
    emit([0x30, 0x01])        # JR NC, +1
    emit([0x24])               # INC H

    emit([0x0D])               # DEC C
    emit_jr_back(0x20, 'fast_row')  # JR NZ → next row

    # Return via bridge (bridge does EI before returning to bank 1)
    emit([0xC3, return_addr & 0xFF, (return_addr >> 8) & 0xFF])

    return bytes(code)


def create_enhanced_tilemap_copy(bg_table_addr: int, base_addr: int,
                                  return_addr: int,
                                  fast_menu_addr: int = 0) -> bytes:
    """Enhanced tilemap copy with mini-batch interleaving.

    For each of 24 rows, 6 mini-batches of 4 tiles each:
      - Palette batch: DI + STAT wait + 4 palette writes (VBK=1)
      - Atomic transition: rewind HL/DE, switch VBK=0 (still DI)
      - Tile batch: STAT wait + 4 tile writes (VBK=0) + EI
      - Prepare VBK=1 for next mini-batch

    Palette→tile gap per 4-tile group: <1 scanline (vs 6 in v2.81).
    Same total HBlank count (12 per row), just reordered for atomicity.

    Entry: H = tilemap base hi (0x98 or 0x9C), set by caller.
    If fast_menu_addr != 0, checks FFC1 and jumps to fast path on menus.
    """
    bg_table_hi = (bg_table_addr >> 8) & 0xFF
    code = bytearray()
    targets = {}

    def emit(opcodes):
        code.extend(opcodes if isinstance(opcodes, (list, bytes, bytearray)) else [opcodes])

    def mark(name):
        targets[name] = len(code)

    def emit_jr_back(opcode, name):
        offset = targets[name] - (len(code) + 2)
        assert -128 <= offset <= 127, f"JR to {name}: offset {offset}"
        emit([opcode, offset & 0xFF])

    def emit_jp_addr(addr):
        emit([0xC3, addr & 0xFF, (addr >> 8) & 0xFF])

    def emit_jp_back(opcode, name):
        addr = base_addr + targets[name]
        emit([opcode, addr & 0xFF, (addr >> 8) & 0xFF])

    # ================================================================
    # MENU CHECK: Skip palette work on menus (FFC1=0)
    # ================================================================
    if fast_menu_addr:
        emit([0xF0, 0xC1])    # LDH A,[FFC1]         ; gameplay flag
        emit([0xB7])           # OR A
        emit([0xCA, fast_menu_addr & 0xFF, (fast_menu_addr >> 8) & 0xFF])
                               # JP Z, fast_menu_copy ; menus → tile-only copy

    # ================================================================
    # PREAMBLE: Save state, set hook flag, mask IE
    # ================================================================
    emit([0x7C])               # LD A, H
    emit([0xE0, 0xEE])        # LDH [FFEE], A       ; save tilemap base hi

    emit([0x3E, HOOK_FLAG])    # LD A, 0x5A
    emit([0xE0, 0x91])        # LDH [FF91], A       ; hook flag → suppress sweep

    emit([0xF0, 0xFF])        # LDH A, [FFFF]       ; read IE register
    emit([0xF5])               # PUSH AF              ; save old IE on stack
    emit([0x3E, 0x01])        # LD A, 0x01           ; VBlank only
    emit([0xE0, 0xFF])        # LDH [FFFF], A       ; mask IE → no timer/STAT

    # Init pointers
    emit([0x2E, 0x00])        # LD L, 0x00
    emit([0x11, 0xA0, 0xC1]) # LD DE, 0xC1A0        ; WRAM tile source

    # Row counter on stack
    emit([0x3E, 24])          # A = 24 rows
    emit([0xF5])               # PUSH AF              ; stack: [row_count] [IE_save]

    # ================================================================
    # ROW LOOP: 6 mini-batches of (4 palette + 4 tile) per row
    # ================================================================
    mark('row_start')

    emit([0x06, bg_table_hi]) # LD B, table_hi       ; B preserved through all batches
    emit([0x3E, 0x01])
    emit([0xE0, 0x4F])        # VBK = 1              ; start in palette mode

    # Push mini-batch counter (6 groups per row)
    emit([0x3E, 6])
    emit([0xF5])               # PUSH AF              ; stack: [batch_count] [row_count] [IE]

    # ----------------------------------------------------------------
    # MINI-BATCH: 4 palette writes + transition + 4 tile writes
    # ----------------------------------------------------------------
    mark('mb_start')

    # Save WRAM position for rewind after palette writes
    emit([0xD5])               # PUSH DE              ; stack: [DE] [batch] [row] [IE]

    # --- Palette group (VBK=1, 4 tiles via ROM lookup) ---
    emit([0xF3])               # DI                   ; protect palette→tile atomicity
    mark('mb_stat1')
    emit([0xF0, 0x41])        # LDH A,[FF41]
    emit([0xE6, 0x02])        # AND 0x02
    emit_jr_back(0x20, 'mb_stat1')  # JR NZ → wait for HBlank

    for _ in range(4):         # 4 tiles per HBlank window (36M)
        emit([0x1A, 0x13])     # LD A,[DE]; INC DE   ; read tile from WRAM
        emit([0x4F])            # LD C, A             ; tile → C for lookup
        emit([0x0A])            # LD A,[BC]           ; palette = table[tile]
        emit([0x22])            # LD [HL+],A          ; write palette attr

    # --- Transition: rewind for tile writes (still DI) ---
    # Rewind HL by 4 (back to these 4 tiles)
    emit([0x7D])               # LD A, L
    emit([0xD6, 4])            # SUB 4
    emit([0x6F])               # LD L, A
    emit([0x30, 0x01])        # JR NC, +1
    emit([0x25])               # DEC H

    # Switch to tile data
    emit([0xAF])               # XOR A
    emit([0xE0, 0x4F])        # VBK = 0

    # Restore DE to mini-batch start
    emit([0xD1])               # POP DE               ; stack: [batch] [row] [IE]

    # --- Tile group (VBK=0, still DI — same 4 tiles) ---
    mark('mb_stat2')
    emit([0xF0, 0x41])        # LDH A,[FF41]
    emit([0xE6, 0x02])        # AND 0x02
    emit_jr_back(0x20, 'mb_stat2')  # JR NZ → wait for HBlank

    for _ in range(4):         # 4 tiles per HBlank window (28M)
        emit([0x1A, 0x13, 0x22])  # LD A,[DE]; INC DE; LD [HL+],A

    emit([0xFB])               # EI                   ; safe to interrupt now

    # --- Prepare next mini-batch ---
    emit([0x3E, 0x01])
    emit([0xE0, 0x4F])        # VBK = 1              ; ready for next palette group

    # Mini-batch counter
    emit([0xF1])               # POP AF               ; A = batch_count
    emit([0x3D])               # DEC A
    emit([0x28, 0x04])        # JR Z, +4             ; → batches_done (skip PUSH+JR)
    emit([0xF5])               # PUSH AF              ; push decremented count
    emit_jr_back(0x18, 'mb_start')  # JR → next mini-batch

    # ----------------------------------------------------------------
    # Row complete: skip 8-column gap, advance row counter
    # ----------------------------------------------------------------
    # batches_done: stack is [row_count] [IE]
    emit([0xAF])               # XOR A
    emit([0xE0, 0x4F])        # VBK = 0              ; clean up after last batch

    # Skip 8-column gap in tilemap
    emit([0x7D])               # LD A, L
    emit([0xC6, 0x08])        # ADD 8
    emit([0x6F])               # LD L, A
    emit([0x30, 0x01])        # JR NC, +1
    emit([0x24])               # INC H

    # Row counter
    emit([0xF1])               # POP AF               ; A = row_count
    emit([0x3D])               # DEC A
    emit([0x28, 0x04])        # JR Z, +4             ; → cleanup (skip PUSH+JP)
    emit([0xF5])               # PUSH AF
    emit_jp_back(0xC3, 'row_start')

    # ================================================================
    # CLEANUP: restore VBK, clear hook flag, restore IE
    # ================================================================
    emit([0xAF])               # XOR A
    emit([0xE0, 0x4F])        # VBK = 0

    emit([0xAF])               # XOR A
    emit([0xE0, 0x91])        # LDH [FF91], A       ; clear hook flag

    emit([0x3E, 24])          # LD A, 24
    emit([0xE0, 0xA5])        # LDH [FFA5], A       ; Phase 2 maintenance mode

    emit([0xF1])               # POP AF              ; restore old IE
    emit([0xE0, 0xFF])        # LDH [FFFF], A       ; restore IE register

    # Return via bridge
    emit_jp_addr(return_addr)

    return bytes(code)


def create_bg_sweep_no_scroll(bg_table_addr: int, base_addr: int,
                               rows_per_frame: int = 2) -> bytes:
    """VBlank BG sweep — simplified v2.73 without scroll column detection.

    Uses FFA5 as state counter (instead of FF91 which is now the hook flag).
    Phase 1 (FFA5 = 0-23): Initial sweep, 2 rows/frame, 12 frames
    Phase 2 (FFA5 = 24-47): Maintenance, 1 row/frame, wraps at 48→24

    Covers all 24 rows that the game's tilemap copy writes.
    No scroll column detection — the combined function handles scroll updates.
    """
    bg_table_hi = (bg_table_addr >> 8) & 0xFF
    code = bytearray()
    jr_patches = []
    jp_patches = []
    targets = {}

    def emit(opcodes):
        code.extend(opcodes if isinstance(opcodes, (list, bytes, bytearray)) else [opcodes])

    def mark(name):
        targets[name] = len(code)

    def emit_jr_fwd(opcode, name):
        code.append(opcode)
        jr_patches.append((len(code), name))
        code.append(0x00)

    def emit_jr_back(opcode, name):
        offset = targets[name] - (len(code) + 2)
        assert -128 <= offset <= 127, f"JR to {name}: offset {offset}"
        emit([opcode, offset & 0xFF])

    def emit_jp_fwd(name):
        emit([0xC3])
        jp_patches.append((len(code), name))
        emit([0x00, 0x00])

    def patch_all():
        for pos, name in jr_patches:
            offset = targets[name] - (pos + 1)
            assert -128 <= offset <= 127, f"JR to {name} from {pos}: {offset}"
            code[pos] = offset & 0xFF
        for pos, name in jp_patches:
            addr = base_addr + targets[name]
            code[pos] = addr & 0xFF
            code[pos + 1] = (addr >> 8) & 0xFF

    # ================================================================
    # Row processing: 32 tiles per row with STAT waits, dual-tilemap writes
    # ================================================================
    def emit_row_loop(stat_label, tile_label):
        emit([0x06, 0x20])        # LD B, 32
        mark(tile_label)
        mark(stat_label)
        emit([0xF0, 0x41])        # LDH A,[FF41]
        emit([0xE6, 0x02])        # AND 0x02
        emit_jr_back(0x20, stat_label)

        emit([0x1A])               # LD A,[DE] ; tile
        emit([0x6F])               # LD L, A
        emit([0x7E])               # LD A,[HL] ; palette
        emit([0xE0, 0xA9])        # LDH [FFA9],A

        emit([0x3E, 0x01])
        emit([0xE0, 0x4F])        # VBK=1

        emit([0xF0, 0xA9])
        emit([0x12])               # write active

        emit([0x7A])
        emit([0xEE, 0x04])
        emit([0x57])               # D ^= 0x04
        emit([0xF0, 0xA9])
        emit([0x12])               # write other

        emit([0x7A])
        emit([0xEE, 0x04])
        emit([0x57])               # restore D

        emit([0xAF])
        emit([0xE0, 0x4F])        # VBK=0

        emit([0x1C])               # INC E
        emit([0x05])               # DEC B
        emit_jr_back(0x20, tile_label)

    def emit_row_addr():
        """Compute D:E from tilemap_row in A. Uses FFEE for base_hi."""
        emit([0x47])               # LD B, A
        emit([0xE6, 0x07])
        emit([0xCB, 0x37])        # SWAP (×16)
        emit([0x87])               # ×32
        emit([0x5F])               # LD E, A

        emit([0x78])               # LD A, B
        emit([0xCB, 0x3F])
        emit([0xCB, 0x3F])
        emit([0xCB, 0x3F])        # row>>3
        emit([0x57])               # LD D
        emit([0xF0, 0xEE])        # base_hi
        emit([0x82])
        emit([0x57])               # D = base_hi + row>>3

    # ================================================================
    # PREAMBLE
    # ================================================================
    emit([0xF0, 0xC1])        # gameplay check
    emit([0xB7])
    emit([0xC8])               # RET Z (menus)

    emit([0xC5, 0xD5, 0xE5])  # PUSH BC, DE, HL
    emit([0x26, bg_table_hi]) # LD H, table_hi
    emit([0xAF])
    emit([0xE0, 0x4F])        # VBK=0

    # Compute base_hi from LCDC
    emit([0xF0, 0x40])
    emit([0xE6, 0x08])
    emit([0x0F])
    emit([0xC6, 0x98])
    emit([0xE0, 0xEE])        # FFEE = base_hi

    # Phase check — using FFA5 (not FF91!)
    emit([0xF0, 0xA5])        # LDH A,[FFA5]
    emit([0xFE, 24])
    emit_jr_fwd(0x30, 'phase2')  # JR NC → phase 2

    # ================================================================
    # PHASE 1: Initial sweep (2 rows/frame)
    # ================================================================
    emit([0x0E, rows_per_frame])  # LD C, rows

    mark('p1_row')
    # tilemap_row = (SCY/8 + FFA5) & 0x1F
    emit([0xF0, 0x42])        # SCY
    emit([0xCB, 0x3F])
    emit([0xCB, 0x3F])
    emit([0xCB, 0x3F])        # SCY/8
    emit([0x47])               # LD B
    emit([0xF0, 0xA5])        # row counter (FFA5)
    emit([0x80])               # + SCY/8
    emit([0xE6, 0x1F])        # & 0x1F

    emit_row_addr()
    emit_row_loop('p1s', 'p1t')

    # Advance FFA5
    emit([0xF0, 0xA5])
    emit([0x3C])               # INC
    emit([0xE0, 0xA5])

    emit([0x0D])               # DEC C
    emit_jr_back(0x20, 'p1_row')

    # Check if Phase 1 complete (FFA5 reached 24)
    emit([0xF0, 0xA5])
    emit([0xFE, 24])          # CP 24
    emit_jr_fwd(0x20, 'p1_done')  # JR NZ → not done

    mark('p1_done')
    emit_jp_fwd('cleanup')

    # ================================================================
    # PHASE 2: Maintenance (1 row/frame, no scroll detection)
    # ================================================================
    mark('phase2')

    # row_index = (FFA5 - 24) = 0-23
    emit([0xF0, 0xA5])        # A = FFA5 (24-47)
    emit([0xD6, 24])          # SUB 24

    # tilemap_row = (SCY/8 + row_index) & 0x1F
    emit([0x47])               # LD B
    emit([0xF0, 0x42])        # SCY
    emit([0xCB, 0x3F])
    emit([0xCB, 0x3F])
    emit([0xCB, 0x3F])
    emit([0x80])               # + row_index
    emit([0xE6, 0x1F])

    emit_row_addr()
    emit_row_loop('p2s', 'p2t')

    # Advance FFA5: 24→25→...→47→24
    emit([0xF0, 0xA5])
    emit([0x3C])               # INC
    emit([0xFE, 48])          # CP 48
    emit_jr_fwd(0x38, 'p2_no_wrap')  # JR C → < 48
    emit([0x3E, 24])          # wrap to 24
    mark('p2_no_wrap')
    emit([0xE0, 0xA5])

    # ================================================================
    # CLEANUP
    # ================================================================
    mark('cleanup')
    emit([0xAF])
    emit([0xE0, 0x4F])        # VBK=0
    emit([0xE1, 0xD1, 0xC1]) # POP HL, DE, BC
    emit([0xC9])               # RET

    patch_all()
    return bytes(code)


def create_combined_with_scroll_edge(bg_sweep_addr: int, cond_pal_addr: int,
                                      shadow_main_addr: int,
                                      bg_table_addr: int) -> bytes:
    """Combined VBlank handler with VBK safety and scroll-edge pre-coloring.

    Flow:
    1. Save/restore VBK (FF4F) around all work
    2. Save FFA9 (prev SCX/8) before sweep can clobber it
    3. Hook flag check → skip both sweep and scroll-edge if active
    4. CALL bg_sweep
    5. Scroll detection: compare prev SCX/8 with current
    6. If scrolled: color right-edge column on active tilemap
    7. Save current SCX/8 to FFA9
    8. CALL cond_pal, OBJ colorizer, DMA
    9. Restore VBK
    """
    bg_table_hi = (bg_table_addr >> 8) & 0xFF
    code = bytearray()
    jr_patches = []  # (pos, target_name) for forward JR
    targets = {}

    def emit(opcodes):
        code.extend(opcodes if isinstance(opcodes, (list, bytes, bytearray)) else [opcodes])

    def mark(name):
        targets[name] = len(code)

    def emit_jr_fwd(opcode, name):
        """Emit a forward JR with placeholder, to be patched."""
        code.append(opcode)
        jr_patches.append((len(code), name))
        code.append(0x00)

    def emit_jr_back(opcode, name):
        offset = targets[name] - (len(code) + 2)
        assert -128 <= offset <= 127, f"JR to {name}: offset {offset}"
        emit([opcode, offset & 0xFF])

    def patch_all():
        for pos, name in jr_patches:
            offset = targets[name] - (pos + 1)
            assert -128 <= offset <= 127, f"JR to {name} from {pos}: {offset}"
            code[pos] = offset & 0xFF

    # ================================================================
    # VBK SAFETY: Save current VBK, force to 0
    # (ISR at 0x06D1 already saves AF/BC/DE/HL — no need to save here)
    # ================================================================
    emit([0xF0, 0x4F])        # LDH A,[FF4F]        ; read current VBK
    emit([0xF5])               # PUSH AF              ; save on stack
    emit([0xAF])               # XOR A
    emit([0xE0, 0x4F])        # LDH [FF4F],A        ; ensure VBK=0

    # ================================================================
    # SAVE FFA9 (prev SCX/8) before sweep can clobber it
    # ================================================================
    emit([0xF0, 0xA9])        # LDH A,[FFA9]
    emit([0xF5])               # PUSH AF              ; stack: [prev_scx] [vbk]

    # ================================================================
    # HOOK FLAG CHECK
    # ================================================================
    emit([0xF0, 0x91])        # LDH A,[FF91]
    emit([0xFE, HOOK_FLAG])   # CP 0x5A
    emit_jr_fwd(0x28, 'skip_bg')  # JR Z → skip sweep + scroll-edge

    # ================================================================
    # BG SWEEP (only when hook NOT active)
    # ================================================================
    emit([0xCD, bg_sweep_addr & 0xFF, (bg_sweep_addr >> 8) & 0xFF])

    # ================================================================
    # SCROLL-EDGE DETECTION (skip on menus — FFC1=0)
    # ================================================================
    emit([0xF1])               # POP AF → A = prev SCX/8
    emit([0x47])               # LD B,A               ; B = prev_scx

    # Menu check: skip edge coloring on title/menus
    emit([0xF0, 0xC1])        # LDH A,[FFC1]         ; gameplay flag
    emit([0xB7])               # OR A
    # If menu (Z), A=0 → writes 0 to FFA9 at no_scroll (harmless)
    emit_jr_fwd(0x28, 'no_scroll')  # JR Z → menu, skip edge

    emit([0xF0, 0x43])        # LDH A,[FF43]         ; SCX register
    emit([0xCB, 0x3F])        # SRL A
    emit([0xCB, 0x3F])        # SRL A
    emit([0xCB, 0x3F])        # SRL A                 ; SCX/8
    emit([0xE6, 0x1F])        # AND 0x1F              ; cur_scx (0-31)
    emit([0xB8])               # CP B                  ; compare with prev

    emit_jr_fwd(0x28, 'no_scroll')  # JR Z → no scroll, skip edge

    # ================================================================
    # SCROLL-EDGE: Color right-edge column on active tilemap
    # ================================================================
    # A = cur_scx at this point
    emit([0xF5])               # PUSH AF              ; save cur_scx

    # Compute right_col = (cur_scx + 20) & 0x1F
    emit([0xC6, 20])          # ADD 20
    emit([0xE6, 0x1F])        # AND 0x1F
    emit([0x5F])               # LD E,A               ; E = right_col

    # Save registers for edge loop
    emit([0xC5])               # PUSH BC
    emit([0xD5])               # PUSH DE
    emit([0xE5])               # PUSH HL

    # Compute tilemap base hi from LCDC bit 3
    # (FFEE may be stale if sweep just ran with different LCDC; recompute)
    emit([0xF0, 0x40])        # LDH A,[FF40]         ; LCDC
    emit([0xE6, 0x08])        # AND 0x08             ; bit 3
    emit([0x0F])               # RRCA                 ; 0x08→0x04, 0x00→0x00
    emit([0xC6, 0x98])        # ADD 0x98             ; 0x98 or 0x9C
    emit([0xE0, 0xEE])        # LDH [FFEE],A         ; save for D wrap check

    # Compute first visible row from SCY
    emit([0xF0, 0x42])        # LDH A,[FF42]         ; SCY
    emit([0xCB, 0x3F])        # SRL A
    emit([0xCB, 0x3F])        # SRL A
    emit([0xCB, 0x3F])        # SRL A                 ; SCY/8 (0-31)
    emit([0x4F])               # LD C,A               ; C = full SCY/8

    # Address low byte: ((SCY/8 & 7) << 5) | right_col
    emit([0xE6, 0x07])        # AND 0x07             ; low 3 bits of row
    emit([0xCB, 0x37])        # SWAP A               ; ×16
    emit([0x87])               # ADD A                ; ×32
    emit([0xB3])               # OR E                 ; | right_col
    emit([0x5F])               # LD E,A               ; E = addr_lo

    # Address high byte: base_hi + (SCY/8 >> 3)
    emit([0x79])               # LD A,C               ; full SCY/8
    emit([0xCB, 0x3F])        # SRL A
    emit([0xCB, 0x3F])        # SRL A
    emit([0xCB, 0x3F])        # SRL A                 ; SCY/8 >> 3 (0-3)
    emit([0x47])               # LD B,A               ; temp
    emit([0xF0, 0xEE])        # LDH A,[FFEE]         ; base_hi
    emit([0x80])               # ADD B
    emit([0x57])               # LD D,A               ; D = addr_hi

    # Palette lookup table
    emit([0x26, bg_table_hi]) # LD H, table_hi (0x70)

    # Loop counter: 18 visible rows
    emit([0x0E, 18])          # LD C, 18

    # ---- EDGE LOOP ----
    mark('edge_loop')
    # Read tile (VBK=0, ensured by VBK safety at entry)
    emit([0x1A])               # LD A,[DE]            ; read tile
    emit([0x6F])               # LD L,A
    emit([0x7E])               # LD A,[HL]            ; palette lookup
    emit([0x47])               # LD B,A               ; save palette

    # Write palette attr (VBK=1)
    emit([0x3E, 0x01])        # LD A,0x01
    emit([0xE0, 0x4F])        # LDH [FF4F],A         ; VBK=1
    emit([0x78])               # LD A,B
    emit([0x12])               # LD [DE],A            ; write palette attr

    # Restore VBK=0
    emit([0xAF])               # XOR A
    emit([0xE0, 0x4F])        # LDH [FF4F],A         ; VBK=0

    # Advance DE by 32 (next tilemap row)
    emit([0x7B])               # LD A,E
    emit([0xC6, 0x20])        # ADD 0x20
    emit([0x5F])               # LD E,A
    emit_jr_fwd(0x30, 'no_d_wrap')  # JR NC → no carry
    emit([0x14])               # INC D
    # Wrap check: if D crossed 4-byte boundary, subtract 4
    # D was base_hi+0..3. After INC, if (D & 0x03) == 0, we overflowed.
    emit([0x7A])               # LD A,D
    emit([0xE6, 0x03])        # AND 0x03
    emit_jr_fwd(0x20, 'no_d_wrap')  # JR NZ → no wrap needed
    emit([0x7A])               # LD A,D
    emit([0xD6, 0x04])        # SUB 4
    emit([0x57])               # LD D,A
    mark('no_d_wrap')

    # Loop counter
    emit([0x0D])               # DEC C
    emit_jr_back(0x20, 'edge_loop')  # JR NZ → next row

    # Restore registers
    emit([0xE1])               # POP HL
    emit([0xD1])               # POP DE
    emit([0xC1])               # POP BC

    # Pop cur_scx → A
    emit([0xF1])               # POP AF → A = cur_scx

    # Fall through to no_scroll

    # ================================================================
    # NO_SCROLL: Save current SCX/8 to FFA9
    # ================================================================
    mark('no_scroll')
    emit([0xE0, 0xA9])        # LDH [FFA9],A         ; save cur SCX/8

    emit_jr_fwd(0x18, 'after_bg')   # JR → skip skip_bg

    # ================================================================
    # SKIP_BG: Hook active — discard prev_scx, skip to standard handler
    # ================================================================
    mark('skip_bg')
    emit([0xF1])               # POP AF               ; discard prev_scx

    # ================================================================
    # AFTER_BG: Standard handler chain
    # ================================================================
    mark('after_bg')
    # Menu early-out: skip palette + OBJ colorizer on menus (saves ~800M/frame)
    emit([0xF0, 0xC1])        # LDH A,[FFC1]
    emit([0xB7])               # OR A
    emit_jr_fwd(0x28, 'just_dma')  # JR Z → menus: skip to DMA only
    emit([0xCD, cond_pal_addr & 0xFF, (cond_pal_addr >> 8) & 0xFF])
    emit([0xCD, shadow_main_addr & 0xFF, (shadow_main_addr >> 8) & 0xFF])
    mark('just_dma')
    emit([0xCD, 0x80, 0xFF])  # CALL DMA (FF80)

    # ================================================================
    # VBK RESTORE
    # ================================================================
    emit([0xF1])               # POP AF               ; restore old VBK
    emit([0xE0, 0x4F])        # LDH [FF4F],A
    emit([0xC9])               # RET

    patch_all()
    return bytes(code)


def build_v284():
    """Build v2.84 ROM — scroll-edge VBlank pre-coloring + VBK safety."""
    input_rom = Path("rom/Penta Dragon (J).gb")
    output_path = Path("rom/working/penta_dragon_dx_FIXED.gb")
    palette_yaml = Path("palettes/penta_palettes_v097.yaml")

    with open(input_rom, "rb") as f:
        rom = bytearray(f.read())

    apply_all_display_patches(rom)
    palettes = load_palettes_from_yaml(palette_yaml)

    # Address layout
    pal_addr = 0x6800
    boss_pal_addr = 0x6880; boss_slot_addr = 0x68C0
    swj_addr = 0x68D0; sdj_addr = 0x68D8
    sp_addr = 0x68E0; shp_addr = 0x68E8; tp_addr = 0x68F0

    pal_loader_addr = 0x6900
    shadow_main_addr = 0x69D0
    colorizer_addr = 0x6A10
    tile_pal_addr = 0x6B00
    enhanced_copy_addr = 0x6C00
    bg_table_addr = 0x7000  # lookup table for hook's palette pass

    # Bank trampoline addresses
    return_bridge_addr = 0x42B4

    # Generate standard components
    pal_loader = create_palette_loader(pal_addr, boss_pal_addr, boss_slot_addr,
                                       swj_addr, sdj_addr, sp_addr, shp_addr, tp_addr)
    shadow_main = create_shadow_colorizer_main(colorizer_addr, boss_slot_addr)
    colorizer = create_tile_based_colorizer(colorizer_addr)
    tile_pal = create_tile_to_palette_subroutine()
    bg_table = create_bg_tile_table(ff_filter=False)

    # Two-pass layout: first pass without fast_menu_addr to determine sizes
    enhanced_copy_tmp = create_enhanced_tilemap_copy(bg_table_addr, enhanced_copy_addr,
                                                      return_bridge_addr, fast_menu_addr=0)
    bg_sweep_addr = (enhanced_copy_addr + len(enhanced_copy_tmp) + 6 + 0xF) & ~0xF  # +6 for FFC1 check
    bg_sweep = create_bg_sweep_no_scroll(bg_table_addr, bg_sweep_addr)
    cond_pal_addr = (bg_sweep_addr + len(bg_sweep) + 0xF) & ~0xF
    cond_pal = create_conditional_palette_always(pal_loader_addr)
    combined_addr = (cond_pal_addr + len(cond_pal) + 0xF) & ~0xF
    combined = create_combined_with_scroll_edge(
        bg_sweep_addr, cond_pal_addr, shadow_main_addr, bg_table_addr
    )

    # Fast menu copy placed after combined
    fast_menu_addr = (combined_addr + len(combined) + 0xF) & ~0xF
    fast_menu_copy = create_fast_menu_copy(fast_menu_addr, return_bridge_addr)
    print(f"Fast menu copy: {len(fast_menu_copy)} bytes at 0x{fast_menu_addr:04X}")

    # Second pass: regenerate enhanced copy WITH fast_menu_addr
    enhanced_copy = create_enhanced_tilemap_copy(bg_table_addr, enhanced_copy_addr,
                                                  return_bridge_addr,
                                                  fast_menu_addr=fast_menu_addr)
    print(f"Enhanced tilemap copy: {len(enhanced_copy)} bytes at 0x{enhanced_copy_addr:04X}")

    # Verify bg_sweep_addr still correct after second pass
    bg_sweep_addr_check = (enhanced_copy_addr + len(enhanced_copy) + 0xF) & ~0xF
    assert bg_sweep_addr_check == bg_sweep_addr, \
        f"Layout shift! bg_sweep moved from {bg_sweep_addr:#x} to {bg_sweep_addr_check:#x}"

    print(f"BG sweep: {len(bg_sweep)} bytes at 0x{bg_sweep_addr:04X}")
    print(f"Cond palette (always-load): {len(cond_pal)} bytes at 0x{cond_pal_addr:04X}")
    print(f"Combined: {len(combined)} bytes at 0x{combined_addr:04X}")
    print(f"  → VBK safety + scroll-edge pre-coloring + hook check + CondPal + OBJ + DMA")

    # Verify layout
    assert fast_menu_addr + len(fast_menu_copy) <= bg_table_addr, \
        f"Layout overflow: fast_menu ends {fast_menu_addr+len(fast_menu_copy):#x} > bg_table {bg_table_addr:#x}"

    hook = create_bank_aware_vblank_hook(combined_addr)

    # Overlap check
    regions = [
        ('pal_loader', pal_loader_addr, len(pal_loader)),
        ('shadow_main', shadow_main_addr, len(shadow_main)),
        ('colorizer', colorizer_addr, len(colorizer)),
        ('tile_pal', tile_pal_addr, len(tile_pal)),
        ('enhanced_copy', enhanced_copy_addr, len(enhanced_copy)),
        ('bg_sweep', bg_sweep_addr, len(bg_sweep)),
        ('cond_pal', cond_pal_addr, len(cond_pal)),
        ('combined', combined_addr, len(combined)),
        ('fast_menu', fast_menu_addr, len(fast_menu_copy)),
        ('bg_table', bg_table_addr, len(bg_table)),
    ]
    for i, (na, sa, sza) in enumerate(regions):
        for nb, sb, szb in regions[i+1:]:
            if sa < sb + szb and sb < sa + sza:
                raise ValueError(f"OVERLAP: {na} ({sa:#x}-{sa+sza:#x}) and {nb} ({sb:#x}-{sb+szb:#x})")

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
    w(enhanced_copy_addr, enhanced_copy)
    w(bg_sweep_addr, bg_sweep)
    w(bg_table_addr, bg_table)
    w(combined_addr, combined)
    w(fast_menu_addr, fast_menu_copy)

    # =============================================
    # HOOK: Bank 1 trampoline at 0x42A7
    # =============================================
    bank1_patch = bytearray([
        0xF3,              # DI                at 0x42A7
        0x3E, 0x0D,        # LD A, 0x0D       at 0x42A8
        0xE0, 0x99,        # LDH [FF99], A    at 0x42AA
        0xEA, 0x00, 0x20,  # LD [0x2000], A   at 0x42AC → bank 13, PC=0x42AF
    ])
    dead_len = 0x42BC - 0x42AF
    bank1_patch.extend([0x00] * dead_len)
    bank1_patch.extend([
        0xFB,              # EI               at 0x42BC
        0xC9,              # RET              at 0x42BD
    ])
    rom[0x42A7:0x42A7+len(bank1_patch)] = bank1_patch
    print(f"Bank 1 trampoline: {len(bank1_patch)} bytes at 0x42A7-0x{0x42A7+len(bank1_patch)-1:04X}")

    # Bank 13 bridge at 0x42AF
    bridge = bytearray([
        0xFB,              # EI               at 0x42AF
        0xC3, enhanced_copy_addr & 0xFF, (enhanced_copy_addr >> 8) & 0xFF,  # JP 0x6C00
        0x00,              # pad              at 0x42B3
        0xF3,              # DI               at 0x42B4
        0x3E, 0x01,        # LD A, 0x01       at 0x42B5
        0xE0, 0x99,        # LDH [FF99], A    at 0x42B7
        0xEA, 0x00, 0x20,  # LD [0x2000], A   at 0x42B9 → bank 1, PC=0x42BC
    ])
    bridge_offset = bank13 + (0x42AF - 0x4000)
    rom[bridge_offset:bridge_offset+len(bridge)] = bridge
    print(f"Bank 13 bridge: {len(bridge)} bytes at 0x42AF-0x{0x42AF+len(bridge)-1:04X}")

    # Standard patches
    rom[0x06D5:0x06D5+3] = bytearray([0x00, 0x00, 0x00])  # NOP out original palette load
    rom[0x0824:0x0824+len(hook)] = hook                     # VBlank hook
    rom[0x143] = 0x80                                       # CGB flag

    # Header checksum
    x = 0
    for i in range(0x134, 0x14D):
        x = (x - rom[i] - 1) & 0xFF
    rom[0x14D] = x

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "wb") as f:
        f.write(rom)
    return output_path


if __name__ == "__main__":
    rom_path = build_v284()
    print(f"\nBuilt v2.84: {rom_path}")
    print(f"Scroll-edge VBlank pre-coloring + VBK safety")
    print(f"VBK save/restore around all VBlank handler work")
    print(f"Right-edge column pre-colored during VBlank when scroll detected")
    print(f"FFA9 repurposed: prev SCX/8 for scroll detection (cond_pal always loads)")
    print(f"VBlank handler: [VBK safety] → [scroll-edge] → CondPal + OBJ + DMA → [VBK restore]")
