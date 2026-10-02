#!/usr/bin/env python3
"""r445: wider HBlank groups for the Stage-1 stock-clone copy (bank28 $6C80).

Stage 1 gameplay is copy-bound: the native loop publishes once per iteration and the
stock/clone copy needs 144 HBlank windows (24 rows x 6 groups of 4 tiles) = one frame,
so stock runs exactly 1 loop/frame and DX loses the loops where its attribute work
(semantic HDMA + CPU writers) pushes a publication past the frame boundary.

DEFAULT (--tiles 5): 24 rows x (5,5,5,5,4) tiles = 120 windows per publication.
Row loop (LD A,$18; PUSH AF ... POP AF; DEC A; JR Z,done; PUSH AF; JP row) with the
row's five groups unrolled.  Per group, byte-for-byte as the clone: DI; the
scene-$02-only predicate; the LY 144..151 VBlank shortcut; then bank26's STAT detect
(mode-3 gate `LDH A,(C); AND 3; CP 3; JR NZ`, fast poll `LDH A,(C); RRCA; JR C`);
tiles as `LD A,(DE); LD (HL+),A; INC DE` (INC DE everywhere, so the 24-stride source
needs no page special-casing and the group's last INC is off the critical path); EI.
C:=$41 at entry (STAT pointer), C:=0 at exit (the clone's counter left C=0; --keep-c
reproduces r445b 48870cb6 without it).  Exit ABI A=1, C=0, Z=1.
Timing proof (Astra 8160/8161/8163): worst onset from the gate's last mode-3 read to the
first tile write = AND/CP/JR-not-taken 6 + LDH 2 + RRCA/JR-not-taken 3 = 11 cycles;
worst critical path to the last VRAM write of a 5-tile group = 4x6 + 4 = 28; total 39 <=
(87 + 80) / 4 = 41.75 (mode 0 >= 87 dots with 10 sprites, plus mode 2 80 dots, VRAM
writable in both).  Live: Stage 1 665/667 = 99.70% on the strict route (r445b).
HELD (--tiles 6): 96 windows, but onset 11 + 32 = 43 > 41.75 on the worst line; not for
adoption without a full timing-state enumeration.
The builder replays the emitted bytes and asserts the identical 576 (src,dst) pairs vs
the 4-tile clone; byte scope: bank28 $6C80.. (old 76-byte helper + free space, bank
bound asserted) and checksums only.
"""
from __future__ import annotations
import argparse, hashlib, json
from pathlib import Path

BANK, ORG = 28, 0x6C80
OLD = bytes.fromhex("11 A0 C1 3E 18 F5 0E 06 C3 AB 6C 1A 1C 22 1A 1C 22 1A 1C 22 1A 13 22 FB 0D 20 ED 7D C6 08 6F 30 01 24 F1 3D 28 02 18 DD 3E 01 C9 F3 FA 80 D8 FE 02 20 08 F0 44 E6 F8 FE 90 28 D0 F0 41 E6 03 FE 03 20 F8 F0 41 E6 03 20 FA C3 8B 6C")
SRC0, ROWS, COLS = 0xC1A0, 24, 24
PATTERNS = {"6": [6, 6, 6, 6], "5": [5, 5, 5, 5, 4]}   # 6 is held: onset 11 + 32 (INC DE) > 41.75   # tiles per HBlank group, per row


def off(bank, addr): return bank * 0x4000 + addr - 0x4000


def update_checksums(rom):
    h = 0
    for v in rom[0x134:0x14D]: h = (h - v - 1) & 0xFF
    rom[0x14D] = h
    g = (sum(rom[:0x14E]) + sum(rom[0x150:])) & 0xFFFF
    rom[0x14E:0x150] = g.to_bytes(2, "big")


