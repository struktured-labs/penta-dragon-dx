#!/usr/bin/env python3
"""Optimized (fused) per-frame BG sweep + an offline equivalence verifier.

WHY
---
`build_v296_phantomsafe.create_bg_sweep_viewport_gated` is the per-frame BG
colorizer that runs in the VBlank handler of every gameplay frame (v3.00+
keeps it as a safety net alongside the inline hook). It processes ONE visible
tilemap row (32 tiles) per frame in THREE separate 32-iteration passes:

  Phase 1 (VBK=0): copy 32 tile IDs   tilemap  -> WRAM buffer DF10
  Phase 2 (VBK=0): look up palette     buffer   -> buffer   (bg_table[tile])
  Phase 3 (VBK=1): write 32 attrs      buffer   -> tilemap

Phase 2 is a redundant pass: the palette lookup can be folded into the
attr-write pass. `bg_table` lives in ROM (Phase-2 read) and the buffer lives
in WRAM — neither is affected by the VBK bank, so the lookup is happy to run
while VBK=1. Fusing 2+3 removes a whole 32-iteration pass (~33% of the loop
work) for free, handing CPU cycles back to the game's main loop -> higher
effective frame rate, especially while scrolling.

The fused loop reuses the exact `[BC]` table-lookup idiom from the v3.00
inline hook (B = bg_table page, C = tile id). It requires bg_table to be
page-aligned (low byte 0x00), which every production build already is
(0x7000 ROM, 0xDA00 WRAM).

SAFETY
------
The fused sweep uses NO DI window, NO FF99 write, and the SAME two VBK
toggles as the original (one per pass). It is strictly *less* work in the
same VBlank context, so it cannot introduce the phantom-sound / DI-backlog
regressions documented in CLAUDE.md. It is behaviour-equivalent at the
attribute-write level, which this file proves with a focused LR35902
interpreter (run `python scripts/optimize_bg_sweep.py`).

This is a CANDIDATE. Per CLAUDE.md it still MUST pass the five probes on a
real build before promotion to FIXED.gb.
"""
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from build_v296_phantomsafe import create_bg_sweep_viewport_gated


def create_bg_sweep_viewport_gated_fast(bg_table_addr: int, base_addr: int) -> bytes:
    """Fused (2-pass) drop-in replacement for create_bg_sweep_viewport_gated.

    Identical setup + Phase 1 (tilemap->buffer read). Phases 2 and 3 are
    fused into a single VBK=1 pass that looks up bg_table[tile] via [BC] and
    writes the attribute in one go, eliminating the standalone lookup pass.

    Requires bg_table_addr to be page-aligned (low byte 0x00) so that
    bg_table[tile] == [bg_table_hi : tile] with no 16-bit carry.
    """
    assert (bg_table_addr & 0xFF) == 0, \
        f"fused sweep needs page-aligned bg_table, got {bg_table_addr:#06x}"
    bg_table_hi = (bg_table_addr >> 8) & 0xFF
    s = bytearray()

    # ===== SETUP + PHASE 1 — byte-for-byte identical to the original =====
    s.extend([0xF0, 0xC1, 0xB7, 0xC8])                       # FFC1 gate (RET Z on menu)
    s.extend([0xC5, 0xD5, 0xE5])                             # PUSH BC, DE, HL
    s.extend([0xF0, 0x40, 0xE6, 0x08, 0x0F, 0xC6, 0x98, 0xEA, 0x01, 0xDF])  # base_hi -> DF01
    s.extend([0xF0, 0x42, 0xCB, 0x3F, 0xCB, 0x3F, 0xCB, 0x3F, 0x47])        # B = SCY/8
    s.extend([0xFA, 0x04, 0xDF, 0x3C, 0xFE, 0x12, 0x20, 0x02, 0x3E, 0x00])  # DF04 inc, clamp 0..17
    s.extend([0xEA, 0x04, 0xDF])                            # store DF04
    s.extend([0x80, 0xE6, 0x1F])                            # tilemap_row = (DF04 + SCY/8) & 0x1F
    s.extend([0x47])                                        # B = row
    s.extend([0xCB, 0x3F, 0xCB, 0x3F, 0xCB, 0x3F, 0x57])    # D = row >> 3
    s.extend([0xFA, 0x01, 0xDF, 0x82, 0x57])               # D = base_hi + (row >> 3)
    s.extend([0x78, 0xE6, 0x07, 0xCB, 0x37, 0x87, 0x5F])   # E = (row & 7) << 5
    s.extend([0xD5])                                        # PUSH DE (row start, for write phase)
    s.extend([0x7A, 0x67, 0x7B, 0x6F])                     # HL = row start
    s.extend([0x11, 0x10, 0xDF])                           # DE = DF10 (buffer)
    s.extend([0xAF, 0xE0, 0x4F])                           # VBK = 0
    s.extend([0x06, 0x20])                                 # B = 32
    s.extend([0x2A, 0x12, 0x13])                           # buffer[DE+] = tilemap[HL+]
    s.extend([0x05, 0x20, 0xFA])                           # DEC B; JR NZ -6

    # ===== FUSED PHASE 2+3 (VBK=1): lookup bg_table[tile] AND write attr =====
    s.extend([0x3E, 0x01, 0xE0, 0x4F])                     # VBK = 1
    s.extend([0xE1])                                       # POP HL = row start (attr write ptr)
    s.extend([0x06, bg_table_hi])                          # B = bg_table page (for [BC] lookup)
    s.extend([0x11, 0x10, 0xDF])                           # DE = DF10 (tile buffer)
    loop = len(s)
    s.extend([0x1A])                                       # A = buffer[DE]  (tile)
    s.extend([0x13])                                       # INC DE
    s.extend([0x4F])                                       # C = A  -> BC = bg_table_hi:tile
    s.extend([0x0A])                                       # A = bg_table[BC]  (palette; ROM read)
    s.extend([0x22])                                       # tilemap_attr[HL+] = A  (VBK=1 write)
    s.extend([0x7B, 0xFE, 0x30])                           # A = E; CP 0x30  (buffer end = DF30)
    off = (loop - (len(s) + 2)) & 0xFF
    s.extend([0x20, off])                                  # JR NZ loop

    s.extend([0xAF, 0xE0, 0x4F])                           # VBK = 0
    s.extend([0xE1, 0xD1, 0xC1])                           # POP HL, DE, BC
    s.append(0xC9)                                          # RET
    return bytes(s)


