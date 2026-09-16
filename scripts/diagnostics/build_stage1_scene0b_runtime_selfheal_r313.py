#!/usr/bin/env python3
"""Build r313: repair stale scene-$0B DAD7 at its live RST entry.

r312 versioned the lazy installer, but an authenticated stationary scene-$0B
replay proved that none of the six installer guards executes on that route.
The fixed RST $18 decision does execute repeatedly and sends live D=$FF
directly to the serialized DAD7 payload.  Both operator states differ from the
candidate-owned runtime only at DADE-DAE0, where the stale gateway bypasses
the repaired scene-$0B split-key consumer.

This overlay redirects only RST $18's live branch through the existing fixed
bank-31 mux.  A new outer-return class compares the three gateway bytes in
exact scene $0B/SVBK1, repairs and invalidates both physical-map keys only on
mismatch, then restores the original register/stack contract and enters DAD7.
The non-live D!=FF DB80 route remains byte exact.  No emulator is invoked.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import build_stage1_runtime_epoch_r312 as r312


r311 = r312.r311
r305 = r312.r305
ROOT = r312.ROOT
TMP = r312.TMP
BASE = r312.DEFAULT_OUTPUT
BASE_RECEIPT = r312.DEFAULT_RECEIPT
DEFAULT_OUTPUT = TMP / "stage1-scene0b-runtime-selfheal-r313/candidate.gb"
DEFAULT_RECEIPT = (
    TMP / "stage1-scene0b-runtime-selfheal-r313/build-receipt.json"
)

BASE_SHA256 = r312.EXPECTED_CANDIDATE_SHA256
BASE_RECEIPT_SHA256 = (
    "3c677ced990956892c876d310207c4549f27016721ebf025db39990f3408f380"
)
BASE_SCHEMA = "penta-stage1-runtime-epoch-r312-build-v1"
EXPECTED_CANDIDATE_SHA256 = (
    "07e12b47c1561822c7dbe2c9f7d739c418ad6fcbb1822d2fa06726c705ec82e8"
)

RST18_ADDR = 0x0018
OLD_RST18 = bytes.fromhex("7A 3C CA D7 DA C3 80 DB")
NEW_RST18 = bytes.fromhex("7A 3C CA 13 00 C3 80 DB")
RST18_OPCODE_ADDR = 0x3492
RST18_LIVE_RETURN = RST18_OPCODE_ADDR + 1
RST18_CALLSITE_ADDR = 0x42A7
RST18_CALLSITE = bytes.fromhex(
    "2E 00 7C E0 A5 16 FF CD 85 34 28 05 F3 CD 13 DA"
)
ATOMIC_COPY_DI_ADDR = 0x42C0
ATOMIC_COPY_DI = bytes.fromhex("F3 F0 41 E6 03 FE 03 20 F8")
ATOMIC_COPY_EI_ADDR = 0x42DB
ATOMIC_COPY_EI = bytes.fromhex("FB 0D 20 E1")
DIRTY_RETURN_ADDR = 0x42B1
DIRTY_RETURN = bytes.fromhex("28 05 F3 CD 13 DA")
DIRTY_TAIL_BANK = 21
DIRTY_TAIL_ADDR = 0x4139
DIRTY_TAIL = bytes.fromhex("3E 01 B7 C3 61 00")

MUX_BANK = r305.BANK31
MUX_BRANCH_ADDR = 0x6C8A
OLD_MUX_BRANCH = bytes.fromhex("20 0E")
HANDLER_ADDR = r305.MUX_ADDR + len(r305.MUX)  # first byte after r305 mux
NEW_MUX_BRANCH_DISPLACEMENT = HANDLER_ADDR - (MUX_BRANCH_ADDR + 2)

STALE_GATEWAY = bytes.fromhex("C2 B9 DA")
CURRENT_GATEWAY = bytes.fromhex("C4 13 00")
GATEWAY_ADDR = 0xDADE
CACHE_ADDRS = (0xDF53, 0xDF57)
CHECKSUM_OFFSETS = r312.CHECKSUM_OFFSETS


def bank_offset(bank: int, address: int) -> int:
    return r312.bank_offset(bank, address)


def assemble_handler() -> tuple[bytes, dict[str, int]]:
    a = r305.Asm(HANDLER_ADDR)
    # Existing mux entry saved caller HL and left HL at SP+4, the low byte of
    # the outer return. Only the live decision helper's RST return $3493 owns
    # this class. All other unexpected callers keep r305's fail-closed ABI.
    a.label("entry")
    a.db(0xFE, RST18_LIVE_RETURN & 0xFF)
    a.jr(0x20, "unknown")
    a.db(0x23, 0x7E, 0xFE, RST18_LIVE_RETURN >> 8)
    a.jr(0x20, "unknown")

    # DAD7's changed predicate is needed only in low-health scene $0B. The
    # payload and semantic caches live in SVBK1; never touch another bank.
    a.db(0xFA, 0x80, 0xD8, 0xFE, 0x0B)
    a.jr(0x20, "resume")
    a.db(0xF0, 0x70, 0xE6, 0x07, 0xFE, 0x01)
    a.jr(0x20, "resume")

    # Compare all three candidate-owned transfer bytes. A current runtime is
    # observation-only. Only the exact captured C2 B9 DA preimage is writable;
    # an unknown or partially corrupt payload resumes unchanged and therefore
    # cannot be silently certified as candidate-owned.
    for index, value in enumerate(CURRENT_GATEWAY):
        address = GATEWAY_ADDR + index
        a.db(0xFA, address & 0xFF, address >> 8, 0xFE, value)
        a.jr(0x20, "check_old")
    a.jr(0x18, "resume")

    a.label("check_old")
    # FFB7 is the authoritative Stage-1 marker.  Keep this off the already
    # current hot path, but require it before admitting the legacy preimage.
    a.db(0xF0, 0xB7, 0xFE, 0x02)
    a.jr(0x20, "resume")
    for index, value in enumerate(STALE_GATEWAY):
        address = GATEWAY_ADDR + index
        a.db(0xFA, address & 0xFF, address >> 8, 0xFE, value)
        a.jr(0x20, "resume")

    a.label("repair")
    # The only three-byte mutation is interrupt-atomic.  The native caller is
    # immediately before its dirty publication DI ($42B3), has a second DI at
    # $42C0, and reaches the existing EI at $42DB.  Do not enable IME locally:
    # no interrupt can observe a partial transfer, while the native path owns
    # the eventual IME transition for both Z/NZ return shapes.
    a.db(0xF3)
    for index, value in enumerate(CURRENT_GATEWAY):
        address = GATEWAY_ADDR + index
        a.db(0x3E, value, 0xEA, address & 0xFF, address >> 8)
    # The repaired gateway must not accept an equal stale semantic key. Force
    # one ordinary dirty decision for each physical BG map.
    a.db(0x3E, 0xFF)
    for address in CACHE_ADDRS:
        a.db(0xEA, address & 0xFF, address >> 8)
    a.label("repair_effect")

    # Replace only the dispatcher's synthetic $084D frame with DAD7. After
    # POP HL, fixed:$0061 maps bank1 and RET enters DAD7; DAD7's own RET then
    # consumes the untouched real $3493 RST frame.
    a.label("resume")
    a.db(0xF8, 0x02, 0x36, r305.RUNTIME_RELOCATED_ADDR & 0xFF)
    a.db(0x23, 0x36, r305.RUNTIME_RELOCATED_ADDR >> 8)
    a.db(0xE1, 0x3E, 0x01, 0xC3, 0x61, 0x00)

    a.label("unknown")
    a.db(0xE1, 0x3E, 0x01, 0xB7, 0xC9)
    code = a.finish()
    return code, dict(a.labels)


HANDLER, HANDLER_LABELS = assemble_handler()
NEW_MUX_BRANCH = bytes((0x20, NEW_MUX_BRANCH_DISPLACEMENT & 0xFF))


def owned_ranges() -> set[int]:
    return (
        set(range(RST18_ADDR, RST18_ADDR + len(NEW_RST18)))
        | set(range(
            bank_offset(MUX_BANK, MUX_BRANCH_ADDR),
            bank_offset(MUX_BANK, MUX_BRANCH_ADDR) + len(NEW_MUX_BRANCH),
        ))
        | set(range(
            bank_offset(MUX_BANK, HANDLER_ADDR),
            bank_offset(MUX_BANK, HANDLER_ADDR) + len(HANDLER),
        ))
    )


def _push16(state: dict[str, Any], value: int) -> None:
    state["sp"] = (state["sp"] - 2) & 0xFFFF
    state["mem"][state["sp"]] = value & 0xFF
    state["mem"][(state["sp"] + 1) & 0xFFFF] = value >> 8


def _pop16(state: dict[str, Any]) -> int:
    value = (
        state["mem"][state["sp"]]
        | (state["mem"][(state["sp"] + 1) & 0xFFFF] << 8)
    )
    state["sp"] = (state["sp"] + 2) & 0xFFFF
    return value


def _cp_flags(a: int, value: int) -> int:
    return (
        (0x80 if a == value else 0)
        | 0x40
        | (0x20 if (a & 0x0F) < (value & 0x0F) else 0)
        | (0x10 if a < value else 0)
    )


def execute_route(
    source: bytes,
    *,
    scene: int,
    svbk: int,
    ffb7: int,
    gateway: bytes,
    start: int = 0x0013,
    stop: int = r305.RUNTIME_RELOCATED_ADDR,
    original_hl: int = 0x9800,
    outer_return: int = RST18_LIVE_RETURN,
) -> dict[str, Any]:
    """Decode/execute the emitted route; this is independent of its assembler.

    The deliberately small LR35902 model accepts only opcodes reachable in
    the fixed bridge, existing r305 mux, new handler, mapper, and DAD7 prefix.
    Any unexpected opcode is a hard build failure rather than an inferred
    semantic result.
    """
    r305.r304.require(len(gateway) == 3, "gateway model width changed")
    mem = bytearray(0x10000)
    mem[:0x4000] = source[:0x4000]
    mux = bytearray(r305.MUX)
    branch_index = MUX_BRANCH_ADDR - r305.MUX_ADDR
    mux[branch_index:branch_index + len(NEW_MUX_BRANCH)] = NEW_MUX_BRANCH
    mem[r305.MUX_ADDR:r305.MUX_ADDR + len(mux)] = mux
    mem[HANDLER_ADDR:HANDLER_ADDR + len(HANDLER)] = HANDLER
    # Model the selected gateway on the candidate-owned runtime template.
    # Historical captures are audited separately, never used as model code.
    runtime = bytearray(r312.desired_dad7(source, r312.BANKS[0]))
    r305.r304.require(len(runtime) == r305.RUNTIME_LENGTH,
                      "source runtime model width changed")
    runtime[7:10] = gateway
    mem[r305.RUNTIME_RELOCATED_ADDR:
        r305.RUNTIME_RELOCATED_ADDR + len(runtime)] = runtime
    consumer = bank_offset(21, 0x4100)
    mem[0x4100:0x4140] = source[consumer:consumer + 0x40]
    mem[0xD880] = scene & 0xFF
    mem[0xFF70] = svbk & 0xFF
    mem[0xFFB7] = ffb7 & 0xFF
    mem[CACHE_ADDRS[0]] = 0x11
    mem[CACHE_ADDRS[1]] = 0x22

    initial_sp = 0xC100
    # RST $18 has already pushed $3493; $3485's caller return is $42B1.
    mem[initial_sp:initial_sp + 4] = bytes((
        outer_return & 0xFF, outer_return >> 8, 0xB1, 0x42,
    ))
    state: dict[str, Any] = {
        "pc": start,
        "sp": initial_sp,
        "a": 0x00,
        "f": 0xB0,  # INC $FF result at fixed:$0019, Carry preserved set.
        "b": 0x12,
        "c": 0x34,
        "d": 0xFF,
        "e": 0x56,
        "h": original_hl >> 8,
        "l": original_hl & 0xFF,
        "ime": True,
        "mem": mem,
        "cycles": 0,
        "trace": [],
        "writes": [],
        "initial_sp": initial_sp,
        "original_hl": original_hl,
    }

    def read16(address: int) -> int:
        return mem[address] | (mem[(address + 1) & 0xFFFF] << 8)

    def write(address: int, value: int) -> None:
        mem[address] = value & 0xFF
        state["writes"].append({
            "pc": pc,
            "address": address,
            "value": value & 0xFF,
            "ime": state["ime"],
        })

    for _step in range(512):
        pc = state["pc"]
        if pc == stop:
            break
        opcode = mem[pc]
        next_pc = (pc + 1) & 0xFFFF
        cycles = 0
        if opcode == 0x3E:  # LD A,d8
            state["a"] = mem[next_pc]
            next_pc = (next_pc + 1) & 0xFFFF
            cycles = 8
        elif opcode == 0xC3:  # JP a16
            next_pc = read16(next_pc)
            cycles = 16
        elif opcode == 0xCD:  # CALL a16
            target = read16(next_pc)
            _push16(state, (pc + 3) & 0xFFFF)
            next_pc = target
            cycles = 24
        elif opcode in (0xC2, 0xC4):  # JP/CALL NZ,a16
            target = read16(next_pc)
            taken = not bool(state["f"] & 0x80)
            if opcode == 0xC2:
                next_pc = target if taken else (pc + 3) & 0xFFFF
                cycles = 16 if taken else 12
            else:
                if taken:
                    _push16(state, (pc + 3) & 0xFFFF)
                    next_pc = target
                    cycles = 24
                else:
                    next_pc = (pc + 3) & 0xFFFF
                    cycles = 12
        elif opcode == 0xC9:  # RET
            next_pc = _pop16(state)
            cycles = 16
        elif opcode == 0xE5:  # PUSH HL
            _push16(state, (state["h"] << 8) | state["l"])
            cycles = 16
        elif opcode == 0xE1:  # POP HL
            value = _pop16(state)
            state["h"], state["l"] = value >> 8, value & 0xFF
            cycles = 12
        elif opcode == 0xF8:  # LD HL,SP+e8
            raw = mem[next_pc]
            signed = raw if raw < 0x80 else raw - 0x100
            sp = state["sp"]
            value = (sp + signed) & 0xFFFF
            state["h"], state["l"] = value >> 8, value & 0xFF
            state["f"] = (
                (0x20 if ((sp & 0x0F) + (raw & 0x0F)) > 0x0F else 0)
                | (0x10 if ((sp & 0xFF) + raw) > 0xFF else 0)
            )
            next_pc = (next_pc + 1) & 0xFFFF
            cycles = 12
        elif opcode == 0x7E:  # LD A,[HL]
            hl = (state["h"] << 8) | state["l"]
            state["a"] = mem[hl]
            cycles = 8
        elif opcode == 0x7C:  # LD A,H
            state["a"] = state["h"]
            cycles = 4
        elif opcode == 0x47:  # LD B,A
            state["b"] = state["a"]
            cycles = 4
        elif opcode == 0x4F:  # LD C,A
            state["c"] = state["a"]
            cycles = 4
        elif opcode == 0x5F:  # LD E,A
            state["e"] = state["a"]
            cycles = 4
        elif opcode == 0x16:  # LD D,d8
            state["d"] = mem[next_pc]
            next_pc = (next_pc + 1) & 0xFFFF
            cycles = 8
        elif opcode == 0x1A:  # LD A,[DE]
            de = (state["d"] << 8) | state["e"]
            state["a"] = mem[de]
            cycles = 8
        elif opcode == 0x12:  # LD [DE],A
            de = (state["d"] << 8) | state["e"]
            write(de, state["a"])
            cycles = 8
        elif opcode == 0x13:  # INC DE
            value = (((state["d"] << 8) | state["e"]) + 1) & 0xFFFF
            state["d"], state["e"] = value >> 8, value & 0xFF
            cycles = 8
        elif opcode == 0x23:  # INC HL
            value = (((state["h"] << 8) | state["l"]) + 1) & 0xFFFF
            state["h"], state["l"] = value >> 8, value & 0xFF
            cycles = 8
        elif opcode == 0x36:  # LD [HL],d8
            hl = (state["h"] << 8) | state["l"]
            write(hl, mem[next_pc])
            next_pc = (next_pc + 1) & 0xFFFF
            cycles = 12
        elif opcode == 0xFA:  # LD A,[a16]
            state["a"] = mem[read16(next_pc)]
            next_pc = (pc + 3) & 0xFFFF
            cycles = 16
        elif opcode == 0xEA:  # LD [a16],A
            write(read16(next_pc), state["a"])
            next_pc = (pc + 3) & 0xFFFF
            cycles = 16
        elif opcode == 0xF0:  # LDH A,[a8]
            state["a"] = mem[0xFF00 | mem[next_pc]]
            next_pc = (next_pc + 1) & 0xFFFF
            cycles = 12
        elif opcode == 0xE0:  # LDH [a8],A
            write(0xFF00 | mem[next_pc], state["a"])
            next_pc = (next_pc + 1) & 0xFFFF
            cycles = 12
        elif opcode == 0xFE:  # CP d8
            state["f"] = _cp_flags(state["a"], mem[next_pc])
            next_pc = (next_pc + 1) & 0xFFFF
            cycles = 8
        elif opcode == 0xE6:  # AND d8
            state["a"] &= mem[next_pc]
            state["f"] = (0x80 if state["a"] == 0 else 0) | 0x20
            next_pc = (next_pc + 1) & 0xFFFF
            cycles = 8
        elif opcode == 0xEE:  # XOR d8
            state["a"] ^= mem[next_pc]
            state["f"] = 0x80 if state["a"] == 0 else 0
            next_pc = (next_pc + 1) & 0xFFFF
            cycles = 8
        elif opcode == 0xA8:  # XOR B
            state["a"] ^= state["b"]
            state["f"] = 0x80 if state["a"] == 0 else 0
            cycles = 4
        elif opcode == 0xB9:  # CP C
            state["f"] = _cp_flags(state["a"], state["c"])
            cycles = 4
        elif opcode == 0xB7:  # OR A
            state["f"] = 0x80 if state["a"] == 0 else 0
            cycles = 4
        elif opcode == 0x3C:  # INC A
            old = state["a"]
            state["a"] = (old + 1) & 0xFF
            state["f"] = (
                (0x80 if state["a"] == 0 else 0)
                | (0x20 if (old & 0x0F) == 0x0F else 0)
                | (state["f"] & 0x10)
            )
            cycles = 4
        elif opcode == 0x3D:  # DEC A
            old = state["a"]
            state["a"] = (old - 1) & 0xFF
            state["f"] = (
                (0x80 if state["a"] == 0 else 0)
                | 0x40
                | (0x20 if (old & 0x0F) == 0 else 0)
                | (state["f"] & 0x10)
            )
            cycles = 4
        elif opcode == 0xF3:  # DI
            state["ime"] = False
            cycles = 4
        elif opcode in (0x18, 0x20, 0x28):  # JR, JR NZ, JR Z
            displacement = mem[next_pc]
            if displacement >= 0x80:
                displacement -= 0x100
            taken = (
                opcode == 0x18
                or (opcode == 0x20 and not (state["f"] & 0x80))
                or (opcode == 0x28 and bool(state["f"] & 0x80))
            )
            next_pc = (
                (pc + 2 + displacement) & 0xFFFF
                if taken else (pc + 2) & 0xFFFF
            )
            cycles = 12 if taken else 8
        else:
            raise AssertionError(
                f"route model reached unsupported ${opcode:02X} at ${pc:04X}"
            )
        state["trace"].append((pc, opcode, cycles, state["ime"]))
        state["cycles"] += cycles
        state["pc"] = next_pc
    else:
        raise AssertionError("route model did not reach its exact stop PC")
    return state


def source_preimages(source: bytes) -> dict[str, Any]:
    r305.r304.require(r305.r304.digest(source) == BASE_SHA256,
                      "r313 requires exact r312")
    r305.r304.require(source[RST18_ADDR:RST18_ADDR + len(OLD_RST18)]
                      == OLD_RST18, "fixed RST18 route changed")
    r305.r304.require(source[RST18_OPCODE_ADDR] == 0xDF,
                      "live helper is no longer RST $18 at $3492")
    r305.r304.require(
        source[RST18_CALLSITE_ADDR:
               RST18_CALLSITE_ADDR + len(RST18_CALLSITE)] == RST18_CALLSITE,
        "live $42AE->$3485 decision call/dirty branch changed",
    )
    r305.r304.require(
        source[DIRTY_RETURN_ADDR:DIRTY_RETURN_ADDR + len(DIRTY_RETURN)]
        == DIRTY_RETURN,
        "native dirty-return DI path changed",
    )
    r305.r304.require(
        source[ATOMIC_COPY_DI_ADDR:
               ATOMIC_COPY_DI_ADDR + len(ATOMIC_COPY_DI)] == ATOMIC_COPY_DI,
        "native atomic-copy DI path changed",
    )
    r305.r304.require(
        source[ATOMIC_COPY_EI_ADDR:
               ATOMIC_COPY_EI_ADDR + len(ATOMIC_COPY_EI)] == ATOMIC_COPY_EI,
        "native atomic-copy EI path changed",
    )
    dirty_tail = bank_offset(DIRTY_TAIL_BANK, DIRTY_TAIL_ADDR)
    r305.r304.require(
        source[dirty_tail:dirty_tail + len(DIRTY_TAIL)] == DIRTY_TAIL,
        "bank21 dirty/NZ mapper tail changed",
    )
    branch = bank_offset(MUX_BANK, MUX_BRANCH_ADDR)
    r305.r304.require(source[branch:branch + len(OLD_MUX_BRANCH)]
                      == OLD_MUX_BRANCH, "bank31 mux unknown branch changed")
    handler = bank_offset(MUX_BANK, HANDLER_ADDR)
    r305.r304.require(source[handler:handler + len(HANDLER)]
                      == bytes([0xFF]) * len(HANDLER),
                      "bank31 self-heal cave is no longer erased")
    r305.r304.require(0 < NEW_MUX_BRANCH_DISPLACEMENT <= 0x7F,
                      "bank31 self-heal branch is out of JR range")

    desired = r312.desired_dad7(source, r312.BANKS[0])
    r305.r304.require(desired[7:10] == CURRENT_GATEWAY,
                      "candidate DAD7 gateway changed")
    return {
        "RST18_preimage": OLD_RST18.hex(" ").upper(),
        "legacy_gateway_model": STALE_GATEWAY.hex(" ").upper(),
        "candidate_gateway": CURRENT_GATEWAY.hex(" ").upper(),
        "live_RST_opcode": "$3492=DF; hardware return is $3493",
        "live_callsite": "$42AE CALL $3485; $42B1 JR Z; $42B3 DI",
        "atomic_copy": "$42C0 DI; first guaranteed EI $42DB",
        "dirty_tail": "bank21:$4139 3E 01 B7 C3 61 00 (A=1,NZ,map bank1)",
        "bank31_cave_preimage": f"{len(HANDLER)} bytes FF",
    }


def validate_preimages(source: bytes, base_receipt_bytes: bytes) -> dict[str, Any]:
    r305.r304.require(r305.r304.digest(source) == BASE_SHA256,
                      "r313 requires exact r312")
    r305.r304.require(
        r305.r304.digest(base_receipt_bytes) == BASE_RECEIPT_SHA256,
        "r312 build receipt identity changed",
    )
    receipt = json.loads(base_receipt_bytes)
    r305.r304.require(receipt.get("schema") == BASE_SCHEMA,
                      "r312 build receipt schema changed")
    r305.r304.require(receipt.get("candidate_sha256") == BASE_SHA256,
                      "r312 receipt names another candidate")
    contract = source_preimages(source)
    r305.r304.require(r312.CAPTURED_STALE_DAD7[7:10] == STALE_GATEWAY,
                      "captured stale DAD7 gateway changed")
    # The old execution model used this template. Authenticate its unchanged
    # non-gateway bytes before reporting the historical model results.
    desired = bytearray(r312.desired_dad7(source, r312.BANKS[0]))
    desired[7:10] = STALE_GATEWAY
    r305.r304.require(bytes(desired) == r312.CAPTURED_STALE_DAD7,
                      "captured runtime template differs outside gateway")
    del contract["legacy_gateway_model"]
    return {
        **contract,
        "r312_build_receipt_sha256": BASE_RECEIPT_SHA256,
        "captured_gateway": STALE_GATEWAY.hex(" ").upper(),
        "known_capture_full_installer_differences": [
            "DADE C2->C4", "DADF B9->13", "DAE0 DA->00",
        ],
        "all_other_DA00_DAFF_DB80_DBFC_installer_bytes": "exact",
    }


def _watched_writes(state: dict[str, Any]) -> list[tuple[int, int, bool]]:
    owned = set(range(GATEWAY_ADDR, GATEWAY_ADDR + 3)) | set(CACHE_ADDRS)
    return [
        (row["address"], row["value"], row["ime"])
        for row in state["writes"] if row["address"] in owned
    ]


def stack_contract(source: bytes) -> dict[str, Any]:
    current = execute_route(
        source, scene=0x0B, svbk=0xF9, ffb7=0x02,
        gateway=CURRENT_GATEWAY,
    )
    initial_sp = current["initial_sp"]
    r305.r304.require(current["sp"] == initial_sp,
                      "self-heal changed SP before DAD7")
    r305.r304.require(
        bytes(current["mem"][initial_sp:initial_sp + 4])
        == bytes.fromhex("93 34 B1 42"),
        "self-heal changed the real $3493/$42B1 frames",
    )
    r305.r304.require(
        (current["h"] << 8) | current["l"] == current["original_hl"],
        "self-heal did not restore caller HL",
    )
    r305.r304.require(
        current["a"] == 1 and current["mem"][0xDC09] == 1
        and current["mem"][0xFF99] == 1,
        "self-heal did not restore the exact bank1 mapper ABI at DAD7",
    )

    compared_fields = ("pc", "sp", "a", "f", "b", "c", "d", "e",
                       "h", "l", "ime")
    byte_exact_scenes: dict[str, bool] = {}
    for scene in (0x02, 0x0B):
        detour = execute_route(
            source, scene=scene, svbk=0xF9, ffb7=0x02,
            gateway=CURRENT_GATEWAY, stop=0x4100,
        )
        direct = execute_route(
            source, scene=scene, svbk=0xF9, ffb7=0x02,
            gateway=CURRENT_GATEWAY, start=r305.RUNTIME_RELOCATED_ADDR,
            stop=0x4100,
        )
        r305.r304.require(
            all(detour[field] == direct[field] for field in compared_fields),
            f"scene${scene:02X} detour changed DAD7 output/ABI",
        )
        r305.r304.require(
            bytes(detour["mem"][initial_sp:initial_sp + 4])
            == bytes(direct["mem"][initial_sp:initial_sp + 4]),
            f"scene${scene:02X} detour changed real return bytes",
        )
        byte_exact_scenes[f"{scene:02X}"] = True

    # Execute the repaired route through both physical-map consumers and the
    # real $3493 RET.  The FF invalidation forces bank21's exact $4139 dirty
    # tail, which returns A=1/NZ to the native $42B1 branch with IME still off.
    dirty_returns: dict[str, Any] = {}
    for hl, cache in ((0x9800, 0xDF53), (0x9C00, 0xDF57)):
        repaired = execute_route(
            source, scene=0x0B, svbk=0xF9, ffb7=0x02,
            gateway=STALE_GATEWAY, stop=DIRTY_RETURN_ADDR, original_hl=hl,
        )
        r305.r304.require(repaired["a"] == 1 and not (repaired["f"] & 0x80),
                          "repaired consumer did not return dirty/NZ")
        r305.r304.require(not repaired["ime"],
                          "repair enabled IME before native $42B1")
        r305.r304.require(repaired["sp"] == initial_sp + 4,
                          "DAD7/$3493 did not consume exactly two real frames")
        r305.r304.require(
            (repaired["h"] << 8) | repaired["l"] == hl,
            "dirty consumer changed physical destination HL",
        )
        other = CACHE_ADDRS[1] if cache == CACHE_ADDRS[0] else CACHE_ADDRS[0]
        r305.r304.require(repaired["mem"][cache] == 0x00
                          and repaired["mem"][other] == 0xFF,
                          "dirty consumer did not publish one invalidated map")
        dirty_returns[f"{hl:04X}"] = {
            "cache": f"{cache:04X}", "A": "01", "Z": False,
            "IME": False, "PC": "42B1",
        }
    return {
        "model": "independent emitted-opcode execution",
        "RST_opcode": "$3492 exact byte DF; pushed return $3493",
        "entry": "[084D,3493,42B1] after mux CALL",
        "after_rewrite_and_HL_restore": "[DAD7,3493,42B1]",
        "return_chain": "fixed:$0061 -> DAD7 -> $3493 -> $42B1",
        "real_frames_and_net_SP_exact_at_DAD7": True,
        "current_scene_outputs_flags_BCDEHL_SP_IME_exact": byte_exact_scenes,
        "repair_dirty_returns": dirty_returns,
        "atomic_IME_chain": "handler DI -> $42B1 -> $42B3/$42C0 DI -> $42DB EI",
    }


def semantic_contract(source: bytes) -> dict[str, Any]:
    expected_repair = [
        (0xDADE, 0xC4, False), (0xDADF, 0x13, False),
        (0xDAE0, 0x00, False), (0xDF53, 0xFF, False),
        (0xDF57, 0xFF, False),
    ]
    executions = 0

    def check(
        *, scene: int = 0x0B, svbk: int = 0xF9, ffb7: int = 0x02,
        gateway: bytes = STALE_GATEWAY, outer: int = RST18_LIVE_RETURN,
        repair: bool,
    ) -> None:
        nonlocal executions
        exact_outer = outer == RST18_LIVE_RETURN
        state = execute_route(
            source, scene=scene, svbk=svbk, ffb7=ffb7,
            gateway=gateway, outer_return=outer,
            stop=r305.RUNTIME_RELOCATED_ADDR if exact_outer else outer,
        )
        writes = _watched_writes(state)
        r305.r304.require(writes == (expected_repair if repair else []),
                          "emitted self-heal write predicate changed")
        result = bytes(state["mem"][GATEWAY_ADDR:GATEWAY_ADDR + 3])
        r305.r304.require(result == (CURRENT_GATEWAY if repair else gateway),
                          "emitted self-heal gateway result changed")
        if repair:
            r305.r304.require(not state["ime"],
                              "repair writes were not protected by DI")
        if not exact_outer:
            r305.r304.require(
                state["a"] == 1 and not (state["f"] & 0x80),
                "wrong outer key changed r305 unknown A/NZ ABI",
            )
            r305.r304.require(
                (state["h"] << 8) | state["l"] == state["original_hl"],
                "wrong outer key did not restore HL",
            )
            r305.r304.require(
                state["sp"] == state["initial_sp"] + 2
                and bytes(state["mem"][state["sp"]:state["sp"] + 2])
                == bytes.fromhex("B1 42"),
                "wrong outer key changed caller frame/SP",
            )
            r305.r304.require(
                state["mem"][0xDC09] == state["mem"][0xFF99] == 1,
                "wrong outer key did not restore the bank1 mapper",
            )
        executions += 1

    # Exhaust every byte of each independent scope dimension against the
    # exact captured preimage.  SVBK is intentionally raw: hardware high bits
    # are ignored and every value whose low three bits equal one is admitted.
    for scene in range(256):
        check(scene=scene, repair=scene == 0x0B)
    for svbk in range(256):
        check(svbk=svbk, repair=(svbk & 0x07) == 1)
    for ffb7 in range(256):
        check(ffb7=ffb7, repair=ffb7 == 0x02)

    # Exhaust all 765 one-byte mutations of the captured triplet.  Only the
    # unchanged exact C2 B9 DA input (seen once in each byte dimension) writes.
    for index in range(3):
        for value in range(256):
            gateway = bytearray(STALE_GATEWAY)
            gateway[index] = value
            check(gateway=bytes(gateway), repair=value == STALE_GATEWAY[index])

    # Exhaust both bytes of the outer stack key independently.  A wrong key
    # must return through r305's old unknown ABI and cannot touch runtime/cache.
    for low in range(256):
        outer = (RST18_LIVE_RETURN & 0xFF00) | low
        check(outer=outer, repair=outer == RST18_LIVE_RETURN)
    for high in range(256):
        outer = (high << 8) | (RST18_LIVE_RETURN & 0xFF)
        check(outer=outer, repair=outer == RST18_LIVE_RETURN)

    for gateway in (
        CURRENT_GATEWAY, bytes.fromhex("00 00 00"),
        bytes.fromhex("C2 13 DA"), bytes.fromhex("FF FF FF"),
    ):
        check(gateway=gateway, repair=False)
    r305.r304.require(executions == 2052,
                      "emitted semantic execution population changed")
    return {
        "emitted_opcode_executions": executions,
        "repair_predicate": (
            "outer=$3493,D880=0B,(SVBK&7)=1,FFB7=02," 
            "DADE-E0 exact C2 B9 DA"
        ),
        "scene_values_exhausted": 256,
        "raw_SVBK_values_exhausted": 256,
        "FFB7_values_exhausted": 256,
        "single_gateway_byte_mutations_exhausted": 768,
        "outer_low_high_values_exhausted": 512,
        "current_and_unknown_controls": 4,
        "repair_writes": [
            "DADE=C4", "DADF=13", "DAE0=00", "DF53=FF", "DF57=FF",
        ],
        "all_repair_writes_IME_disabled": True,
        "current_gateway_cache_writes": 0,
        "unknown_gateway_writes": 0,
    }


def source_timing_contract(source: bytes) -> dict[str, Any]:
    cases = {
        "scene0B_current": execute_route(
            source, scene=0x0B, svbk=0xF9, ffb7=0x02,
            gateway=CURRENT_GATEWAY,
        ),
        "scene02_current": execute_route(
            source, scene=0x02, svbk=0xF9, ffb7=0x02,
            gateway=CURRENT_GATEWAY,
        ),
        "scene0B_exact_legacy_repair": execute_route(
            source, scene=0x0B, svbk=0xF9, ffb7=0x02,
            gateway=STALE_GATEWAY,
        ),
    }
    expected = {
        "scene0B_current": (220, 304, 76, 600),
        "scene02_current": (220, 164, 76, 460),
        "scene0B_exact_legacy_repair": (220, 472, 76, 768),
    }
    paths: dict[str, Any] = {}
    for name, state in cases.items():
        trace = state["trace"]
        first = next(index for index, row in enumerate(trace)
                     if row[0] == HANDLER_ADDR)
        last = max(index for index, row in enumerate(trace)
                   if HANDLER_ADDR <= row[0] < HANDLER_ADDR + len(HANDLER))
        measured = (
            sum(row[2] for row in trace[:first]),
            sum(row[2] for row in trace[first:last + 1]),
            sum(row[2] for row in trace[last + 1:]),
            state["cycles"],
        )
        r305.r304.require(measured == expected[name],
                          f"emitted {name} timing changed: {measured}")
        paths[name] = {
            "fixed_dispatch_mux_prefix": measured[0],
            "handler_through_mapper_jump": measured[1],
            "final_mapper": measured[2],
            "delta_t_cycles": measured[3],
        }
    return {
        "model": "decoded emitted bytes and branch outcomes",
        "measurement_boundary": (
            "redirect target $0013 through mapper RET immediately before DAD7; "
            "pre-DAD7 detour overhead, excluding downstream DAD7/consumer"
        ),
        "paths": paths,
        "current_gateway_cache_writes": 0,
        "renderer_inner_loop_delta": 0,
        "atomic_group_D_not_FF_route_delta": 0,
    }


def timing_contract(source: bytes) -> dict[str, Any]:
    contract = source_timing_contract(source)
    paths = contract["paths"]
    hot_average = paths["scene0B_current"]["delta_t_cycles"] * 23 / 162
    first_replay_average = (
        paths["scene0B_exact_legacy_repair"]["delta_t_cycles"]
        + paths["scene0B_current"]["delta_t_cycles"] * 22
    ) / 162
    return {
        **contract,
        "observed_rejected_route_density": "23 DAD7 entries / 162 frames",
        "steady_average_t_per_frame": f"{hot_average:.2f}",
        "steady_frame_budget_fraction": f"{hot_average / 70224 * 100:.4f}%",
        "first_repair_average_t_per_frame": f"{first_replay_average:.2f}",
        "first_repair_frame_budget_fraction": (
            f"{first_replay_average / 70224 * 100:.4f}%"
        ),
    }


def validate_candidate(source: bytes, candidate: bytes) -> dict[str, Any]:
    r305.r304.require(
        len(source) == len(candidate) == r305.r304.ROM_SIZE,
        "r313 candidate size changed",
    )
    changed = r305.r304.delta(source, candidate)
    functional = r305.r304.delta(source, candidate, functional=True)
    expected = {offset for offset in owned_ranges()
                if source[offset] != candidate[offset]}
    r305.r304.require(functional == expected,
                      "r313 functional delta differs from exact patch")
    r305.r304.require(changed <= owned_ranges() | CHECKSUM_OFFSETS,
                      "r313 escaped self-heal/checksum ownership")
    r305.r304.require(candidate[RST18_ADDR:RST18_ADDR + len(NEW_RST18)]
                      == NEW_RST18, "r313 RST18 route changed")
    branch = bank_offset(MUX_BANK, MUX_BRANCH_ADDR)
    r305.r304.require(candidate[branch:branch + len(NEW_MUX_BRANCH)]
                      == NEW_MUX_BRANCH, "r313 mux branch changed")
    handler = bank_offset(MUX_BANK, HANDLER_ADDR)
    r305.r304.require(candidate[handler:handler + len(HANDLER)] == HANDLER,
                      "r313 self-heal handler changed")
    # Existing attr/menu mux bytes remain exact except the one reviewed JR.
    mux = bank_offset(MUX_BANK, r305.MUX_ADDR)
    for index, pair in enumerate(zip(
        source[mux:mux + len(r305.MUX)],
        candidate[mux:mux + len(r305.MUX)], strict=True,
    )):
        address = r305.MUX_ADDR + index
        if address == MUX_BRANCH_ADDR + 1:
            continue
        r305.r304.require(pair[0] == pair[1],
                          f"existing mux drift at ${address:04X}")
    return {
        "functional_changed_bytes": len(functional),
        "changed_offsets": [f"0x{offset:06X}" for offset in sorted(functional)],
        "owned_ranges": [
            "fixed:$0018-$001F RST18 live target",
            "bank31:$6C8A-$6C8B unknown-branch target",
            f"bank31:${HANDLER_ADDR:04X}-${HANDLER_ADDR + len(HANDLER)-1:04X}",
        ],
        "escaped_bytes": 0,
        "r312_other_bytes_exact": True,
    }


def construct(source: bytes) -> tuple[bytes, dict[str, Any]]:
    preimages = source_preimages(source)
    rom = bytearray(source)
    rom[RST18_ADDR:RST18_ADDR + len(NEW_RST18)] = NEW_RST18
    branch = bank_offset(MUX_BANK, MUX_BRANCH_ADDR)
    rom[branch:branch + len(NEW_MUX_BRANCH)] = NEW_MUX_BRANCH
    handler = bank_offset(MUX_BANK, HANDLER_ADDR)
    rom[handler:handler + len(HANDLER)] = HANDLER
    r305.r304.update_checksums(rom)
    candidate = bytes(rom)
    ownership = validate_candidate(source, candidate)
    abi = stack_contract(source)
    semantic = semantic_contract(source)
    timing = source_timing_contract(source)
    sha = r305.r304.digest(candidate)
    if EXPECTED_CANDIDATE_SHA256 != "TO_BE_PINNED":
        r305.r304.require(sha == EXPECTED_CANDIDATE_SHA256,
                          f"r313 candidate identity drift: {sha}")

    receipt: dict[str, Any] = {
        "schema": "penta-stage1-scene0b-runtime-selfheal-r313-construction-v1",
        "status": "construction-only",
        "historical_evidence_consumed": False,
        "fresh_live_qualification": False,
        "promotable": False,
        "emulator_invoked": False,
        "base": {
            "revision": "r312-unreachable-epoch-guard",
            "candidate_sha256": BASE_SHA256,
        },
        "candidate_sha256": sha,
        "checksums": {
            "header": f"{candidate[0x014D]:02X}",
            "global": candidate[0x014E:0x0150].hex().upper(),
        },
        "root_cause": (
            "stationary scene0B repeatedly executes serialized DAD7 without "
            "reaching any DF51 lazy-installer gate; stale JP NZ,$DAB9 "
            "bypasses the split-key consumer and physical attr publication"
        ),
        "patch": {
            "RST18_live_target": "$DAD7->$0013",
            "mux_new_outer_return": "$3493",
            "selfheal_handler": (
                f"bank31:${HANDLER_ADDR:04X}-"
                f"${HANDLER_ADDR + len(HANDLER)-1:04X}"
            ),
            "runtime_bytes": "DADE-E0 C4 13 00",
            "repair_cache_invalidation": "DF53=DF57=FF",
        },
        "preimage_contract": preimages,
        "offline_contract": {
            "semantic": semantic, "stack_abi": abi, "timing": timing,
        },
        "ownership": ownership,
        "timing": timing | {
            "scope": "one bank31 detour per live D=$FF map decision",
            "normal_scene02_output_flags_BCDEHL_SP": "byte-exact after DAD7",
            "release_speed_gate_required": True,
        },
        "required_live_gates": [
            "exact two-capture scene0B menu roundtrip with self-heal audit",
            "zero wall/red-green/weird-edge/yellow-trail/gray-spike frames",
            "candidate DAD7 reaches consumer and both physical publications",
            "release speed matrix >=95% Stage1 and strict later-stage policy",
        ],
        "decision": "CONSTRUCTION_ONLY_LIVE_GATES_REQUIRED",
    }
    return candidate, receipt


def build(
    source: bytes, base_receipt_bytes: bytes,
) -> tuple[bytes, dict[str, Any]]:
    preimages = validate_preimages(source, base_receipt_bytes)
    candidate, receipt = construct(source)
    timing = timing_contract(source)
    receipt.update({
        "schema": "penta-stage1-scene0b-runtime-selfheal-r313-build-v1",
        "status": "STATIC_PASS_R313_LIVE_GATES_REQUIRED",
        "preimage_contract": preimages,
        "decision": "STATIC_SELFHEAL_PATCH_LIVE_GATES_REQUIRED",
    })
    receipt["base"]["build_receipt_sha256"] = BASE_RECEIPT_SHA256
    receipt["offline_contract"]["timing"] = timing
    receipt["timing"].update(timing)
    del receipt["historical_evidence_consumed"], receipt["fresh_live_qualification"]
    return candidate, receipt


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", type=Path, default=BASE)
    parser.add_argument("--base-receipt", type=Path, default=BASE_RECEIPT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--receipt", type=Path, default=DEFAULT_RECEIPT)
    args = parser.parse_args()
    output = r305.r304.checked_output(args.output, "candidate output")
    receipt_path = r305.r304.checked_output(args.receipt, "receipt output")
    candidate, receipt = build(
        args.base.read_bytes(), args.base_receipt.read_bytes()
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