def emit(pattern, exit_c0: bool = True, r5_table=None, class_gate: bool = False, ei_gap: bool = False, fused: bool = False, org: int = ORG, tail_wait_groups: int = 0) -> bytes:
    """Row loop (24 iterations via PUSH AF, as the clone) with the row's groups unrolled.
    INC DE everywhere (no page special-casing), so any 24-stride source works.
    r5_table (r447 pacing): 8 bytes indexed by FFBA = how many leading rows use the wide
    `pattern`; the remaining rows use the clone's 6x4 groups, so windows per publication
    = 144 - rows5 * (6 - len(pattern)).  None = every row wide (r445/r446 behaviour).
    tail_wait_groups adds write-free HBlank waits after the copy for a stage-private
    cadence adjustment; zero preserves every historical composer byte."""
    assert tail_wait_groups >= 0
    code = bytearray()
    code += bytes.fromhex("11 A0 C1 0E 41")                    # LD DE,$C1A0; LD C,$41
    table_fix = None
    dual = (r5_table is not None) or class_gate
    jp_fused = None
    if fused:
        # r449: FFBA >= 2 and FF01 odd and FFE0 != 3 -> fused loop (stock 144 windows, the
        # attribute lookups hidden in each HBlank wait, FFE0 := 3 at exit so $42FC's
        # existing "buffer already compiled" bypass skips the $4302 compile pass).
        # r449f: no FFE0==3 exclusion.  The fused exit leaves FFE0=3 for the $42FC bypass;
        # an atomic publication that reaches the copy WITHOUT the decision stub ($3485's
        # DCFD==0 branch -> $10E7 -> NZ) keeps that stale 3, and excluding it here sent it
        # down the wide path with the compile bypassed -> a STALE buffer was DMA'd
        # (Stage 4 flips 55/56).  Running the fused lookups for every later-stage atomic
        # copy makes the buffer always fresh; a genuine decision-3 buffer is the same
        # lookup product and is simply recomputed.
        code += bytes.fromhex("F0 BA FE 02 38 18")             # LDH A,(FFBA); CP 2; JR C,+24 (not fused)
        code += bytes.fromhex("F0 01 1F 30 13")                # LDH A,(FF01); RRA; JR NC,+19
        code += bytes.fromhex("FA 4C DF B7 20 0F")             # LD A,($DF4C); OR A; JR NZ,+15  (palette machine busy: it edits the LUT -> not fused)
        # fail-closed steady-state gate: the transition detector ($6F90) caches the last
        # processed scene in $DF0D and runs the LUT-editing hook only when D880 differs from
        # it; the main thread cannot change D880 during its own copy, so DF0D == D880 here
        # means no ISR LUT edit can start before this copy ends.
        code += bytes.fromhex("FA 0D DF 47 FA 80 D8 B8 20 05") # LD A,($DF0D); LD B,A; LD A,($D880); CP B; JR NZ,+5
        code += bytes((0xC3, 0, 0)); jp_fused = len(code) - 2  # JP fused (fixup)
        code += bytes.fromhex("00 00")                         # NOP NOP (branch landing pad sizing)
    if class_gate:
        # r448 work-class gate (no counts): every row wide (B=24) when this publication
        # carries DX attribute work -- Stage 1 (FFBA==0: semantic chain follows the copy)
        # or a later-stage ATOMIC copy (FF01 odd, set by $DA13 before the copy: compile
        # follows); pure later-stage copies keep the stock 4-tile groups (B=0, 144 windows).
        code += bytes.fromhex("06 18 F0 BA B7 28 07 F0 01 1F 38 02 06 00")   # LD B,$18; LDH A,(FFBA); OR A; JR Z,+7; LDH A,(FF01); RRA; JR C,+2; LD B,$00
    if r5_table is not None:
        # B := r5_table[FFBA]  (HL preserved; table lives at the end of the helper, page-safe)
        code += bytes.fromhex("E5 F0 BA E6 07")                # PUSH HL; LDH A,(FFBA); AND 7
        table_fix = len(code) + 1
        code += bytes.fromhex("C6 00 6F 26 00 46 E1")          # ADD A,lo; LD L,A; LD H,hi; LD B,(HL); POP HL  (fixups)
    code += bytes.fromhex("3E 18 F5")                          # LD A,$18; PUSH AF
    row = len(code)
    if dual:
        code += bytes.fromhex("78 B7")                         # LD A,B; OR A
        code += bytes((0xCA, 0, 0)); jp_row4 = len(code) - 2   # JP Z,row4 (fixup; the wide body exceeds JR range)
        code += bytes.fromhex("05")                            # DEC B

    def group(ntiles):
        wait = len(code)
        code.extend(bytes.fromhex("F3 FA 80 D8 FE 02"))        # DI; LD A,($D880); CP 2
        code.extend(bytes((0x20, 0))); jr_nz = len(code) - 1   # JR NZ,stat
        code.extend(bytes.fromhex("F0 44 E6 F8 FE 90"))        # LDH A,(FF44); AND $F8; CP $90
        code.extend(bytes((0x28, 0))); jr_z = len(code) - 1    # JR Z,copy
        stat = len(code); code[jr_nz] = stat - (jr_nz + 1)
        code.extend(bytes.fromhex("F2 E6 03 FE 03"))           # LDH A,(C); AND 3; CP 3   (mode-3 gate)
        code.extend(bytes((0x20, (stat - (len(code) + 2)) & 0xFF)))
        m0 = len(code)
        code.extend(bytes.fromhex("F2 0F"))                    # LDH A,(C); RRCA          (fast mode-0 poll)
        code.extend(bytes((0x38, (m0 - (len(code) + 2)) & 0xFF)))
        copy = len(code); code[jr_z] = copy - (jr_z + 1)
        for k in range(ntiles):
            code.extend(bytes.fromhex("1A 22 13"))             # LD A,(DE); LD (HL+),A; INC DE
        code.extend(bytes.fromhex("FB"))                       # EI
        if ei_gap:
            # The clone follows EI with `DEC C; JR NZ` before the next DI, so a pending
            # interrupt is serviced once per GROUP.  `EI; DI` back-to-back services
            # nothing (EI takes effect after the next instruction), which made r445b..r448
            # service interrupts only at row ends (<= 5 lines late: a VBlank ISR can then
            # miss its LY 144..147 commit gate).  One NOP restores per-group service.
            code.extend(bytes.fromhex("00"))                   # NOP

    for ntiles in pattern: group(ntiles)
    if dual:
        code += bytes((0xC3, 0, 0)); jp_adv = len(code) - 2    # JP advance (fixup)
        row4 = org + len(code); code[jp_row4] = row4 & 0xFF; code[jp_row4 + 1] = row4 >> 8
        for ntiles in (4, 4, 4, 4, 4, 4): group(ntiles)
        adv = org + len(code); code[jp_adv] = adv & 0xFF; code[jp_adv + 1] = adv >> 8
    code += bytes.fromhex("7D C6 08 6F 30 01 24")             # LD A,L; ADD 8; LD L,A; JR NC,+1; INC H
    code += bytes.fromhex("F1 3D")                             # POP AF; DEC A
    code += bytes((0x28, 0)); jr_done = len(code) - 1          # JR Z,done (fixup)
    code += bytes.fromhex("F5")                                # PUSH AF
    code += bytes((0xC3, (org + row) & 0xFF, (org + row) >> 8))   # JP row
    done = len(code); code[jr_done] = done - (jr_done + 1)
    for _ in range(tail_wait_groups):
        group(0)
    if exit_c0:
        code += bytes.fromhex("0E 00")                         # LD C,$00: the clone exited with C=0 (its group counter);
    code += bytes.fromhex("3E 01 C9")                          # done: LD A,1; RET   restore that ABI exactly (off critical path)
    if fused:
        fstart = org + len(code); code[jp_fused] = fstart & 0xFF; code[jp_fused + 1] = fstart >> 8
        # bank30 $6C80 pre-compile side effect the fused path must keep: when FFB7 == 2 and
        # (D880 & $F6) == 2, the wall "material" LUT entries $C624/$C627/$C630/$C633 are
        # set to 6 if the effective room FFE5 == 1, else 0, before the rows are compiled.
        # (r449d omitted this: Stage 4 soak material mismatches.)  Done here at entry; the
        # inputs cannot change during this main-thread copy.
        code += bytes.fromhex("F0 B7 FE 02")                   # LDH A,(FFB7); CP 2
        code += bytes((0x20, 0)); jr_p1 = len(code) - 1        # JR NZ,skip_patch (fixup)
        code += bytes.fromhex("FA 80 D8 E6 F6 FE 02")          # LD A,($D880); AND $F6; CP 2
        code += bytes((0x20, 0)); jr_p2 = len(code) - 1        # JR NZ,skip_patch (fixup)
        code += bytes.fromhex("F0 E5 3D 3E 00 20 02 3E 06")    # LDH A,(FFE5); DEC A; LD A,0; JR NZ,+2; LD A,6
        code += bytes.fromhex("EA 24 C6 EA 27 C6 EA 30 C6 EA 33 C6")   # LD ($C624/$C627/$C630/$C633),A
        skip_patch = len(code); code[jr_p1] = skip_patch - (jr_p1 + 1); code[jr_p2] = skip_patch - (jr_p2 + 1)
        code += bytes.fromhex("06 C6 3E 18 F5")                # LD B,$C6 (lookup table page); LD A,$18; PUSH AF
        frow = len(code)
        for g in range(6):
            stat = len(code)
            code += bytes.fromhex("F3 F2 E6 03 FE 03")         # DI; LDH A,(C); AND 3; CP 3   (mode-3 gate)
            code += bytes((0x20, (stat + 1 - (len(code) + 2)) & 0xFF))    # JR NZ,gate (after the DI)
            m0 = len(code)
            code += bytes.fromhex("F2 0F")                     # LDH A,(C); RRCA
            code += bytes((0x38, (m0 - (len(code) + 2)) & 0xFF))          # JR C,poll
            code += bytes.fromhex("1A 22 1C 1A 22 1C 1A 22 1C 1A 22 13")   # 4 tiles (4-aligned: INC E x3, INC DE)
            # shadow
            code += bytes.fromhex("3E 03 E0 70")               # SVBK := 3
            code += bytes.fromhex("E5")                        # PUSH HL
            code += bytes.fromhex("7C E6 03 F6 D0 67")         # H := (H & 3) | $D0   (buffer page)
            code += bytes.fromhex("7D D6 04 6F")               # L -= 4
            # DE -= 4: after a 4-aligned group E % 4 == 0, so only the first decrement can
            # borrow; DEC DE once, then DEC E x3 (5 cycles instead of 8; Astra 8246).
            code += bytes.fromhex("1B 1D 1D 1D")
            code += bytes.fromhex("1A 1C 4F 0A 22") * 3        # LD A,(DE); INC E; LD C,A; LD A,(BC); LD (HL+),A
            code += bytes.fromhex("1A 13 4F 0A 22")            # 4th with INC DE
            code += bytes.fromhex("E1 0E 41")                  # POP HL; LD C,$41
            code += bytes.fromhex("3E 01 E0 70")               # SVBK := 1
            code += bytes.fromhex("FB 00")                     # EI; NOP  (per-group service point)
        code += bytes.fromhex("7D C6 08 6F 30 01 24")          # row advance
        code += bytes.fromhex("F1 3D")                         # POP AF; DEC A
        code += bytes((0x28, 0)); jr_fdone = len(code) - 1     # JR Z,fdone
        code += bytes.fromhex("F5")                            # PUSH AF
        code += bytes((0xC3, (org + frow) & 0xFF, (org + frow) >> 8))   # JP frow
        fdone = len(code); code[jr_fdone] = fdone - (jr_fdone + 1)
        code += bytes.fromhex("3E 03 E0 E0")                   # FFE0 := 3  (buffer already compiled -> $42FC bypass)
        code += bytes.fromhex("0E 00 3E 01 C9")                # LD C,0; LD A,1; RET
    if r5_table is not None:
        taddr = org + len(code)
        assert (taddr & 0xFF) <= 0xF8, "pacing table would cross a page (ADD A,lo must not carry)"
        code[table_fix] = taddr & 0xFF; code[table_fix + 3] = taddr >> 8
        code += bytes(r5_table)
    return bytes(code)


