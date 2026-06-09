#!/usr/bin/env python3
"""Position-based arena colorization (the "holy grail" path).

Tile-ID keying cannot reach zero alternation: a boss cell's tile flips between
boss-part and background as the boss animates, so a tile->palette table flips
the cell's color with it (and a shared tile bleeds the boss color onto the
background). The fix is **position keying**: a fixed per-cell palette map. Every
write of cell (r,c) writes the SAME value, so the attribute never flips — by
construction, regardless of the boss animation. The "bob" is an SCX/SCY scroll
shake (the boss footprint is stable in tilemap space), so a tilemap-space cell
map is bob-proof.

This module provides:
  * parse_footprint_posmaps() — turn the probed footprint maps
    (scripts/diagnostics/footprint_maps.log) into 18x32 per-cell palette maps.
  * create_position_sweep() — a VBlank routine that writes the active arena's
    posmap to the BG attribute plane, a few rows per frame (cycling), reading
    the map from bank-13 ROM. Runs ONLY in arenas (D880 0x0C..0x14); in every
    other scene it tail-calls the normal tile-ID sweep.

Why a VBlank sweep (not STAT-wait, not GDMA):
  * It runs inside the colorize handler (VBlank IRQ), where the whole VRAM is
    writable (LCD mode 1) — no HBlank racing needed, so no STAT-wait (a
    STAT-wait would hang: there is no mode 0/3 during VBlank).
  * Plain CPU stores, no HDMA — so it coexists with the arena's HBlank-HDMA
    scroll-shake (GDMA terminated that and collapsed the arena; see
    docs/FINDINGS_2026_06_07_arena_gdma_isolation.md).

For zero alternation the inline hook's ATTR writes must be neutralized in
arenas (tile-only), so this sweep is the sole attr writer there; otherwise the
hook's tile-ID attrs fight the posmap between sweep passes. (Done in
build_v301_gdma.create_inline_tile_copy_tileonly via arena_neutralize_d880.)

Map layout: 18 rows x 32 cols (matches the tilemap stride). Cols 0..19 come
from the probe; cols 20..31 are 0 (off-screen). Palette 0 = background/floor.
"""
from pathlib import Path


# ----------------------------------------------------------------------
# Footprint -> per-cell posmap
# ----------------------------------------------------------------------
POSMAP_ROWS = 18
POSMAP_COLS = 32          # tilemap stride
POSMAP_SIZE = POSMAP_ROWS * POSMAP_COLS   # 576 bytes


def parse_footprint_posmaps(log_path):
    """Parse footprint_maps.log -> {boss_name: bytes(576)}.

    Lines look like:  ROW shalamar 0 00000004444444444444
    (20 base-10 palette digits, one per visible column). Missing rows -> all 0.
    """
    rows = {}   # name -> {row_index: "digit string"}
    for line in Path(log_path).read_text().splitlines():
        parts = line.split()
        if len(parts) == 4 and parts[0] == "ROW":
            name, r, digits = parts[1], int(parts[2]), parts[3]
            rows.setdefault(name, {})[r] = digits
    maps = {}
    for name, rd in rows.items():
        m = bytearray(POSMAP_SIZE)
        for r in range(POSMAP_ROWS):
            d = rd.get(r, "")
            for c in range(min(20, len(d))):
                ch = d[c]
                m[r * POSMAP_COLS + c] = (int(ch) & 7) if ch.isdigit() else 0
        maps[name] = bytes(m)
    return maps


# ----------------------------------------------------------------------
# Tiny relative-jump assembler (mirrors build_v301_gdma's style)
# ----------------------------------------------------------------------
class _Asm:
    def __init__(self):
        self.code = bytearray()
        self.labels = {}
        self.fwd = []   # (pos, label)

    def db(self, *bs):
        for b in bs:
            if isinstance(b, (list, bytes, bytearray)):
                self.code.extend(b)
            else:
                self.code.append(b & 0xFF)
        return self

    def label(self, name):
        self.labels[name] = len(self.code)
        return self

    def jr(self, opcode, name):
        """Emit a JR; resolve now if label known (backward), else defer."""
        if name in self.labels:
            off = self.labels[name] - (len(self.code) + 2)
            assert -128 <= off <= 127, f"JR {name} out of range: {off}"
            self.db(opcode, off & 0xFF)
        else:
            self.db(opcode, 0x00)
            self.fwd.append((len(self.code) - 1, name))
        return self

    def finish(self):
        for pos, name in self.fwd:
            off = self.labels[name] - (pos + 1)
            assert -128 <= off <= 127, f"fwd JR {name} out of range: {off}"
            self.code[pos] = off & 0xFF
        return bytes(self.code)