# ===========================================================================
# Focused LR35902 interpreter — just enough to execute both sweep variants.
# Models: HRAM/WRAM/ROM flat memory + a separate VRAM bank-1 plane (attrs),
# selected by VBK (FF4F). Records every attribute write so we can compare.
# ===========================================================================

class Mem:
    def __init__(self, bg_table: bytes, bg_table_addr: int, tilemap: dict, base: int):
        self.flat = bytearray(0x10000)     # ROM + WRAM + HRAM + VRAM bank 0
        self.vram1 = bytearray(0x2000)     # VRAM bank 1 (0x8000-0x9FFF), attrs
        self.vbk = 0
        self.attr_writes = []              # (addr, value) recorded in order
        self.flat[bg_table_addr:bg_table_addr + len(bg_table)] = bg_table
        for off, tile in tilemap.items():  # tile IDs into VRAM bank 0
            self.flat[base + off] = tile

    def read(self, addr):
        if addr == 0xFF4F:
            return 0xFE | self.vbk
        if 0x8000 <= addr <= 0x9FFF and self.vbk == 1:
            return self.vram1[addr - 0x8000]
        return self.flat[addr]

    def write(self, addr, val):
        val &= 0xFF
        if addr == 0xFF4F:
            self.vbk = val & 1
            return
        if 0x8000 <= addr <= 0x9FFF and self.vbk == 1:
            self.vram1[addr - 0x8000] = val
            self.attr_writes.append((addr, val))
            return
        self.flat[addr] = val


