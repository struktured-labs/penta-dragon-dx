#!/usr/bin/env python3
"""r443 (experiment): later-stage deferred attribute DMA, on exact r442.

Stage 1 is byte-identical to r442.  For FFBA != 0 the atomic tail currently
compiles the attribute buffer and then busy-waits for VBlank inside the bank23
service before a 48-block GDMA (~0.29 f average per copy).  Later stages have no
post-DMA semantic scanner (DBF1 only clears FF01 there), so the DMA can run inside
the VBlank ISR commit and the flip can follow in the same pass: no added latency,
no main-loop hook, no scan continuation.

Latch (FFC4 bits 6:5): 00 IDLE, 01 DMA_PENDING, 10 READY (legacy $C0 format).
  packer (bank24 $6E00): backpressure on any non-idle state; FFC4 bit0 set
      (marked by the bank23 prefix) -> 01; everything else -> 10 (Stage 1 unchanged).
  bank23 $6C80: prefixed `FFBA==0 -> body; LCDC.7==0 -> body; else FFC4 |= 1; LD A,1; RET`
      (later-stage LCD-on copies skip the synchronous wait+DMA; Stage 1 and LCD-off
      publications keep it -- an LCD-off publish flips immediately at $12E6 and never
      reaches the packer, so it must DMA synchronously).
  r443 (7a3766bd) defect: its packer tested FF01, but $DBF1 zeroes FF01 for FFBA!=0
      before the packer runs, so it always emitted READY and the attribute plane stayed
      zero (Stage 3 soak: attr.bin all-zero vs populated shadow).  r443b fixes that.
  r443c -> r443d: marker moved from "set bit0" to "clear bit3" (bit0 of the raw
      end-of-copy H $9B/$9F is always 1, so r443c latched DMA for pure copies too).
  r443b -> r443c: the guard re-enables interrupts (EI) after its flush; the transcribed
      wait body ends IME=0 because its original home is the RETI-terminated atomic tail,
      but the guard falls into the source clone, which the game runs with IME=1.
  ISR: bank13 $746D `LDH A,(FFC4); AND $40; JP $7400` -> `LD A,$19; CALL $0847;
      JR $7485` ; $7485 = `JP $7400`; bank25:$6C80 = LY 144..147 gate; 01 -> GDMA
      (SVBK 3, VBK 1, no push, dest page from latch bit4) then Z=0 (commit: the
      existing $7407.. path flips and clears); 10 -> Z=0; else Z=1; returns A=$0D.
  Guard (backpressure) before source generation: the later-stage source path is
      bank24 $7000 -> JP $7089 -> JP $7380 -> (FFBA==4 ? $7800 : $7300).  $7089 is
      retargeted to a guard in bank24 free space: if state == 01, run the synchronous
      wait+DMA of the OLD page (latch bit4) and set READY, then JP $7380 (so Stage 5's
      private source handler is covered too).
      HL/DE preserved (clone ABI), BC/AF preserved by the wait body.
No WRAM, no bank-0 bytes, banks 26-28 untouched, bank 25 used for the ISR service
(a title-composed variant will merge the two bank-25 services later).
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).resolve().parent))
from build_deferred_dma_pipeline_r397 import Asm, sync_wait_dma, IDLE, DMA_PENDING, READY  # noqa: E402

BASE = ROOT / "tmp/stage1-subscene-tracking-r442/candidate.gb"
BASE_SHA = "ea53ebb1f8cef8480b6ad3b4472b74f11bab6b0ea9f03660ea8e5ca7bcde1a46"
OUT = ROOT / "tmp/later-stage-deferred-dma-r443d"
PRETEST_CAVE = 0x76EE          # bank13: 21 bytes inside the zero cave after RET $76D5 (title uses $76D7..$76ED)
CHECKSUMS = frozenset((0x014D, 0x014E, 0x014F))
ISR_BANK, SVC = 25, 0x6C80
GUARD_BANK, GUARD_ADDR = 24, 0x7500          # inside the 814-byte FF run at $74D2
SYNC_BANK = 23
PACKER_OLD = bytes.fromhex("F0 C4 CB 77 C0 FA 00 DC EA 5C DF F0 C4 B7 28 06 E6 04 07 07 F6 80 F6 40 47 FA 02 DC E6 0F B0 E0 C4 C9")
# Stage 1 (FFBA==0) and LCD-off publications fall through to the synchronous body.
# Later-stage LCD-on: CLEAR FFC4 bit3 = "atomic, DMA still owed" and return.  The raw
# FFC4 at packer time is the END-of-copy H ($9B/$9F, r383 docs; $98/$9C for short
# copies), so bit0/bit1 are NOT free (r443b/c marked bit0 -> every pure later-stage
# copy was mis-latched as DMA_PENDING and a stale 24-row buffer was DMA'd: Stage 5/7
# raw audits).  Bit3 is 1 for every legal raw H ($98..$9F); the ISR tests bits 6:5
# only, the packer uses bit2 + the zero test, and the only raw-H reader of bit3 is the
# bank23 body (`AND $FC`), which the marked path skips.  The marker survives $DBF1.
SYNC_PREFIX = bytes.fromhex("F0 BA B7 28 0F F0 40 CB 7F 28 09 F0 C4 E6 F7 E0 C4 3E 01 C9")
FALLBACK_ENTRY = 0x7089          # bank24: every non-Stage-1 source path passes `JP $7380` here
FALLBACK_TARGET = 0x7380         # ... which routes FFBA==4 to $7800 (Stage 5 private) else $7300


def off(bank: int, addr: int) -> int:
    return bank * 0x4000 + addr - 0x4000


def update_checksums(rom: bytearray) -> None:
    h = 0
    for v in rom[0x134:0x14D]:
        h = (h - v - 1) & 0xFF
    rom[0x14D] = h
    g = (sum(rom[:0x14E]) + sum(rom[0x150:])) & 0xFFFF
    rom[0x14E:0x150] = g.to_bytes(2, "big")


def packer() -> bytes:
    a = Asm(0x6E00)
    a.db(0xF0, 0xC4, 0xE6, 0x60, 0xC0)                            # any non-idle -> drop request
    a.db(0xFA, 0x00, 0xDC, 0xEA, 0x5C, 0xDF)                      # DF5C := SCX
    a.db(0xF0, 0xC4, 0xB7); a.jr(0x28, "rel")                     # raw 0 = relative request
    a.db(0xE6, 0x04, 0x07, 0x07, 0xF6, 0x80, 0x47)                # B := abs|page (raw H bit2 -> bit4)
    a.db(0xF0, 0xC4, 0xCB, 0x5F, 0x3E, READY); a.jr(0x20, "pack") # raw H bit3 still set -> READY (pure / Stage 1 / LCD-off)
    a.db(0x3E, DMA_PENDING); a.jr(0x18, "pack")                   # bank23 prefix cleared bit3 -> later-stage atomic, DMA owed
    a.label("rel")
    a.db(0x47, 0x3E, READY)                                       # B := 0 (A==0); relative requests are always READY
    a.label("pack")
    a.db(0xB0, 0x47, 0xFA, 0x02, 0xDC, 0xE6, 0x0F, 0xB0, 0xE0, 0xC4, 0xC9)
    return a.finish()


def isr_service() -> bytes:
    a = Asm(SVC)
    a.db(0xF0, 0x44, 0xE6, 0xFC, 0xFE, 0x90); a.jr(0x20, "skip")  # LY 144..147 only
    a.db(0xF0, 0xC4, 0xE6, 0x60); a.jr(0x28, "skip")              # idle
    a.db(0xFE, READY); a.jr(0x28, "commit")
    a.db(0xFE, DMA_PENDING); a.jr(0x20, "skip")
    a.db(0xF0, 0x4F, 0x4F)                                        # C := VBK
    a.db(0x3E, 0x03, 0xE0, 0x70)                                  # SVBK=3 (no push until restored)
    a.db(0x3E, 0xD0, 0xE0, 0x51, 0xAF, 0xE0, 0x52)                # src $D000
    a.db(0xF0, 0xC4, 0xE6, 0x10, 0x0F, 0x0F, 0xF6, 0x18, 0xE0, 0x53, 0xAF, 0xE0, 0x54)  # dest $18/$1C page
    a.db(0x3E, 0x01, 0xE0, 0x4F, 0x3E, 0x2F, 0xE0, 0x55)          # VBK=1; GDMA 48 blocks (CPU halted)
    a.db(0x79, 0xE0, 0x4F, 0x3E, 0x01, 0xE0, 0x70)                # VBK restore; SVBK=1
    a.label("commit")
    a.db(0xAF, 0x3C, 0x3E, 0x0D, 0xC9)                            # Z=0 -> $7400 falls into the commit path
    a.label("skip")
    a.db(0xAF, 0x3E, 0x0D, 0xC9)                                  # Z=1 -> JP Z,$6F1D
    return a.finish()


def guard() -> bytes:
    a = Asm(GUARD_ADDR)
    a.db(0xE5, 0xD5)                                              # PUSH HL; PUSH DE (clone ABI)
    a.db(0xF0, 0xC4, 0xE6, 0x60, 0xFE, DMA_PENDING); a.jr(0x20, "done")
    sync_wait_dma(a, dest_from_latch=True)                        # old page now (ends IME=0)
    a.db(0xF0, 0xC4, 0xE6, 0x9F, 0xF6, READY, 0xE0, 0xC4)         # 01 -> 10: flip at the next commit
    a.db(0xFB)                                                    # EI: the wait body exits IME=0 (it was written for the
                                                                  # RETI-terminated atomic tail); the source clone that follows
                                                                  # runs with IME=1 (IE masked to Timer by $1399) -- r443c
    a.label("done")
    a.db(0xD1, 0xE1, 0xC3, FALLBACK_TARGET & 0xFF, FALLBACK_TARGET >> 8)   # POP DE; POP HL; JP $7380
    return a.finish()


def latch_model() -> dict:
    def packer_(s, atomic, ffba, lcd_on=True, raw_h=0x9B):
        if s != IDLE: return s, "dropped"
        if raw_h == 0: return READY, "latched"       # relative request
        assert raw_h & 0x08, "every legal raw H has bit3 set"
        marked = atomic and ffba and lcd_on          # bank23 prefix clears bit3 of raw H
        raw = raw_h & (0xF7 if marked else 0xFF)
        return ((DMA_PENDING if not (raw & 0x08) else READY), "latched")

    def isr(s, ly=145):
        if not 144 <= ly <= 147: return s, "gate-skip"
        if s == DMA_PENDING: return IDLE, "dma+flip"
        if s == READY: return IDLE, "flip"
        return s, "skip"

    def guard_(s):
        return (READY, "flush") if s == DMA_PENDING else (s, "none")

    c = {}
    s, e = packer_(IDLE, True, 2); s, e1 = isr(s); assert (e, e1, s) == ("latched", "dma+flip", IDLE)
    c["later_stage_atomic"] = "latched -> dma+flip in one VBlank"
    s, e = packer_(IDLE, True, 0); s, e1 = isr(s); assert (e, e1, s) == ("latched", "flip", IDLE)
    c["stage1_atomic_unchanged"] = True
    s, e = packer_(IDLE, False, 2); s, e1 = isr(s); assert (e, e1, s) == ("latched", "flip", IDLE)
    c["pure_unchanged"] = True
    s, _ = packer_(IDLE, True, 2); s, e = guard_(s); assert (e, s) == ("flush", READY)
    s, e2 = packer_(s, True, 2); assert e2 == "dropped"; s, e3 = isr(s); assert (e3, s) == ("flip", IDLE)
    c["double_publication_flush_then_drop_then_flip"] = True
    assert isr(DMA_PENDING, ly=60) == (DMA_PENDING, "gate-skip")
    c["ly_gate"] = True
    assert packer_(IDLE, True, 2, lcd_on=False) == (READY, "latched")
    c["lcd_off_publish_syncs_in_bank23"] = True
    for h in (0x98, 0x9B, 0x9C, 0x9F):
        assert packer_(IDLE, False, 6, raw_h=h) == (READY, "latched"), hex(h)    # pure later-stage copy never DMAs
        assert packer_(IDLE, True, 6, raw_h=h) == (DMA_PENDING, "latched"), hex(h)
    c["pure_copy_raw_h_9B_9F_never_marked"] = True
    assert packer_(IDLE, False, 6, raw_h=0) == (READY, "latched")
    c["relative_request_ready"] = True
    return c


def isr_pretest() -> bytes:
    """bank13 pre-test so idle VBlanks never pay the $0847 round trip (~80 cycles):
    scene $01 -> always far-call (title repaint lives in the bank25 service);
    FFC4 state idle -> JP $6F1D (Z set, same as the service's Z path);
    else far-call and continue at $7485 (JP $7400) exactly as before."""
    blob = bytes.fromhex("FA 80 D8 3D 28 07" "F0 C4 E6 60 CA 1D 6F" "3E 19 CD 47 08 C3 85 74")
    # JR Z at offset 4 must land on the `LD A,$19` call label at offset 13 (r443f v1 had
    # `28 06` -> the $6F operand of JP Z,$6F1D, i.e. a stray LD L,A on scene $01; Astra caught it)
    assert 6 + blob[5] == 13 and blob[13] == 0x3E, "pretest JR misaligned"
    return blob


def build(source: bytes, *, isr_pretest_on: bool = False) -> tuple[bytes, dict]:
    assert hashlib.sha256(source).hexdigest() == BASE_SHA, "wrong exact r442 base"
    assert set(source[ISR_BANK * 0x4000:(ISR_BANK + 1) * 0x4000]) == {0xFF}, "bank 25 not virgin"
    g = off(GUARD_BANK, GUARD_ADDR)
    assert set(source[g:g + 0x100]) == {0xFF}, "bank24 guard area not free"
    assert source[off(GUARD_BANK, FALLBACK_ENTRY):off(GUARD_BANK, FALLBACK_ENTRY) + 3] == bytes.fromhex("C3 80 73"), "fallback entry $7089"
    assert source[off(GUARD_BANK, FALLBACK_TARGET):off(GUARD_BANK, FALLBACK_TARGET) + 10] == bytes.fromhex("F0 BA FE 04 CA 00 78 C3 00 73"), "fallback router $7380"
    assert source[off(GUARD_BANK, 0x7000):off(GUARD_BANK, 0x7011)] == bytes.fromhex("F0 B7 FE 02 00 C2 89 70 F0 BA B7 C2 89 70 C3 0E 74"), "$7000 entry predicate"
    assert source[off(24, 0x6E00):off(24, 0x6E00) + len(PACKER_OLD)] == PACKER_OLD, "packer preimage"
    sync_off = off(SYNC_BANK, SVC)
    sync_len = max(i for i in range(0x100) if source[sync_off + i] != 0xFF) + 1
    sync_old = source[sync_off:sync_off + sync_len]
    assert sync_old[:4] == bytes.fromhex("C5 F0 FF F5") and sync_old[-1] == 0xC9, "bank23 service preimage"
    assert b"\xc3" not in sync_old and b"\xcd" not in sync_old, "bank23 service has absolute refs; cannot shift"
    assert set(source[sync_off + sync_len:sync_off + sync_len + len(SYNC_PREFIX)]) == {0xFF}
    assert source[off(13, 0x746D):off(13, 0x7474)] == bytes.fromhex("F0 C4 E6 40 C3 00 74"), "ISR gate preimage"
    assert source[off(13, 0x7485):off(13, 0x7488)] == bytes(3), "$7485 slack not free"
    assert source[off(13, 0x7400):off(13, 0x7403)] == bytes.fromhex("CA 1D 6F")
    assert source[0x0847:0x0850] == bytes.fromhex("CD 61 00 CD 80 6C C3 61 00")
    assert source[0x42ED:0x42FB] == bytes.fromhex("7C E0 C4 F0 01 1F 38 07 CD F1 DB 00 FB C9"), "atomic/pure split changed"
    assert source[0x4324:0x4330] == bytes.fromhex("3E 01 E0 70 3E 17 CD 47 08 C3 54 43"), "atomic tail changed"

    images = {"packer": packer(), "isr": isr_service(), "guard": guard()}
    assert len(images["packer"]) <= len(PACKER_OLD) + 0x10
    checks = {"latch_model": latch_model()}
    rom = bytearray(source); owned = set()

    def put(bank, addr, data):
        o = off(bank, addr) if bank else addr
        rom[o:o + len(data)] = data; owned.update(range(o, o + len(data)))

    pad = len(PACKER_OLD) - len(images["packer"])
    put(24, 0x6E00, images["packer"] + (bytes([0xFF]) * pad if pad > 0 else b""))
    put(SYNC_BANK, SVC, SYNC_PREFIX + sync_old)
    if isr_pretest_on:
        pre = isr_pretest(); assert len(pre) == 21
        assert source[off(13, 0x76D5)] == 0xC9 and set(source[off(13, PRETEST_CAVE):off(13, PRETEST_CAVE) + len(pre)]) == {0}, "pretest cave not free"
        assert source[off(13, 0x6F1D):off(13, 0x6F20)] == bytes.fromhex("C5 D5 E5"), "prelude entry $6F1D changed"
        put(13, 0x746D, bytes((0xC3, PRETEST_CAVE & 0xFF, PRETEST_CAVE >> 8, 0, 0, 0, 0)))
        put(13, PRETEST_CAVE, pre)
    else:
        put(13, 0x746D, bytes.fromhex("3E 19 CD 47 08 18 11"))   # JR from $7474 +$11 -> $7485
    assert 0x7472 + 2 + 0x11 == 0x7485
    put(13, 0x7485, bytes.fromhex("C3 00 74"))
    put(ISR_BANK, SVC, images["isr"])
    put(GUARD_BANK, GUARD_ADDR, images["guard"])
    put(GUARD_BANK, FALLBACK_ENTRY, bytes((0xC3, GUARD_ADDR & 0xFF, GUARD_ADDR >> 8)))
    update_checksums(rom)
    changed = {i for i, (x, y) in enumerate(zip(source, rom)) if x != y}
    assert changed <= owned | CHECKSUMS, sorted(changed - owned - CHECKSUMS)[:8]
    receipt = {
        "schema": "penta-later-stage-deferred-dma-r443f-build-v1" if isr_pretest_on else "penta-later-stage-deferred-dma-r443d-build-v1",
        "isr_pretest": (f"bank13:$746D JP ${PRETEST_CAVE:04X}: scene $01 or FFC4 state != idle -> far-call; else JP $6F1D" if isr_pretest_on else None),
        "experimental": True, "promotable": False, "live_tested": False,
        "base_sha256": BASE_SHA, "candidate_sha256": hashlib.sha256(rom).hexdigest(),
        "changed_offsets": sorted(changed),
        "images": {k: v.hex() for k, v in images.items()},
        "stage1_unchanged": "packer emits READY for FFBA==0; bank23 prefix falls through for FFBA==0; "
                            "atomic tail/scan bytes untouched",
        "harness_note": "later-stage atomic publications no longer execute the bank23 wait/GDMA; their DMA "
                        "site is bank25:$6C80 (from ISR $746D); flush site bank24:$7500 (fallback path)",
        "static_checks": checks,
    }
    return bytes(rom), receipt


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--base", type=Path, default=BASE)
    ap.add_argument("--out-dir", type=Path, default=OUT)
    ap.add_argument("--isr-pretest", action="store_true", help="r443f: bank13 idle pre-test before the $0847 ISR far-call")
    args = ap.parse_args()
    rom, receipt = build(args.base.read_bytes(), isr_pretest_on=args.isr_pretest)
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