def create_position_sweep(possweep_addr, orig_sweep_addr, ptr_table_addr,
                          row_cursor_addr, rows_per_frame=2,
                          scratch_addr=0xDF41):
    """VBlank position sweep. Placed at possweep_addr; the colorize handler's
    `CALL bg_sweep` is repointed here.

    Dispatch: idx = D880 - 0x0C. Outside 0..8 -> JP orig_sweep (tile-ID).
    Else load posmap base = [ptr_table + idx*2]; if 0 -> JP orig_sweep.
    Then copy `rows_per_frame` rows (32 bytes each) posmap->VRAM attr plane,
    cycling row_cursor 0..17 across frames.

    Scratch WRAM (must be free, DF40+): row_cursor_addr (persistent cursor),
    scratch_addr..scratch_addr+3 (posmap_lo, posmap_hi, vram_hi, rows_left).
    """
    a = _Asm()
    ol, oh = orig_sweep_addr & 0xFF, (orig_sweep_addr >> 8) & 0xFF
    ptl, pth = ptr_table_addr & 0xFF, (ptr_table_addr >> 8) & 0xFF
    rc_l, rc_h = row_cursor_addr & 0xFF, (row_cursor_addr >> 8) & 0xFF
    pm_lo = scratch_addr & 0xFF;       pm_lo_h = (scratch_addr >> 8) & 0xFF
    pm_hi = (scratch_addr + 1) & 0xFF
    vhi = (scratch_addr + 2) & 0xFF
    rleft = (scratch_addr + 3) & 0xFF

    # --- dispatch ---
    a.db(0xFA, 0x80, 0xD8)            # LD A,[D880]
    a.db(0xD6, 0x0C)                  # SUB 0x0C
    a.jr(0x38, 'normal')             # JR C, normal
    a.db(0xFE, 0x09)                 # CP 9
    a.jr(0x30, 'normal')             # JR NC, normal
    a.jr(0x18, 'arena')              # JR arena
    a.label('normal')
    a.db(0xC3, ol, oh)               # JP orig_sweep

    # --- arena: A = idx ---
    a.label('arena')
    a.db(0x87)                       # ADD A,A      (idx*2)
    a.db(0x06, 0x00)                 # LD B,0
    a.db(0x4F)                       # LD C,A       (BC = idx*2)
    a.db(0x21, ptl, pth)             # LD HL, ptr_table
    a.db(0x09)                       # ADD HL,BC
    a.db(0x2A)                       # LD A,[HL+]   (posmap_lo)
    a.db(0x5F)                       # LD E,A
    a.db(0x7E)                       # LD A,[HL]    (posmap_hi)
    a.db(0x57)                       # LD D,A       (DE = posmap base)
    a.db(0x7B, 0xB2)                 # LD A,E; OR D
    a.jr(0x20, 'have_map')          # JR NZ, have_map
    a.db(0xC3, ol, oh)               # JP orig_sweep  (no map -> tile-ID)

    a.label('have_map')
    # store posmap base
    a.db(0x7B, 0xEA, pm_lo, pm_lo_h) # LD A,E; LD [pm_lo],A
    a.db(0x7A, 0xEA, pm_hi, pm_lo_h) # LD A,D; LD [pm_hi],A
    # vram base hi (0x98/0x9C) from LCDC bit 3
    a.db(0xF0, 0x40, 0xE6, 0x08)     # LDH A,[FF40]; AND 0x08
    a.jr(0x28, 'use98')             # JR Z, use98
    a.db(0x3E, 0x9C)                 # LD A,0x9C
    a.jr(0x18, 'haveH')             # JR haveH
    a.label('use98')
    a.db(0x3E, 0x98)                 # LD A,0x98
    a.label('haveH')
    a.db(0xEA, vhi, pm_lo_h)         # LD [vhi],A
    # rows_left = rows_per_frame
    a.db(0x3E, rows_per_frame & 0xFF)
    a.db(0xEA, rleft, pm_lo_h)       # LD [rows_left],A

    # --- per-row loop ---
    a.label('rowloop')
    a.db(0xFA, rc_l, rc_h)           # LD A,[row_cursor]
    a.db(0x6F, 0x26, 0x00)           # LD L,A; LD H,0
    a.db(0x29, 0x29, 0x29, 0x29, 0x29)  # ADD HL,HL x5  (row*32)
    a.db(0x44, 0x4D)                 # LD B,H; LD C,L   (BC = offset)
    # pos_src = posmap_base + offset -> DE
    a.db(0xFA, pm_lo, pm_lo_h, 0x6F) # LD A,[pm_lo]; LD L,A
    a.db(0xFA, pm_hi, pm_lo_h, 0x67) # LD A,[pm_hi]; LD H,A
    a.db(0x09)                       # ADD HL,BC
    a.db(0x5D, 0x54)                 # LD E,L; LD D,H   (DE = pos_src)
    # vram_dest = (vhi:00) + offset -> HL
    a.db(0x60, 0x69)                 # LD H,B; LD L,C   (HL = offset)
    a.db(0xFA, vhi, pm_lo_h)         # LD A,[vhi]
    a.db(0x84, 0x67)                 # ADD H; LD H,A    (H = vhi + offset_hi)
    # copy 32 bytes pos_src -> vram_dest, VBK=1
    a.db(0x3E, 0x01, 0xE0, 0x4F)     # LD A,1; LDH [FF4F],A
    a.db(0x06, 0x20)                 # LD B,32
    a.label('copy')
    a.db(0x1A, 0x22, 0x13, 0x05)     # LD A,[DE]; LD [HL+],A; INC DE; DEC B
    a.jr(0x20, 'copy')              # JR NZ, copy
    a.db(0xAF, 0xE0, 0x4F)           # XOR A; LDH [FF4F],A  (VBK=0)
    # advance row_cursor (0..17 wrap)
    a.db(0xFA, rc_l, rc_h, 0x3C)     # LD A,[row_cursor]; INC A
    a.db(0xFE, 0x12)                 # CP 18
    a.jr(0x20, 'nowrap')            # JR NZ, nowrap
    a.db(0xAF)                       # XOR A
    a.label('nowrap')
    a.db(0xEA, rc_l, rc_h)           # LD [row_cursor],A
    # rows_left--
    a.db(0xFA, rleft, pm_lo_h, 0x3D) # LD A,[rows_left]; DEC A
    a.db(0xEA, rleft, pm_lo_h)       # LD [rows_left],A
    a.jr(0x20, 'rowloop')           # JR NZ, rowloop
    a.db(0xC9)                       # RET
    return a.finish()
