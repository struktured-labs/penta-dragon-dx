#!/usr/bin/env python3
"""Penta Dragon DX v3.01 — GDMA-based BG attr transfer.

Replaces v3.00's dual-STAT-wait inline hook with:
  1. Tile-only inline hook (single STAT wait, vanilla speed)
  2. VBlank attr computation: read tiles from C1A0, lookup bg_table,
     write a 256-byte attr buffer to WRAM bank 0 (CC80-CCFF)
  3. GDMA transfer: hardware DMA 256 bytes from WRAM bank 0 to
     VRAM tilemap VBK=1 every VBlank (~2048T)

All runtime WRAM code/data uses bank 0, which is accessible without FF70.
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
    """Tile-to-palette lookup table (256 bytes, one per tile ID).

    Tile-ID assignments derived from multi-room tilemap context
    analysis. Pal-5 (red hazard) entries restored for spike cylinders
    only; tiles 0x47/0x57 are dual-use (wall corners + thrusting
    spikes) and we choose pal-6 (wall) because the orange/red
    artifacts on wall corners are MORE visible than wall-color spikes.

    User-reported regression 2026-05-23: 0x47/0x57 = pal 5 caused
    orange wall-corner artifacts (matched v3.00 byte but visible
    regression). Reverted to pal 6 to avoid wall-corner artifacts.
    """
    table = bytearray(256)
    # Wall edge tiles → pal 6 (slate gray)
    for i in [0x14, 0x16, 0x17, 0x18, 0x19, 0x1A, 0x1C, 0x1E]:
        table[i] = 6
    # Wall interior tiles → pal 6
    for i in [0x25, 0x26, 0x34, 0x35, 0x36, 0x37, 0x38]:
        table[i] = 6
    # Corner/doorway tiles → pal 6. 0x47 and 0x57 INCLUDED here
    # (NOT in hazard list) because their wall-corner use is more
    # visible than their thrusting-spike use.
    for i in [0x41, 0x42, 0x44, 0x45, 0x46, 0x47, 0x48, 0x49,
              0x54, 0x55, 0x56, 0x57, 0x59]:
        table[i] = 6
    # Hazards: rotating spike cylinders → pal 6 (METALLIC slate/gunmetal,
    # 7FFF/6F7B/2D4A). Was pal 5 (white/yellow/red) which read washed-out and
    # lava-ish; user wants a metallic look. pal 6 is the existing metal ramp
    # (shared with walls, but spikes are shape-distinct rotating cylinders).
    # pal 5 stays free for stage-2 LAVA. (0x47/0x57 excluded — wall corners.)
    for i in [0x2A, 0x2B, 0x2C, 0x2D, 0x2E, 0x3A, 0x3B, 0x3C, 0x3D]:
        table[i] = 6
    # Items + FONT. Tiles 0x80-0x99 are the title/menu uppercase font (A=0x80..
    # Z=0x99); 0x88-0xDF are item pickups. Both -> pal 1 so ALL title/menu text
    # is one uniform color (red) instead of the A-H(pal0=black)/I-Z(pal1=red)
    # two-tone split. Verified safe: tiles 0x80-0x9F never appear as dungeon BG
    # tiles (they're font/letters only), so the dungeon is unaffected; arenas
    # use their own tables. Start at 0x80 (was 0x88) to also catch A-H.
    for i in range(0x80, 0xE0):
        table[i] = 1
    # Sentinel — was 0xFF historically (palette 7 sentinel for ff_filter).
    # Changed to 0x00 (pal 0): inline tile+attr copy at 0x42A7 looks up
    # bg_table[tile_id] and writes the result as the attr byte. Any
    # tile-ID 0xFF the game writes would have attr=0xFF=pal 7 splotch.
    # The sentinel role is no longer needed in v3.01.
    table[0xFF] = 0x00
    return bytes(table)


BG_TABLE_BYTES = _bg_table()
WRAM_BG_TABLE = 0xCC00
WRAM_BG_TABLE_HI = (WRAM_BG_TABLE >> 8) & 0xFF
ATTR_BUFFER = 0xCC80  # WRAM bank 0 (dead-code attr buffer, kept consistent)


def create_inline_tile_copy_tileonly(arena_neutralize_d880=None,
                                      title_gate=None) -> bytes:
    """Inline tile+attr copy with D880-gated attr writes.

    Per group: 4 tile writes (VBK=0) then 4 attr writes (VBK=1) with
    WRAM_BG_TABLE lookup. Single STAT wait per phase. ~vanilla speed
    once optimized.

    Dispatch (when gates are set):
      1. D880 < title_gate          -> tile-only (title screen — avoids
         animation race between tile phase and attr phase)
      2. D880 < arena_neutralize    -> full tile+attr (dungeon — pickup
         items get immediate attrs, no palette flicker)
      3. D880 in [base, base+9)     -> tile-only (arena — position sweep
         owns the attr plane, tile-ID attrs would fight posmap)
      4. else                       -> full tile+attr (splash/banner;
         scene_detect loads all-pal0 table, attrs are harmless)

    Replaces 0x42A7..0x436D. H pre-set to 0x98 or 0x9C by entry point.
    24 rows x 6 groups x 4 tiles = 576 tiles.
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

    # Setup (H pre-set by entry point to 0x98 or 0x9C)
    emit([0x2E, 0x00])               # LD L, 0x00
    emit([0x11, 0xA0, 0xC1])         # LD DE, 0xC1A0 (WRAM tile source)

    # ---- Dispatch: title gate + arena neutralize ----
    # Both gate the attr phase. When both are set:
    #   1. D880 < title_gate         -> tile-only (title screen)
    #   2. D880 < arena_neutralize   -> full tile+attr (dungeon)
    #   3. D880 in [base, base+9)    -> tile-only (arena)
    #   4. else                      -> full tile+attr (splash/banner)
    # When neither is set: simple full tile+attr copy everywhere.
    j_tileonly = None                # arena dispatch JR patch pos
    j_tileonly_title = None          # title gate JR patch pos

    # 1. Title gate: D880 < title_gate -> tile-only
    if title_gate is not None:
        emit([0xFA, 0x80, 0xD8])     # LD A, [D880]
        emit([0xFE, title_gate & 0xFF])  # CP title_gate
        j_tileonly_title = emit_jr_fwd(0x38)  # JR C, tileonly

    # 2. Arena neutralize: D880 in [base, base+9) -> tile-only
    if arena_neutralize_d880 is not None:
        emit([0xFA, 0x80, 0xD8])     # LD A, [D880]
        emit([0xD6, arena_neutralize_d880 & 0xFF])  # SUB base
        j_full = emit_jr_fwd(0x38)   # JR C, full      (D880 < base = dungeon)
        emit([0xFE, 0x09])           # CP 9
        j_tileonly = emit_jr_fwd(0x38)  # JR C, tileonly (idx 0..8 = arena)
        patch_jr_fwd(j_full)         # else fall through to full

    emit([0x3E, 0x18])               # LD A, 24
    emit([0xF5])                     # PUSH AF (row counter on stack)

    mark('row_loop')
    emit([0x0E, 0x06])               # LD C, 6 (groups per row)

    mark('group_loop')
    # -------- TILE PHASE: VBK=0 (default), 4 tile writes --------
    emit([0xF3])                     # DI
    mark('stat3a')
    emit([0xF0, 0x41])               # LDH A,[FF41]
    emit([0xE6, 0x03])               # AND 3
    emit([0xFE, 0x03])               # CP 3
    emit_jr_back(0x20, 'stat3a')     # JR NZ, stat3a
    mark('stat0a')
    emit([0xF0, 0x41])               # LDH A,[FF41]
    emit([0xE6, 0x03])               # AND 3
    emit_jr_back(0x20, 'stat0a')     # JR NZ, stat0a
    for _ in range(4):
        emit([0x1A, 0x13, 0x22])     # LD A,[DE]; INC DE; LD [HL+],A
    emit([0xFB])                     # EI

    # -------- TRANSITION: rewind L,E by 4; VBK=1 --------
    emit([0xC5])                     # PUSH BC (save group counter C)
    emit([0x7D])                     # LD A, L
    emit([0xD6, 0x04])               # SUB 4
    emit([0x6F])                     # LD L, A
    emit([0x30, 0x01])               # JR NC, +1
    emit([0x25])                     # DEC H
    emit([0x7B])                     # LD A, E
    emit([0xD6, 0x04])               # SUB 4
    emit([0x5F])                     # LD E, A
    emit([0x30, 0x01])               # JR NC, +1
    emit([0x15])                     # DEC D
    emit([0x06, WRAM_BG_TABLE_HI])   # LD B, 0xCC (bg_table_hi in WRAM)
    emit([0x3E, 0x01])               # LD A, 1
    emit([0xE0, 0x4F])               # LDH [FF4F], A (VBK=1 attr bank)

    # -------- ATTR PHASE: VBK=1, 4 attr writes via [BC] lookup --------
    emit([0xF3])                     # DI
    mark('stat3b')
    emit([0xF0, 0x41])
    emit([0xE6, 0x03])
    emit([0xFE, 0x03])
    emit_jr_back(0x20, 'stat3b')
    mark('stat0b')
    emit([0xF0, 0x41])
    emit([0xE6, 0x03])
    emit_jr_back(0x20, 'stat0b')
    # 4 attr writes: LD A,[DE]; INC DE; LD C,A; LD A,[BC]; LD [HL+],A
    for _ in range(4):
        emit([0x1A, 0x13, 0x4F, 0x0A, 0x22])
    emit([0xFB])                     # EI

    # -------- POST-ATTR: VBK=0 --------
    emit([0xAF])                     # XOR A
    emit([0xE0, 0x4F])               # LDH [FF4F], A (VBK=0)
    emit([0xC1])                     # POP BC (restore group counter)

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
    emit([0xC9])                     # RET (full tile+attr path)

    # ---- TILE-ONLY PATH: copy tiles, write NO attrs ----
    # Both title gate and arena dispatch jump here (at j_tileonly or
    # j_tileonly_title). Same L/E/HL advancement as full path.
    if j_tileonly is not None or j_tileonly_title is not None:
        if j_tileonly is not None:
            patch_jr_fwd(j_tileonly)
        if j_tileonly_title is not None:
            patch_jr_fwd(j_tileonly_title)
        emit([0x3E, 0x18])           # LD A, 24
        emit([0xF5])                 # PUSH AF
        mark('to_row')
        emit([0x0E, 0x06])           # LD C, 6
        mark('to_group')
        emit([0xF3])                 # DI
        mark('to_s3')
        emit([0xF0, 0x41, 0xE6, 0x03, 0xFE, 0x03])  # LDH A,[FF41];AND 3;CP 3
        emit_jr_back(0x20, 'to_s3')                   # JR NZ, to_s3
        mark('to_s0')
        emit([0xF0, 0x41, 0xE6, 0x03])               # LDH A,[FF41];AND 3
        emit_jr_back(0x20, 'to_s0')                   # JR NZ, to_s0
        for _ in range(4):
            emit([0x1A, 0x13, 0x22])  # LD A,[DE]; INC DE; LD [HL+],A
        emit([0xFB])                 # EI
        emit([0x0D])                 # DEC C
        emit_jr_back(0x20, 'to_group')
        # row end: HL += 8 (24 written + 8 skip = 32 stride)
        emit([0x7D, 0xC6, 0x08, 0x6F, 0x30, 0x01, 0x24])
        emit([0xF1])                 # POP AF
        emit([0x3D])                 # DEC A
        j_to_done = emit_jr_fwd(0x28)  # JR Z, done
        emit([0xF5])                 # PUSH AF
        offset = targets['to_row'] - (len(code) + 2)
        if -128 <= offset <= 127:
            emit([0x18, offset & 0xFF])
        else:
            target_addr = 0x42A7 + targets['to_row']
            emit([0xC3, target_addr & 0xFF, (target_addr >> 8) & 0xFF])
        patch_jr_fwd(j_to_done)
        emit([0xC9])                 # RET

    return bytes(code)


