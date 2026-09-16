#!/usr/bin/env python3
"""Install the receipt-qualified Stage-1 room-$03 scanner fast path.

The ordinary north-route room has no semantic hazard spans in the complete
captured corpus.  Preserve the existing CALL/mapper stack shape, but unwind
directly to the common post-copy handoff for exact scene $02 + room $03.
Every other room, attract/miniboss scene $0A, and all repair-bearing hazard
rooms enter the byte-identical dynamic scanner.
"""

from __future__ import annotations


BANK_SIZE = 0x4000
PRIVATE_BANK = 19
SCANNER_CALL_ADDR = 0x6BE7
SCANNER_ADDR = 0x61B7
# $6B6F is the live high operand of the start-4 hazard publisher's
# `CALL $0061` at $6B6D.  The first experimental placement there silently
# turned that call into $CB61 and froze as soon as a moving row matched.
# $6B70-$6B76 is the bank-19 side of the cross-bank return slot: the matching
# bank-20 address owns JP $4300, while these seven private-bank bytes are
# asserted zero and unreachable from the publisher after its bank switch.
GATE_ADDR = 0x6B70
ROOM_GATE_ADDR = 0x6B7A

SCANNER_CALL = bytes.fromhex("CD B7 61")
GATE = bytes.fromhex("CB 58 28 06 C3 B7 61")
ROOM_GATE = bytes.fromhex("F0 BD FE 03 C2 B7 61 C1 D1 C5 C9")
LIVE_HAZARD_MAPPER_CALL_ADDR = 0x6B6D
LIVE_HAZARD_MAPPER_CALL = bytes.fromhex("CD 61 00")
EXPANDED_RETURN_TRAMPOLINE = bytes.fromhex("C3 00 43")


def bank_offset(address: int) -> int:
    if not 0x4000 <= address < 0x8000:
        raise ValueError(f"switchable address out of range: ${address:04X}")
    return PRIVATE_BANK * BANK_SIZE + address - 0x4000


def inspect(rom: bytes | bytearray) -> dict[str, object]:
    call = bank_offset(SCANNER_CALL_ADDR)
    gate = bank_offset(GATE_ADDR)
    room = bank_offset(ROOM_GATE_ADDR)
    installed_call = bytes([
        0xCD, GATE_ADDR & 0xFF, GATE_ADDR >> 8,
    ])
    return {
        "installed": (
            bytes(rom[call:call + 3]) == installed_call
            and bytes(rom[gate:gate + len(GATE)]) == GATE
            and bytes(rom[room:room + len(ROOM_GATE)]) == ROOM_GATE
        ),
        "bank": PRIVATE_BANK,
        "call_address": SCANNER_CALL_ADDR,
        "gate_address": GATE_ADDR,
        "room_gate_address": ROOM_GATE_ADDR,
        "scanner_address": SCANNER_ADDR,
        "live_hazard_mapper_call_preserved": (
            bytes(rom[
                bank_offset(LIVE_HAZARD_MAPPER_CALL_ADDR):
                bank_offset(LIVE_HAZARD_MAPPER_CALL_ADDR) + 3
            ]) == LIVE_HAZARD_MAPPER_CALL
        ),
        "expanded_return_trampoline_preserved": (
            bytes(rom[
                20 * BANK_SIZE + GATE_ADDR - 0x4000:
                20 * BANK_SIZE + GATE_ADDR - 0x4000 + 3
            ]) == EXPANDED_RETURN_TRAMPOLINE
        ),
    }


def install(rom: bytearray) -> dict[str, object]:
    if len(rom) != 32 * BANK_SIZE:
        raise AssertionError(f"expected 512 KiB image, got {len(rom)} bytes")
    room_jump_target = GATE_ADDR + 4 + int.from_bytes(
        GATE[3:4], byteorder="little", signed=True
    )
    if room_jump_target != ROOM_GATE_ADDR:
        raise AssertionError(
            f"room-gate JR lands at ${room_jump_target:04X}, expected "
            f"${ROOM_GATE_ADDR:04X}"
        )
    call = bank_offset(SCANNER_CALL_ADDR)
    gate = bank_offset(GATE_ADDR)
    room = bank_offset(ROOM_GATE_ADDR)
    if bytes(rom[call:call + len(SCANNER_CALL)]) != SCANNER_CALL:
        raise AssertionError("Stage-1 scanner CALL preimage changed")
    live_call = bank_offset(LIVE_HAZARD_MAPPER_CALL_ADDR)
    if bytes(rom[live_call:live_call + 3]) != LIVE_HAZARD_MAPPER_CALL:
        raise AssertionError(
            "Stage-1 start-4 mapper CALL changed; refusing a cave collision"
        )
    expanded_return = 20 * BANK_SIZE + GATE_ADDR - 0x4000
    if bytes(
        rom[expanded_return:expanded_return + 3]
    ) != EXPANDED_RETURN_TRAMPOLINE:
        raise AssertionError("bank-20 semantic return trampoline changed")
    for address, offset, payload in (
        (GATE_ADDR, gate, GATE),
        (ROOM_GATE_ADDR, room, ROOM_GATE),
    ):
        if bytes(rom[offset:offset + len(payload)]) != bytes(len(payload)):
            raise AssertionError(
                f"Stage-1 room-$03 fast-path cave ${address:04X} changed"
            )
        rom[offset:offset + len(payload)] = payload
    rom[call:call + 3] = bytes([
        0xCD, GATE_ADDR & 0xFF, GATE_ADDR >> 8,
    ])
    report = inspect(rom)
    if (
        not report["installed"]
        or not report["live_hazard_mapper_call_preserved"]
        or not report["expanded_return_trampoline_preserved"]
    ):
        raise AssertionError("Stage-1 room-$03 fast-path postcheck failed")
    return report
