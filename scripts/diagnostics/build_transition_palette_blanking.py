#!/usr/bin/env python3
"""#55/#83: mirror the native DMG blanking in CGB palette RAM at two transitions.

Root cause (shared). The original hides two load phases with BGP/OBP, which
CGB mode ignores, so DX shows whatever palette RAM / VRAM happens to hold:

* #55 stage start. ``00:0F7D`` (native fade-in, BGP 00 -> 40 -> 90 -> E4)
  runs right after the STAGE card.  The DX palette sequencer is gated on
  ``BGP == E4`` (``0D:6BA4``), so during the fade BG1-BG7 still hold the
  previous deck (BG6 = flat yellow on the wall columns) and OBJ0-7 are
  white; only BG0 is installed by the map-flip arm (``0D:740F``).  On main,
  that stale deck lasts ~46 frames.
* #83 secret-area entry. ``00:1494`` sets the native fade owner ``FFE4`` and
  calls ``169C``, which sets BGP/OBP0/OBP1 = FF (all black) and then streams
  the STAGE ?? font/map into VRAM for ~17 frames.  On CGB the half-written
  tiles are displayed (garbled text flash).

Fix (single deterministic stage; every hooked site is gameplay-only and never
executed by the attract demo or title, so attract stays byte-identical):

1. ``00:0F8B CALL 4068`` (the fade-in's 8-frame waits) -> ``CALL 00F0``.
   The body samples the caller bank's own ``4068`` one frame at a time until
   the map is presented, then writes the stage deck once (BG1-BG7 and
   OBJ0-OBJ7 when ``D880 == 02``, ``FFC1 != 0`` and ``LCDC.3``; OBJ0-OBJ7
   only when ``D880 == 09``) and finishes any remaining frames with one
   native ``CALL 4068``.  That keeps later phase (Cameo publication) on the
   parent 8-frame wait, instead of re-installing every leftover fade frame.
   Same source rows and selection rules as the sequencer phases at
   ``0D:6900``; BG0 is still installed by the existing arm and the STAGE
   card's CRAM is never deliberately touched.  The map flip itself lives in
   the attract-shared VBlank ISR (``0D:7430-746D``), which is not modified;
   one presented frame may still show leftover palettes, and the suite
   allows exactly that frame.
2. ``00:1494 LD A,1; LDH [FFE4],A; CALL 169C; JP 146C`` ->
   ``CALL 00F0; LD A,1; CALL 169C; JR 146C``.  The body sets ``FFE4 = 1`` and
   blacks out all 16 CGB palettes, matching the original's BGP=OBP=FF frames.
3. ``00:159F CALL 75C7`` (STAGE ?? card, reached only from the secret ``1594``
   path) -> ``CALL 00F0``.  The body replays bank-1 ``75C7`` as a return chain
   (492B, 0A16, 109E, 7653, re-entering bank $30 through the trampoline at
   ``00F3``), performs the card map flip (``75D8``) and the card map copy
   (``75DE CALL 4B52``) while CRAM is still black, then from the top of the
   next frame restores BG0-BG7 (paced, finished before the card glyph rows)
   and OBJ0-OBJ7, and resumes at ``1:75E2``.
   The card therefore appears complete in one frame, with no garbled map.
4. Fixed-bank ``00F0-00FE`` (unreferenced stock fill after #54/#78): far-call
   trampoline into bank ``$30`` via the stock ``0061`` bank switch (FF99/DC09
   protocol), restoring the caller's bank on return.  Re-entry through
   ``00F3`` with a continuation >= $4000 on the stack returns straight to it.
5. ``14:7F1D``: the DX window-enable VBlank wait accepts any vblank line
   (``CP $90; JR NC``) after DI instead of exactly ``LY == $90`` (timer-IRQ
   starvation hang, see WAIT_SITE).  The six-byte change is owned by this
   stage; three bank-20 authentication gates carry a documented carve-out
   for exactly these bytes.

Mid-frame CRAM writes are 4-byte bursts started on a mode-3 -> HBlank edge (or
immediately inside VBlank) with interrupts held only for that burst; unpaced
if the LCD is off.  The deck rows are copied from ``0D:6800`` at build time.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

PARENT = '9642170ac94ebcf8b278eaffd6afea1d3545d851123b33233f08fa69a14fe095'
ORIGINAL = '2f32570cff62b8664bfa06b939988c3fd6a7efabf870a990a5fa65bab37eac30'

BANK = 0x30
BODY = 0x4000
TRAMP = 0x00F0
CARD_SITE = 0x159F            # CALL 75C7 (bank-1 stage card) in the secret-only 1594 path
CARD_RET = CARD_SITE + 3
CARD_PRE = bytes.fromhex('CDC775')
FADE_SITE = 0x0F8B            # CALL 4068 (B = 8 frames) inside the native fade-in 0F7D
FADE_RET = FADE_SITE + 3
SECRET_SITE = 0x1494
SECRET_RET = SECRET_SITE + 3
DECK = 0x0D * 0x4000 + 0x2800  # 0D:6800 compiled palette deck (BG 00-3F, OBJ 40-FF)

FADE_PRE = bytes.fromhex('CD6840')
# 14:7F1D (DX window-enable VBlank wait, r373): after DI it required LY == $90
# exactly and otherwise re-armed with EI.  A timer IRQ that straddles the edge
# can starve it forever (boss card / mid-fight hang once the timer/LCD phase
# shifts).  The preceding 7F10-7F1A already waits for vblank (LY >= $90); the
# post-DI check accepts any vblank line (CP $90; JR NC) so an IRQ that burns
# past LY $93 cannot send it back around the wait.  Same size and cycles;
# never executed by the attract demo.
WAIT_SITE = 0x14 * 0x4000 + 0x3F1D
WAIT_PRE = bytes.fromhex('F044FE902804')
WAIT_NEW = bytes.fromhex('F044FE903004')
SECRET_PRE = bytes.fromhex('3E01E0E4CD9C16C36C14')


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def checksum(rom: bytearray) -> None:
    rom[0x14E:0x150] = ((sum(rom[:0x14E]) + sum(rom[0x150:])) & 0xFFFF).to_bytes(2, 'big')


class Asm:
    def __init__(self, org):
        self.org, self.b, self.labels, self.fix = org, bytearray(), {}, []

    def db(self, *v):
        self.b.extend(v)

    def label(self, name):
        self.labels[name] = self.org + len(self.b)

    def jr(self, op, name):
        self.b.extend((op, 0)); self.fix.append(('jr', len(self.b) - 1, name))

    def abs16(self, op, name):
        self.b.extend((op, 0, 0)); self.fix.append(('abs', len(self.b) - 2, name))

    def ld16(self, op, name):
        self.abs16(op, name)

    def finish(self):
        for kind, at, name in self.fix:
            target = self.labels[name]
            if kind == 'jr':
                rel = target - (self.org + at + 1)
                assert -128 <= rel <= 127, name
                self.b[at] = rel & 0xFF
            else:
                self.b[at:at + 2] = target.to_bytes(2, 'little')
        return bytes(self.b)


def trampoline() -> bytes:
    # LDH A,[FF99]; PUSH AF; LD A,$30; CALL 0061; CALL 4000; POP AF; JP 0061
    return bytes([0xF0, 0x99, 0xF5, 0x3E, BANK, 0xCD, 0x61, 0x00,
                  0xCD, BODY & 0xFF, BODY >> 8, 0xF1, 0xC3, 0x61, 0x00])


def body(deck: bytes) -> bytes:
    a = Asm(BODY)
    a.db(0xC5, 0xD5, 0xE5)                 # PUSH BC/DE/HL
    a.db(0xF8, 0x0A)                       # LD HL,SP+10 -> site return address
    a.db(0x2A, 0x66, 0x6F)                 # LD A,[HL+]; LD H,[HL]; LD L,A
    a.db(0x7C, 0xFE, 0x40)                 # LD A,H; far-call re-entry?
    a.jr(0x30, 'resume')
    a.db(0xFE, SECRET_RET >> 8)            # CP $14
    a.abs16(0xCA, 'secret')                # JP Z
    a.db(0xFE, CARD_RET >> 8)              # CP $15
    a.abs16(0xCA, 'card')
    a.abs16(0xC3, 'fwait')                 # 0F8E: fade-in frame wait
    # ---- re-entry from a far call: return straight to the continuation --
    a.label('resume')
    a.db(0xE1, 0xD1, 0xC1, 0xC9)
    # ---- #55 fade-in frame waits ---------------------------------------
    # Site 0F8B CALL 4068 (B = 8 frames).  Sample at a 1-frame grain (caller
    # bank 4068 with B = 1, re-entering through 00F3) until the dungeon or
    # secret map is presented, install the deck once (never over the STAGE
    # card), then finish any remaining frames with one native CALL 4068 so
    # later phase (Cameo publication) matches the parent 8-frame wait.
    # The attract-shared flip ISR is not modified, so one presented frame
    # may still show leftover palettes.
    a.label('fwait')
    a.db(0xE1, 0xD1, 0xC1)                 # POP HL/DE/BC (B = frame count)
    a.db(0xE5, 0xD5)                       # keep the caller's HL/DE
    a.label('fw_loop')
    a.db(0xC5)                             # PUSH BC (counter)
    a.ld16(0x21, 'fw_cont'); a.db(0xE5)
    for word in (0x3000, TRAMP + 3, 0x4068):
        a.db(0x21, word & 0xFF, word >> 8, 0xE5)
    a.db(0xF8, 17, 0x7E)                   # LD HL,SP+17; LD A,[HL] (caller bank)
    a.db(0x06, 0x01, 0xC3, 0x61, 0x00)     # LD B,1; JP 0061 -> RET into 4068
    a.label('fw_cont')
    a.abs16(0xCD, 'install')
    a.db(0x5F)                             # LD E,A (A=1 if the deck was written)
    a.db(0xC1, 0x05)                       # POP BC; DEC B
    a.jr(0x28, 'fw_done')                  # no frames left (B = 0 as native)
    a.db(0x7B, 0xB7)                       # LD A,E; OR A
    a.jr(0x28, 'fw_loop')                  # no-op: keep sampling at 1-frame grain
    a.label('fw_bulk')
    a.db(0xC5)
    a.ld16(0x21, 'fw_bulk_done'); a.db(0xE5)
    for word in (0x3000, TRAMP + 3, 0x4068):
        a.db(0x21, word & 0xFF, word >> 8, 0xE5)
    a.db(0xF8, 17, 0x7E)
    a.db(0xC3, 0x61, 0x00)                 # JP 0061, B = remaining frames
    a.label('fw_bulk_done')
    a.db(0xC1)                             # drop the remaining-count slot
    a.label('fw_done')
    a.db(0xD1, 0xE1, 0xC9)                 # POP DE/HL; RET
    a.label('install')
    a.db(0xFA, 0x80, 0xD8, 0xFE, 0x09)     # LD A,[D880]; CP 9 (secret fade-in)
    a.jr(0x28, 'inst_obj')
    a.db(0xFE, 0x02)                       # CP 2
    a.jr(0x20, 'inst_noop')                # not dungeon: A=0
    a.db(0xF0, 0xC1, 0xB7)                 # LDH A,[FFC1]; OR A
    a.jr(0x28, 'inst_noop')
    a.db(0xF0, 0x40, 0xCB, 0x5F)           # dungeon map (LCDC.3) not presented yet
    a.jr(0x28, 'inst_noop')
    a.db(0x3E, 0xB0, 0xE0, 0x68)           # BCPS = BG6 colour 0: walls/BG7 first
    a.ld16(0x21, 'bg6_row')                # BG6, BG7 dungeon row
    a.db(0x0E, 0x69, 0x06, 4)
    a.abs16(0xCD, 'write')
    a.db(0x3E, 0x88, 0xE0, 0x68)           # BCPS = BG1 colour 0
    a.ld16(0x21, 'bg_rows')                # BG1-BG5
    a.db(0x06, 10)
    a.abs16(0xCD, 'write')
    a.label('inst_obj')
    a.abs16(0xC3, 'load_obj')
    a.label('inst_noop')
    a.db(0xAF, 0xC9)                       # XOR A; RET (no deck written)
    # ---- #83 secret-area entry blackout -------------------------------
    a.label('secret')
    a.db(0x3E, 0x01, 0xE0, 0xE4)           # LD A,1; LDH [FFE4],A (displaced)
    a.db(0x3E, 0x80, 0xE0, 0x68)           # BCPS = BG0 colour 0
    a.ld16(0x21, 'black')
    a.db(0x0E, 0x69, 0x06, 16)
    a.abs16(0xCD, 'write')
    a.db(0x3E, 0x80, 0xE0, 0x6A)           # OCPS = OBJ0 colour 0
    a.ld16(0x21, 'black')
    a.db(0x0E, 0x6B, 0x06, 16)
    a.abs16(0xCD, 'write')
    a.db(0xFB, 0xE1, 0xD1, 0xC1, 0xC9)     # EI; POP HL/DE/BC; RET
    # ---- #83 secret card: replay bank-1 75C7 with the BG restore at the flip
    # Stack on entry: regs, 00FB, saved AF, 15A2.  Drop the trampoline frame
    # and run 492B/0A16/109E/7653 as a bank-1 return chain that comes back
    # here through the trampoline's bank-$30 re-entry (00F3).
    a.label('card')
    a.db(0xE1, 0xD1, 0xC1)                 # POP HL/DE/BC
    a.db(0xE8, 0x04)                       # ADD SP,4 (drop 00FB and saved AF)
    a.ld16(0x21, 'card_cont'); a.db(0xE5)
    for word in (0x3000, TRAMP + 3, 0x7653, 0x109E, 0x0A16, 0x492B):
        a.db(0x21, word & 0xFF, word >> 8, 0xE5)
    a.db(0x3E, 0x01, 0xC3, 0x61, 0x00)     # LD A,1; JP 0061 -> RET into 492B
    a.label('card_cont')
    a.db(0xAF, 0xE0, 0x43, 0xE0, 0x42)     # XOR A; SCY = SCX = 0 (75D3)
    a.db(0xF0, 0x40, 0xCB, 0x9F, 0xE0, 0x40)   # card map flip (75D8); CRAM still black
    # 75DE CALL 4B52 (card map copy, several frames) as a chain back to here
    a.ld16(0x21, 'card_lit'); a.db(0xE5)
    for word in (0x3000, TRAMP + 3, 0x4B52):
        a.db(0x21, word & 0xFF, word >> 8, 0xE5)
    a.db(0x3E, 0x01, 0xC3, 0x61, 0x00)
    a.label('card_lit')
    a.db(0xF5, 0xE5)                       # slots: AF for 75E7 POP, return for 0061
    a.db(0xC5, 0xD5, 0xE5)
    a.db(0xF0, 0x40, 0xCB, 0x7F)           # LCD off -> restore immediately
    a.jr(0x28, 'card_restore')
    a.label('card_vb')
    a.db(0xF0, 0x44, 0xFE, 0x90)           # wait for VBlank (interrupts stay on)
    a.jr(0x38, 'card_vb')
    a.label('card_top')
    a.db(0xF0, 0x44, 0xFE, 0x90)           # ... then for the next frame's top
    a.jr(0x30, 'card_top')
    a.label('card_restore')
    a.db(0x3E, 0x80, 0xE0, 0x68)           # BCPS = BG0 colour 0
    a.ld16(0x21, 'bg0_row')                # BG0-BG7, paced from line ~0: done
    a.db(0x0E, 0x69, 0x06, 16)             # before the card glyph rows (y >= 40)
    a.abs16(0xCD, 'write')
    a.abs16(0xCD, 'load_obj')              # OBJ0-7 (no sprites on the card)
    a.db(0xFB)                             # IME back on before resume 75E2
    a.db(0xF8, 0x06, 0x36, 0xE2, 0x23, 0x36, 0x75)   # slot = 75E2
    a.db(0xE1, 0xD1, 0xC1)
    a.db(0x3E, 0x01, 0xC3, 0x61, 0x00)     # resume bank-1 75E2 (D880 = 18; fade 0F47)
    # ---- load_obj: OBJ0-7 from the deck with the sequencer's row rules ----
    a.label('load_obj')
    a.db(0x3E, 0x80, 0xE0, 0x6A)           # OCPS = OBJ0 colour 0, auto-inc
    a.db(0x1E, 0x00)                       # LD E,0 (OBJ slot)
    a.label('obj_loop')
    a.abs16(0xCD, 'obj_row')               # HL = source row for slot E
    a.db(0x0E, 0x6B, 0x06, 2)              # LD C,$6B; LD B,2 bursts
    a.abs16(0xCD, 'write')
    a.db(0x1C, 0x7B, 0xFE, 0x08)           # INC E; LD A,E; CP 8
    a.jr(0x20, 'obj_loop')
    a.db(0x3E, 0x01, 0xC9)             # LD A,1; RET (deck written)
    # ---- obj_row: E = slot -> HL = obj_rows + offset (sequencer rules) --
    a.label('obj_row')
    a.db(0x7B, 0x07, 0x07, 0x07, 0xC6, 0x40, 0x6F)   # L = $40 + 8*E (default)
    a.db(0xF0, 0xBF, 0xB7)                 # miniboss slot? FFBF != 0
    a.jr(0x28, 'not_boss')
    a.db(0x3D, 0x47, 0xE6, 0x01, 0xC6, 0x06, 0xBB)   # DEC A; LD B,A; AND 1; ADD 6; CP E
    a.jr(0x20, 'not_boss')
    a.db(0x78, 0xE6, 0x07, 0x07, 0x07, 0x07, 0xC6, 0x80, 0x6F)  # L = $80 + 8*((FFBF-1)&7)
    a.jr(0x18, 'row_ready')
    a.label('not_boss')
    a.db(0x7B, 0xB7)                       # E == 0: Sara form (FFC0)
    a.jr(0x20, 'not_sara')
    a.db(0xF0, 0xC0, 0xB7)
    a.jr(0x28, 'row_ready')
    a.db(0x2E, 0xF0, 0xFE, 0x01)           # default other: $F0
    a.jr(0x20, 'sara2')
    a.db(0x2E, 0xE0)
    a.jr(0x18, 'row_ready')
    a.label('sara2')
    a.db(0xFE, 0x02)
    a.jr(0x20, 'row_ready')
    a.db(0x2E, 0xE8)
    a.jr(0x18, 'row_ready')
    a.label('not_sara')
    a.db(0xFE, 0x03)
    a.jr(0x30, 'high_slot')
    a.db(0xF0, 0xD0, 0xFE, 0x01)           # E = 1/2 with FFD0 == 1
    a.jr(0x20, 'row_ready')
    a.db(0x2E, 0xD0, 0x7B, 0xFE, 0x01)     # E=2 -> $D0
    a.jr(0x20, 'row_ready')
    a.db(0x2E, 0xD8)                       # E=1 -> $D8
    a.jr(0x18, 'row_ready')
    a.label('high_slot')
    a.db(0xCB, 0x53)                       # BIT 2,E
    a.jr(0x28, 'row_ready')
    a.db(0xF0, 0xB7, 0xFE, 0x0E)
    a.jr(0x20, 'row_ready')
    a.db(0x2E, 0x98)
    a.label('row_ready')
    a.db(0x7D, 0xD6, 0x40, 0x6F, 0x26, 0x00)  # L -= $40 (rows copied from $6840); H = 0
    a.ld16(0x01, 'obj_rows')               # LD BC,obj_rows
    a.db(0x09, 0xC9)                       # ADD HL,BC; RET
    # ---- write: B bursts of 4 bytes from HL to [C] ---------------------
    a.label('write')
    a.db(0xF0, 0x40, 0xCB, 0x7F)           # LCD off -> unpaced
    a.jr(0x28, 'fast')
    a.label('burst')
    a.db(0xF3)                             # DI
    a.db(0xF0, 0x41, 0xE6, 0x03, 0xFE, 0x01)   # in VBlank (mode 1): CRAM is writable through LY 153 and mode 2
    a.jr(0x20, 'paced')
    a.db(0xF0, 0x44, 0xFE, 0x9A)
    a.jr(0x38, 'vblank_fast')
    a.label('paced')
    a.db(0xFB)                             # EI while waiting for mode 3
    a.label('w3')
    a.db(0xF0, 0x41, 0xE6, 0x03, 0xFE, 0x03)
    a.jr(0x20, 'w3')
    a.db(0xF3)                             # DI
    a.db(0xF0, 0x41, 0xE6, 0x03, 0xFE, 0x03)
    a.jr(0x20, 'paced')                    # interrupted: wait for the next line
    a.label('w0')
    a.db(0xF0, 0x41, 0xE6, 0x03, 0xFE, 0x03)
    a.jr(0x28, 'w0')
    a.label('four')
    a.db(0x2A, 0xE2, 0x2A, 0xE2, 0x2A, 0xE2, 0x2A, 0xE2)
    a.db(0xFB, 0x05)                       # EI; DEC B
    a.jr(0x20, 'burst')
    a.db(0xC9)
    a.label('vblank_fast')
    a.db(0x2A, 0xE2, 0x2A, 0xE2, 0x2A, 0xE2, 0x2A, 0xE2, 0x05)
    a.jr(0x20, 'vblank_fast')
    # Ack a timer request that may have arrived during the long DI, then EI.
    # Immediate EI with a deferred timer pending (c1aba914) stranded later
    # gameplay in the bank-20 window path. Returning with IME off (c5c86525)
    # or EI only after leaving vblank (df664f22) either broke blank-SRAM
    # stage-card presentation or still took that IRQ. Clearing IF.2 before
    # EI keeps remaining 4068 waits at IME=1 without replaying the missed tick.
    a.db(0xF0, 0x0F, 0xE6, 0xFB, 0xE0, 0x0F, 0xFB, 0xC9)
    a.label('fast')
    a.db(0x2A, 0xE2, 0x2A, 0xE2, 0x2A, 0xE2, 0x2A, 0xE2, 0x05)
    a.jr(0x20, 'fast')
    a.db(0xC9)
    # ---- data ----------------------------------------------------------
    a.label('bg0_row')
    a.db(*deck[0x00:0x08])
    a.label('bg_rows')
    a.db(*deck[0x08:0x30])
    a.label('bg6_row')
    a.db(*deck[0x30:0x38], *deck[0xC8:0xD0])
    a.label('obj_rows')
    a.db(*deck[0x40:0x100])
    a.label('black')
    a.db(*bytes(64))
    code = a.finish()
    return code


def build(parent: bytes, original: bytes) -> bytes:
    if sha(parent) != PARENT:
        raise ValueError('exact soft-reset-cold-init parent required')
    if sha(original) != ORIGINAL:
        raise ValueError('exact original cartridge required')
    if parent[FADE_SITE:FADE_SITE + 3] != FADE_PRE or original[FADE_SITE:FADE_SITE + 3] != FADE_PRE:
        raise ValueError('fade-in CALL 4068 preimage differs')
    if parent[SECRET_SITE:SECRET_SITE + 10] != SECRET_PRE or original[SECRET_SITE:SECRET_SITE + 10] != SECRET_PRE:
        raise ValueError('secret-entry preimage differs')
    if parent[CARD_SITE:CARD_SITE + 3] != CARD_PRE or original[CARD_SITE:CARD_SITE + 3] != CARD_PRE:
        raise ValueError('secret card call preimage differs')
    if parent[WAIT_SITE:WAIT_SITE + 6] != WAIT_PRE:
        raise ValueError('bank-14 VBlank wait preimage differs')
    tramp = trampoline()
    if parent[TRAMP:TRAMP + len(tramp)] != original[TRAMP:TRAMP + len(tramp)]:
        raise ValueError('bank-0 fill 00F0 is no longer stock')
    base = BANK * 0x4000
    if parent[base:base + 0x4000] != b'\xff' * 0x4000:
        raise ValueError('bank $30 is not erased')
    code = body(parent[DECK:DECK + 0x100])
    result = bytearray(parent)
    result[TRAMP:TRAMP + len(tramp)] = tramp
    result[FADE_SITE:FADE_SITE + 3] = bytes([0xCD, TRAMP & 0xFF, TRAMP >> 8])
    jr = (0x146C - (SECRET_SITE + 10)) & 0xFF
    result[SECRET_SITE:SECRET_SITE + 10] = bytes([0xCD, TRAMP & 0xFF, TRAMP >> 8, 0x3E, 0x01,
                                                  0xCD, 0x9C, 0x16, 0x18, jr])
    result[CARD_SITE:CARD_SITE + 3] = bytes([0xCD, TRAMP & 0xFF, TRAMP >> 8])
    result[WAIT_SITE:WAIT_SITE + 6] = WAIT_NEW
    result[base:base + len(code)] = code
    checksum(result)
    return bytes(result)


def changed_spans(original: bytes) -> list[tuple[int, int]]:
    base = BANK * 0x4000
    return [(TRAMP, TRAMP + len(trampoline())), (FADE_SITE, FADE_SITE + 3),
            (SECRET_SITE, SECRET_SITE + 10), (CARD_SITE, CARD_SITE + 3),
            (WAIT_SITE, WAIT_SITE + 6), (base, base + 0x4000)]


def reconstruct_parent(rom: bytes, original: bytes) -> bytes:
    parent = bytearray(rom)
    base = BANK * 0x4000
    for lo, hi in changed_spans(original):
        if lo in (WAIT_SITE, base):
            continue
        parent[lo:hi] = original[lo:hi]
    parent[WAIT_SITE:WAIT_SITE + 6] = WAIT_PRE
    parent[base:base + 0x4000] = b'\xff' * 0x4000
    checksum(parent)
    parent = bytes(parent)
    if sha(parent) != PARENT or build(parent, original) != rom:
        raise ValueError('transition palette blanking reconstruction failed')
    return parent


def verify_installed(rom: bytes, original: bytes) -> list[str]:
    failures = []
    if rom[TRAMP:TRAMP + len(trampoline())] != trampoline():
        failures.append('bank-0 trampoline missing')
    if rom[FADE_SITE:FADE_SITE + 3] != bytes([0xCD, TRAMP & 0xFF, TRAMP >> 8]):
        failures.append('fade-in site does not call the trampoline')
    if rom[SECRET_SITE:SECRET_SITE + 3] != bytes([0xCD, TRAMP & 0xFF, TRAMP >> 8]):
        failures.append('secret-entry site does not call the trampoline')
    if rom[CARD_SITE:CARD_SITE + 3] != bytes([0xCD, TRAMP & 0xFF, TRAMP >> 8]):
        failures.append('secret card site does not call the trampoline')
    if rom[WAIT_SITE:WAIT_SITE + 6] != WAIT_NEW:
        failures.append('bank-14 VBlank wait still requires the exact edge')
    code = body(rom[DECK:DECK + 0x100])
    base = BANK * 0x4000
    if rom[base:base + len(code)] != code or rom[base + len(code):base + 0x4000] != b'\xff' * (0x4000 - len(code)):
        failures.append('bank $30 body differs')
    return failures


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('parent', type=Path)
    parser.add_argument('--original', type=Path, default=ROOT / 'rom/Penta Dragon (J).gb')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists() or (ROOT / 'tmp').resolve() not in args.output.resolve().parents:
        parser.error('fresh repository-local tmp output required')
    original = args.original.read_bytes()
    result = build(args.parent.read_bytes(), original)
    args.output.mkdir(parents=True)
    (args.output / 'candidate.gb').write_bytes(result)
    receipt = dict(parent_sha256=PARENT, original_sha256=ORIGINAL, candidate_sha256=sha(result),
                   builder_sha256=sha(Path(__file__).read_bytes()),
                   static_failures=verify_installed(result, original))
    (args.output / 'receipt.json').write_text(json.dumps(receipt, indent=2) + '\n')
    print(json.dumps(receipt))
