#!/usr/bin/env python3
"""r393: step 1 of the deferred-DMA plan — semantic writer buffer redirect + scanner reorder.

Base: exact r392 early-w4 (c8f21f0e...).  Static only.

What changes (and nothing else):

1. bank19:$6C8F (27 B, the semantic attribute writer) becomes a 7-byte stub
   `LD A,$1A; CALL $0847; XOR A; RET`.  $0847 is the fixed-bank far-call
   dispatcher (CALL $0061; CALL $6C80; JP $0061): the callee at bank26:$6C80 runs
   with bank 26 mapped and returns A=$13, which $0847 maps back before RETurning
   into the stub with bank 19 mapped.  (A direct `CALL $0061` from switchable ROM
   would RET into the newly mapped bank — Astra's review, msg 8002.)  Bank 19 has
   no free run large enough for a second writer form; bank 26 is virgin.
2. bank26:$6C80 hosts BOTH writer forms, selected by FF01 bit 0 (odd = atomic
   publisher, see bank1:$42F0); each form ends `LD A,$13; RET`:
     atomic (buffer) form: DI; H := H - page + $D0 (page = FFC4 & $FC: at this
       point FFC4 holds the copy's final H, $9B/$9F = page+3, see bank1:$42ED, and
       the bank19 vector at $6CCE masks it the same way); SVBK=3; C x `LD A,E; LD (HL+),A`;
       SVBK=1; H := H + page - $D0 (callers reuse H); XOR A; RET.
       No CALL/PUSH between SVBK=3 and SVBK=1 (the native stack lives in WRAM1),
       IRQs are already off in the atomic tail and DI makes that explicit.
     pure (VRAM) form: the original 26 bytes before its RET (VBK=1, STAT mode-0
       wait, stores, VBK=C) followed by `LD A,$13; RET` (A was 0 before; the stub's
       XOR A restores A=0 for the callers).
3. bank1: the atomic tail runs the Stage-1 scanner BEFORE the wait+DMA service so
   the corrections land in the compiled $D000 buffer and the DMA carries them:
     $4324  3E 01 E0 70 3E 17 CD 47 08 C3 54 43  ->  3E 01 E0 70 CD F1 DB C3 C6 42 00 00
     $42C6  9 x 00 (dead: preceded by JP $13C0, entered only by jump)
                                              ->  3E 17 CD 47 08 C3 DF DB 00
   $4354..$4359 (CD F1 DB C3 DF DB) become unreachable and are left in place
   (RST $30 -> $435A is live code right behind them).

Pure/semantic publications (FF01 even) and every non-Stage-1 path are unchanged:
DBF1 still clears FF01 and returns for FFBA != 0, the VRAM writer form is
byte-identical, and the bank19 callers see the same HL/C/A contract.

Static proofs in this file: preimages, owned-byte set, an executed-bytes model of
both writer forms (stores land in $D0xx under SVBK 3 vs VRAM under VBK 1, H is
restored, C ends 0, A ends 0, no stack op inside the SVBK window), and bank/stack
restoration of the stub under BANKED instruction fetch (FF99/DC09 end at $13, SP
unchanged, writer entered with bank 26 mapped).
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BASE = ROOT / "tmp/cold-art-vblank-guard-r392-early-w4/candidate.gb"
BASE_SHA = "c8f21f0ed47b40b1372e1e2a73d6f526590e5dc4d1b2b2d00b9c1e916e59c5ff"
OUT = ROOT / "tmp/semantic-buffer-redirect-r393"

WRITER_BANK, WRITER_ADDR = 19, 0x6C8F
WRITER_OLD = bytes.fromhex("3E 01 E0 4F F0 41 E6 03 FE 03 20 F4 F0 41 E6 03 20 FA 7B 22 0D 20 FC 79 E0 4F C9")
NEW_BANK, NEW_ADDR = 26, 0x6C80      # reached ONLY through the fixed-bank $0847 dispatcher
RESTORE_BANK = 19                    # every writer RET returns this in A for $0847's JP $0061
TAIL_ADDR, TAIL_OLD = 0x4324, bytes.fromhex("3E 01 E0 70 3E 17 CD 47 08 C3 54 43")
TAIL_NEW = bytes.fromhex("3E 01 E0 70 CD F1 DB C3 C6 42 00 00")
CAVE_ADDR, CAVE_OLD = 0x42C6, bytes(9)
CAVE_NEW = bytes.fromhex("3E 17 CD 47 08 C3 DF DB 00")
CHECKSUMS = frozenset((0x014D, 0x014E, 0x014F))


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
    """Tiny label-resolving assembler for the handful of encodings used here."""

    def __init__(self, org: int) -> None:
        self.org, self.code, self.labels, self.fix = org, bytearray(), {}, []

    def label(self, name: str) -> None:
        self.labels[name] = self.org + len(self.code)

    def db(self, *b: int) -> None:
        self.code += bytes(b)

    def jr(self, op: int, name: str) -> None:
        self.fix.append((len(self.code) + 1, name)); self.db(op, 0)

    def finish(self) -> bytes:
        for pos, name in self.fix:
            d = self.labels[name] - (self.org + pos + 1)
            assert -128 <= d <= 127, (name, d)
            self.code[pos] = d & 0xFF
        return bytes(self.code)


def stub() -> bytes:
    # A `CALL $0061` from switchable ROM would RET into the newly mapped bank, so the
    # stub must not switch banks itself.  $0847 (fixed bank) does: CALL $0061 (map A);
    # CALL $6C80; JP $0061 (map the bank the callee returns in A) -> RET lands back
    # here with bank 19 mapped.
    a = Asm(WRITER_ADDR)
    a.db(0x3E, NEW_BANK, 0xCD, 0x47, 0x08)             # LD A,$1A; CALL $0847
    a.db(0xAF, 0xC9)                                    # XOR A; RET  (A=0 like the original)
    code = a.finish()
    assert len(code) <= len(WRITER_OLD)
    return code + bytes(len(WRITER_OLD) - len(code))


def writer() -> bytes:
    a = Asm(NEW_ADDR)
    a.db(0xF0, 0x01, 0x1F)                              # LDH A,(FF01); RRA
    a.jr(0x30, "vram")                                  # JR NC,vram   (even = pure owner)
    a.db(0xF3)                                          # DI
    # FFC4 holds the copy's FINAL H ($9B/$9F = page+3, see $42ED after the 768-byte copy);
    # AND $FC yields the page base exactly as the bank19 vector at $6CCE does.
    a.db(0xF0, 0xC4, 0xE6, 0xFC, 0x2F, 0x84, 0xC6, 0xD1, 0x67)   # LDH A,(FFC4); AND $FC; CPL; ADD A,H; ADD A,$D1; LD H,A
    a.db(0x3E, 0x03, 0xE0, 0x70)                        # SVBK=3
    a.label("loop")
    a.db(0x7B, 0x22, 0x0D)                              # LD A,E; LD (HL+),A; DEC C
    a.jr(0x20, "loop")
    a.db(0x3E, 0x01, 0xE0, 0x70)                        # SVBK=1
    a.db(0xF0, 0xC4, 0xE6, 0xFC, 0x84, 0xD6, 0xD0, 0x67)   # LDH A,(FFC4); AND $FC; ADD A,H; SUB $D0; LD H,A
    a.db(0x3E, RESTORE_BANK, 0xC9)                      # LD A,$13; RET   (bank for $0847's JP $0061)
    a.label("vram")
    a.db(*WRITER_OLD[:-1])                              # original minus its RET (relative JRs only)
    a.db(0x3E, RESTORE_BANK, 0xC9)                      # LD A,$13; RET
    return a.finish()


# ---------------------------------------------------------------- executed-bytes model
def run_writer(code: bytes, *, ff01: int, page: int, h: int, l: int, e: int, c: int) -> dict:
    """Execute the bank23 writer bytes with a small model.

    Tracks stores by domain (svbk/vbk), the SP-touching ops, and the register
    contract.  STAT is modelled as a rotating mode sequence so the VRAM form's
    two-poll wait terminates.
    """
    A = 0x5A; H, L, E, C = h, l, e, c
    Z = CY = False; ime = True; svbk = 1; vbk = 0
    pc = NEW_ADDR; stores = []; stack_ops_in_svbk3 = 0; stat_seq = [0, 2, 3, 0, 0, 3, 0]; si = 0
    for _ in range(5000):
        op = code[pc - NEW_ADDR]
        if op == 0xF0:
            reg = code[pc - NEW_ADDR + 1]
            if reg == 0x01: A = ff01
            elif reg == 0xC4: A = page + 3          # raw completed-map H ($9B/$9F), NOT the page base
            elif reg == 0x41: A = stat_seq[si % len(stat_seq)]; si += 1
            else: raise AssertionError(reg)
            pc += 2
        elif op == 0x1F: CY, A = bool(A & 1), (A >> 1) | (0x80 if CY else 0); pc += 1  # RRA (old carry in)
        elif op == 0x30:
            d = code[pc - NEW_ADDR + 1]; d = d - 256 if d > 127 else d
            pc = pc + 2 + (d if not CY else 0)
        elif op == 0x20:
            d = code[pc - NEW_ADDR + 1]; d = d - 256 if d > 127 else d
            pc = pc + 2 + (d if not Z else 0)
        elif op == 0xF3: ime = False; pc += 1
        elif op == 0x2F: A ^= 0xFF; pc += 1
        elif op == 0x84: A = (A + H) & 0xFF; pc += 1
        elif op == 0xC6: A = (A + code[pc - NEW_ADDR + 1]) & 0xFF; pc += 2
        elif op == 0xD6: A = (A - code[pc - NEW_ADDR + 1]) & 0xFF; pc += 2
        elif op == 0x67: H = A; pc += 1
        elif op == 0x3E: A = code[pc - NEW_ADDR + 1]; pc += 2
        elif op == 0xE0:
            reg = code[pc - NEW_ADDR + 1]
            if reg == 0x70: svbk = A
            elif reg == 0x4F: vbk = A
            else: raise AssertionError(reg)
            pc += 2
        elif op == 0x7B: A = E; pc += 1
        elif op == 0x79: A = C; pc += 1
        elif op == 0x22:
            stores.append(((H << 8) | L, A, svbk, vbk))
            L = (L + 1) & 0xFF; H = (H + (L == 0)) & 0xFF; pc += 1
        elif op == 0x0D: C = (C - 1) & 0xFF; Z = C == 0; pc += 1
        elif op == 0xE6: A &= code[pc - NEW_ADDR + 1]; Z = A == 0; pc += 2
        elif op == 0xFE: Z = A == code[pc - NEW_ADDR + 1]; CY = A < code[pc - NEW_ADDR + 1]; pc += 2
        elif op == 0xAF: A = 0; Z = True; pc += 1
        elif op == 0xC9:
            return {"A": A, "H": H, "L": L, "C": C, "stores": stores, "ime": ime, "svbk": svbk, "vbk": vbk,
                    "stack_ops_in_svbk3": stack_ops_in_svbk3}
        elif op in (0xC5, 0xD5, 0xE5, 0xF5, 0xC1, 0xD1, 0xE1, 0xF1, 0xCD):
            if svbk == 3: stack_ops_in_svbk3 += 1
            raise AssertionError(f"stack op {op:02X} in writer")
        else:
            raise AssertionError(f"unmodelled opcode {op:02X} at ${pc:04X}")
    raise AssertionError("writer did not terminate")


def static_checks(code: bytes) -> dict:
    results = {"cases": 0}
    for page in (0x98, 0x9C):
        for row in range(24):
            for col, count in ((0x0B, 2), (0x4A, 1), (0x10, 1), (0x0D, 4), (0x1F, 3)):
                h, l = page + (row * 32 + col) // 256, (row * 32 + col) % 256
                h_end = (h + (1 if l + count > 0xFF else 0)) & 0xFF   # original also carries into H
                # atomic owner: FF01 odd -> buffer form
                res = run_writer(code, ff01=page | 1, page=page, h=h, l=l, e=0x26, c=count)
                exp = [(0xD000 + row * 32 + col + i, 0x26, 3, 0) for i in range(count)]
                assert [(s[0], s[1], s[2], s[3]) for s in res["stores"]] == exp, (page, row, col, res["stores"], exp)
                assert res["H"] == h_end and res["L"] == (l + count) & 0xFF, "H not restored / L contract"
                assert res["C"] == 0 and res["A"] == RESTORE_BANK and res["svbk"] == 1 and res["ime"] is False
                assert res["stack_ops_in_svbk3"] == 0
                # pure owner: FF01 even -> VRAM form, byte-identical behaviour
                res = run_writer(code, ff01=page, page=page, h=h, l=l, e=0x26, c=count)
                exp = [(((h << 8) | l) + i, 0x26, 1, 1) for i in range(count)]
                assert [(s[0], s[1], s[2], s[3]) for s in res["stores"]] == exp, (res["stores"], exp)
                assert res["H"] == h_end and res["C"] == 0 and res["A"] == RESTORE_BANK and res["vbk"] == 0 and res["ime"] is True
                results["cases"] += 2
    results["buffer_form"] = ("stores at $D000+row*32+col under SVBK 3 with FFC4 modelled as page+3 ($9B/$9F), "
                              "H restored, C=0, A=0, IME off, no stack ops")
    results["vram_form"] = "original 27 bytes, stores under VBK 1, VBK restored to 0, C=0, A=0"
    return results


def stub_checks(code: bytes, writer_code: bytes) -> dict:
    """Model the stub WITH banked instruction fetch.

    Memory image: fixed bank 0 holds $0061/$09BE/$0847; the switchable window
    $4000-$7FFF fetches from `bank`.  Bank 19 holds the stub at $6C8F, bank 26 the
    writer at $6C80.  Any fetch from an address not defined for the current bank is
    an error (that is exactly the fault Astra found in the CALL $0061 form).
    """
    fixed = {0x0061: bytes.fromhex("EA 09 DC C3 BE 09"), 0x09BE: bytes.fromhex("E0 99 EA 00 21 C9"),
             0x0847: bytes.fromhex("CD 61 00 CD 80 6C C3 61 00")}
    banked = {WRITER_BANK: {WRITER_ADDR: code}, NEW_BANK: {NEW_ADDR: writer_code}}

    def fetch(bank: int, pc: int) -> int:
        for base, blob in fixed.items():
            if base <= pc < base + len(blob):
                return blob[pc - base]
        for base, blob in banked.get(bank, {}).items():
            if base <= pc < base + len(blob):
                return blob[pc - base]
        raise AssertionError(f"fetch from ${pc:04X} with bank {bank} mapped: no code there")

    bank, ff99, dc09, A, sp, pc = WRITER_BANK, WRITER_BANK, WRITER_BANK, 0x5A, 0xDFF0, WRITER_ADDR
    stack: list[int] = []; writer_entered_with = None
    for _ in range(200):
        op = fetch(bank, pc)
        if op == 0x3E: A = fetch(bank, pc + 1); pc += 2
        elif op == 0xCD:
            t = fetch(bank, pc + 1) | (fetch(bank, pc + 2) << 8); stack.append(pc + 3); sp -= 2
            if t == NEW_ADDR: writer_entered_with = bank
            pc = t
        elif op == 0xC3: pc = fetch(bank, pc + 1) | (fetch(bank, pc + 2) << 8)
        elif op == 0xEA:
            addr = fetch(bank, pc + 1) | (fetch(bank, pc + 2) << 8)
            if addr == 0xDC09: dc09 = A
            elif addr == 0x2100: bank = A
            pc += 3
        elif op == 0xE0: assert fetch(bank, pc + 1) == 0x99; ff99 = A; pc += 2
        elif op == 0xC9:
            if pc >= NEW_ADDR and bank == NEW_BANK and pc < NEW_ADDR + len(writer_code):
                A = RESTORE_BANK        # writer body is proven separately; only its return contract matters here
            if not stack:
                break
            pc = stack.pop(); sp += 2
        elif op == 0xAF: A = 0; pc += 1
        elif pc >= NEW_ADDR and bank == NEW_BANK:
            # inside the writer: skip its body to the modelled RET contract
            pc = NEW_ADDR + len(writer_code) - 1; A = RESTORE_BANK; continue
        else:
            raise AssertionError(f"unmodelled {op:02X} at ${pc:04X} bank {bank}")
    assert writer_entered_with == NEW_BANK, "writer not entered with bank 26 mapped"
    assert bank == ff99 == dc09 == WRITER_BANK and A == 0 and sp == 0xDFF0 and not stack
    return {"bank_on_writer_call": NEW_BANK, "bank_on_return": bank, "ff99_dc09_on_return": ff99,
            "A_on_return": A, "sp_delta": 0, "dispatcher": "$0847 fixed-bank far call"}


def build(source: bytes) -> tuple[bytes, dict]:
    assert hashlib.sha256(source).hexdigest() == BASE_SHA, "wrong exact r392 early-w4 base"
    w = off(WRITER_BANK, WRITER_ADDR)
    assert source[w:w + len(WRITER_OLD)] == WRITER_OLD, "semantic writer preimage changed"
    assert source[w + len(WRITER_OLD):w + len(WRITER_OLD) + 4] == bytes.fromhex("21 5B DF 34"), "$6CAA blob moved"
    n = off(NEW_BANK, NEW_ADDR)
    assert set(source[NEW_BANK * 0x4000:(NEW_BANK + 1) * 0x4000]) == {0xFF}, f"bank {NEW_BANK} not virgin"
    assert source[TAIL_ADDR:TAIL_ADDR + 12] == TAIL_OLD, "atomic tail preimage changed"
    assert source[CAVE_ADDR:CAVE_ADDR + 9] == CAVE_OLD and source[CAVE_ADDR - 3:CAVE_ADDR] == bytes.fromhex("C3 C0 13"), \
        "$42C6 cave not free / not fenced by JP $13C0"
    assert source[0x42CF] == 0x1A, "copy loop entry at $42CF moved"
    assert source[0x42ED:0x42F5] == bytes.fromhex("7C E0 C4 F0 01 1F 38 07"), "FFC4 page store / FF01 owner test changed"
    assert source[0x4354:0x435A] == bytes.fromhex("CD F1 DB C3 DF DB"), "old scanner tail changed"
    assert source[0x0847:0x0850] == bytes.fromhex("CD 61 00 CD 80 6C C3 61 00"), "$0847 trampoline changed"
    assert source[0x0061:0x0067] == bytes.fromhex("EA 09 DC C3 BE 09"), "$0061 mapper changed"
    # every caller of the writer must be in bank 19 (the stub restores bank 19)
    callers = [i for i in range(len(source) - 2) if source[i] in (0xCD, 0xC3) and source[i + 1] == 0x8F and source[i + 2] == 0x6C]
    assert all(i // 0x4000 == WRITER_BANK for i in callers), [hex(i) for i in callers]

    new_stub, new_writer = stub(), writer()
    assert new_writer.endswith(WRITER_OLD[:-1] + bytes((0x3E, RESTORE_BANK, 0xC9)))
    checks = {"writer": static_checks(new_writer), "stub": stub_checks(new_stub[:7], new_writer),
              "writer_callers_bank19": [hex((i % 0x4000) + 0x4000) for i in callers]}

    rom = bytearray(source)
    rom[w:w + len(new_stub)] = new_stub
    rom[n:n + len(new_writer)] = new_writer
    rom[TAIL_ADDR:TAIL_ADDR + 12] = TAIL_NEW
    rom[CAVE_ADDR:CAVE_ADDR + 9] = CAVE_NEW
    update_checksums(rom)
    owned = set(range(w, w + len(new_stub))) | set(range(n, n + len(new_writer))) \
        | set(range(TAIL_ADDR, TAIL_ADDR + 12)) | set(range(CAVE_ADDR, CAVE_ADDR + 9))
    changed = {i for i, (x, y) in enumerate(zip(source, rom)) if x != y}
    assert changed <= owned | CHECKSUMS, sorted(changed - owned - CHECKSUMS)[:8]
    receipt = {
        "schema": "penta-semantic-buffer-redirect-r393-build-v1",
        "experimental": True, "promotable": False, "live_tested": False,
        "base_sha256": BASE_SHA, "candidate_sha256": hashlib.sha256(rom).hexdigest(),
        "changed_offsets": sorted(changed),
        "patch": {
            "bank19_writer_stub": f"bank19:${WRITER_ADDR:04X} {new_stub[:7].hex()} (+20 NOP pad) via $0847",
            "bank26_writer": f"bank{NEW_BANK}:${NEW_ADDR:04X} {new_writer.hex()}",
            "bank1_tail": f"${TAIL_ADDR:04X} {TAIL_NEW.hex()}",
            "bank1_cave": f"${CAVE_ADDR:04X} {CAVE_NEW.hex()}",
            "order": "copy -> compile -> scanner (buffer) -> wait+DMA (unchanged service) -> $DBDF",
            "unreachable_left_in_place": "$4354..$4359",
        },
        "static_checks": checks,
        "abi": "writer: HL page-relative in/out (H restored), E attr, C->0, A->0; pure owner path byte-identical; "
               "stub maps 23 then restores 19 (FF99/DC09), SP unchanged; scanner runs with IME=0 in atomic tail",
        "cost_note": "one $0847 far call per writer call (~60 M-cycles x ~664 calls/north route ~0.6 frame); "
                     "the scanner now overlaps the VBlank wait, so net route time should not grow",
    }
    return bytes(rom), receipt


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--base", type=Path, default=BASE)
    ap.add_argument("--out-dir", type=Path, default=OUT)
    args = ap.parse_args()
    rom, receipt = build(args.base.read_bytes())
    args.out_dir.mkdir(parents=True, exist_ok=True)
    target = args.out_dir / "candidate.gb"
    if target.exists() and target.read_bytes() != rom:
        raise SystemExit("candidate collision")
    target.write_bytes(rom)
    (args.out_dir / "build-receipt.json").write_text(json.dumps(receipt, indent=2) + "\n")
    print(json.dumps({"candidate_sha256": receipt["candidate_sha256"], "changed_bytes": len(receipt["changed_offsets"]),
                      "writer_cases": receipt["static_checks"]["writer"]["cases"], "stub": receipt["static_checks"]["stub"]}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
