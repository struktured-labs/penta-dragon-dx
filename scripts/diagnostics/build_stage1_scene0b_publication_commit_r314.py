#!/usr/bin/env python3
"""Build r314: commit scene-$0B self-heal only after clean publication.

r313 repairs the live SVBK1 DAD7 gateway and invalidates both physical-map
semantic keys at the RST decision point.  Authenticated operator replays then
proved that the repair marker can precede the completed hidden-map tile/attr/
hazard publication: one corrupted-walls frame and four menu-loaded low-health
frames were sampled with stale semantic attributes after the early marker.

This overlay makes that one-time repair transactional.  The exact r313 repair
site writes a semantically equivalent pending gateway (unconditional CALL
$0013 is equivalent to CALL NZ there in exact scene $0B), invalidates both
keys, and inserts a private $A314 stack capability beneath the exact $12E0 map
return.  Native map copy, postcopy, and hazard work remains byte exact.  Only
after that whole call returns does the capability re-enter the existing fixed
bank-31 bridge.  The commit handler reproduces fixed:$12E0's LCDC selector,
publishes the completed physical map first, changes only DADE CD->C4 second,
removes the capability, and resumes at fixed:$12EE.  Current-runtime and all
ordinary publication paths remain byte exact.  No emulator is invoked.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import build_stage1_scene0b_runtime_selfheal_r313 as r313


r305 = r313.r305
ROOT = r313.ROOT
TMP = r313.TMP
BASE = r313.DEFAULT_OUTPUT
BASE_RECEIPT = r313.DEFAULT_RECEIPT
DEFAULT_OUTPUT = TMP / "stage1-scene0b-publication-commit-r314/candidate.gb"
DEFAULT_RECEIPT = (
    TMP / "stage1-scene0b-publication-commit-r314/build-receipt.json"
)

BASE_SHA256 = r313.EXPECTED_CANDIDATE_SHA256
BASE_RECEIPT_SHA256 = (
    "c4086dc2d7186d8e6b9c88829d130034b64fee83783a9314944023f44138ba96"
)
BASE_SCHEMA = "penta-stage1-scene0b-runtime-selfheal-r313-build-v1"
EXPECTED_CANDIDATE_SHA256 = (
    "010f9b78e5294f436d4a6735e799f12546a26827637db5ce1d6646eeff06c303"
)

REJECTED_LIVE_RECEIPT = (
    TMP / "stage1-scene0b-runtime-selfheal-r313/"
    "live-scene0b-hardening-diagnostic-r7/receipt.json"
)
REJECTED_LIVE_RECEIPT_SHA256 = (
    "158f31790ae4495894b26b80d7863deac36ccf8efbe28feb51f24e4acb3ccf08"
)
REJECTED_LIVE_SCHEMA = "penta-stage1-scene0b-cache-publication-diagnostic-v4"

HANDLER_ADDR = r313.HANDLER_ADDR
MUX_BANK = r313.MUX_BANK
GATEWAY_ADDR = r313.GATEWAY_ADDR
CACHE_ADDRS = r313.CACHE_ADDRS
STALE_GATEWAY = r313.STALE_GATEWAY
PENDING_GATEWAY = bytes.fromhex("CD 13 00")
CURRENT_GATEWAY = r313.CURRENT_GATEWAY
CHECKSUM_OFFSETS = r313.CHECKSUM_OFFSETS

RST_OUTER_RETURN = r313.RST18_LIVE_RETURN       # fixed:$3493
DIRTY_RETURN = r313.DIRTY_RETURN_ADDR           # fixed:$42B1
MAP_RETURN = 0x12E0                             # CALL $4295 return
PUBLISH_CONTINUATION = 0x12EE                   # first byte after LCDC store
SYNTHETIC_RETURN = 0x084D                       # fixed bridge mapper tail
TRANSACTION_SENTINEL = 0xA314                   # non-executable WRAM key

MAIN_PUBLISH_CALL_ADDR = 0x12DD
ALT_PUBLISH_CALL_ADDR = 0x0AB5
MAP_CALL = bytes.fromhex("CD 95 42")
MAIN_PUBLISHER = bytes.fromhex(
    "CD 95 42 FA 0B DC B7 28 04 3E 8B 18 02 3E 83 E0 40 F0 97"
)
LCDC_SELECTOR = bytes.fromhex(
    "FA 0B DC B7 28 04 3E 8B 18 02 3E 83 E0 40"
)


def bank_offset(bank: int, address: int) -> int:
    return r313.bank_offset(bank, address)


class Asm(r305.Asm):
    """r305's relative assembler plus fail-closed absolute label jumps."""

    def __init__(self, origin: int) -> None:
        super().__init__(origin)
        self.absolute_fixups: list[tuple[int, str]] = []

    def jp(self, opcode: int, label: str) -> None:
        r305.r304.require(opcode in (0xC2, 0xCA, 0xC3),
                          "unsupported absolute branch opcode")
        self.db(opcode, 0, 0)
        self.absolute_fixups.append((len(self.code) - 2, label))

    def finish(self) -> bytes:
        code = bytearray(super().finish())
        for operand, label in self.absolute_fixups:
            r305.r304.require(label in self.labels,
                              f"undefined absolute label {label}")
            target = self.labels[label]
            code[operand] = target & 0xFF
            code[operand + 1] = target >> 8
        return bytes(code)