def run(code: bytes, base_addr: int, mem: Mem, regs: dict):
    """Execute `code` (loaded at base_addr) until top-level RET. Returns cycles."""
    r = regs
    Z = [False]; C = [False]
    stack = []
    pc = base_addr
    end = base_addr + len(code)
    cycles = 0
    GUARD = 200000

    def b():        # next immediate byte
        nonlocal pc
        v = code[pc - base_addr]; pc += 1; return v

    def w16():
        lo = b(); hi = b(); return lo | (hi << 8)

    def pair(hi, lo): return (r[hi] << 8) | r[lo]
    def setpair(hi, lo, v): r[hi] = (v >> 8) & 0xFF; r[lo] = v & 0xFF

    def addA(v):
        res = r['A'] + v
        C[0] = res > 0xFF; r['A'] = res & 0xFF; Z[0] = r['A'] == 0

    steps = 0
    while True:
        steps += 1
        if steps > GUARD:
            raise RuntimeError("runaway program (no RET)")
        op = code[pc - base_addr]; pc += 1
        if op == 0x00:   # NOP (appears when the FFC1 gate is stripped)
            cycles += 4
        elif op == 0xF0:   # LDH A,[FF00+n]
            r['A'] = mem.read(0xFF00 | b()); cycles += 12
        elif op == 0xE0: # LDH [FF00+n],A
            mem.write(0xFF00 | b(), r['A']); cycles += 12
        elif op == 0xFA: # LD A,[nn]
            r['A'] = mem.read(w16()); cycles += 16
        elif op == 0xEA: # LD [nn],A
            mem.write(w16(), r['A']); cycles += 16
        elif op == 0xB7: # OR A
            r['A'] &= 0xFF; Z[0] = r['A'] == 0; C[0] = False; cycles += 4
        elif op == 0xC8: # RET Z
            cycles += 8
            if Z[0]:
                if not stack: return cycles
                pc = stack.pop(); cycles += 12
        elif op == 0xC9: # RET
            cycles += 16
            if not stack: return cycles
            pc = stack.pop()
        elif op == 0xC5: stack.append(pair('B', 'C')); cycles += 16
        elif op == 0xD5: stack.append(pair('D', 'E')); cycles += 16
        elif op == 0xE5: stack.append(pair('H', 'L')); cycles += 16
        elif op == 0xC1: setpair('B', 'C', stack.pop()); cycles += 12
        elif op == 0xD1: setpair('D', 'E', stack.pop()); cycles += 12
        elif op == 0xE1: setpair('H', 'L', stack.pop()); cycles += 12
        elif op == 0xE6: # AND n
            r['A'] &= b(); Z[0] = r['A'] == 0; C[0] = False; cycles += 8
        elif op == 0x0F: # RRCA
            bit0 = r['A'] & 1; r['A'] = ((r['A'] >> 1) | (bit0 << 7)) & 0xFF
            C[0] = bool(bit0); Z[0] = False; cycles += 4
        elif op == 0xC6: addA(b()); cycles += 8        # ADD A,n
        elif op == 0x80: addA(r['B']); cycles += 4     # ADD A,B
        elif op == 0x82: addA(r['D']); cycles += 4     # ADD A,D
        elif op == 0x85: addA(r['L']); cycles += 4     # ADD A,L
        elif op == 0x87: addA(r['A']); cycles += 4     # ADD A,A
        elif op == 0x47: r['B'] = r['A']; cycles += 4  # LD B,A
        elif op == 0x4F: r['C'] = r['A']; cycles += 4  # LD C,A
        elif op == 0x57: r['D'] = r['A']; cycles += 4  # LD D,A
        elif op == 0x5F: r['E'] = r['A']; cycles += 4  # LD E,A
        elif op == 0x67: r['H'] = r['A']; cycles += 4  # LD H,A
        elif op == 0x6F: r['L'] = r['A']; cycles += 4  # LD L,A
        elif op == 0x78: r['A'] = r['B']; cycles += 4  # LD A,B
        elif op == 0x7A: r['A'] = r['D']; cycles += 4  # LD A,D
        elif op == 0x7B: r['A'] = r['E']; cycles += 4  # LD A,E
        elif op == 0x11: setpair('D', 'E', w16()); cycles += 12   # LD DE,nn
        elif op == 0x21: setpair('H', 'L', w16()); cycles += 12   # LD HL,nn
        elif op == 0x06: r['B'] = b(); cycles += 8     # LD B,n
        elif op == 0x3E: r['A'] = b(); cycles += 8     # LD A,n
        elif op == 0xAF: r['A'] = 0; Z[0] = True; C[0] = False; cycles += 4  # XOR A
        elif op == 0x2A: # LD A,[HL+]
            hl = pair('H', 'L'); r['A'] = mem.read(hl); setpair('H', 'L', (hl + 1) & 0xFFFF); cycles += 8
        elif op == 0x22: # LD [HL+],A
            hl = pair('H', 'L'); mem.write(hl, r['A']); setpair('H', 'L', (hl + 1) & 0xFFFF); cycles += 8
        elif op == 0x1A: r['A'] = mem.read(pair('D', 'E')); cycles += 8   # LD A,[DE]
        elif op == 0x12: mem.write(pair('D', 'E'), r['A']); cycles += 8   # LD [DE],A
        elif op == 0x0A: r['A'] = mem.read(pair('B', 'C')); cycles += 8   # LD A,[BC]
        elif op == 0x7E: r['A'] = mem.read(pair('H', 'L')); cycles += 8   # LD A,[HL]
        elif op == 0x13: setpair('D', 'E', (pair('D', 'E') + 1) & 0xFFFF); cycles += 8  # INC DE
        elif op == 0x24: r['H'] = (r['H'] + 1) & 0xFF; Z[0] = r['H'] == 0; cycles += 4   # INC H
        elif op == 0x3C: r['A'] = (r['A'] + 1) & 0xFF; Z[0] = r['A'] == 0; cycles += 4   # INC A
        elif op == 0x05: r['B'] = (r['B'] - 1) & 0xFF; Z[0] = r['B'] == 0; cycles += 4   # DEC B
        elif op == 0xFE: # CP n
            n = b(); C[0] = r['A'] < n; Z[0] = r['A'] == n; cycles += 8
        elif op == 0xCB:
            sub = b()
            if sub == 0x3F:   # SRL A
                C[0] = bool(r['A'] & 1); r['A'] >>= 1; Z[0] = r['A'] == 0; cycles += 8
            elif sub == 0x37: # SWAP A
                r['A'] = ((r['A'] << 4) | (r['A'] >> 4)) & 0xFF; Z[0] = r['A'] == 0; C[0] = False; cycles += 8
            else:
                raise NotImplementedError(f"CB {sub:02X}")
        elif op == 0x20: # JR NZ
            off = b(); cycles += 8
            if not Z[0]:
                pc += off - 256 if off > 127 else off; cycles += 4
        elif op == 0x30: # JR NC
            off = b(); cycles += 8
            if not C[0]:
                pc += off - 256 if off > 127 else off; cycles += 4
        elif op == 0x18: # JR
            off = b(); pc += off - 256 if off > 127 else off; cycles += 12
        else:
            raise NotImplementedError(f"opcode {op:02X} at {pc-1:#06x}")
    return cycles