def create_inline_tile_copy_pure_tileonly() -> bytes:
    """PURE tile-only inline hook: copies tiles ONLY, no attr writes.

    Single STAT wait. ~vanilla speed. No VBK=1 writes, no bg_table lookup.
    Attrs are handled by bg_sweep + position sweep in the VBlank handler.

    Replaces 0x42A7..0x436D. H pre-set to 0x98 or 0x9C by entry point.
    24 rows x 6 groups x 4 tiles = 576 tiles.
    Same L/E/HL advancement as the tile phase of the full version.
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

    # Setup (H pre-set by entry point to 0x98 or 0x9C)
    emit([0x2E, 0x00])               # LD L, 0x00
    emit([0x11, 0xA0, 0xC1])         # LD DE, 0xC1A0 (WRAM tile source)

    # Row counter
    emit([0x3E, 0x18])               # LD A, 24
    emit([0xF5])                     # PUSH AF

    mark("row_loop")
    emit([0x0E, 0x06])               # LD C, 6 (groups per row)

    mark("group_loop")
    # STAT wait (MODE 3 then 0 - single phase)
    emit([0xF3])                     # DI
    mark("stat3")
    emit([0xF0, 0x41])               # LDH A,[FF41]
    emit([0xE6, 0x03])               # AND 3
    emit([0xFE, 0x03])               # CP 3
    emit_jr_back(0x20, "stat3")      # JR NZ, stat3
    mark("stat0")
    emit([0xF0, 0x41])               # LDH A,[FF41]
    emit([0xE6, 0x03])               # AND 3
    emit_jr_back(0x20, "stat0")      # JR NZ, stat0
    # 4 tile writes
    for _ in range(4):
        emit([0x1A, 0x13, 0x22])     # LD A,[DE]; INC DE; LD [HL+],A
    emit([0xFB])                     # EI

    # Group counter
    emit([0x0D])                     # DEC C
    emit_jr_back(0x20, "group_loop") # JR NZ, group_loop

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
    offset = targets["row_loop"] - (len(code) + 2)
    if -128 <= offset <= 127:
        emit([0x18, offset & 0xFF])
    else:
        target_addr = 0x42A7 + targets["row_loop"]
        emit([0xC3, target_addr & 0xFF, (target_addr >> 8) & 0xFF])

    patch_jr_fwd(j_done)
    emit([0xC9])                     # RET
    return bytes(code)


def create_gdma_transfer() -> bytes:
    """GDMA 256 bytes from WRAM bank 0:CC80 to displayed tilemap VBK=1.

    Must run during VBlank. DI protects the general-mode transfer.
    Checks LCDC bit 3 for tilemap base (0x9800 or 0x9C00).
    """
    code = bytearray()

    # VBK=1
    code.extend([0x3E, 0x01, 0xE0, 0x4F])

    # DI — protect general-mode GDMA from Timer ISR
    code.extend([0xF3])

    # HDMA source = CC80 (WRAM bank 0, always accessible)
    code.extend([0x3E, 0xCC, 0xE0, 0x51])   # HDMA1 = 0xCC
    code.extend([0x3E, 0x80, 0xE0, 0x52])   # HDMA2 = 0x80

    # HDMA dest = tilemap base (check LCDC bit 3)
    code.extend([0xF0, 0x40])               # LDH A,[LCDC]
    code.extend([0xE6, 0x08])               # AND 0x08
    code.extend([0x28, 0x04])               # JR Z, +4 (use 0x98)
    code.extend([0x3E, 0x9C])               # LD A, 0x9C
    code.extend([0x18, 0x02])               # JR +2
    code.extend([0x3E, 0x98])               # LD A, 0x98
    code.extend([0xE0, 0x53])               # HDMA3 = dest high
    code.extend([0xAF, 0xE0, 0x54])         # HDMA4 = 0x00

    # General-mode GDMA (HDMA5=0x3F): copies 1024 bytes atomically
    # while CPU is halted (~512T). Required because HBlank-mode HDMA
    # (HDMA5=0xBF) continues across multiple HBlanks; once we restore
    # VBK=0 after the call returns, subsequent HBlank steps write to
    # VRAM bank 0 (tile IDs) instead of bank 1 (attributes) — visible
    # as random tile garbage. General mode completes before VBK is
    # restored, keeping every write in VRAM bank 1.
    # HDMA5 = 0x0F → 256-byte general-mode transfer (matches the 8 rows
    # × 32 bytes attr_comp fills). Saves ~768T per frame vs full 1024-byte
    # transfer, and preserves bg_sweep's writes to VRAM rows 8-31.
    code.extend([0x3E, 0x0F, 0xE0, 0x55])   # HDMA5 = 0x0F → general mode 256 bytes

    # GDMA done. Restore interrupts and VBK=0.
    code.extend([0xFB])                     # EI
    code.extend([0xAF, 0xE0, 0x4F])         # VBK=0
    code.extend([0xC9])                     # RET

    return bytes(code)


def create_attr_computation(bg_table_addr: int) -> bytes:
    """Compute an attr buffer in WRAM bank 0 from the tile buffer.

    Reads tiles from WRAM 0xC1A0 (bank 0, always accessible).
    Looks up bg_table from ROM bank 13 (active during VBlank handler).
    Writes to WRAM bank 0:CC80 onward.

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
      DE = attr dest (CC80+, bank 0 — always accessible)
      FFE0 (HRAM scratch) = row counter (avoids DI-internal PUSH/POP nesting)
    """
    bg_table_hi = (bg_table_addr >> 8) & 0xFF
    code = bytearray()

    code.extend([0xC5, 0xD5, 0xE5, 0xF5])  # PUSH BC, DE, HL, AF
    code.extend([0x21, 0xA0, 0xC1])         # LD HL, 0xC1A0
    code.extend([0x11, ATTR_BUFFER & 0xFF, (ATTR_BUFFER >> 8) & 0xFF])  # LD DE, 0xCC80 (attr buffer)
    code.extend([0x3E, 0x08])               # LD A, 8 (gameplay-safe cliff; preserves mini-boss + room progression)
    code.extend([0xE0, 0xE0])               # LDH [FFE0], A (row counter in HRAM)

    row_loop = len(code)
    code.extend([0xF3])                     # DI
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
    # OAM scan cap (LD B,n at colorizer entry). Kept at 0x0A=10 (the shipped,
    # hardware-verified VBlank-safe value). Raising it to 0x28=40 (full OAM
    # coverage) was TESTED for the black-enemy issue (items 3,4,6,11) but did NOT
    # fix in-game enemies: they still render p0 (blue/black) because the real bug
    # is a DMA-ordering race (the colorizer assigns p6/p7 in the shadow buffer but
    # the game's main-loop OAM rebuild overwrites HW OAM with p0 before display).
    # The full OBJ fix (cap 40 + DMA-ordering rework) is timing-critical and needs
    # MiSTer hardware verification — see docs/audit/obj_enemy_color_race.md.
    colorizer[1] = 0x0A
    w(colorizer_addr, bytes(colorizer))

    w(tile_pal_addr, create_tile_to_palette_subroutine())
    w(bg_table_addr, BG_TABLE_BYTES)
    w(cond_pal_addr, create_conditional_palette_cached(pal_loader_addr))

    # bg_sweep safety net. Strip the internal FFC1 gate (first 4 bytes
    # Strip FFC1 prefix (`F0 C1 B7 C8` = LDH A,[FFC1]; OR A; RET Z).
    # Without this, bg_sweep skips title/menu (FFC1=0). Hardware
    # testing on MiSTer showed white splotches on title screen and
    # inventory menu — the inline tile+attr copy doesn't catch all
    # tile-write paths (e.g., title animation, menu rendering go
    # through other routines that don't update attrs).
    # The previous time I stripped this the issue was COMPOUND with
    # attr_comp + GDMA being called too; with those disabled, bg_sweep
    # ×1 outside the FFC1 gate is the same cycle cost as v3.00's
    # bg_sweep ×1 inside the gate during gameplay, and adds title
    # coverage as a free bonus.
    sweep = bytearray(create_bg_sweep_viewport_gated(bg_table_addr, bg_sweep_addr))
    assert sweep[:4] == bytearray([0xF0, 0xC1, 0xB7, 0xC8]), \
        f"bg_sweep prefix changed: {sweep[:4].hex()}"
    sweep[0:4] = bytearray([0x00, 0x00, 0x00, 0x00])  # NOPs — run on title too
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
    # FF99 protocol REMOVED — v3.00 doesn't have it and works correctly.
    # Adding it on v3.01 cost ~100T per VBlank and pushed palette_loader
    # writes into LCD mode 3 where CRAM writes are dropped silently,
    # producing the "splotches" the user reported on title screen.
    # The original concern (ISRs restoring wrong ROM bank from FF99) is
    # not a problem in practice: STAT and Timer ISRs in this ROM don't
    # mid-handler restore FF99 in a way that breaks our bank context.
    # code.extend([0xF0, 0x99, 0xF5])           # LDH A,[FF99]; PUSH AF
    # code.extend([0x3E, 0x0D, 0xE0, 0x99])     # FF99 = 0x0D
    code.extend([0xF0, 0x4F, 0xF5])           # save VBK
    code.extend([0xAF, 0xE0, 0x4F])           # VBK = 0

    # DF02 magic byte cold-boot check
    code.extend([0xFA, 0x02, 0xDF, 0xFE, 0x5A])
    df02_jr = len(code) + 1
    code.extend([0x28, 0x00])                 # JR Z, skip_cold

    # ---- COLD-BOOT PATH ----
    code.extend([0x3E, 0x5A, 0xEA, 0x02, 0xDF])  # DF02 = 0x5A
    code.extend([0xAF, 0xEA, 0x00, 0xDF])         # DF00 = 0 (hash)
    code.extend([0xEA, 0x0A, 0xDF])               # DF0A = 0 (teleport req — A still 0)
    # DF03 init REMOVED. Was unused (only meaningful for attr_comp+GDMA
    # path which isn't called). Saving 4 bytes / ~25T from cold-boot.
    # Brings v3.01 cold-boot bytes to match v3.00 baseline exactly.
    # code.extend([0xAF, 0xEA, 0x03, 0xDF])

    # Copy bg_table ROM → WRAM 0xCC00 (for inline hook compatibility — not
    # strictly needed for v3.01 since inline hook no longer reads it, but
    # keeping it doesn't hurt and allows fallback)
    code.extend([0x21, bg_table_addr & 0xFF, (bg_table_addr >> 8) & 0xFF])
    code.extend([0x11, WRAM_BG_TABLE & 0xFF, (WRAM_BG_TABLE >> 8) & 0xFF])
    code.extend([0x06, 0x00])                 # B = 0 (256 iters)
    bg_copy = len(code)
    code.extend([0x2A, 0x12, 0x13, 0x05])    # [HL+]→[DE]; INC DE; DEC B
    offset = bg_copy - (len(code) + 2)
    code.extend([0x20, offset & 0xFF])

    # Cold-boot bank-2 zero REMOVED. It took ~5K T on the first VBlank,
    # which spilled the subsequent palette_loader call out of LCD mode 1
    # into modes 2/3. CGB CRAM writes during mode 3 are dropped silently,
    # leaving some OBJ palette bytes at boot defaults (0xFF 0x7F = white).
    # Symptom: Sara's body rendered with white instead of pink because
    # OBJ palette 2 color 1 stayed at 0x7FFF after palette_loader's
    # writes were partially dropped.
    # Since attr_comp + GDMA aren't called in the warm path, WRAM bank 2
    # is never read — zeroing it served no purpose. Removed entirely.

    # ---- skip_cold target ----
    code[df02_jr] = (len(code) - df02_jr - 1) & 0xFF

    # DX TELEPORT hook REMOVED (was: JP bank2:0x4000 from VBlank IRQ).
    # Investigation showed bank2:0x4000 calls bank0:0x0099, which is a
    # STAT-mode busy-wait for LCD mode 3. From VBlank IRQ context the
    # LCD is in mode 1 and stays there until our IRQ returns — so the
    # busy-wait loops forever, and EI'd nested IRQs recurse into the
    # same loop. Result: freeze.
    #
    # True teleport would require either:
    #   a) Hooking the GAME's main loop (no free bank-0 space)
    #   b) Per-boss save states (manual one-time capture)
    #   c) Reverse-engineering the natural boss-spawn trigger flag
    # Pending a follow-up. For now teleport is unsupported; the
    # editor's "State-byte Hold (legacy)" section is still usable for
    # forcing FFBA/D880/FFB7 if user wants to experiment.

    # ---- WARM PATH ----
    # Structure matches v3.00 exactly: cond_pal → FFC1 gate {bg_sweep, OAM,
    # shadow_main}. Running bg_sweep on title added ~3K T per title frame
    # which slowed the title's tile-draw animation visibly: the YANOMAN
    # logo took longer to draw, producing "splotch" artifacts when the
    # user pressed START before the draw completed.
    # Since the inline tile+attr copy at 0x42A7 already handles title
    # tiles when the game's tilemap copy runs, bg_sweep on title was
    # redundant for correctness and harmful for timing.
    code.extend([0xCD, cond_pal_addr & 0xFF, (cond_pal_addr >> 8) & 0xFF])

    # ============================================================
    # ATTR CLEANER (from build_v301_attrinit.py; verified in mGBA to
    # eliminate ALL uninit 0xFF attrs that produce title/menu splotches).
    #
    # Clears one row (32 bytes) of attrs in BOTH 0x9800 and 0x9C00
    # tilemap regions per frame, for 32 frames after cold-boot. Then
    # becomes a ~12T no-op. Runs AFTER cond_pal so palette_loader's
    # CRAM writes have finished (avoids LCD mode 3 drops).
    #
    # State bytes:
    #   DF07 = row counter (32→0)
    #   DF08 = init sentinel (0x5A means counter initialized)
    # ============================================================
    # First-run handshake: DF08 sentinel
    code.extend([0xFA, 0x08, 0xDF])           # LD A, [DF08]
    code.extend([0xFE, 0x5A])                 # CP 0x5A
    df08_jr = len(code) + 1
    code.extend([0x20, 0x00])                 # JR NZ, do_init
    # Already-initialized: load DF07
    code.extend([0xFA, 0x07, 0xDF])           # LD A, [DF07]
    code.extend([0xB7])                       # OR A
    cleaner_skip_jr = len(code) + 1
    code.extend([0x28, 0x00])                 # JR Z, skip_cleaner
    code.extend([0x3D])                       # DEC A
    code.extend([0xEA, 0x07, 0xDF])           # DF07 = A (current row 0..31)
    # HL = 0x9800 + (A << 5)
    code.extend([0x6F])                       # LD L, A
    code.extend([0x26, 0x00])                 # LD H, 0
    code.extend([0x29, 0x29, 0x29, 0x29, 0x29])  # ADD HL,HL × 5 (×32)
    code.extend([0x7C])                       # LD A, H
    code.extend([0xF6, 0x98])                 # OR 0x98
    code.extend([0x67])                       # LD H, A
    code.extend([0xE5])                       # PUSH HL (save for 2nd pass)
    # VBK = 1
    code.extend([0x3E, 0x01, 0xE0, 0x4F])
    # Clear 32 bytes at 0x9800 + row*32
    code.extend([0xAF])                       # A = 0
    code.extend([0x06, 0x20])                 # B = 32
    code.extend([0x22, 0x05, 0x20, 0xFC])     # loop: [HL+]=A; DEC B; JR NZ
    # Switch to 0x9C00 region (H |= 0x04)
    code.extend([0xE1])                       # POP HL
    code.extend([0x7C, 0xF6, 0x04, 0x67])     # H |= 0x04
    code.extend([0xAF])
    code.extend([0x06, 0x20])
    code.extend([0x22, 0x05, 0x20, 0xFC])     # clear 32 bytes at 0x9C00 + row*32
    # VBK = 0
    code.extend([0xAF, 0xE0, 0x4F])
    skip_init_jr = len(code) + 1
    code.extend([0x18, 0x00])                 # JR end_cleaner

    # do_init target: set DF08=0x5A, DF07=32, skip cleaner this frame
    code[df08_jr] = (len(code) - df08_jr - 1) & 0xFF
    code.extend([0x3E, 0x5A, 0xEA, 0x08, 0xDF])  # DF08 = 0x5A
    code.extend([0x3E, 0x20, 0xEA, 0x07, 0xDF])  # DF07 = 32
    # end_cleaner / skip_cleaner targets
    code[skip_init_jr] = (len(code) - skip_init_jr - 1) & 0xFF
    code[cleaner_skip_jr] = (len(code) - cleaner_skip_jr - 1) & 0xFF

    # Gate: run bg_sweep on title banner/showcase (D880=0x1B/0x1C) even if FFC1=0
    code.extend([0xFA, 0x80, 0xD8])           # LD A, [D880]
    code.extend([0xFE, 0x1B])                 # CP 0x1B (banner showcase)
    code.extend([0x28, 0x04])                 # JR Z, do_sweep (D880=0x1B → run)
    code.extend([0xFE, 0x1C])                 # CP 0x1C
    do_sweep = len(code) + 1
    code.extend([0x20, 0x00])                 # JR NZ, check_ffc1 (offset fixed below)
    # do_sweep target: emit CALL bg_sweep, then JR past ffc1 check + sweep
    code.extend([0xCD, bg_sweep_addr & 0xFF, (bg_sweep_addr >> 8) & 0xFF])
    code.extend([0x18, 0x0B])                 # JR past ffc1 check + sweep (to VBK restore)
    # Now fixup the JR NZ offset — must be done AFTER do_sweep code is emitted
    code[do_sweep] = (len(code) - do_sweep - 1) & 0xFF
    # check_ffc1
    check_ffc1 = len(code)
    code.extend([0xF0, 0xC1, 0xB7])           # LDH A,[FFC1]; OR A
    ffc1_skip = len(code) + 1
    code.extend([0x28, 0x00])                 # JR Z, skip
    code[ffc1_skip] = 0x28                    # fixup JR Z
    code.extend([0xCD, shadow_main_addr & 0xFF, (shadow_main_addr >> 8) & 0xFF])
    code.extend([0xCD, 0x80, 0xFF])           # OAM DMA
    code[ffc1_skip] = (len(code) - ffc1_skip - 1) & 0xFF

    # Restore VBK, restore FF99, return
    code.extend([0xF1, 0xE0, 0x4F])           # POP AF; LDH [VBK], A
    # code.extend([0xF1, 0xE0, 0x99])           # POP AF; LDH [FF99], A (FF99 protocol removed)
    code.extend([0xC9])

    assert colorize_addr + len(code) <= bg_table_addr, \
        f"colorize handler overflow: {colorize_addr + len(code):#X} > {bg_table_addr:#X}"
    w(colorize_addr, bytes(code))
    print(f"  colorize handler: {len(code)} bytes at 0x{colorize_addr:04X}")

    # ============================================================
    # VBLANK HOOK at 0x0824 and Wrapper at 0x6F10
    # ============================================================
    wrapper_addr = 0x6F10

    # Write wrapper to bank 13 ROM (offset in file is 13 * 0x4000 + (wrapper_addr - 0x4000))
    wrapper_off = 13 * 0x4000 + (wrapper_addr - 0x4000)
    wrapper = bytearray([
        # --- PRESERVE REGISTERS (AF too, for sound engine compat) ---
        0xF5,                                 # PUSH AF
        0xC5,                                 # PUSH BC
        0xD5,                                 # PUSH DE
        0xE5,                                 # PUSH HL

        # --- Robust 8-debounce joypad read ---
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

        # --- CALL actual colorize_handler ---
        0xCD, colorize_addr & 0xFF, (colorize_addr >> 8) & 0xFF,

        # --- SOUND ENGINE VBlank update (replaces CALL 0xFF80 at 0x06D5 which was NOP'd) ---
        0xCD, 0x80, 0xFF,                     # CALL 0xFF80

        # --- RESTORE REGISTERS ---
        0xE1,                                 # POP HL
        0xD1,                                 # POP DE
        0xC1,                                 # POP BC
        0xF1,                                 # POP AF

        0xC9,                                 # RET
    ])
    rom[wrapper_off:wrapper_off + len(wrapper)] = wrapper
    print(f"  VBlank wrapper written: {len(wrapper)} bytes at bank13:0x{wrapper_addr:04X}")

    hook = bytearray([
        0xF0, 0x99,                           # LDH A, [FF99]
        0xF5,                                 # PUSH AF (save original bank)
        0x3E, 0x0D,                           # LD A, 13 (ROM bank of wrapper)
        0xE0, 0x99,                           # LDH [FF99], A (update shadow to 13)
        0xEA, 0x00, 0x21,                     # LD [0x2100], A (switch MBC bank to 13)
        0xCD, wrapper_addr & 0xFF, (wrapper_addr >> 8) & 0xFF,  # CALL wrapper
        0xF1,                                 # POP AF (restore original bank value)
        0xE0, 0x99,                           # LDH [FF99], A (restore original shadow)
        0xEA, 0x00, 0x21,                     # LD [0x2100], A (restore original MBC ROM bank)
        0xC9,                                 # RET
    ])
    assert len(hook) <= 47
    rom[0x0824:0x0824 + 47] = (hook + bytearray(47 - len(hook)))[:47]

    # NOP original CALL 0xFF80 (sound engine VBlank update — replaced by wrapper CALL)
    rom[0x06D5:0x06D8] = bytearray([0x00, 0x00, 0x00])

    # RST $38 RETI → RET
    rom[0x003B] = 0xC9

    # ============================================================
    # INLINE PURE TILE-ONLY HOOK at bank1:0x42A7
    # ============================================================
    inline_code = create_inline_tile_copy_pure_tileonly()
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