def _emit_stack_word_check(
    a: Asm, offset: int, value: int, failure: str,
) -> None:
    a.db(0xF8, offset, 0x7E, 0xFE, value & 0xFF)
    a.jp(0xC2, failure)
    a.db(0x23, 0x7E, 0xFE, value >> 8)
    a.jp(0xC2, failure)


def _emit_remove_sentinel(a: Asm, continuation: int) -> None:
    """Remove [saved,084D,A314,caller] without moving caller/older data.

    Copy the saved HL upward over 084D, place the chosen continuation over the
    sentinel, then atomically add two to SP.  POP HL and the fixed mapper RET
    consequently consume [saved,continuation], leaving [caller,older] exact.
    """
    a.db(0xF8, 0x00, 0x7E, 0xF8, 0x02, 0x77)
    a.db(0xF8, 0x01, 0x7E, 0xF8, 0x03, 0x77)
    a.db(0xF8, 0x04, 0x36, continuation & 0xFF)
    a.db(0x23, 0x36, continuation >> 8)
    a.db(0xE8, 0x02)  # ADD SP,+2; remove exactly the capability word.


def assemble_handler() -> tuple[bytes, dict[str, int]]:
    a = Asm(HANDLER_ADDR)

    # Preserve every r313 instruction address through repair_effect=$6D4D.
    # Only the first low-byte mismatch is allowed to classify the new private
    # capability; a malformed high byte of $3493 goes straight fail-closed.
    a.label("entry")
    a.db(0xFE, RST_OUTER_RETURN & 0xFF)
    a.jr(0x20, "maybe_commit")
    a.db(0x23, 0x7E, 0xFE, RST_OUTER_RETURN >> 8)
    a.jr(0x20, "unknown")

    a.db(0xFA, 0x80, 0xD8, 0xFE, 0x0B)
    a.jr(0x20, "hot_resume")
    a.db(0xF0, 0x70, 0xE6, 0x07, 0xFE, 0x01)
    a.jr(0x20, "hot_resume")

    # An already current runtime remains observation-only.  Pending CD 13 00
    # naturally misses both exact triplets and also resumes without writes.
    for index, value in enumerate(CURRENT_GATEWAY):
        address = GATEWAY_ADDR + index
        a.db(0xFA, address & 0xFF, address >> 8, 0xFE, value)
        a.jr(0x20, "check_old")
    a.jr(0x18, "hot_resume")

    a.label("check_old")
    a.db(0xF0, 0xB7, 0xFE, 0x02)
    a.jr(0x20, "hot_resume")
    for index, value in enumerate(STALE_GATEWAY):
        address = GATEWAY_ADDR + index
        a.db(0xFA, address & 0xFF, address >> 8, 0xFE, value)
        a.jr(0x20, "hot_resume")

    a.label("repair")
    a.db(0xF3)  # DI through stack insertion and native dirty publication.
    for index, value in enumerate(PENDING_GATEWAY):
        address = GATEWAY_ADDR + index
        a.db(0x3E, value, 0xEA, address & 0xFF, address >> 8)
    a.db(0x3E, 0xFF)
    for address in CACHE_ADDRS:
        a.db(0xEA, address & 0xFF, address >> 8)

    # Keep the r313 live observation point exact, but it now means transaction
    # start, never completed repair.  Release acknowledgment is commit_effect.
    a.label("repair_effect")
    a.jp(0xC3, "arm_transaction")

    # Current and pending hot paths retain r313's exact register/mapper ABI.
    a.label("hot_resume")
    a.db(0xF8, 0x02, 0x36, r305.RUNTIME_RELOCATED_ADDR & 0xFF)
    a.db(0x23, 0x36, r305.RUNTIME_RELOCATED_ADDR >> 8)
    a.db(0xE1, 0x3E, 0x01, 0xC3, 0x61, 0x00)

    # Only the private sentinel can enter commit.  All other r305 unknown
    # callers retain POP HL; A=1/NZ; RET to the synthetic mapper continuation.
    a.label("maybe_commit")
    a.db(0xFE, TRANSACTION_SENTINEL & 0xFF)
    a.jr(0x20, "unknown")
    a.db(0x23, 0x7E, 0xFE, TRANSACTION_SENTINEL >> 8)
    a.jp(0xCA, "commit")
    a.label("unknown")
    a.db(0xE1, 0x3E, 0x01, 0xB7, 0xC9)

    a.label("arm_transaction")
    # The repair mutation is useful on any exact r313 live state, but only the
    # reviewed primary publisher receives the private delayed-commit frame.
    # Synthetic, dirty, and map returns are all authenticated before SP moves.
    _emit_stack_word_check(a, 0x02, SYNTHETIC_RETURN, "arm_fail")
    _emit_stack_word_check(a, 0x06, DIRTY_RETURN, "arm_fail")
    _emit_stack_word_check(a, 0x08, MAP_RETURN, "arm_fail")

    # Make two bytes below SP, copy the sole unknown word (saved caller HL),
    # and reconstruct the five authenticated words one position lower.  The
    # original function return and every older stack byte are never written.
    a.db(0xF8, 0x00, 0x7E, 0xF8, 0xFE, 0x77)
    a.db(0xF8, 0x01, 0x7E, 0xF8, 0xFF, 0x77)
    for offset, value in (
        (0x00, SYNTHETIC_RETURN),
        (0x02, RST_OUTER_RETURN),
        (0x04, DIRTY_RETURN),
        (0x06, 0x0013),
        (0x08, TRANSACTION_SENTINEL),
    ):
        a.db(0xF8, offset, 0x36, value & 0xFF)
        a.db(0x23, 0x36, value >> 8)
    a.db(0xE8, 0xFE)  # ADD SP,-2; activate the shifted saved-HL word.
    a.label("transaction_armed_effect")
    a.jp(0xC3, "hot_resume")

    a.label("arm_fail")
    # Pending is deliberately not promoted.  Restore the entry IME before
    # resuming because an unreviewed stack cannot prove it reaches $42DB EI.
    a.db(0xFB)
    a.jp(0xC3, "hot_resume")

    a.label("commit")
    # A sentinel is a capability, not sufficient scope by itself.  Recheck all
    # scene ownership and the complete pending gateway before any publication.
    a.db(0xFA, 0x80, 0xD8, 0xFE, 0x0B)
    a.jp(0xC2, "commit_abort")
    a.db(0xF0, 0x70, 0xE6, 0x07, 0xFE, 0x01)
    a.jp(0xC2, "commit_abort")
    a.db(0xF0, 0xB7, 0xFE, 0x02)
    a.jp(0xC2, "commit_abort")
    for index, value in enumerate(PENDING_GATEWAY):
        address = GATEWAY_ADDR + index
        a.db(0xFA, address & 0xFF, address >> 8, 0xFE, value)
        a.jp(0xC2, "commit_abort")

    _emit_remove_sentinel(a, PUBLISH_CONTINUATION)

    # Byte-for-byte semantics of fixed:$12E0-$12ED.  The completed hidden map
    # becomes the display owner before DADE changes from pending to current.
    a.db(0xFA, 0x0B, 0xDC, 0xB7)
    a.jr(0x28, "select_9800")
    a.db(0x3E, 0x8B)
    a.jr(0x18, "publish_lcdc")
    a.label("select_9800")
    a.db(0x3E, 0x83)
    a.label("publish_lcdc")
    a.db(0xE0, 0x40)
    a.label("display_flip_effect")
    a.db(0x3E, CURRENT_GATEWAY[0], 0xEA,
         GATEWAY_ADDR & 0xFF, GATEWAY_ADDR >> 8)
    a.label("commit_effect")
    a.db(0xE1, 0x3E, 0x01, 0xC3, 0x61, 0x00)

    a.label("commit_abort")
    # Remove the private word safely, but route through the untouched native
    # selector.  Pending remains pending, so no failed scope can be certified.
    _emit_remove_sentinel(a, MAP_RETURN)
    a.db(0xE1, 0x3E, 0x01, 0xC3, 0x61, 0x00)

    code = a.finish()
    return code, dict(a.labels)