def model_old():
    seq = []; src = SRC0; dst = 0
    for row in range(ROWS):
        for g in range(6):
            for k in range(4):
                seq.append((src, dst)); src += 1; dst += 1
        dst += 8
    return seq


def model_new(code: bytes, ffba: int = 0, ff01: int = 0x98, ffe0: int = 1, table=None, collect_attrs=None, org: int = ORG):
    """Interpret the emitted bytes (data movement + row/pacing loops; waits are skipped)."""
    seq = []; d = 0; hl = 0; a = 0; b = 0; c = 0; sp = []; z = False; carry = False; pc = 0; steps = 0; hl_saved = []
    ffe0_v = ffe0; table = table or {}; lut_patches = []
    def rel(i): return code[i] - 256 if code[i] > 127 else code[i]
    while True:
        op = code[pc]; steps += 1; assert steps < 400000
        if code[pc:pc + 7] == bytes.fromhex("7D C6 08 6F 30 01 24"): hl += 8; pc += 7; continue   # row advance (16-bit)
        if op == 0x11: d = code[pc + 1] | (code[pc + 2] << 8); pc += 3
        elif op == 0x0E: pc += 2
        elif op == 0x3E: a = code[pc + 1]; pc += 2
        elif op == 0xF5: sp.append(a); pc += 1
        elif op == 0xF1: a = sp.pop(); pc += 1
        elif op == 0xE5: hl_saved.append(hl); pc += 1
        elif op == 0xE1: hl = hl_saved.pop(); pc += 1
        elif op == 0xF0 and code[pc + 1] == 0xBA: a = ffba; pc += 2
        elif op == 0xF0 and code[pc + 1] == 0x01: a = ff01; pc += 2
        elif op == 0xF0 and code[pc + 1] == 0xE0: a = ffe0_v; pc += 2
        elif op == 0xF0 and code[pc + 1] in (0xB7, 0xE5): a = 2 if code[pc + 1] == 0xB7 else 1; pc += 2   # scene base 2, room 1 (patch path exercised)
        elif op == 0xEA and code[pc + 2] == 0xC6: lut_patches.append((code[pc + 1] | 0xC600, a)); pc += 3
        elif op == 0xE0 and code[pc + 1] == 0xE0: ffe0_v = a; pc += 2
        elif op == 0xE0 and code[pc + 1] == 0x70: pc += 2                       # SVBK (modelled by address)
        elif op == 0x7C: a = hl >> 8; pc += 1
        elif op == 0x7D: a = hl & 0xFF; pc += 1
        elif op == 0xF6: a |= code[pc + 1]; pc += 2
        elif op == 0x67: hl = (a << 8) | (hl & 0xFF); pc += 1
        elif op == 0xD6: a = (a - code[pc + 1]) & 0xFF; pc += 2
        elif op == 0x1B: d = (d - 1) & 0xFFFF; pc += 1
        elif op == 0x1D: d = (d & 0xFF00) | ((d - 1) & 0xFF); pc += 1                 # DEC E (no borrow into D)
        elif op == 0x4F: c = a; pc += 1
        elif op == 0x0A: a = table.get((b << 8) | c, 0xEE); pc += 1              # LD A,(BC): attribute lookup
        elif op == 0xFE: z = (a == code[pc + 1]); carry = a < code[pc + 1]; pc += 2
        elif op == 0x06: b = code[pc + 1]; pc += 2
        elif op == 0x1F: carry = a & 1; a = a >> 1; pc += 1   # RRA (carry-in ignored: only the carry-out is tested)
        elif op == 0x38: pc = pc + 2 + rel(pc + 1) if carry else pc + 2
        elif op == 0xE6: a &= code[pc + 1]; z = a == 0; pc += 2
        elif op == 0xC6: a = (a + code[pc + 1]) & 0xFF; pc += 2
        elif op == 0x6F: hl = (hl & 0xFF00) | a; pc += 1          # LD L,A  (table address, not VRAM)
        elif op == 0x26: hl = (hl & 0xFF) | (code[pc + 1] << 8); pc += 2
        elif op == 0x46: b = code[hl - org]; pc += 1              # LD B,(HL) from the helper's own table
        elif op == 0x78: a = b; pc += 1
        elif op == 0xB7: z = a == 0; pc += 1
        elif op == 0x05: b = (b - 1) & 0xFF; pc += 1
        elif op == 0x1A: last_src = d; seq.append((d, hl)) if (hl >> 8) < 0xD0 else None; pc += 1
        elif op == 0x22:
            if (hl >> 8) >= 0xD0 and collect_attrs is not None: collect_attrs.append((hl, a))
            hl += 1; pc += 1
        elif op == 0x13: d = (d + 1) & 0xFFFF; pc += 1
        elif op == 0x1C: d = (d & 0xFF00) | ((d + 1) & 0xFF); pc += 1
        elif op == 0x3D: a = (a - 1) & 0xFF; z = a == 0; pc += 1
        elif op == 0x28: pc = pc + 2 + rel(pc + 1) if z else pc + 2
        elif op == 0x30: pc = pc + 2 + rel(pc + 1) if not carry else pc + 2
        elif op == 0x18: pc = pc + 2 + rel(pc + 1)
        elif op == 0xC3: pc = (code[pc + 1] | (code[pc + 2] << 8)) - org
        elif op == 0xCA: pc = ((code[pc + 1] | (code[pc + 2] << 8)) - org) if z else pc + 3
        elif op == 0xC9:
            if collect_attrs is not None: collect_attrs.extend(("lut", addr, val) for addr, val in lut_patches)
            return seq
        elif op == 0x0F: carry = False; pc += 1                 # RRCA on the STAT poll: model = mode 0 seen
        elif op in (0xF3, 0xFB, 0xF2, 0x00): pc += 1
        elif op == 0xFA and code[pc + 1:pc + 3] == bytes.fromhex("4C DF"): a = 0; z = True; pc += 3   # DF4C idle in the model
        elif op == 0xFA and code[pc + 1:pc + 3] in (bytes.fromhex("0D DF"), bytes.fromhex("80 D8")): a = 4; pc += 3   # DF0D == D880 (steady scene 4)
        elif op == 0x47: b = a; pc += 1
        elif op == 0xB8: z = (a == b); carry = a < b; pc += 1
        elif op == 0xFA: pc += 3
        elif op in (0xF0, 0x20): pc += 2   # waits: fall through (not taken)
        else: raise AssertionError(f"unmodelled opcode {op:02X} at {pc}")


