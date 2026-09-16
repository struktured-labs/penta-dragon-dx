#!/usr/bin/env python3
"""r392: VBlank-guard the cold hazard-art GDMA chain (on exact r391).

Root cause (2026-09-06, static + Astra's writer trace): the cold hazard-art
installer (bank13:$6A0E admission -> bank19:$6CAA -> $6BEE -> bank7:$6BFF ->
$65FF -> $6940) performs three general-purpose DMAs (64+96+96 bytes) from the
main-loop publication tail with no display-timing guard.  GDMA during mode 3
is discarded by hardware and mGBA, so whenever the loop phase lands the chain
in active display the art keeps its cleared bytes (20 zero bytes in tiles
$64/$78/$79 on r391).

Patch (bank 13 only, 30 bytes changed + checksums):
  $6A15  14 -> E1   (DF5B-done `JR Z` now targets the RET at $69F7; $6A2A is code now)
  $6A21  01 AA 6C C5 3E 13 C3 61 00 C9 00 00   ->  C3 74 74 | 01 AA 6C C5 3E 13 C3 61 00
         (tail relocated by 3 bytes into the dead RET and the two NOPs behind it;
          the RET at $6A2A was unreachable: $0061's RET returns to bank19:$6CAA)
  $7474  guard, 17 bytes in the free slack behind the r389 prelude patch:
    defer variant (default, Astra's spec):
        LDH A,(FF44); SUB $90; CP 6; JP C,$6A24      ; LY 144..149 -> admit
        LDH A,(FF40); BIT 7,A; RET NZ                ; LCD on -> defer (NZ, DF5B untouched)
        JP $6A24                                     ; LCD off -> admit
    wait variant (--wait): LCD off -> admit; else spin until LY 144..149, admit.
Both variants clobber only A, like the original admission, and return with NZ
on defer exactly as the existing `CALL NZ,$5D25; RET NZ` rejection does.

Window LY 144..149 leaves >= 4 lines for a Timer ISR (~1-2 lines) plus the
~2-line chain before line 0's mode 3.  The defer variant can starve when the
main loop phase is periodic (static room) - use --wait if the art stays absent.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BASE = ROOT / "tmp/source-timer-mask-r391/candidate.gb"
BASE_SHA = "4c0d927985893cd31480301376c465f97ea84157299cb783689cbe82d774dd13"
OUT = ROOT / "tmp/cold-art-vblank-guard-r392"
BANK = 13
ADMIT_TAIL_ADDR = 0x6A21
ADMIT_TAIL_OLD = bytes.fromhex("01 AA 6C C5 3E 13 C3 61 00 C9 00 00")
ADMIT_TAIL_NEW = bytes.fromhex("C3 74 74 01 AA 6C C5 3E 13 C3 61 00")
RELOCATED_TAIL = 0x6A24
GUARD_ADDR = 0x7474
GUARD_SLACK = 20
LY_WINDOW = 6          # default: LY 144 .. 149 admitted (tested candidate 973fa77a...)
TAIL_LO, TAIL_HI = RELOCATED_TAIL & 0xFF, RELOCATED_TAIL >> 8


def guard_defer(window: int) -> bytes:
    return bytes((
        0xF0, 0x44,                 # LDH A,($FF44)
        0xD6, 0x90,                 # SUB $90
        0xFE, window,               # CP window
        0xDA, TAIL_LO, TAIL_HI,     # JP C,tail   (LY in window)
        0xF0, 0x40,                 # LDH A,($FF40)
        0xCB, 0x7F,                 # BIT 7,A
        0xC0,                       # RET NZ   (LCD on: defer)
        0xC3, TAIL_LO, TAIL_HI,     # JP tail (LCD off)
    ))


def guard_protected(window: int, nop_control: bool = False) -> bytes:
    """Defer variant that executes DI on the admit path (negative control).

    The hook already runs with IME=0 (the $06D1 VBlank ISR never executes EI
    before CALL $0824), so the DI cannot change behaviour.  CAVEAT (Astra,
    msg 7988): this layout (JR NC not taken + DI + JP) costs 7 M-cycles on the
    admit path where the plain defer variant's JP C costs 4, so a live timing
    difference against the plain variant proves nothing.  Compare against the
    cycle-equal control (`--eq-control`: identical bytes with NOP in place of
    DI) or against IRQ breakpoint observations; only a difference between the
    protected build and its cycle-equal control isolates the DI.  The outer
    RETI restores IME as before.
    """
    return bytes((
        0xF0, 0x44,                 # LDH A,($FF44)
        0xD6, 0x90,                 # SUB $90
        0xFE, window,               # CP window
        0x30, 0x04,                 # JR NC,+4 -> lcd check
        0x00 if nop_control else 0xF3,   # DI (admit path only) / NOP in the cycle-equal control
        0xC3, TAIL_LO, TAIL_HI,     # JP tail
        0xF0, 0x40,                 # LDH A,($FF40)
        0xCB, 0x7F,                 # BIT 7,A
        0xC0,                       # RET NZ   (LCD on: defer)
        0xC3, TAIL_LO, TAIL_HI,     # JP tail (LCD off)
    ))


def guard_wait(window: int) -> bytes:
    return bytes((
        0xF0, 0x40,                 # LDH A,($FF40)
        0xCB, 0x7F,                 # BIT 7,A
        0x28, 0x08,                 # JR Z,+8 -> JP tail (LCD off)
        0xF0, 0x44,                 # loop: LDH A,($FF44)
        0xD6, 0x90,                 # SUB $90
        0xFE, window,               # CP window
        0x30, 0xF8,                 # JR NC,loop
        0xC3, TAIL_LO, TAIL_HI,     # JP tail
    ))
CHECKSUMS = frozenset((0x014D, 0x014E, 0x014F))

# --early: run the admission at the HEAD of the VBlank prelude (LY ~144) instead of
# at its tail ($6F89), where the prelude has often already overrun into the next
# frame (Astra's r391 trace: LY 2..24) and a defer guard starves (r392 w4: 214 art
# bytes missing).  The JR sled $6ED3-$6EF3 (12x JR+0 then 9 zeros) is reached only
# from $6EC4's `JR $6ED3`; retargeting that JR to $6EF4 makes the sled dead space.
EARLY_JR_ADDR = 0x6EC4                      # 18 0D  -> 18 2E   (JR $6ED3 -> JR $6EF4)
EARLY_SLED_ADDR = 0x6ED3
EARLY_SLED_OLD = bytes.fromhex("18 00" * 12 + "00" * 9)
EARLY_HEAD_CALL = 0x6F20                    # CD 00 71 -> CD D3 6E
EARLY_TAIL_CALL = 0x6F85                    # FA FD DC B7 C4 0E 6A -> 7x NOP
EARLY_TAIL_OLD = bytes.fromhex("FA FD DC B7 C4 0E 6A")
EARLY_STUB = bytes.fromhex("FA FD DC B7 C4 0E 6A C3 00 71")   # LD A,(DCFD); OR A; CALL NZ,$6A0E; JP $7100


def off(bank: int, addr: int) -> int:
    return bank * 0x4000 + addr - 0x4000


def update_checksums(rom: bytearray) -> None:
    h = 0
    for v in rom[0x134:0x14D]:
        h = (h - v - 1) & 0xFF
    rom[0x14D] = h
    g = (sum(rom[:0x14E]) + sum(rom[0x150:])) & 0xFFFF
    rom[0x14E:0x150] = g.to_bytes(2, "big")


def run_guard(code: bytes, base: int, ly: int, lcd_on: bool, window: int, a_in: int = 0x5A) -> tuple[str, int]:
    """Execute the guard bytes with a micro LR35902 interpreter.

    Returns ("admit"|"defer", A). Only the opcodes the guard uses are modelled;
    anything else is a build error.  LY reads 0 when the LCD is off.
    """
    a, z, cy, pc, steps, di = a_in, False, False, base, 0, False
    ly_val = ly if lcd_on else 0
    while True:
        steps += 1
        if steps > 4000:
            raise AssertionError("guard did not terminate (wait loop with LCD on outside window is expected only at runtime)")
        op = code[pc - base]
        if op == 0xF0:
            reg = code[pc - base + 1]
            a = {0x44: ly_val, 0x40: 0x91 if lcd_on else 0x11}[reg]
            pc += 2
        elif op == 0xD6:
            n = code[pc - base + 1]; cy = a < n; a = (a - n) & 0xFF; z = a == 0; pc += 2
        elif op == 0xFE:
            n = code[pc - base + 1]; cy = a < n; z = a == n; pc += 2
        elif op == 0xDA:
            t = code[pc - base + 1] | (code[pc - base + 2] << 8)
            if cy:
                return ("admit" if t == RELOCATED_TAIL else f"jump ${t:04X}"), a
            pc += 3
        elif op == 0xC3:
            t = code[pc - base + 1] | (code[pc - base + 2] << 8)
            return (("admit-di" if di else "admit") if t == RELOCATED_TAIL else f"jump ${t:04X}"), a
        elif op == 0xCB and code[pc - base + 1] == 0x7F:
            z = not (a & 0x80); pc += 2
        elif op == 0xC0:
            if not z:
                return "defer", a
            pc += 1
        elif op == 0x28:
            d = code[pc - base + 1]; d = d - 256 if d > 127 else d
            pc = pc + 2 + d if z else pc + 2
        elif op == 0xF3:
            di = True; pc += 1
        elif op == 0x00:
            pc += 1
        elif op == 0x30:
            d = code[pc - base + 1]; d = d - 256 if d > 127 else d
            if not cy:
                if d < 0:
                    if not lcd_on or 144 <= ly < 144 + window:
                        raise AssertionError("wait loop looped although inside window")
                    return "wait-then-admit", a
                pc = pc + 2 + d
            else:
                pc += 2
        else:
            raise AssertionError(f"unmodelled opcode {op:02X} at ${pc:04X}")


def static_checks(guard: bytes, variant: str, window: int) -> dict:
    results = {}
    for lcd_on in (True, False):
        for ly in range(154):
            verdict, _ = run_guard(guard, GUARD_ADDR, ly, lcd_on, window)
            in_window = lcd_on and 144 <= ly < 144 + window
            if not lcd_on:
                assert verdict == "admit", (lcd_on, ly, verdict)          # LCD off: never DI
            elif in_window:
                assert verdict == ("admit-di" if variant == "protected" else "admit"), (lcd_on, ly, verdict)
            else:
                assert verdict == ("wait-then-admit" if variant == "wait" else "defer"), (lcd_on, ly, verdict)
    results["ly_states_checked"] = 2 * 154
    results["admit_window"] = f"LY 144..{144 + window - 1} or LCD off"
    results["defer_flag"] = "n/a (spins)" if variant == "wait" else "NZ (matches existing CALL NZ,$5D25 / RET NZ rejection)"
    results["di_on_admit"] = variant == "protected"
    return results


def build(source: bytes, *, variant: str, window: int, early: bool = False) -> tuple[bytes, dict]:
    assert variant in ("defer", "protected", "eq-control", "wait") and 1 <= window <= 9
    assert hashlib.sha256(source).hexdigest() == BASE_SHA, "wrong exact r391 base"
    tail = off(BANK, ADMIT_TAIL_ADDR)
    assert source[tail:tail + len(ADMIT_TAIL_OLD)] == ADMIT_TAIL_OLD, "admission tail preimage changed"
    # The admission head must still be the r391 form so the NZ-defer contract holds.
    head = off(BANK, 0x6A0E)
    assert source[head:head + 19] == bytes.fromhex("FA 5B DF 3C E6 03 28 14 FA 80 D8 E6 F7 FE 02 C4 25 5D C0"), \
        "admission head changed (DF5B gate / scene gate / $5D25 rejection)"
    g = off(BANK, GUARD_ADDR)
    assert source[g:g + GUARD_SLACK] == bytes(GUARD_SLACK), "guard slack $7474 not free"
    assert source[g - 3:g] == bytes.fromhex("C3 00 74"), "r389 prelude patch before slack changed"
    # bank19 side unchanged: $6CAA still increments DF5B exactly once per admitted pass.
    inc = off(19, 0x6CAA)
    assert source[inc:inc + 4] == bytes.fromhex("21 5B DF 34"), "bank19:$6CAA increment changed"
    guard = {"defer": guard_defer, "protected": guard_protected, "wait": guard_wait,
             "eq-control": lambda w: guard_protected(w, nop_control=True)}[variant](window)
    assert len(guard) <= GUARD_SLACK
    checks = static_checks(guard, variant, window)

    # The DF5B "done" branch `JR Z,+$14` at $6A14 targeted the RET at $6A2A, which the
    # relocated tail now occupies.  Retarget it to the RET at $69F7 (same flags: Z set, A=0).
    done_ret = off(BANK, 0x69F7)
    assert source[done_ret] == 0xC9, "$69F7 is no longer a RET"
    jr = off(BANK, 0x6A15)
    assert source[jr] == 0x14 and (0x6A16 + 0x14) == 0x6A2A
    rom = bytearray(source)
    rom[jr] = (0x69F7 - 0x6A16) & 0xFF
    rom[tail:tail + len(ADMIT_TAIL_NEW)] = ADMIT_TAIL_NEW
    rom[g:g + len(guard)] = guard
    owned = {jr} | set(range(tail, tail + len(ADMIT_TAIL_NEW))) | set(range(g, g + len(guard)))
    early_receipt: dict[str, object] = {"applied": False}
    if early:
        ejr = off(BANK, EARLY_JR_ADDR)
        assert source[ejr:ejr + 2] == bytes.fromhex("18 0D"), "$6EC4 JR preimage changed"
        assert (EARLY_JR_ADDR + 2 + 0x0D) == EARLY_SLED_ADDR and (EARLY_JR_ADDR + 2 + 0x2E) == 0x6EF4
        sled = off(BANK, EARLY_SLED_ADDR)
        assert source[sled:sled + len(EARLY_SLED_OLD)] == EARLY_SLED_OLD, "JR sled preimage changed"
        # no other reference may land inside the sled
        bank = source[BANK * 0x4000:(BANK + 1) * 0x4000]
        for i in range(len(bank) - 2):
            t = bank[i + 1] | (bank[i + 2] << 8)
            if bank[i] in (0xC3, 0xCD, 0xC2, 0xCA, 0xD2, 0xDA, 0xC4, 0xCC, 0xD4, 0xDC) and EARLY_SLED_ADDR <= t < 0x6EF4:
                raise AssertionError(f"absolute reference into sled at ${0x4000 + i:04X}")
        for i in range(len(bank) - 1):
            if bank[i] in (0x18, 0x20, 0x28, 0x30, 0x38) and not (EARLY_SLED_ADDR <= 0x4000 + i < 0x6EF4):
                d = bank[i + 1]; d = d - 256 if d > 127 else d
                if EARLY_SLED_ADDR <= 0x4000 + i + 2 + d < 0x6EF4 and 0x4000 + i != EARLY_JR_ADDR:
                    raise AssertionError(f"relative reference into sled at ${0x4000 + i:04X}")
        hc = off(BANK, EARLY_HEAD_CALL)
        assert source[hc:hc + 3] == bytes.fromhex("CD 00 71"), "prelude head CALL $7100 changed"
        tc = off(BANK, EARLY_TAIL_CALL)
        assert source[tc:tc + 7] == EARLY_TAIL_OLD, "prelude tail admission call changed"
        assert source[tc + 7] == 0xE1, "prelude epilogue POP HL not at $6F8C"
        rom[ejr + 1] = 0x2E
        rom[sled:sled + len(EARLY_STUB)] = EARLY_STUB
        rom[hc:hc + 3] = bytes((0xCD, EARLY_SLED_ADDR & 0xFF, EARLY_SLED_ADDR >> 8))
        rom[tc:tc + 7] = bytes(7)
        owned |= {ejr + 1} | set(range(sled, sled + len(EARLY_STUB))) | set(range(hc, hc + 3)) | set(range(tc, tc + 7))
        early_receipt = {
            "applied": True,
            "sled_freed": "bank13:$6EC4 JR $6ED3 -> JR $6EF4 (only reference, verified bank-wide)",
            "stub": f"bank13:${EARLY_SLED_ADDR:04X} {EARLY_STUB.hex()}",
            "prelude_head": "bank13:$6F20 CALL $7100 -> CALL $6ED3 (stub tail-jumps to $7100; stack depth unchanged, "
                            "so $7100's early-out `POP HL; JP $6F8C` still discards the right word)",
            "prelude_tail": "bank13:$6F85..$6F8B admission call -> NOP x7 (no double admission per frame)",
            "register_safety": "$7100 assigns A/B before use and does not read HL/DE on entry; chain clobbers A/HL only",
        }
    update_checksums(rom)
    changed = {i for i, (x, y) in enumerate(zip(source, rom)) if x != y}
    assert changed <= owned | CHECKSUMS, sorted(changed - owned - CHECKSUMS)[:8]
    receipt = {
        "schema": "penta-cold-art-vblank-guard-r392-build-v1",
        "experimental": True, "promotable": False, "live_tested": False,
        "variant": variant + ("+early" if early else ""),
        "ly_window": f"144..{144 + window - 1}",
        "early_admission": early_receipt,
        "base_sha256": BASE_SHA,
        "candidate_sha256": hashlib.sha256(rom).hexdigest(),
        "changed_offsets": sorted(changed),
        "patch": {
            "admission_tail": f"bank13:${ADMIT_TAIL_ADDR:04X} JP ${GUARD_ADDR:04X}; tail relocated to ${RELOCATED_TAIL:04X}",
            "done_branch": "bank13:$6A14 JR Z retargeted $6A2A -> $69F7 (RET), flags/A unchanged",
            "guard": f"bank13:${GUARD_ADDR:04X} ({len(guard)} bytes) {guard.hex()}",
            "bank19_bank7_untouched": True,
        },
        "static_checks": checks,
        "abi": "clobbers A only (as before); defer returns NZ with DF5B unchanged; "
               "admit continues to PUSH $6CAA; LD A,$13; JP $0061 exactly as r391",
    }
    return bytes(rom), receipt


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--base", type=Path, default=BASE)
    ap.add_argument("--out-dir", type=Path, default=OUT)
    ap.add_argument("--wait", action="store_true", help="spin for VBlank instead of deferring")
    ap.add_argument("--protected", action="store_true", help="defer variant with DI on the admit path")
    ap.add_argument("--eq-control", action="store_true", help="cycle-equal control for --protected (NOP instead of DI)")
    ap.add_argument("--window", type=int, default=LY_WINDOW, help="admit LY 144..144+window-1 (default 6)")
    ap.add_argument("--early", action="store_true", help="move the admission to the head of the VBlank prelude")
    args = ap.parse_args()
    variant = ("wait" if args.wait else "protected" if args.protected
               else "eq-control" if args.eq_control else "defer")
    rom, receipt = build(args.base.read_bytes(), variant=variant, window=args.window, early=args.early)
    args.out_dir.mkdir(parents=True, exist_ok=True)
    target = args.out_dir / "candidate.gb"
    if target.exists() and target.read_bytes() != rom:
        raise SystemExit("candidate collision")
    target.write_bytes(rom)
    (args.out_dir / "build-receipt.json").write_text(json.dumps(receipt, indent=2) + "\n")
    print(json.dumps({k: receipt[k] for k in ("variant", "ly_window", "candidate_sha256", "static_checks")}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