HANDLER, HANDLER_LABELS = assemble_handler()


def owned_ranges() -> set[int]:
    start = bank_offset(MUX_BANK, HANDLER_ADDR)
    return set(range(start, start + len(HANDLER)))


def _read16(mem: bytearray, address: int) -> int:
    return mem[address] | (mem[(address + 1) & 0xFFFF] << 8)


def execute_handler(
    *,
    scene: int = 0x0B,
    svbk: int = 0xF9,
    ffb7: int = 0x02,
    gateway: bytes = STALE_GATEWAY,
    outer_return: int = RST_OUTER_RETURN,
    dirty_return: int = DIRTY_RETURN,
    map_return: int = MAP_RETURN,
    original_return: int = 0x1357,
    saved_hl: int = 0x9C00,
    dc0b: int = 1,
    layout: str = "repair",
) -> dict[str, Any]:
    """Execute emitted r314 handler bytes in a strict small LR35902 model."""
    r305.r304.require(len(gateway) == 3, "gateway model width changed")
    r305.r304.require(layout in ("repair", "commit"),
                      "unknown handler stack layout")
    mem = bytearray(0x10000)
    mem[HANDLER_ADDR:HANDLER_ADDR + len(HANDLER)] = HANDLER
    mem[0xD880] = scene & 0xFF
    mem[0xFF70] = svbk & 0xFF
    mem[0xFFB7] = ffb7 & 0xFF
    mem[0xDC0B] = dc0b & 0xFF
    mem[GATEWAY_ADDR:GATEWAY_ADDR + 3] = gateway
    mem[CACHE_ADDRS[0]] = 0x11
    mem[CACHE_ADDRS[1]] = 0x22

    initial_sp = 0xC080
    if layout == "repair":
        words = (
            saved_hl, SYNTHETIC_RETURN, outer_return, dirty_return,
            map_return, original_return, 0xBEEF, 0xCAFE,
        )
    else:
        words = (
            saved_hl, SYNTHETIC_RETURN, outer_return,
            original_return, 0xBEEF, 0xCAFE,
        )
    for index, value in enumerate(words):
        address = initial_sp + 2 * index
        mem[address] = value & 0xFF
        mem[address + 1] = value >> 8

    state: dict[str, Any] = {
        "pc": HANDLER_ADDR,
        "sp": initial_sp,
        "a": outer_return & 0xFF,
        "f": 0,
        "h": (initial_sp + 4) >> 8,
        "l": (initial_sp + 4) & 0xFF,
        "ime": True,
        "mem": mem,
        "writes": [],
        "trace": [],
        "initial_sp": initial_sp,
        "saved_hl": saved_hl,
        "original_return": original_return,
        "canary": bytes(mem[initial_sp + (12 if layout == "repair" else 8):
                            initial_sp + (16 if layout == "repair" else 12)]),
    }

    def write(pc: int, address: int, value: int) -> None:
        mem[address] = value & 0xFF
        state["writes"].append({
            "pc": pc, "address": address, "value": value & 0xFF,
            "ime": state["ime"],
        })

    for _step in range(512):
        pc = state["pc"]
        if not (HANDLER_ADDR <= pc < HANDLER_ADDR + len(HANDLER)):
            break
        opcode = mem[pc]
        next_pc = (pc + 1) & 0xFFFF
        cycles = 0
        if opcode == 0xFE:  # CP d8
            state["f"] = 0x80 if state["a"] == mem[next_pc] else 0
            next_pc += 1
            cycles = 8
        elif opcode in (0x18, 0x20, 0x28):  # JR / JR NZ / JR Z
            displacement = mem[next_pc]
            if displacement >= 0x80:
                displacement -= 0x100
            taken = (
                opcode == 0x18
                or (opcode == 0x20 and not (state["f"] & 0x80))
                or (opcode == 0x28 and bool(state["f"] & 0x80))
            )
            next_pc = pc + 2 + displacement if taken else pc + 2
            cycles = 12 if taken else 8
        elif opcode in (0xC2, 0xCA, 0xC3):  # JP NZ / JP Z / JP
            target = _read16(mem, next_pc)
            taken = (
                opcode == 0xC3
                or (opcode == 0xC2 and not (state["f"] & 0x80))
                or (opcode == 0xCA and bool(state["f"] & 0x80))
            )
            next_pc = target if taken else pc + 3
            cycles = 16 if taken or opcode == 0xC3 else 12
        elif opcode == 0x23:  # INC HL
            value = (((state["h"] << 8) | state["l"]) + 1) & 0xFFFF
            state["h"], state["l"] = value >> 8, value & 0xFF
            cycles = 8
        elif opcode == 0x7E:  # LD A,[HL]
            state["a"] = mem[(state["h"] << 8) | state["l"]]
            cycles = 8
        elif opcode == 0x77:  # LD [HL],A
            write(pc, (state["h"] << 8) | state["l"], state["a"])
            cycles = 8
        elif opcode == 0xFA:  # LD A,[a16]
            state["a"] = mem[_read16(mem, next_pc)]
            next_pc = pc + 3
            cycles = 16
        elif opcode == 0xEA:  # LD [a16],A
            write(pc, _read16(mem, next_pc), state["a"])
            next_pc = pc + 3
            cycles = 16
        elif opcode == 0xF0:  # LDH A,[a8]
            state["a"] = mem[0xFF00 | mem[next_pc]]
            next_pc += 1
            cycles = 12
        elif opcode == 0xE0:  # LDH [a8],A
            write(pc, 0xFF00 | mem[next_pc], state["a"])
            next_pc += 1
            cycles = 12
        elif opcode == 0xE6:  # AND d8
            state["a"] &= mem[next_pc]
            state["f"] = 0x80 if state["a"] == 0 else 0
            next_pc += 1
            cycles = 8
        elif opcode == 0xB7:  # OR A
            state["f"] = 0x80 if state["a"] == 0 else 0
            cycles = 4
        elif opcode == 0xF3:  # DI
            state["ime"] = False
            cycles = 4
        elif opcode == 0xFB:  # EI (model records restored end state)
            state["ime"] = True
            cycles = 4
        elif opcode == 0x3E:  # LD A,d8
            state["a"] = mem[next_pc]
            next_pc += 1
            cycles = 8
        elif opcode == 0xF8:  # LD HL,SP+e8
            raw = mem[next_pc]
            signed = raw if raw < 0x80 else raw - 0x100
            value = (state["sp"] + signed) & 0xFFFF
            state["h"], state["l"] = value >> 8, value & 0xFF
            state["f"] = 0
            next_pc += 1
            cycles = 12
        elif opcode == 0x36:  # LD [HL],d8
            write(pc, (state["h"] << 8) | state["l"], mem[next_pc])
            next_pc += 1
            cycles = 12
        elif opcode == 0xE8:  # ADD SP,e8
            raw = mem[next_pc]
            signed = raw if raw < 0x80 else raw - 0x100
            state["sp"] = (state["sp"] + signed) & 0xFFFF
            state["f"] = 0
            next_pc += 1
            cycles = 16
        elif opcode == 0xE1:  # POP HL
            value = _read16(mem, state["sp"])
            state["sp"] = (state["sp"] + 2) & 0xFFFF
            state["h"], state["l"] = value >> 8, value & 0xFF
            cycles = 12
        elif opcode == 0xC9:  # RET
            next_pc = _read16(mem, state["sp"])
            state["sp"] = (state["sp"] + 2) & 0xFFFF
            cycles = 16
        else:
            raise AssertionError(
                f"handler model reached unsupported ${opcode:02X} at ${pc:04X}"
            )
        state["trace"].append((pc, opcode, cycles, state["ime"]))
        state["pc"] = next_pc & 0xFFFF
    else:
        raise AssertionError("handler model did not leave emitted code")
    return state