def _fresh_regs():
    return {k: 0 for k in "ABCDEHL"}


def verify(trials: int = 4000) -> bool:
    """Run old vs fused sweep over random inputs; assert attr writes match.

    Covers both how the sweep is used in production:
      - gated (FFC1 checked, gameplay): build_v300 / build_v296
      - gate-stripped (first 4 bytes NOPed, runs regardless of FFC1):
        build_v301_fast_sweep
    """
    from build_v300_inline_hook import BG_TABLE_BYTES
    bg_table_addr = 0x7000
    base_addr = 0x6CD0

    def strip_gate(code: bytes) -> bytes:
        b = bytearray(code); b[0:4] = bytes(4); return bytes(b)

    scenarios = [
        ("gated (FFC1=1)", lambda c: c, 1),
        ("gate-stripped (FFC1=0)", strip_gate, 0),  # fast-sweep on title
        ("gate-stripped (FFC1=1)", strip_gate, 1),  # fast-sweep in game
    ]

    for name, transform, ffc1 in scenarios:
        rng = random.Random(0xC0FFEE)
        old = transform(create_bg_sweep_viewport_gated(bg_table_addr, base_addr))
        new = transform(create_bg_sweep_viewport_gated_fast(bg_table_addr, base_addr))
        old_cycles = new_cycles = 0
        n_old = n_new = 0
        for t in range(trials):
            scy = rng.randint(0, 255)
            lcdc = 0x91 | (rng.randint(0, 1) << 3)   # bit3 = tilemap select
            df04 = rng.randint(0, 17)
            base = 0x9C00 if (lcdc & 0x08) else 0x9800
            tilemap = {i: rng.randint(0, 255) for i in range(0x400)}

            def setup():
                m = Mem(BG_TABLE_BYTES, bg_table_addr, tilemap, base)
                m.flat[0xFFC1] = ffc1
                m.flat[0xFF40] = lcdc
                m.flat[0xFF42] = scy
                m.flat[0xDF04] = df04
                return m

            mo = setup(); old_cycles += run(old, base_addr, mo, _fresh_regs())
            mn = setup(); new_cycles += run(new, base_addr, mn, _fresh_regs())

            if mo.attr_writes != mn.attr_writes:
                print(f"MISMATCH [{name}] trial {t}: scy={scy} lcdc={lcdc:#x} df04={df04}")
                print("  old:", mo.attr_writes[:8])
                print("  new:", mn.attr_writes[:8])
                return False
            if mo.flat[0xDF04] != mn.flat[0xDF04]:
                print(f"DF04 MISMATCH [{name}] trial {t}: "
                      f"old={mo.flat[0xDF04]} new={mn.flat[0xDF04]}")
                return False
            n_old = len(mo.attr_writes); n_new = len(mn.attr_writes)

        print(f"OK [{name}]: {trials} trials, attr writes byte-identical; "
              f"attrs/call={n_old}; "
              f"cyc old={old_cycles/trials:.0f}T fused={new_cycles/trials:.0f}T "
              f"(-{100*(old_cycles-new_cycles)/old_cycles:.1f}%)")

    old = create_bg_sweep_viewport_gated(bg_table_addr, base_addr)
    new = create_bg_sweep_viewport_gated_fast(bg_table_addr, base_addr)
    print(f"    code size: old={len(old)}B  fused={len(new)}B")
    return True


if __name__ == "__main__":
    ok = verify()
    sys.exit(0 if ok else 1)