def build(src: bytes, *, tiles: str = "5", keep_c: bool = False,
          r5: list[int] | None = None, class_gate: bool = False,
          ei_gap: bool = False, fused: bool = False) -> tuple[bytes, dict]:
    """Compose and model-check the helper entirely in memory."""
    o = off(BANK, ORG)
    assert src[o:o + len(OLD)] == OLD, "bank28 stock-clone helper preimage differs"
    pattern = PATTERNS[tiles]
    if r5 is not None:
        assert len(r5) == 8 and all(0 <= x <= ROWS for x in r5)
    assert not (class_gate and r5 is not None)
    code = emit(pattern, exit_c0=not keep_c, r5_table=r5, class_gate=class_gate, ei_gap=ei_gap, fused=fused)
    assert code[3:5] == bytes.fromhex("0E 41")
    assert ORG + len(code) <= 0x8000, "helper overflows bank 28"
    assert set(src[o + len(OLD):o + len(code)]) == {0xFF}, "bank28 free space after helper not free"
    table = {0xC600 + t: (t * 7 + 3) & 0x07 for t in range(256)}
    for ffba in range(8):
        for ff01 in (0x98, 0x99, 0x9C, 0x9D):
            for ffe0 in (1, 3):
                attrs = []
                assert model_new(code, ffba, ff01, ffe0, table, attrs) == model_old(), f"copy sequence differs from the 4-tile clone (FFBA={ffba}, FF01={ff01:02X})"
                fused_taken = fused and ffba >= 2 and (ff01 & 1)
                luts = [x for x in attrs if x[0] == "lut"]; attrs = [x for x in attrs if x[0] != "lut"]
                if fused_taken:
                    assert luts == [("lut", 0xC624, 6), ("lut", 0xC627, 6), ("lut", 0xC630, 6), ("lut", 0xC633, 6)], luts   # bank30 material patch (room 1 -> 6)
                    # attribute buffer must equal the $4302 compile: table[src tile] at $D000 + row*32 + col
                    assert len(attrs) == 576, len(attrs)
                    # the model's table is keyed by tile id; the src byte is not known to the replay, so
                    # check addresses and that every cell was written exactly once in row-major order
                    expect = [0xD000 + r * 32 + col for r in range(24) for col in range(24)]
                    assert [addr for addr, _ in attrs] == expect, "attribute buffer address order differs from the compile"
                else:
                    assert attrs == [] and luts == [], "attribute/LUT writes outside the fused class"
    rom = bytearray(src); rom[o:o + len(code)] = code; update_checksums(rom)
    changed = sorted(i for i in range(len(src)) if src[i] != rom[i])
    assert set(changed) <= set(range(o, o + len(code))) | {0x14D, 0x14E, 0x14F}
    straddles = "n/a (INC DE everywhere)"
    rec = {"schema": "penta-compose-stage1-wide-copy-r445-v5", "base_sha256": hashlib.sha256(src).hexdigest(),
           "candidate_sha256": hashlib.sha256(rom).hexdigest(), "changed_range": f"bank{BANK}:${ORG:04X}..${ORG + len(code) - 1:04X} ({len(code)} B) + checksums",
           "windows_per_publication": (ROWS * len(pattern) if r5 is None else {f"FFBA{i}": 144 - n * (6 - len(pattern)) for i, n in enumerate(r5)}),
           "old_windows": ROWS * 6, "tiles_per_group": pattern, "r5_table": r5,
           "class_gate": ("wide (120 windows) iff FFBA==0 or FF01 odd; else stock 4-tile (144 windows)" if class_gate else None),
           "ei_gap": ("EI; NOP per group (interrupts serviced per group as the clone)" if ei_gap else "EI;DI back-to-back: interrupts serviced only at row ends (r445b..r448)"),
           "fused": ("FFBA>=2 && FF01 odd && DF4C==0 && DF0D==D880: 144 windows, lookups in shadow -> $D000 (row stride 32), FFE0:=3, exit A=1,C=0" if fused else None),
           "page_end_sources_using_INC_DE": straddles, "model_equivalence": "old==new (src,dst) sequence, 576 cells",
           "precedent": "bank26 Stage-1 atomic path uses 6-tile CPU groups ($6D33..$6D44 etc.) and this exact poll, live-audited",
           "exit_abi": ("A=1, C=0 (as the clone), Z=1" if not keep_c else "A=1, C=$41 (r445b), Z=1"),
           "worst_case_cycles": "onset 11 (gate last read -> AND/CP/JR 6 -> LDH 2 -> RRCA/JR 3) + critical path to the last VRAM write (5-tile, INC DE: 4x6+4 = 28) = 39 <= (87+80)/4 = 41.75", "live_tested": False}
    return bytes(rom), rec


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--base", type=Path, required=True); ap.add_argument("--out-dir", type=Path, required=True)
    ap.add_argument("--tiles", choices=tuple(PATTERNS), default="5", help="tiles per HBlank group: 5 = (5,5,5,5,4) 120 windows [default]; 6 = 96 windows (worst case 42 > 41.75, held)")
    ap.add_argument("--keep-c", action="store_true", help="omit the LD C,0 exit (reproduces r445b 48870cb6; C exits $41)")
    ap.add_argument("--r5", default=None, help="r447 pacing: 8 comma-separated leading-wide-row counts indexed by FFBA (0..24 each); omit = all rows wide")
    ap.add_argument("--class-gate", action="store_true", help="r448: wide rows only for publications that carry DX attribute work (FFBA==0, or FF01 odd); pure later-stage copies keep 4-tile groups")
    ap.add_argument("--ei-gap", action="store_true", help="r448b+: NOP after each group's EI so interrupts are serviced per group like the clone (r445b..r448 serviced only at row ends)")
    ap.add_argument("--fused", action="store_true", help="r449f: steady later-stage atomic copies compile attributes in the HBlank shadow; FFE0:=3 at exit")
    a = ap.parse_args()
    r5 = [int(x) for x in a.r5.split(",")] if a.r5 is not None else None
    rom, rec = build(a.base.read_bytes(), tiles=a.tiles, keep_c=a.keep_c,
                     r5=r5, class_gate=a.class_gate, ei_gap=a.ei_gap, fused=a.fused)
    a.out_dir.mkdir(parents=True, exist_ok=True)
    t = a.out_dir / "candidate.gb"
    if t.exists() and t.read_bytes() != rom: raise SystemExit("candidate collision")
    t.write_bytes(rom)
    (a.out_dir / "build-receipt.json").write_text(json.dumps(rec, indent=2) + "\n")
    print(json.dumps({k: rec[k] for k in ("candidate_sha256", "changed_range", "windows_per_publication", "page_end_sources_using_INC_DE")}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