def _owned_writes(state: dict[str, Any]) -> list[tuple[int, int, bool]]:
    watched = (
        set(range(GATEWAY_ADDR, GATEWAY_ADDR + 3))
        | set(CACHE_ADDRS) | {0xFF40}
    )
    return [
        (row["address"], row["value"], row["ime"])
        for row in state["writes"] if row["address"] in watched
    ]


def transaction_contract() -> dict[str, Any]:
    repair = execute_handler()
    sp = repair["initial_sp"]
    expected_repair = [
        (0xDADE, 0xCD, False), (0xDADF, 0x13, False),
        (0xDAE0, 0x00, False), (0xDF53, 0xFF, False),
        (0xDF57, 0xFF, False),
    ]
    r305.r304.require(_owned_writes(repair) == expected_repair,
                      "transaction start writes changed")
    r305.r304.require(repair["pc"] == 0x0061 and repair["sp"] == sp,
                      "armed repair did not reach mapper with shifted SP")
    r305.r304.require(
        _read16(repair["mem"], sp) == r305.RUNTIME_RELOCATED_ADDR
        and _read16(repair["mem"], sp + 2) == RST_OUTER_RETURN
        and _read16(repair["mem"], sp + 4) == DIRTY_RETURN
        and _read16(repair["mem"], sp + 6) == 0x0013
        and _read16(repair["mem"], sp + 8) == TRANSACTION_SENTINEL
        and _read16(repair["mem"], sp + 10) == repair["original_return"],
        "armed return chain changed",
    )
    r305.r304.require(
        bytes(repair["mem"][sp + 12:sp + 16]) == repair["canary"],
        "transaction insertion overwrote older stack data",
    )
    r305.r304.require(
        (repair["h"] << 8) | repair["l"] == repair["saved_hl"],
        "transaction start did not restore caller HL",
    )

    commits: dict[str, Any] = {}
    for dc0b, lcdc in ((0, 0x83), (1, 0x8B)):
        commit = execute_handler(
            gateway=PENDING_GATEWAY, outer_return=TRANSACTION_SENTINEL,
            layout="commit", dc0b=dc0b,
        )
        csp = commit["initial_sp"]
        writes = _owned_writes(commit)
        r305.r304.require(
            writes == [(0xFF40, lcdc, True), (0xDADE, 0xC4, True)],
            "commit did not publish before finalizing gateway",
        )
        r305.r304.require(commit["pc"] == 0x0061
                          and commit["sp"] == csp + 4,
                          "commit did not remove exactly one stack word")
        r305.r304.require(
            _read16(commit["mem"], csp + 4) == PUBLISH_CONTINUATION
            and _read16(commit["mem"], csp + 6)
            == commit["original_return"],
            "commit continuation/caller chain changed",
        )
        r305.r304.require(
            bytes(commit["mem"][csp + 8:csp + 12]) == commit["canary"],
            "commit overwrote older stack data",
        )
        r305.r304.require(
            (commit["h"] << 8) | commit["l"] == commit["saved_hl"],
            "commit did not restore caller HL",
        )
        commits[str(dc0b)] = {
            "LCDC": f"{lcdc:02X}",
            "ordered_writes": ["FF40 completed-map owner", "DADE CD->C4"],
            "continuation": "12EE",
        }

    abort = execute_handler(
        gateway=STALE_GATEWAY, outer_return=TRANSACTION_SENTINEL,
        layout="commit",
    )
    asp = abort["initial_sp"]
    r305.r304.require(_owned_writes(abort) == [],
                      "failed commit scope performed owned writes")
    r305.r304.require(
        abort["pc"] == 0x0061 and abort["sp"] == asp + 4
        and _read16(abort["mem"], asp + 4) == MAP_RETURN
        and _read16(abort["mem"], asp + 6) == abort["original_return"],
        "commit abort did not collapse to native publisher",
    )
    return {
        "model": "independent emitted-handler opcode execution",
        "start_chain": "[084D,3493,42B1,12E0,caller]",
        "armed_chain": "[DAD7,3493,42B1,0013,A314,caller]",
        "completion_chain": "[12EE,caller]",
        "transaction_start_writes": [
            "DADE-E0=CD 13 00", "DF53=FF", "DF57=FF",
        ],
        "all_transaction_start_writes_IME_disabled": True,
        "older_stack_bytes_exact": True,
        "commit_selectors": commits,
        "commit_order": "completed-map LCDC owner -> DADE CD-to-C4 acknowledgment",
        "commit_abort": "no owned writes; exact native $12E0 continuation",
    }


