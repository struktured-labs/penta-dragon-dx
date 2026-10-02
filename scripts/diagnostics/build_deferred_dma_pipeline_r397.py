#!/usr/bin/env python3
"""r397: deferred attribute-DMA pipeline (Stage 1), ROM-only, on exact r392 early-w4.

Removes the per-publication VBlank busy-wait (~69 f on the north route) by letting
the CPU continue after the attribute compile and doing the 48-block GDMA inside
the VBlank ISR, running the semantic scanner afterwards from the main loop, and
flipping only once the scanner has finished.  Every existing VRAM writer keeps
its order (scan is always after the DMA), so no writer census is disturbed.

Latch (FFC4, existing byte; bit7 abs, bit4 page, bits3-0 SCY; bits 6:5 = state):
    00 IDLE   01 DMA_PENDING   10 READY_TO_FLIP   11 SCAN_PENDING
Raw completed H ($98..$9F) has bits 6:5 = 00 and the old packed $C0|.. is 10, so
every non-Stage-1 / pure publication keeps today's format and behaviour.

Sites (bank-local; every preimage asserted):
  b00 $018A  JP $016C            -> JP $13DE                    (loop hook, registers dead by construction)
  b00 $13DE  7 x 00              -> CALL $13B3; JP $016C
  b00 $13B3  13 x 00             -> PUSH AF; PUSH BC; LDH A,(FF99); LD B,A; LD A,$1A; CALL $0847; POP BC; POP AF; RET
  b26 $6C80  virgin              -> combined service; role from the caller return address at SP+8
                                    ($13E1 = loop: 11 -> READY, DI, push $42C6, JP $DBF1; else nothing)
                                    ($12DA = guard: 01 -> synchronous wait+DMA of the old page then scan;
                                     11 -> scan; 10/00 -> nothing; always leaves HL=$C1A0 for $1399)
  b01 $42C6  9 x 00 (dead cave)  -> POP HL; POP DE; POP BC; LD A,B; EI; RET   (scanner continuation, bank 1;
                                    the service pushes BC/DE/HL before the scan, HL=$C1A0 on the publish path)
  b00 $12D7  LD HL,$C1A0         -> CALL $13B3                  (publish guard, before $1399 regenerates C1A0)
  (no WRAM is touched: the live stub installer is bank31's and $DBE2..$DBF0 is live code there)
  b13 $746D  LDH A,(FFC4); AND $40; JP $7400 -> LD A,$1C; CALL $0847; JP $7400   (ISR: bank28 decides, Z = skip)
  b28 $6C80  virgin              -> ISR service: LY gate; 01 -> GDMA (SVBK3/VBK1, no push) then 01->11, skip;
                                    10 -> commit (Z=0); 00/11 -> skip (Z=1); returns A=$0D
  b24 $6E00  packer              -> backpressure on any non-idle state; Stage-1 atomic writes 01, everything else 10
  b23 $6C80  wait+DMA service    -> prefixed with `LDH A,(FFBA); OR A; JR NZ,+3; LD A,1; RET` (Stage 1: no sync DMA)
  b01 $432D  JP $4354            -> JP $4351 ; $4351 = LDH A,(FFBA); OR A; CALL NZ,$DBF1 (Stage 1: scan deferred)
  b19 $6CCE  LDH A,(FFC4); AND $FC; LD H,A -> LDH A,(FF01); ... (page for the deferred scan; FFC4 is the latch then)

Rules obeyed (learned tonight): a switchable-bank service never far-calls another
through $0847 (the callee's returned bank replaces the caller's); the scanner
returns with bank 1 mapped, so its continuation lives in bank 1 ($42C6); no
PUSH/CALL between SVBK=3 and SVBK=1; the ISR path runs with IME=0.
Static proofs below: preimages, owned bytes, label assembly, a banked-fetch walk
of every far-call path, and a latch state-machine simulation.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BASE = ROOT / "tmp/cold-art-vblank-guard-r392-early-w4/candidate.gb"
BASE_SHA = "c8f21f0ed47b40b1372e1e2a73d6f526590e5dc4d1b2b2d00b9c1e916e59c5ff"
OUT = ROOT / "tmp/deferred-dma-pipeline-r397"
CHECKSUMS = frozenset((0x014D, 0x014E, 0x014F))
SCAN_BANK, ISR_BANK, SYNC_BANK = 26, 28, 23   # bank 26 serves BOTH hook sites (see scan_service)
SVC = 0x6C80
CAVE_42C6 = 0x42C6
IDLE, DMA_PENDING, READY, SCAN_PENDING = 0x00, 0x20, 0x40, 0x60


def off(bank: int, addr: int) -> int:
    return bank * 0x4000 + addr - 0x4000


def update_checksums(rom: bytearray) -> None:
    h = 0
    for v in rom[0x134:0x14D]:
        h = (h - v - 1) & 0xFF
    rom[0x14D] = h
    g = (sum(rom[:0x14E]) + sum(rom[0x150:])) & 0xFFFF
    rom[0x14E:0x150] = g.to_bytes(2, "big")


class Asm:
    def __init__(self, org: int) -> None:
        self.org, self.code, self.labels, self.fix = org, bytearray(), {}, []

    def label(self, n: str) -> None:
        self.labels[n] = self.org + len(self.code)

    def db(self, *b: int) -> None:
        self.code += bytes(b)

    def jr(self, op: int, n: str) -> None:
        self.fix.append((len(self.code) + 1, n, "rel")); self.db(op, 0)

    def jp(self, op: int, n: str) -> None:
        self.fix.append((len(self.code) + 1, n, "abs")); self.db(op, 0, 0)

    def finish(self) -> bytes:
        for pos, n, kind in self.fix:
            if kind == "abs":
                t = self.labels[n]; self.code[pos] = t & 0xFF; self.code[pos + 1] = t >> 8
                continue
            d = self.labels[n] - (self.org + pos + 1)
            assert -128 <= d <= 127, (n, d)
            self.code[pos] = d & 0xFF
        return bytes(self.code)


# ---------------------------------------------------------------- code images
LOOP_HOOK = bytes.fromhex("C3 DE 13")                                 # $018A
LOOP_FRAG = bytes.fromhex("CD B3 13 C3 6C 01 00")                     # $13DE (7)
BRIDGE = bytes.fromhex("F5 C5 F0 99 47 3E 1A CD 47 08 C1 F1 C9")      # $13B3 (13)
CAVE = bytes.fromhex("E1 D1 C1 78 FB C9")                             # $42C6 (6 of 9): POP HL; POP DE; POP BC; LD A,B; EI; RET
PUBLISH_HOOK = bytes.fromhex("CD B3 13")                              # $12D7: CALL $13B3 (same bridge; HL=$C1A0 restored by the cave/service)
TAIL_432D = bytes.fromhex("C3 51 43")                                 # $432D
TAIL_4351 = bytes.fromhex("F0 BA B7 C4 F1 DB")                        # $4351..$4356


MARK_RET = 0x09A1      # fixed-bank `RET` (end of $099A); low byte $A1 selects the wait role
BRIDGE_ADDR = 0x13B3


def scan_service() -> bytes:
    """bank26:$6C80 — one service, three roles, selected by the word at SP+10
    (below the bridge's AF/BC and the two CALL returns; HL is saved around the probe):
      $E1 (loop frag $13E1)  : SCAN -> READY under DI, push BC/DE/HL + $42C6, JP $DBF1; else EI, return
      $DA (publish $12DA)    : DMA -> old wait+DMA; then (or SCAN ->) plant [MARK_RET][BRIDGE] on the
                               stack, HL=$C1A0, scan as above.  After the scan the cave RETs into the
                               BRIDGE (fake return) which re-enters this service in the wait role;
                               READY -> wait role directly.  IDLE -> nothing.
      $A1 (MARK_RET)         : wait until the ISR has committed (IDLE), LCD-off escape, HL=$C1A0,
                               EI, return; the bridge tail then RETs into MARK_RET (a RET) which
                               pops the real $084D and the original chain continues to $12DA.
    Every state test and READY write happens under DI.
    """
    a = Asm(SVC)
    a.db(0xE5, 0xF8, 0x0A, 0x7E, 0xE1)                            # PUSH HL; LD HL,SP+10; LD A,(HL); POP HL
    a.db(0xFE, 0xDA); a.jr(0x28, "guard")
    a.db(0xFE, MARK_RET & 0xFF); a.jp(0xCA, "wait_role")         # JP Z (out of JR range)
    a.db(0xF3)                                                    # DI  (loop role)
    a.db(0xF0, 0xC4, 0xE6, 0x60, 0xFE, SCAN_PENDING); a.jr(0x20, "idle_ei")
    a.label("scan")                                               # IME=0 on every path here
    a.db(0xF0, 0xC4, 0xE6, 0x9F, 0xF6, READY, 0xE0, 0xC4)         # state := READY
    a.db(0xC5, 0xD5, 0xE5)                                        # PUSH BC; PUSH DE; PUSH HL (cave restores)
    a.db(0x21, CAVE_42C6 & 0xFF, CAVE_42C6 >> 8, 0xE5, 0xC3, 0xF1, 0xDB)  # push continuation; JP $DBF1
    a.label("idle_ei")
    a.db(0xFB, 0x78, 0xC9)                                        # EI; LD A,B; RET
    a.label("guard")
    a.db(0xF3)                                                    # DI
    a.db(0xF0, 0xC4, 0xE6, 0x60); a.jr(0x28, "gdone")            # idle
    a.db(0xFE, READY); a.jp(0xCA, "wait_role")                    # ready: wait for the commit
    a.db(0xFE, SCAN_PENDING); a.jr(0x28, "plant")                 # scan owed
    sync_wait_dma(a, dest_from_latch=True)                        # DMA_PENDING: old DMA now (ends IME=0)
    a.label("plant")                                              # arrange: cave RET -> BRIDGE -> wait role
    a.db(0x21, MARK_RET & 0xFF, MARK_RET >> 8, 0xE5)              # push MARK_RET (probe word + final RET)
    a.db(0x21, BRIDGE_ADDR & 0xFF, BRIDGE_ADDR >> 8, 0xE5)        # push fake return into the bridge
    a.db(0x21, 0xA0, 0xC1)                                        # HL=$C1A0 (restored by the cave)
    a.jp(0xC3, "scan")
    a.label("wait_role")
    a.db(0xFB)                                                    # EI: the ISR must run
    a.db(0xF0, 0x40, 0xCB, 0x7F); a.jr(0x28, "gdone")            # LCD off: no ISR; proceed
    a.db(0xF0, 0xC4, 0xE6, 0x60); a.jr(0x20, "wait_role")        # spin until IDLE
    a.label("gdone")
    a.db(0x21, 0xA0, 0xC1, 0xFB, 0x78, 0xC9)                      # HL=$C1A0; EI; LD A,B; RET
    return a.finish()


def sync_wait_dma(a: Asm, *, dest_from_latch: bool) -> None:
    """Astra's r371/r373 wait+DMA body (bank23 $6C80..$6CD8), transcribed; dest page
    from the latch bit4 when dest_from_latch, else from FFC4&FC (raw H)."""
    a.db(0xC5, 0xF0, 0xFF, 0xF5, 0x3E, 0x01, 0xE0, 0x70)          # PUSH BC; LDH A,(FFFF); PUSH AF; SVBK=1
    a.db(0xF0, 0xFF, 0xE6, 0x04, 0xE0, 0xFF, 0xFB)                # IE &= Timer; EI
    a.label("wait")
    a.db(0xF0, 0x40, 0xCB, 0x7F); a.jr(0x28, "go")                # LCD off -> go
    a.db(0xF0, 0x44, 0xE6, 0xFC, 0xFE, 0x90); a.jr(0x20, "wait")  # LY&FC != 90 -> wait
    a.db(0xF3, 0xF0, 0x44, 0xE6, 0xFC, 0xFE, 0x90); a.jr(0x28, "go2")  # DI; recheck
    a.db(0xFB); a.jr(0x18, "wait")
    a.label("go")
    a.db(0xF3)
    a.label("go2")
    a.db(0x3E, 0x03, 0xE0, 0x70)                                  # SVBK=3
    if dest_from_latch:
        a.db(0xF0, 0xC4, 0xE6, 0x10, 0x0F, 0x0F, 0xF6, 0x18, 0xE0, 0x53)  # page bit4 -> $18/$1C
    else:
        a.db(0xF0, 0xC4, 0xE6, 0xFC, 0xE0, 0x53)
    a.db(0xAF, 0xE0, 0x54, 0x3E, 0x01, 0xE0, 0x4F, 0x3E, 0xD0, 0xE0, 0x51, 0xAF, 0xE0, 0x52)
    a.db(0x3E, 0x2F, 0xE0, 0x55)                                  # GDMA 48 blocks
    a.label("poll")
    a.db(0xF0, 0x55, 0xCB, 0x7F); a.jr(0x28, "poll")
    a.db(0xAF, 0xE0, 0x4F, 0x3C, 0xE0, 0x70)                      # VBK=0; SVBK=1
    a.db(0xF1, 0xE0, 0xFF, 0xC1)                                  # IE restore; POP BC


def isr_service() -> bytes:
    a = Asm(SVC)
    a.db(0xF0, 0x44, 0xE6, 0xFC, 0xFE, 0x90); a.jr(0x20, "skip")  # LY 144..147 only
    a.db(0xF0, 0xC4, 0xE6, 0x60); a.jr(0x28, "skip")              # idle
    a.db(0xFE, READY); a.jr(0x28, "commit")
    a.db(0xFE, DMA_PENDING); a.jr(0x20, "skip")                   # 11 -> wait for scan
    a.db(0xF0, 0x4F, 0x4F)                                        # LD C,VBK (save)
    a.db(0x3E, 0x03, 0xE0, 0x70)                                  # SVBK=3 (no push from here)
    a.db(0x3E, 0xD0, 0xE0, 0x51, 0xAF, 0xE0, 0x52)                # src $D000
    a.db(0xF0, 0xC4, 0xE6, 0x10, 0x0F, 0x0F, 0xF6, 0x18, 0xE0, 0x53, 0xAF, 0xE0, 0x54)  # dest page
    a.db(0x3E, 0x01, 0xE0, 0x4F, 0x3E, 0x2F, 0xE0, 0x55)          # VBK=1; GDMA (CPU halted until done)
    a.db(0x79, 0xE0, 0x4F, 0x3E, 0x01, 0xE0, 0x70)                # VBK restore; SVBK=1
    a.db(0x21, 0xC4, 0xFF, 0xCB, 0xF6)                            # 01 -> 11
    a.label("skip")
    a.db(0xAF, 0x3E, 0x0D, 0xC9)                                  # Z=1; A=$0D; RET
    a.label("commit")
    a.db(0xAF, 0x3C, 0x3E, 0x0D, 0xC9)                            # Z=0; A=$0D; RET
    return a.finish()


def packer() -> bytes:
    a = Asm(0x6E00)
    a.db(0xF0, 0xC4, 0xE6, 0x60, 0xC0)                            # backpressure: any non-idle
    a.db(0xFA, 0x00, 0xDC, 0xEA, 0x5C, 0xDF)                      # DF5C := SCX
    a.db(0xF0, 0xC4, 0xB7); a.jr(0x28, "rel")                     # raw H == 0 -> relative
    a.db(0xE6, 0x04, 0x07, 0x07, 0xF6, 0x80)                      # page -> bit4, abs
    a.label("rel")
    a.db(0x47)                                                    # LD B,A
    a.db(0xF0, 0x01, 0x1F, 0x3E, READY); a.jr(0x30, "pack")       # FF01 even -> READY
    a.db(0xF0, 0xBA, 0xB7, 0x3E, READY); a.jr(0x20, "pack")       # not Stage 1 -> READY
    a.db(0x3E, DMA_PENDING)
    a.label("pack")
    a.db(0xB0, 0x47, 0xFA, 0x02, 0xDC, 0xE6, 0x0F, 0xB0, 0xE0, 0xC4, 0xC9)
    return a.finish()


PACKER_OLD = bytes.fromhex("F0 C4 CB 77 C0 FA 00 DC EA 5C DF F0 C4 B7 28 06 E6 04 07 07 F6 80 F6 40 47 FA 02 DC E6 0F B0 E0 C4 C9")
SYNC_OLD_LEN = 0x59   # bank23 $6C80..$6CD8
SYNC_PREFIX = bytes.fromhex("F0 BA B7 20 03 3E 01 C9")


# ---------------------------------------------------------------- models
def walk_far_calls(rom: bytes, images: dict) -> dict:
    """Banked-fetch walk of the three bridge paths.  $DBF1 is abstracted as
    'switch to bank 1, RET to the top of stack'; everything else is executed."""
    fixed = {0x0061: rom[0x0061:0x0067], 0x09BE: rom[0x09BE:0x09C4], 0x0847: rom[0x0847:0x0850],
             0x13B3: images["bridge"], 0x13DE: images["loop_frag"], MARK_RET: b"\xc9"}
    assert rom[MARK_RET] == 0xC9, "MARK_RET must be a RET in fixed bank"
    banked = {1: {CAVE_42C6: images["cave"], 0x4351: TAIL_4351}, SCAN_BANK: {SVC: images["scan"]},
              ISR_BANK: {SVC: images["isr"]}}
    wram = {}

    def fetch(bank, pc):
        for base, blob in list(fixed.items()) + list(wram.items()):
            if base <= pc < base + len(blob):
                return blob[pc - base]
        for base, blob in banked.get(bank, {}).items():
            if base <= pc < base + len(blob):
                return blob[pc - base]
        raise AssertionError(f"fetch ${pc:04X} bank {bank}: no code")

    def run(entry, bank, ffc4, ly=145, ffba=0, ret_to=None):
        A = 0x5A; B = C = 0x11; H, L = 0x77, 0x66; D = E = 0x55; Z = CY = False; ime = True
        ff99 = dc09 = bank; stack = []; pc = entry; trace = []; svbk = 1
        sp_probe = None
        if ret_to is not None:
            stack.append(("RET", (bank, ret_to)))
        for _ in range(400):
            op = fetch(bank, pc)
            trace.append((bank, pc, op))
            if op == 0xF5: stack.append(("AF", A)); pc += 1
            elif op == 0xC5: stack.append(("BC", (B << 8) | C)); assert svbk == 1; pc += 1
            elif op == 0xE5: stack.append(("HL", (H << 8) | L)); pc += 1
            elif op == 0xD5: stack.append(("DE", (D << 8) | E)); pc += 1
            elif op == 0xD1: k, v = stack.pop(); assert k == "DE"; D, E = v >> 8, v & 0xFF; pc += 1
            elif op == 0xF1: k, v = stack.pop(); assert k == "AF"; A = v; pc += 1
            elif op == 0xC1: k, v = stack.pop(); assert k == "BC"; B, C = v >> 8, v & 0xFF; pc += 1
            elif op == 0xE1: k, v = stack.pop(); assert k == "HL"; H, L = v >> 8, v & 0xFF; pc += 1
            elif op == 0xF0:
                r = fetch(bank, pc + 1)
                A = {0x99: ff99, 0xC4: ffc4, 0x44: ly, 0xBA: ffba, 0x01: 0x99, 0xFF: 0x0D, 0x4F: 0, 0x40: 0x91, 0x55: 0xFF}[r]; pc += 2
            elif op == 0xE0:
                r = fetch(bank, pc + 1)
                if r == 0x99: ff99 = A
                elif r == 0xC4:
                    if (A & 0x60) == READY and (ffc4 & 0x60) == SCAN_PENDING:
                        assert ime is False, "READY must be published with IME off"
                    ffc4 = A
                elif r == 0x70: svbk = A
                pc += 2
            elif op == 0x47: B = A; pc += 1
            elif op == 0x4F: C = A; pc += 1
            elif op == 0x78: A = B; pc += 1
            elif op == 0x79: A = C; pc += 1
            elif op == 0x3E: A = fetch(bank, pc + 1); pc += 2
            elif op == 0x21: L, H = fetch(bank, pc + 1), fetch(bank, pc + 2); pc += 3
            elif op == 0xF8:                                    # LD HL,SP+e8 -> probe into the stack model
                e = fetch(bank, pc + 1); assert e % 2 == 0
                H, L = 0x12, 0x34; sp_probe = stack[-(e // 2 + 1)]; pc += 2
            elif op == 0x7E:                                    # LD A,(HL): only used on the SP probe
                assert (H << 8) | L == 0x1234
                k, v = sp_probe
                A = (v[1] if k == "RET" else v) & 0xFF; pc += 1
            elif op == 0xE6: A &= fetch(bank, pc + 1); Z = A == 0; pc += 2
            elif op == 0xF6: A |= fetch(bank, pc + 1); Z = A == 0; pc += 2
            elif op == 0xFE: n = fetch(bank, pc + 1); Z = A == n; CY = A < n; pc += 2
            elif op == 0xB7: Z = A == 0; pc += 1
            elif op == 0xAF: A = 0; Z = True; pc += 1
            elif op == 0x3C: A = (A + 1) & 0xFF; Z = A == 0; pc += 1
            elif op == 0x1F: CY, A = bool(A & 1), A >> 1; pc += 1
            elif op == 0x0F: A = ((A >> 1) | ((A & 1) << 7)) & 0xFF; pc += 1
            elif op == 0xF3: ime = False; pc += 1
            elif op == 0xFB: ime = True; pc += 1
            elif op == 0xCB:
                sub = fetch(bank, pc + 1)
                if sub in (0xAE, 0xF6):
                    assert (H << 8) | L == 0xFFC4, "latch RES/SET must address FFC4"
                if sub == 0xAE: ffc4 &= ~0x20 & 0xFF
                elif sub == 0xAF: raise AssertionError("CB AF is RES 5,A — latch update must use (HL)")
                elif sub == 0xF6: ffc4 |= 0x40
                elif sub == 0x7F: Z = not (A & 0x80)
                else: raise AssertionError(sub)
                pc += 2
            elif op in (0x18, 0x20, 0x28, 0x30):
                d = fetch(bank, pc + 1); d = d - 256 if d > 127 else d
                take = {0x18: True, 0x20: not Z, 0x28: Z, 0x30: not CY}[op]
                if take and d < 0 and bank == SCAN_BANK and (ffc4 & 0x60) == READY and ime:
                    assert ime, "wait_idle must spin with IME on so the ISR can commit"
                    ffc4 &= 0x9F                                 # model: the ISR commits during the wait loop
                pc = pc + 2 + d if take else pc + 2
            elif op == 0xCD:
                t = fetch(bank, pc + 1) | (fetch(bank, pc + 2) << 8)
                stack.append(("RET", (bank, pc + 3)))
                if t == 0xDBF1: raise AssertionError("CALL $DBF1 must be a JP with pushed continuation")
                pc = t
            elif op == 0xCA:                                    # JP Z,nn
                t = fetch(bank, pc + 1) | (fetch(bank, pc + 2) << 8)
                pc = t if Z else pc + 3
            elif op == 0xC3:
                t = fetch(bank, pc + 1) | (fetch(bank, pc + 2) << 8)
                if t == 0xDBF1:
                    assert ime is False, "scanner must be entered with IME=0"
                    bank = ff99 = dc09 = 1                      # scanner ends with bank 1 mapped
                    D = E = 0xAA; H = L = 0xBB                  # scanner clobbers DE/HL
                    k, v = stack.pop(); assert k == "HL", "continuation must be on top of stack"
                    pc = v; continue
                if t == 0x016C: return {"bank": bank, "ff99": ff99, "ffc4": ffc4, "sp_ok": not stack, "A": A,
                                        "HL": (H << 8) | L, "DE": (D << 8) | E}
                pc = t
            elif op == 0xEA:
                addr = fetch(bank, pc + 1) | (fetch(bank, pc + 2) << 8)
                if addr == 0xDC09: dc09 = A
                elif addr == 0x2100: bank = A
                elif addr in (0xDF5C,): pass
                pc += 3
            elif op == 0xFA: pc += 3; A = 0
            elif op == 0xC0:
                if not Z: k, v = stack.pop(); assert k == "RET"; _, pc = v
                else: pc += 1
            elif op == 0xC9:
                k, v = stack.pop()
                if k == "RET": _, pc = v
                elif k == "HL": pc = v                          # planted return (fake bridge entry / MARK_RET)
                else: raise AssertionError((k, trace[-6:]))
                if pc == 0x12DA:                                # returned to the publish site
                    return {"bank": bank, "ff99": ff99, "ffc4": ffc4, "sp_ok": not stack, "HL": (H << 8) | L, "ime": ime}
                if pc == 0x13E1:                                # loop frag continues with JP $016C
                    pass
            else:
                raise AssertionError(f"unmodelled {op:02X} at ${pc:04X} bank {bank}")
        raise AssertionError("walk did not terminate")

    res = {}
    # loop hook from $018A with bank 1 mapped, for each latch state
    for st in (IDLE, DMA_PENDING, READY, SCAN_PENDING):
        r = run(0x13DE, 1, 0x90 | st)
        assert r["bank"] == 1 and r["ff99"] == 1 and r["sp_ok"], (st, r)
        assert r["HL"] == 0x7766 and r["DE"] == 0x5555, "loop hook must preserve HL/DE"
        assert (r["ffc4"] & 0x60) == (READY if st == SCAN_PENDING else st), (st, hex(r["ffc4"]))
        res[f"loop_state_{st >> 5}"] = hex(r["ffc4"])
    # publish guard from $12D7 (CALL $DBE2) with bank 1 mapped
    for st in (IDLE, READY, SCAN_PENDING, DMA_PENDING):
        r = run(0x13B3, 1, 0x90 | st, ret_to=0x12DA)
        assert r["bank"] == 1 and r["ff99"] == 1 and r["sp_ok"] and r["HL"] == 0xC1A0, (st, r)
        assert (r["ffc4"] & 0x60) == IDLE, (st, hex(r["ffc4"]))   # every guard path leaves the pipeline drained
        assert r["ime"] is True, "guard must return with IME re-enabled"
        res[f"guard_state_{st >> 5}"] = hex(r["ffc4"])
    return res


def latch_state_machine() -> dict:
    """Event-level simulation of the pipeline for atomic Stage-1 publications."""
    def isr(s, ly=145):
        if not (144 <= ly <= 147): return s, "gate-skip"
        if s == DMA_PENDING: return SCAN_PENDING, "dma"
        if s == READY: return IDLE, "flip"
        return s, "skip"

    def loop(s):
        return (READY, "scan") if s == SCAN_PENDING else (s, "none")

    def guard(s):
        if s == DMA_PENDING: return IDLE, "flush+scan+wait"
        if s == SCAN_PENDING: return IDLE, "scan+wait"
        if s == READY: return IDLE, "wait-for-commit"
        return s, "none"

    def packer(s, atomic=True):
        if s != IDLE: return s, "dropped"
        return (DMA_PENDING if atomic else READY), "latched"

    checks = {}
    # normal: publish -> ISR dma -> loop scan -> ISR flip
    s, ev = packer(IDLE); s, e1 = isr(s); s, e2 = loop(s); s, e3 = isr(s)
    assert (ev, e1, e2, e3) == ("latched", "dma", "scan", "flip") and s == IDLE
    checks["normal_sequence"] = "latched -> dma -> scan -> flip"
    # scan must never be skipped before flip: ISR after dma without loop
    s, _ = packer(IDLE); s, _ = isr(s); s, e = isr(s); assert e == "skip" and s == SCAN_PENDING
    checks["no_flip_before_scan"] = True
    # double publication before ISR: guard flushes, then packer drops the new request
    s, _ = packer(IDLE); s, e = guard(s); assert e == "flush+scan+wait" and s == IDLE
    s, e3 = packer(s); assert e3 == "latched"
    checks["double_publication_flushes_scans_waits_then_latches"] = "no publication superseded"
    # scan owed when the next publish arrives: guard scans first
    s, _ = packer(IDLE); s, _ = isr(s); s, e = guard(s); assert e == "scan+wait" and s == IDLE
    checks["scan_owed_at_publish_is_paid_first"] = True
    # pure / later-stage publication: unchanged single-step flip
    s, _ = packer(IDLE, atomic=False); s, e = isr(s); assert e == "flip" and s == IDLE
    checks["pure_publication_unchanged"] = True
    # ISR outside the LY gate never touches state
    for st in (DMA_PENDING, READY, SCAN_PENDING):
        assert isr(st, ly=60) == (st, "gate-skip")
    checks["ly_gate"] = True
    return checks


# ---------------------------------------------------------------- build
def build(source: bytes) -> tuple[bytes, dict]:
    assert hashlib.sha256(source).hexdigest() == BASE_SHA, "wrong exact early-w4 base"
    pre = {
        (0, 0x018A, 3): bytes.fromhex("C3 6C 01"), (0, 0x13DE, 7): bytes(7), (0, 0x13B3, 13): bytes(13),
        (0, 0x12D7, 3): bytes.fromhex("21 A0 C1"), (0, 0x12DA, 3): bytes.fromhex("CD 99 13"),
        (0, 0x0847, 9): bytes.fromhex("CD 61 00 CD 80 6C C3 61 00"), (0, 0x0061, 6): bytes.fromhex("EA 09 DC C3 BE 09"),
        (0, 0x016C, 3): bytes.fromhex("CD 5D 49"),
        (1, 0x42C6, 9): bytes(9), (1, 0x42C3, 3): bytes.fromhex("C3 C0 13"), (1, 0x42CF, 1): b"\x1a",
        (1, 0x432D, 3): bytes.fromhex("C3 54 43"), (1, 0x4351, 9): bytes.fromhex("00 00 00 CD F1 DB C3 DF DB"),
        (1, 0x435A, 2): bytes.fromhex("26 98"), (1, 0x4324, 4): bytes.fromhex("3E 01 E0 70"),
        # pure path (FF01 even) -> CALL $DBF1 at $42F5; EI; RET : must stay untouched (Astra 8031/8037)
        (1, 0x42ED, 14): bytes.fromhex("7C E0 C4 F0 01 1F 38 07 CD F1 DB 00 FB C9"),
        (13, 0x746D, 7): bytes.fromhex("F0 C4 E6 40 C3 00 74"),
        (13, 0x7400, 3): bytes.fromhex("CA 1D 6F"), (13, 0x7464, 9): bytes.fromhex("F0 44 E6 FC FE 90 C2 1D 6F"),
        (13, 0x7474, 2): bytes.fromhex("F0 44"),
        (24, 0x6E00, len(PACKER_OLD)): PACKER_OLD,
        (13, 0x5830, 12): bytes.fromhex("F0 BA B7 28 04 AF E0 01 C9 C3 E2 10"),   # DBF1 image
        # Stage-1 chain vector: page from FFC4&FC.  In the pipeline the deferred scan runs AFTER the
        # packer has repacked FFC4 into the latch, so this must read FF01 (H or H+1, &FC = page)
        # instead — valid in the synchronous pure path too (FF01 = H there).  Forgetting this sent
        # the corrections to $C0xx/$D0xx WRAM (live north rejection, Astra msg 8041).
        (19, 0x6CCE, 8): bytes.fromhex("F0 C4 E6 FC 67 C3 A7 6B"),
    }
    # No other FFC4 reader may exist in the scan-chain banks.
    for bank in (19, 20, 21):
        hits = [i for i in range(0x4000 - 1) if source[bank * 0x4000 + i] == 0xF0 and source[bank * 0x4000 + i + 1] == 0xC4]
        assert hits == ([0x2CCE] if bank == 19 else []), (bank, [hex(0x4000 + h) for h in hits])
    for (bank, addr, n), want in pre.items():
        o = off(bank, addr) if bank else addr
        assert source[o:o + n] == want, f"preimage bank{bank}:${addr:04X}"
    for bank in (SCAN_BANK, ISR_BANK):
        assert set(source[bank * 0x4000:(bank + 1) * 0x4000]) == {0xFF}, f"bank {bank} not virgin"
    sync_old = source[off(SYNC_BANK, SVC):off(SYNC_BANK, SVC) + SYNC_OLD_LEN]
    assert sync_old[:4] == bytes.fromhex("C5 F0 FF F5") and sync_old[-1] == 0xC9, "bank23 service preimage"
    assert b"\xc3" not in sync_old and b"\xcd" not in sync_old, "bank23 service has absolute refs; cannot shift"
    assert set(source[off(SYNC_BANK, SVC + SYNC_OLD_LEN):off(SYNC_BANK, SVC + SYNC_OLD_LEN + 8)]) == {0xFF}
    # $12D7's site is bank-1 code by construction ($12D4 CALL $439F, bank 1 address)
    assert source[0x12D4:0x12D7] == bytes.fromhex("CD 9F 43")
    # $4351 (Stage-1 scan skip) must be reachable only from the atomic tail's $432D.
    b1 = source[0x4000:0x8000]
    refs = [0x4000 + i for i in range(len(b1) - 2)
            if b1[i] in (0xC3, 0xCD, 0xC2, 0xCA, 0xD2, 0xDA, 0xC4, 0xCC, 0xD4, 0xDC)
            and 0x4351 <= (b1[i + 1] | (b1[i + 2] << 8)) <= 0x4357]
    refs += [0x4000 + i for i in range(len(b1) - 1) if b1[i] in (0x18, 0x20, 0x28, 0x30, 0x38)
             and 0x4351 <= 0x4000 + i + 2 + (b1[i + 1] - 256 if b1[i + 1] > 127 else b1[i + 1]) <= 0x4357]
    assert refs == [0x432D], f"$4351..$4357 referenced from {[hex(x) for x in refs]}"

    images = {"bridge": BRIDGE, "loop_frag": LOOP_FRAG, "cave": CAVE,
              "scan": scan_service(), "isr": isr_service(), "packer": packer()}
    assert len(images["packer"]) <= 0x50 and len(images["scan"]) < 0x100 and len(images["isr"]) < 0x60
    checks = {"far_call_walk": walk_far_calls(source, images), "latch_state_machine": latch_state_machine()}

    rom = bytearray(source); owned = set()

    def put(bank, addr, data):
        o = off(bank, addr) if bank else addr
        rom[o:o + len(data)] = data; owned.update(range(o, o + len(data)))

    put(0, 0x018A, LOOP_HOOK); put(0, 0x13DE, LOOP_FRAG); put(0, 0x13B3, BRIDGE); put(0, 0x12D7, PUBLISH_HOOK)
    put(1, CAVE_42C6, CAVE); put(1, 0x432D, TAIL_432D); put(1, 0x4351, TAIL_4351)
    # $7474 holds the r392 guard (must stay); the ISR far call needs 8 bytes in 7, so
    # $746D..$7473 = `LD A,$1C; CALL $0847; JR $7485` and the spare $7485..$7487 = `JP $7400`.
    put(13, 0x746D, bytes.fromhex("3E 1C CD 47 08 18 11"))       # JR from $7474 +$11 -> $7485
    assert 0x7472 + 2 + 0x11 == 0x7485
    assert rom[off(13, 0x7474)] == 0xF0 and source[off(13, 0x7485):off(13, 0x7488)] == bytes(3)
    put(13, 0x7485, bytes.fromhex("C3 00 74"))
    put(SCAN_BANK, SVC, images["scan"]); put(ISR_BANK, SVC, images["isr"])
    put(19, 0x6CCF, bytes((0x01,)))                               # $6CCE: LDH A,(FFC4) -> LDH A,(FF01)
    pad = len(PACKER_OLD) - len(images["packer"])
    put(24, 0x6E00, images["packer"] + (bytes([0xFF]) * pad if pad > 0 else b""))
    put(SYNC_BANK, SVC, SYNC_PREFIX + sync_old)
    update_checksums(rom)
    changed = {i for i, (x, y) in enumerate(zip(source, rom)) if x != y}
    assert changed <= owned | CHECKSUMS, sorted(changed - owned - CHECKSUMS)[:8]
    receipt = {
        "schema": "penta-deferred-dma-pipeline-r397-build-v1",
        "experimental": True, "promotable": False, "live_tested": False,
        "base_sha256": BASE_SHA, "candidate_sha256": hashlib.sha256(rom).hexdigest(),
        "changed_offsets": sorted(changed),
        "latch_encoding": {"idle": "00", "dma_pending": "01", "ready_to_flip": "10", "scan_pending": "11",
                           "note": "raw H = 00, legacy packed $C0 = 10; later stages unchanged"},
        "images": {k: v.hex() for k, v in images.items()},
        "harness_note": "atomic Stage-1 publications no longer reach $4354/$6C80(bank23); scan-done site is bank1:$42C6, "
                        "DMA site is bank28:$6C80 (from ISR), flush site bank27:$6C80 (from publish guard)",
        "latency": "+1 VBlank per atomic Stage-1 publication (flip after ISR DMA + main-loop scan)",
        "scene_0b": "included (FFBA==0 predicate); scan chain self-gates on FFB7/D880 as before",
        "static_checks": checks,
    }
    return bytes(rom), receipt


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--base", type=Path, default=BASE)
    ap.add_argument("--out-dir", type=Path, default=OUT)
    args = ap.parse_args()
    rom, receipt = build(args.base.read_bytes())
    args.out_dir.mkdir(parents=True, exist_ok=True)
    t = args.out_dir / "candidate.gb"
    if t.exists() and t.read_bytes() != rom:
        raise SystemExit("candidate collision")
    t.write_bytes(rom)
    (args.out_dir / "build-receipt.json").write_text(json.dumps(receipt, indent=2) + "\n")
    print(json.dumps({"candidate_sha256": receipt["candidate_sha256"], "changed_bytes": len(receipt["changed_offsets"]),
                      "checks": receipt["static_checks"]}, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