def semantic_contract() -> dict[str, Any]:
    executions = 0

    def check(
        *, scene: int = 0x0B, svbk: int = 0xF9, ffb7: int = 0x02,
        gateway: bytes = STALE_GATEWAY,
        outer: int = RST_OUTER_RETURN, should_start: bool,
    ) -> None:
        nonlocal executions
        state = execute_handler(
            scene=scene, svbk=svbk, ffb7=ffb7, gateway=gateway,
            outer_return=outer,
        )
        writes = _owned_writes(state)
        expected = [
            (0xDADE, 0xCD, False), (0xDADF, 0x13, False),
            (0xDAE0, 0x00, False), (0xDF53, 0xFF, False),
            (0xDF57, 0xFF, False),
        ] if should_start else []
        r305.r304.require(writes == expected,
                          "r314 emitted start predicate changed")
        executions += 1

    for scene in range(256):
        check(scene=scene, should_start=scene == 0x0B)
    for svbk in range(256):
        check(svbk=svbk, should_start=(svbk & 7) == 1)
    for ffb7 in range(256):
        check(ffb7=ffb7, should_start=ffb7 == 0x02)
    for index in range(3):
        for value in range(256):
            gateway = bytearray(STALE_GATEWAY)
            gateway[index] = value
            check(gateway=bytes(gateway),
                  should_start=value == STALE_GATEWAY[index])
    for low in range(256):
        outer = (RST_OUTER_RETURN & 0xFF00) | low
        check(outer=outer, should_start=outer == RST_OUTER_RETURN)
    for high in range(256):
        outer = (high << 8) | (RST_OUTER_RETURN & 0xFF)
        check(outer=outer, should_start=outer == RST_OUTER_RETURN)
    for gateway in (
        CURRENT_GATEWAY, PENDING_GATEWAY, bytes.fromhex("00 00 00"),
        bytes.fromhex("C2 13 DA"), bytes.fromhex("FF FF FF"),
    ):
        check(gateway=gateway, should_start=False)

    r305.r304.require(executions == 2053,
                      "r314 semantic population changed")
    return {
        "emitted_opcode_executions": executions,
        "start_predicate": (
            "outer=$3493,D880=0B,(SVBK&7)=1,FFB7=02,"
            "DADE-E0 exact C2 B9 DA"
        ),
        "scene_values_exhausted": 256,
        "raw_SVBK_values_exhausted": 256,
        "FFB7_values_exhausted": 256,
        "single_gateway_byte_mutations_exhausted": 768,
        "outer_low_high_values_exhausted": 512,
        "current_pending_unknown_controls": 5,
        "current_gateway_writes": 0,
        "pending_gateway_writes": 0,
    }


def source_preimages(source: bytes) -> dict[str, Any]:
    r305.r304.require(r305.r304.digest(source) == BASE_SHA256,
                      "r314 requires exact r313 candidate")

    r305.r304.require(
        source[r313.RST18_ADDR:r313.RST18_ADDR + len(r313.NEW_RST18)]
        == r313.NEW_RST18,
        "r313 fixed RST route changed",
    )
    branch = bank_offset(MUX_BANK, r313.MUX_BRANCH_ADDR)
    r305.r304.require(
        source[branch:branch + len(r313.NEW_MUX_BRANCH)]
        == r313.NEW_MUX_BRANCH,
        "r313 mux branch changed",
    )
    handler = bank_offset(MUX_BANK, HANDLER_ADDR)
    r305.r304.require(source[handler:handler + len(r313.HANDLER)]
                      == r313.HANDLER, "r313 handler preimage changed")
    r305.r304.require(
        source[handler + len(r313.HANDLER):handler + len(HANDLER)]
        == bytes([0xFF]) * (len(HANDLER) - len(r313.HANDLER)),
        "r314 handler suffix cave is no longer erased",
    )
    r305.r304.require(
        source[MAIN_PUBLISH_CALL_ADDR:
               MAIN_PUBLISH_CALL_ADDR + len(MAIN_PUBLISHER)]
        == MAIN_PUBLISHER,
        "primary $12DD/$12E0 publisher changed",
    )
    r305.r304.require(
        source[ALT_PUBLISH_CALL_ADDR:ALT_PUBLISH_CALL_ADDR + len(MAP_CALL)]
        == MAP_CALL,
        "alternate $0AB5 publisher changed",
    )
    callers = [
        offset for offset in range(0x4000 - len(MAP_CALL) + 1)
        if source.startswith(MAP_CALL, offset)
    ]
    r305.r304.require(callers == [ALT_PUBLISH_CALL_ADDR,
                                  MAIN_PUBLISH_CALL_ADDR],
                      "fixed-bank $4295 caller census changed")
    r305.r304.require(
        source[0x12E0:0x12E0 + len(LCDC_SELECTOR)] == LCDC_SELECTOR,
        "native LCDC selector changed",
    )
    r305.r304.require(
        HANDLER_LABELS["repair_effect"]
        == r313.HANDLER_LABELS["repair_effect"] == 0x6D4D,
        "r313 repair observation address moved",
    )
    r305.r304.require(HANDLER_ADDR + len(HANDLER) <= 0x8000,
                      "r314 handler escaped bank31")
    return {
        "fixed_map_callers": ["$0AB5->$0AB8", "$12DD->$12E0"],
        "admitted_transaction_return": "$12E0 only",
        "native_primary_publisher": "$12E0-$12ED exact",
        "r313_repair_effect_preserved": "$6D4D",
        "handler_suffix_preimage": (
            f"{len(HANDLER) - len(r313.HANDLER)} erased bank31 bytes"
        ),
    }


def validate_preimages(
    source: bytes, base_receipt_bytes: bytes,
    rejected_receipt_bytes: bytes,
) -> dict[str, Any]:
    r305.r304.require(r305.r304.digest(source) == BASE_SHA256,
                      "r314 requires exact r313 candidate")
    r305.r304.require(
        r305.r304.digest(base_receipt_bytes) == BASE_RECEIPT_SHA256,
        "r313 build receipt identity changed",
    )
    base_receipt = json.loads(base_receipt_bytes)
    r305.r304.require(base_receipt.get("schema") == BASE_SCHEMA,
                      "r313 build receipt schema changed")
    r305.r304.require(base_receipt.get("candidate_sha256") == BASE_SHA256,
                      "r313 receipt names another candidate")
    r305.r304.require(
        r305.r304.digest(rejected_receipt_bytes)
        == REJECTED_LIVE_RECEIPT_SHA256,
        "r313 diagnostic rejection identity changed",
    )
    rejected = json.loads(rejected_receipt_bytes)
    r305.r304.require(rejected.get("schema") == REJECTED_LIVE_SCHEMA,
                      "r313 diagnostic rejection schema changed")
    r305.r304.require(rejected.get("status") == "FAIL",
                      "r313 diagnostic rejection is no longer FAIL")
    r305.r304.require(rejected.get("candidate_sha256") == BASE_SHA256,
                      "r313 rejection names another candidate")
    mismatch_counts = sorted(
        replay.get("postrepair_semantic_attr_mismatch_frames")
        for replay in rejected.get("replays", [])
    )
    r305.r304.require(mismatch_counts == [1, 1, 4, 4],
                      "r313 observed mismatch population changed")
    return {
        "r313_build_receipt_sha256": BASE_RECEIPT_SHA256,
        "r313_rejected_live_receipt_sha256": REJECTED_LIVE_RECEIPT_SHA256,
        "r313_postrepair_semantic_attr_mismatch_frames": [1, 1, 4, 4],
        **source_preimages(source),
    }


def validate_candidate(source: bytes, candidate: bytes) -> dict[str, Any]:
    r305.r304.require(
        len(source) == len(candidate) == r305.r304.ROM_SIZE,
        "r314 candidate size changed",
    )
    changed = r305.r304.delta(source, candidate)
    functional = r305.r304.delta(source, candidate, functional=True)
    expected = {
        offset for offset in owned_ranges() if source[offset] != candidate[offset]
    }
    r305.r304.require(functional == expected,
                      "r314 functional delta differs from exact handler")
    r305.r304.require(changed <= owned_ranges() | CHECKSUM_OFFSETS,
                      "r314 escaped handler/checksum ownership")
    handler = bank_offset(MUX_BANK, HANDLER_ADDR)
    r305.r304.require(candidate[handler:handler + len(HANDLER)] == HANDLER,
                      "r314 emitted handler changed")

    # Everything before the handler, including fixed bridge, r305 mux branch,
    # RST route, and native $12EC publication instruction, stays byte exact.
    for offset, (before, after) in enumerate(
        zip(source[:handler], candidate[:handler], strict=True)
    ):
        if offset in CHECKSUM_OFFSETS:
            continue
        r305.r304.require(before == after,
                          f"r314 changed pre-handler byte {offset:#x}")
    suffix = handler + len(HANDLER)
    for offset, (before, after) in enumerate(
        zip(source[suffix:], candidate[suffix:], strict=True), start=suffix
    ):
        if offset in CHECKSUM_OFFSETS:
            continue
        r305.r304.require(before == after,
                          f"r314 changed unowned byte {offset:#x}")
    r305.r304.require(candidate[0x12EC:0x12EE] == bytes.fromhex("E0 40"),
                      "native $12EC LCDC publication moved")
    return {
        "functional_changed_bytes": len(functional),
        "changed_offsets": [f"0x{offset:06X}" for offset in sorted(functional)],
        "owned_range": (
            f"bank31:${HANDLER_ADDR:04X}-"
            f"${HANDLER_ADDR + len(HANDLER) - 1:04X}"
        ),
        "escaped_bytes": 0,
        "r313_bytes_outside_handler_exact": True,
        "native_12EC_publication_bytes_exact": True,
    }


def construct(source: bytes) -> tuple[bytes, dict[str, Any]]:
    preimages = source_preimages(source)
    transaction = transaction_contract()
    semantic = semantic_contract()

    rom = bytearray(source)
    handler = bank_offset(MUX_BANK, HANDLER_ADDR)
    rom[handler:handler + len(HANDLER)] = HANDLER
    r305.r304.update_checksums(rom)
    candidate = bytes(rom)
    ownership = validate_candidate(source, candidate)
    sha = r305.r304.digest(candidate)
    if EXPECTED_CANDIDATE_SHA256 != "TO_BE_PINNED":
        r305.r304.require(sha == EXPECTED_CANDIDATE_SHA256,
                          f"r314 candidate identity drift: {sha}")

    receipt: dict[str, Any] = {
        "schema": "penta-stage1-scene0b-publication-commit-r314-construction-v1",
        "status": "construction-only",
        "historical_evidence_consumed": False,
        "fresh_live_qualification": False,
        "promotable": False,
        "emulator_invoked": False,
        "base": {
            "revision": "r313-early-selfheal-acknowledgment",
            "candidate_sha256": BASE_SHA256,
        },
        "candidate_sha256": sha,
        "checksums": {
            "header": f"{candidate[0x014D]:02X}",
            "global": candidate[0x014E:0x0150].hex().upper(),
        },
        "root_cause": (
            "r313 marks DADE current and invalidates both keys before the "
            "native hidden physical map has completed tile, attribute, "
            "postcopy, and hazard publication; acknowledgment must follow "
            "the completed physical-map publication"
        ),
        "patch": {
            "transaction_start": (
                f"bank31:${HANDLER_LABELS['repair_effect']:04X} "
                "writes CD 13 00 + invalidates DF53/DF57"
            ),
            "transaction_capability": "$A314 beneath exact $12E0 return",
            "native_work_between_start_and_commit": (
                "fixed:$42B1 dirty branch, tile/attr atomic copy, $42DB EI, "
                "postcopy/hazard, map-call RET"
            ),
            "display_flip_effect": (
                f"bank31:${HANDLER_LABELS['display_flip_effect']:04X}"
            ),
            "commit_effect": (
                f"bank31:${HANDLER_LABELS['commit_effect']:04X}"
            ),
            "commit_order": "write FF40 completed owner, then DADE CD->C4",
            "continuation": "fixed:$12EE; native $12EC bytes unchanged",
        },
        "preimage_contract": preimages,
        "offline_contract": {
            "transaction": transaction,
            "semantic": semantic,
        },
        "ownership": ownership,
        "timing": {
            "current_scene0B_handler_path": "same opcodes/cycles as r313",
            "current_scene02_handler_path": "same opcodes/cycles as r313",
            "ordinary_map_publication_delta": "0T; fixed:$12E0 exact",
            "renderer_inner_loop_delta": 0,
            "one_time_stale_repair": "stack arm plus post-map commit only",
            "release_speed_gate_required": True,
        },
        "required_live_gates": [
            "new commit-effect breakpoint is the sole repaired acknowledgment",
            "first acknowledged closed frame has immutable semantic attrs",
            "every repair-settle frame has exact tiles/attrs/CRAM/hazards",
            "both physical maps complete publication-owned full-plane oracles",
            "release speed matrix >=95% Stage1 and strict later-stage policy",
        ],
        "decision": "CONSTRUCTION_ONLY_LIVE_GATES_REQUIRED",
    }
    return candidate, receipt


def build(
    source: bytes, base_receipt_bytes: bytes,
    rejected_receipt_bytes: bytes,
) -> tuple[bytes, dict[str, Any]]:
    preimages = validate_preimages(source, base_receipt_bytes, rejected_receipt_bytes)
    candidate, receipt = construct(source)
    receipt.update({
        "schema": "penta-stage1-scene0b-publication-commit-r314-build-v1",
        "status": "STATIC_PASS_R314_LIVE_GATES_REQUIRED",
        "preimage_contract": preimages,
        "root_cause": (
            "r313 marks DADE current and invalidates both keys before the "
            "native hidden physical map has completed tile, attribute, "
            "postcopy, and hazard publication; rendered repair-settle "
            "sampling can therefore acknowledge one/four stale attr frames"
        ),
        "decision": "STATIC_PUBLICATION_TRANSACTION_LIVE_GATES_REQUIRED",
    })
    receipt["base"].update({
        "build_receipt_sha256": BASE_RECEIPT_SHA256,
        "rejected_live_receipt_sha256": REJECTED_LIVE_RECEIPT_SHA256,
    })
    del receipt["historical_evidence_consumed"], receipt["fresh_live_qualification"]
    return candidate, receipt


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", type=Path, default=BASE)
    parser.add_argument("--base-receipt", type=Path, default=BASE_RECEIPT)
    parser.add_argument(
        "--rejected-live-receipt", type=Path, default=REJECTED_LIVE_RECEIPT
    )
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--receipt", type=Path, default=DEFAULT_RECEIPT)
    args = parser.parse_args()
    output = r305.r304.checked_output(args.output, "candidate output")
    receipt_path = r305.r304.checked_output(args.receipt, "receipt output")
    candidate, receipt = build(
        args.base.read_bytes(),
        args.base_receipt.read_bytes(),
        args.rejected_live_receipt.read_bytes(),
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    receipt_path.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(candidate)
    receipt_path.write_bytes(r305.r304.receipt_bytes(receipt))
    print(json.dumps(receipt, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except AssertionError as error:
        print(f"FAIL: {error}")
        raise SystemExit(1)
