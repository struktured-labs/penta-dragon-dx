#!/usr/bin/env python3
"""Fail-closed static gate for the Stage-1 SELECT-menu map race.

This verifier does not launch an emulator.  It executes the relevant LR35902
instruction bytes with a deliberately small interpreter, exhaustively checks
the live-LCDC selector over every LCDC/DC0B byte pair, and checks the Stage-1
menu sentinel over every FFE4/scene byte pair.  The same checks must reject the
old DC0B selector and the old zero-sentinel helper; those negative controls
keep the gate from becoming a byte-presence tautology.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass, field
import hashlib
import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
BANK_SIZE = 0x4000
ROM_SIZE = 32 * BANK_SIZE

SCHEMA = "penta-stage1-menu-race-static-v2"

SELECTOR_ADDR = 0x200E
SELECTOR_END = 0x2029
SELECTOR_NEW = bytes.fromhex("F0 40 CB 5F")
SELECTOR_OLD = bytes.fromhex("FA 0B DC A7")
SELECTOR_TAIL = bytes.fromhex(
    "28 0C 21 00 98 F0 40 CB B7 E0 40 C3 29 20 "
    "21 00 9C F0 40 CB F7 E0 40"
)

MENU_BANK = 20
MENU_COMMON_ADDR = 0x4020
MENU_COMMON = bytes.fromhex(
    "CD 0E 20 F0 40 CB 77 28 04 CB 9F 18 02 CB DF E0 40"
)
MENU_POSTCOPY_ADDR = 0x4023
MENU_POSTCOPY_END = 0x4031
MENU_FIRST_FLAG_ADDR = 0x1B3A
MENU_INTERACTIVE_FLAG_ADDR = 0x1D65
MENU_FLAG_SET = bytes.fromhex("3E 01 E0 E4")
MENU_FIRST_WRAPPER_ADDR = 0x1B48
MENU_FIRST_WRAPPER = bytes.fromhex(
    "F0 99 F5 3E 14 CD 61 00 CD 00 40 F1 CD 61 00"
)
MENU_INTERACTIVE_WRAPPER_ADDR = 0x1D78
MENU_INTERACTIVE_WRAPPER = bytes.fromhex(
    "F0 99 F5 3E 14 CD 61 00 CD 17 40 F1 CD 61 00"
)
MENU_REDRAW_ADDR = 0x77F0
MENU_REDRAW = bytes.fromhex("CD 0E 20 3E 06 F5 CD 6F 40 F1 3D 20 F8 C9")
MENU_FIRST_CLOSE_ADDR = 0x1B69
MENU_INTERACTIVE_CLOSE_ADDR = 0x1DC2
MENU_CLOSE = bytes.fromhex("F0 40 CB AF E0 40 CD 98 77 AF E0 E4 C9")
MENU_RESET_ADDR = 0x7798
MENU_RESET_PREFIX = bytes.fromhex(
    "21 7C C0 06 04 CD A2 09 21 7C C1 06 04 CD A2 09"
)
MENU_RESET_LEGACY_TAIL = bytes.fromhex("AF E0 E4 C9")
MENU_RESET_LEGACY_FIXED_STUB = bytes.fromhex("DF AE BB 52 7B")
MENU_RESET_ROUTED_TAIL = bytes.fromhex("CD 13 00 C9")

# r304 replaced the shared reset tail with a reviewed CALL through fixed:$0013
# so scene-$0B can invalidate both physical-map semantic keys before restoring
# the native A=0/Z/FFE4=0 return ABI.  Accepting those four bytes alone would
# be unsafe: pin the complete bridge and one of the exact reviewed bank-31
# implementations.  r305-r312 use the original unified mux; r313 changes only
# its fail-closed unknown-caller displacement while leaving the complete menu
# route byte-exact.  The r304 leaf is retained as an exact historical member
# of the same reviewed route family.
MENU_RESET_ROUTED_FIXED_STUB_ADDR = 0x0013
MENU_RESET_ROUTED_FIXED_STUB = bytes.fromhex("3E 1F C3 47 08")
MENU_RESET_ROUTED_DISPATCH_ADDR = 0x0847
MENU_RESET_ROUTED_DISPATCH = bytes.fromhex("CD 61 00 CD 80 6C C3 61 00")
MENU_RESET_ROUTED_MAPPER_ENTRY_ADDR = 0x0061
MENU_RESET_ROUTED_MAPPER_ENTRY = bytes.fromhex("EA 09 DC C3 BE 09")
MENU_RESET_ROUTED_MAPPER_BODY_ADDR = 0x09BE
MENU_RESET_ROUTED_MAPPER_BODY = bytes.fromhex("E0 99 EA 00 21 C9")
MENU_RESET_ROUTED_BANK1_THUNK_ADDR = 0x099A
MENU_RESET_ROUTED_BANK1_THUNK = bytes.fromhex(
    "F5 3E 01 CD 61 00 F1 C9"
)
MENU_RESET_ROUTED_BANK = 31
MENU_RESET_ROUTED_HELPER_ADDR = 0x6C80
MENU_RESET_ROUTED_R304_HELPER = bytes.fromhex(
    "FA 80 D8 FE 0B 20 0E F0 B7 FE 02 20 08 "
    "3E FF EA 53 DF EA 57 DF F1 AF E0 E4 C3 9A 09"
)
MENU_RESET_ROUTED_R305_MUX = bytes.fromhex(
    "E5 F8 04 7E FE E1 28 0C FE AB 20 0E 23 7E FE 77 28 33 18 06 "
    "23 7E FE DA 28 05 E1 3E 01 B7 C9 F0 70 E6 07 FE 01 20 13 "
    "FA 80 D8 E6 F7 FE 03 20 0A F0 B7 FE 02 20 04 E1 3E 01 C9 "
    "2B 36 B9 23 36 DA E1 3E 01 B7 C9 F0 70 E6 07 FE 01 20 15 "
    "FA 80 D8 FE 0B 20 0E F0 B7 FE 02 20 08 3E FF EA 53 DF "
    "EA 57 DF E1 F1 AF E0 E4 C3 9A 09"
)
MENU_RESET_ROUTED_R313_MUX = (
    MENU_RESET_ROUTED_R305_MUX[:11]
    + bytes([0x5E])
    + MENU_RESET_ROUTED_R305_MUX[12:]
)
MENU_RESET_ROUTED_R325_MUX = (
    MENU_RESET_ROUTED_R313_MUX[:90]
    + bytes.fromhex("C3 D0 6E 00 00 00 00 00")
    + MENU_RESET_ROUTED_R313_MUX[98:]
)
MENU_RESET_ROUTED_R325_WRAPPER_ADDR = 0x6ED0
MENU_RESET_ROUTED_R325_WRAPPER = bytes.fromhex(
    "F3 F0 40 F5 CB EF E0 40 "
    "3E FF EA 53 DF EA 57 DF "
    "CD 50 6E 20 FB F1 CB AF E0 40 FB C3 E2 6C"
)
MENU_RESET_ROUTED_R364_MUX = (
    MENU_RESET_ROUTED_R325_MUX[:100]
    + bytes.fromhex("C3 F0 6E 00 00 00")
)
MENU_RESET_ROUTED_R364_WRAPPER = (
    MENU_RESET_ROUTED_R325_WRAPPER[:26]
    + bytes.fromhex("00")
    + MENU_RESET_ROUTED_R325_WRAPPER[27:]
)
MENU_RESET_ROUTED_R364_ATOMIC_EXIT_ADDR = 0x6EF0
MENU_RESET_ROUTED_R364_ATOMIC_EXIT = bytes.fromhex(
    "AF E0 E4 F0 40 CB AF E0 40 AF FB C3 9A 09"
)
# r535/r536 replace only the scene load in the r364 mux with a tail jump to
# an exact, bounded close-time repair.  The new helper keeps the original
# scene/stage branches, repairs the six menu-owned rows only in Stage 1 room
# $01, waits through the next reveal boundary, invalidates both physical-map
# keys, and then rejoins the unchanged r364 atomic exit.  Pin the complete
# allocated page, including its erased padding: accepting only the JP would
# leave both the VRAM writer and the reveal barrier unaudited.
MENU_RESET_ROUTED_R535_MUX = (
    MENU_RESET_ROUTED_R364_MUX[:77]
    + bytes.fromhex("C3 00 74")
    + MENU_RESET_ROUTED_R364_MUX[80:]
)
MENU_RESET_ROUTED_R535_PAGE_ADDR = 0x7400
MENU_RESET_ROUTED_R535_CLOSE_HELPER = bytes.fromhex(
    "FA 80 D8 FE 02 20 15 F0 B7 FE 02 20 12 "
    "F3 CD 80 74 3E FF EA 53 DF EA 57 DF C3 E2 6C "
    "C3 D0 6C C3 E2 6C"
)
MENU_RESET_ROUTED_R535_VISIBLE_REPAIR_ADDR = 0x7480
MENU_RESET_ROUTED_R535_VISIBLE_REPAIR = bytes.fromhex(
    "F0 BD FE 01 C0 F0 40 CB 7F C8 C5 D5 E5 F0 4F F5 "
    "F0 40 CB 5F 11 00 98 28 02 16 9C 26 C6 06 06 0E 0A C5 "
    "F0 41 E6 03 FE 03 20 F8 F0 41 E6 03 20 FA "
    "AF E0 4F 1A 6F 7E 47 13 1A 6F 7E 4F 1B "
    "3E 01 E0 4F 78 12 13 79 12 13 C1 0D 20 D6 "
    "7B C6 0C 5F 30 01 14 05 20 CA "
    "F0 44 FE 90 30 FA F0 44 FE 90 38 FA "
    "F1 E0 4F E1 D1 C1 C9"
)
MENU_RESET_ROUTED_R535_PAGE = (
    MENU_RESET_ROUTED_R535_CLOSE_HELPER
    + bytes([0xFF]) * (
        MENU_RESET_ROUTED_R535_VISIBLE_REPAIR_ADDR
        - MENU_RESET_ROUTED_R535_PAGE_ADDR
        - len(MENU_RESET_ROUTED_R535_CLOSE_HELPER)
    )
    + MENU_RESET_ROUTED_R535_VISIBLE_REPAIR
    + bytes([0xFF]) * (
        0x100
        - (MENU_RESET_ROUTED_R535_VISIBLE_REPAIR_ADDR
           - MENU_RESET_ROUTED_R535_PAGE_ADDR)
        - len(MENU_RESET_ROUTED_R535_VISIBLE_REPAIR)
    )
)
assert len(MENU_RESET_ROUTED_R535_PAGE) == 0x100
MENU_RESET_ROUTED_IMPLEMENTATIONS = (
    MENU_RESET_ROUTED_R304_HELPER,
    MENU_RESET_ROUTED_R305_MUX,
    MENU_RESET_ROUTED_R313_MUX,
    MENU_RESET_ROUTED_R325_MUX,
    MENU_RESET_ROUTED_R364_MUX,
    MENU_RESET_ROUTED_R535_MUX,
)

SENTINEL_BANK = 13
SENTINEL_ADDR = 0x6A40
SENTINEL_NEW = bytes.fromhex(
    "F0 E4 B7 C8 FA 80 D8 D6 02 FE 07 3D D0 "
    "87 9F EA 53 DF EA 57 DF 3D C9"
)
SENTINEL_OLD = bytes.fromhex(
    "F0 E4 B7 C8 FA 80 D8 D6 02 FE 07 3D D0 "
    "AF EA 53 DF EA 57 DF 3C C9 00"
)
SENTINEL_CALLER_ADDR = 0x6EB1
SENTINEL_CALLER = bytes.fromhex(
    "CD 40 6A 28 10 F0 40 CB 77 28 04 CB 9F 18 02 CB DF E0 40"
)

ATTR_DECIDER_ADDR = 0x3485
ATTR_DECIDER_MENU_SHORT_CIRCUIT = bytes.fromhex("F0 E4 3D C8")
PUBLISHER_ADDR = 0x4295
PUBLISHER_PREFIX_LEGACY = bytes.fromhex(
    "FA 0B DC 3C E6 01 EA 0B DC 28 05 26 9C C3 A7 42 "
    "26 98 2E 00 7C E0 A5 16 FF CD 85 34"
)
# r316 relocates only the destination latch operand $FFA5->$FF01; the DC0B
# toggle, hidden-map choice, publication ordering, and timing stay byte exact.
PUBLISHER_PREFIX_RELOCATED = (
    PUBLISHER_PREFIX_LEGACY[:22]
    + bytes.fromhex("01")
    + PUBLISHER_PREFIX_LEGACY[23:]
)
PUBLISHER_PREFIX = PUBLISHER_PREFIX_RELOCATED

STAGE1_DECIDER_BANK = 21
STAGE1_DECIDER_ADDR = 0x4100
STAGE1_DECIDER = bytes.fromhex(
    "16 DF 7C EE CB 5F 1A 4F F0 42 47 FA 02 DC A8 47 "
    "FA 1B C2 A8 47 FA B8 C2 A8 B9 20 17 3C 28 0E "
    "13 1A 4F FA 00 DC B9 20 08 3E 01 C3 61 00 3D "
    "18 03 12 18 06 12 13 FA 00 DC 12 3E 01 B7 C3 61 00"
)
# r442 keeps the exact menu/scene fail-closed predicates while replacing the
# older cache signature with the source-write generation key used by the
# current r534 lineage.  Pin the complete implementation; accepting a shared
# prefix would leave the dirty fallback or mapper return unaudited.
STAGE1_SOURCE_TRACKED_DECIDER = bytes.fromhex(
    "F0 B7 FE 02 00 C2 34 41 F0 BA B7 C2 34 41 "
    "16 DF 7C EE CB 5F 1A FE A5 20 0E 13 1A 4F "
    "F0 E5 B9 1B 20 05 3E 01 C3 61 00 3E A5 12 "
    "13 F0 E5 12 3E 01 B7 C3 61 00 C3 00 7E"
)

EXPECTED_SELECTOR_CALLS = {
    0x0077F0,
    MENU_BANK * BANK_SIZE + MENU_COMMON_ADDR - 0x4000,
}


class StaticGateError(RuntimeError):
    """The ROM does not satisfy the audited static contract."""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise StaticGateError(message)


def digest(payload: bytes | bytearray) -> str:
    return hashlib.sha256(payload).hexdigest()


def bank_offset_for(bank: int, address: int) -> int:
    require(bank > 0 and 0x4000 <= address < 0x8000,
            f"invalid banked address: bank={bank} address={address:04X}")
    return bank * BANK_SIZE + address - 0x4000


def require_menu_reset_lifecycle(rom: bytes) -> str:
    """Accept only the exact legacy or reviewed routed shared reset."""
    prefix = rom[
        MENU_RESET_ADDR:MENU_RESET_ADDR + len(MENU_RESET_PREFIX)
    ]
    require(prefix == MENU_RESET_PREFIX,
            "menu reset lifecycle prefix changed")
    tail_addr = MENU_RESET_ADDR + len(MENU_RESET_PREFIX)
    tail = rom[tail_addr:tail_addr + len(MENU_RESET_LEGACY_TAIL)]
    if tail == MENU_RESET_LEGACY_TAIL:
        require(
            rom[
                MENU_RESET_ROUTED_FIXED_STUB_ADDR:
                MENU_RESET_ROUTED_FIXED_STUB_ADDR
                + len(MENU_RESET_LEGACY_FIXED_STUB)
            ] == MENU_RESET_LEGACY_FIXED_STUB,
            "legacy menu reset fixed-stub preimage changed",
        )
        return "legacy-direct-clear"
    require(tail == MENU_RESET_ROUTED_TAIL,
            "menu reset lifecycle tail is neither exact legacy nor routed")

    fixed_contracts = (
        (
            MENU_RESET_ROUTED_FIXED_STUB_ADDR,
            MENU_RESET_ROUTED_FIXED_STUB,
            "fixed $0013 bridge",
        ),
        (
            MENU_RESET_ROUTED_DISPATCH_ADDR,
            MENU_RESET_ROUTED_DISPATCH,
            "fixed mapper dispatcher",
        ),
        (
            MENU_RESET_ROUTED_MAPPER_ENTRY_ADDR,
            MENU_RESET_ROUTED_MAPPER_ENTRY,
            "fixed coherent mapper entry",
        ),
        (
            MENU_RESET_ROUTED_MAPPER_BODY_ADDR,
            MENU_RESET_ROUTED_MAPPER_BODY,
            "fixed coherent mapper body",
        ),
        (
            MENU_RESET_ROUTED_BANK1_THUNK_ADDR,
            MENU_RESET_ROUTED_BANK1_THUNK,
            "fixed AF-preserving bank-1 thunk",
        ),
    )
    for address, expected, label in fixed_contracts:
        require(
            rom[address:address + len(expected)] == expected,
            f"routed menu reset {label} changed",
        )

    helper = bank_offset_for(
        MENU_RESET_ROUTED_BANK, MENU_RESET_ROUTED_HELPER_ADDR
    )
    implementation = next((
        index
        for index, expected in enumerate(MENU_RESET_ROUTED_IMPLEMENTATIONS)
        if rom[helper:helper + len(expected)] == expected
    ), None)
    require(implementation is not None,
            "routed menu reset bank-31 implementation changed")
    if implementation in {3, 4, 5}:
        wrapper = bank_offset_for(
            MENU_RESET_ROUTED_BANK, MENU_RESET_ROUTED_R325_WRAPPER_ADDR
        )
        expected_wrapper = (
            MENU_RESET_ROUTED_R364_WRAPPER
            if implementation in {4, 5}
            else MENU_RESET_ROUTED_R325_WRAPPER
        )
        require(
            rom[wrapper:wrapper + len(expected_wrapper)] == expected_wrapper,
            "routed menu reset menu-art wrapper changed",
        )
    if implementation in {4, 5}:
        atomic_exit = bank_offset_for(
            MENU_RESET_ROUTED_BANK,
            MENU_RESET_ROUTED_R364_ATOMIC_EXIT_ADDR,
        )
        require(
            rom[
                atomic_exit:
                atomic_exit + len(MENU_RESET_ROUTED_R364_ATOMIC_EXIT)
            ] == MENU_RESET_ROUTED_R364_ATOMIC_EXIT,
            "routed menu reset r364 atomic exit changed",
        )
    if implementation == 5:
        page = bank_offset_for(
            MENU_RESET_ROUTED_BANK,
            MENU_RESET_ROUTED_R535_PAGE_ADDR,
        )
        require(
            rom[page:page + len(MENU_RESET_ROUTED_R535_PAGE)]
            == MENU_RESET_ROUTED_R535_PAGE,
            "routed menu reset r535 close-time repair changed",
        )
    return (
        "r304-leaf" if implementation == 0
        else "r305-unified-mux" if implementation == 1
        else "r313-selfheal-mux" if implementation == 2
        else "r325-menu-art-wrapper" if implementation == 3
        else "r364-atomic-menu-exit" if implementation == 4
        else "r535-visible-menu-close"
    )


def signed_byte(value: int) -> int:
    return value if value < 0x80 else value - 0x100


@dataclass
class TinyLR35902:
    """Instruction-complete only for the audited selector/helper snippets."""

    code: dict[int, int]
    memory: dict[int, int]
    pc: int
    a: int = 0
    h: int = 0
    l: int = 0
    z: bool = False
    n: bool = False
    half: bool = False
    carry: bool = False
    cycles: int = 0
    returned: bool = False
    writes: list[tuple[int, int]] = field(default_factory=list)

    def byte(self, address: int) -> int:
        try:
            return self.code[address]
        except KeyError as error:
            raise StaticGateError(
                f"tiny interpreter escaped audited code at ${address:04X}"
            ) from error

    def immediate8(self) -> int:
        return self.byte(self.pc + 1)

    def immediate16(self) -> int:
        return self.byte(self.pc + 1) | (self.byte(self.pc + 2) << 8)

    def read(self, address: int) -> int:
        return self.memory.get(address, 0) & 0xFF

    def write(self, address: int, value: int) -> None:
        value &= 0xFF
        self.memory[address] = value
        self.writes.append((address, value))

    @property
    def hl(self) -> int:
        return (self.h << 8) | self.l

    def step(self) -> None:
        opcode = self.byte(self.pc)

        if opcode == 0xF0:  # LDH A,[a8]
            self.a = self.read(0xFF00 | self.immediate8())
            self.pc += 2
            self.cycles += 12
            return
        if opcode == 0xE0:  # LDH [a8],A
            self.write(0xFF00 | self.immediate8(), self.a)
            self.pc += 2
            self.cycles += 12
            return
        if opcode == 0xFA:  # LD A,[a16]
            self.a = self.read(self.immediate16())
            self.pc += 3
            self.cycles += 16
            return
        if opcode == 0xEA:  # LD [a16],A
            self.write(self.immediate16(), self.a)
            self.pc += 3
            self.cycles += 16
            return
        if opcode == 0x21:  # LD HL,d16
            value = self.immediate16()
            self.h, self.l = value >> 8, value & 0xFF
            self.pc += 3
            self.cycles += 12
            return
        if opcode == 0x28:  # JR Z,r8
            if self.z:
                self.pc = self.pc + 2 + signed_byte(self.immediate8())
                self.cycles += 12
            else:
                self.pc += 2
                self.cycles += 8
            return
        if opcode == 0x18:  # JR r8
            self.pc = self.pc + 2 + signed_byte(self.immediate8())
            self.cycles += 12
            return
        if opcode == 0xC3:  # JP a16
            self.pc = self.immediate16()
            self.cycles += 16
            return
        if opcode == 0xA7:  # AND A
            self.z = self.a == 0
            self.n = False
            self.half = True
            self.carry = False
            self.pc += 1
            self.cycles += 4
            return
        if opcode == 0xB7:  # OR A
            self.z = self.a == 0
            self.n = False
            self.half = False
            self.carry = False
            self.pc += 1
            self.cycles += 4
            return
        if opcode == 0xAF:  # XOR A
            self.a = 0
            self.z = True
            self.n = False
            self.half = False
            self.carry = False
            self.pc += 1
            self.cycles += 4
            return
        if opcode == 0xD6:  # SUB d8
            operand = self.immediate8()
            before = self.a
            self.a = (before - operand) & 0xFF
            self.z = self.a == 0
            self.n = True
            self.half = (before & 0x0F) < (operand & 0x0F)
            self.carry = before < operand
            self.pc += 2
            self.cycles += 8
            return
        if opcode == 0xFE:  # CP d8
            operand = self.immediate8()
            self.z = self.a == operand
            self.n = True
            self.half = (self.a & 0x0F) < (operand & 0x0F)
            self.carry = self.a < operand
            self.pc += 2
            self.cycles += 8
            return
        if opcode == 0x3D:  # DEC A; carry is preserved
            before = self.a
            self.a = (before - 1) & 0xFF
            self.z = self.a == 0
            self.n = True
            self.half = (before & 0x0F) == 0
            self.pc += 1
            self.cycles += 4
            return
        if opcode == 0x3C:  # INC A; carry is preserved
            before = self.a
            self.a = (before + 1) & 0xFF
            self.z = self.a == 0
            self.n = False
            self.half = (before & 0x0F) == 0x0F
            self.pc += 1
            self.cycles += 4
            return
        if opcode == 0x87:  # ADD A,A
            before = self.a
            total = before * 2
            self.a = total & 0xFF
            self.z = self.a == 0
            self.n = False
            self.half = ((before & 0x0F) * 2) > 0x0F
            self.carry = total > 0xFF
            self.pc += 1
            self.cycles += 4
            return
        if opcode == 0x9F:  # SBC A,A
            carry = int(self.carry)
            before = self.a
            self.a = (-carry) & 0xFF
            self.z = self.a == 0
            self.n = True
            self.half = (before & 0x0F) < ((before & 0x0F) + carry)
            self.carry = carry != 0
            self.pc += 1
            self.cycles += 4
            return
        if opcode == 0xC8:  # RET Z
            if self.z:
                self.returned = True
                self.cycles += 20
            else:
                self.pc += 1
                self.cycles += 8
            return
        if opcode == 0xD0:  # RET NC
            if not self.carry:
                self.returned = True
                self.cycles += 20
            else:
                self.pc += 1
                self.cycles += 8
            return
        if opcode == 0xC9:  # RET
            self.returned = True
            self.cycles += 16
            return
        if opcode == 0xCB:
            operation = self.immediate8()
            if operation == 0x57:  # BIT 2,A (negative control only)
                self.z = (self.a & 0x04) == 0
                self.n = False
                self.half = True
            elif operation == 0x5F:  # BIT 3,A
                self.z = (self.a & 0x08) == 0
                self.n = False
                self.half = True
            elif operation == 0x77:  # BIT 6,A
                self.z = (self.a & 0x40) == 0
                self.n = False
                self.half = True
            elif operation == 0xB7:  # RES 6,A
                self.a &= ~0x40
            elif operation == 0xF7:  # SET 6,A
                self.a |= 0x40
            elif operation == 0x9F:  # RES 3,A
                self.a &= ~0x08
            elif operation == 0xDF:  # SET 3,A
                self.a |= 0x08
            else:
                raise StaticGateError(
                    f"unsupported CB opcode ${operation:02X} at ${self.pc:04X}"
                )
            self.pc += 2
            self.cycles += 8
            return

        raise StaticGateError(
            f"unsupported opcode ${opcode:02X} at ${self.pc:04X}"
        )

    def run_until_pc(self, stop_pc: int, limit: int = 64) -> None:
        for _ in range(limit):
            if self.pc == stop_pc:
                return
            require(not self.returned,
                    f"snippet returned before reaching ${stop_pc:04X}")
            self.step()
        raise StaticGateError(
            f"snippet did not reach ${stop_pc:04X} in {limit} instructions"
        )

    def run_until_return(self, limit: int = 64) -> None:
        for _ in range(limit):
            if self.returned:
                return
            self.step()
        raise StaticGateError(f"snippet did not return in {limit} instructions")


def code_map(start: int, payload: bytes) -> dict[int, int]:
    return {start + offset: value for offset, value in enumerate(payload)}


def selector_result(
    selector: bytes, postcopy: bytes, lcdc: int, dc0b: int
) -> dict[str, Any]:
    selector_code = code_map(SELECTOR_ADDR, selector)
    cpu = TinyLR35902(
        code=selector_code,
        memory={0xFF40: lcdc, 0xDC0B: dc0b},
        pc=SELECTOR_ADDR,
        a=0xA5,
        carry=True,
    )
    cpu.run_until_pc(SELECTOR_ADDR + len(SELECTOR_NEW))
    prefix_cycles = cpu.cycles
    cpu.run_until_pc(SELECTOR_END)
    after_selector = cpu.read(0xFF40)
    selector_cycles = cpu.cycles

    post = TinyLR35902(
        code=code_map(MENU_POSTCOPY_ADDR, postcopy),
        memory={0xFF40: after_selector},
        pc=MENU_POSTCOPY_ADDR,
        a=0x5A,
        carry=cpu.carry,
    )
    post.run_until_pc(MENU_POSTCOPY_END)
    return {
        "hl": cpu.hl,
        "after_selector": after_selector,
        "after_postcopy": post.read(0xFF40),
        "prefix_cycles": prefix_cycles,
        "selector_cycles": selector_cycles,
        "postcopy_cycles": post.cycles,
    }


def selector_violations(selector: bytes, postcopy: bytes) -> list[str]:
    violations: list[str] = []
    for lcdc in range(256):
        live_bg = (lcdc >> 3) & 1
        expected_window = live_bg ^ 1
        expected_hl = 0x9C00 if expected_window else 0x9800
        for dc0b in range(256):
            result = selector_result(selector, postcopy, lcdc, dc0b)
            selected = result["after_selector"]
            final = result["after_postcopy"]
            ok = (
                result["hl"] == expected_hl
                and result["prefix_cycles"] == 20
                and ((selected >> 3) & 1) == live_bg
                and ((selected >> 6) & 1) == expected_window
                and (selected & ~0x40) == (lcdc & ~0x40)
                and ((final >> 3) & 1) == live_bg
                and ((final >> 6) & 1) == expected_window
                and (final & ~0x48) == (lcdc & ~0x48)
            )
            if not ok:
                violations.append(
                    f"LCDC={lcdc:02X},DC0B={dc0b:02X},"
                    f"HL={result['hl']:04X},selector={selected:02X},"
                    f"post={final:02X}"
                )
    return violations


def run_sentinel(
    helper: bytes, ffe4: int, scene: int
) -> dict[str, Any]:
    initial53, initial57 = 0xA5, 0x5A
    cpu = TinyLR35902(
        code=code_map(SENTINEL_ADDR, helper),
        memory={
            0xFFE4: ffe4,
            0xD880: scene,
            0xDF53: initial53,
            0xDF57: initial57,
        },
        pc=SENTINEL_ADDR,
        a=0xC3,
        carry=True,
    )
    cpu.run_until_return()
    return {
        "z": cpu.z,
        "cache53": cpu.read(0xDF53),
        "cache57": cpu.read(0xDF57),
        "wrote53": any(address == 0xDF53 for address, _ in cpu.writes),
        "wrote57": any(address == 0xDF57 for address, _ in cpu.writes),
        "cycles": cpu.cycles,
    }


def sentinel_violations(
    helper: bytes, *, enforce_r289_timing: bool = True
) -> list[str]:
    violations: list[str] = []
    for ffe4 in range(256):
        for scene in range(256):
            result = run_sentinel(helper, ffe4, scene)
            target = ffe4 != 0 and 2 <= scene <= 8
            expected = 0xFF if target and scene == 2 else 0x00
            if ffe4 == 0:
                ok = (
                    result["z"] is True
                    and result["wrote53"] is False
                    and result["wrote57"] is False
                    and (
                        not enforce_r289_timing or result["cycles"] == 36
                    )
                )
            elif target:
                ok = (
                    result["z"] is False
                    and result["wrote53"] is True
                    and result["wrote57"] is True
                    and result["cache53"] == expected
                    and result["cache57"] == expected
                    and (
                        not enforce_r289_timing or result["cycles"] == 128
                    )
                )
            else:
                ok = (
                    result["z"] is False
                    and result["wrote53"] is False
                    and result["wrote57"] is False
                    and (
                        not enforce_r289_timing or result["cycles"] == 80
                    )
                )
            if not ok:
                violations.append(
                    f"FFE4={ffe4:02X},scene={scene:02X},"
                    f"Z={int(result['z'])},DF53={result['cache53']:02X},"
                    f"DF57={result['cache57']:02X},cycles={result['cycles']}"
                )
    return violations


def decider_repaints(
    cached_signature: int,
    actual_signature: int,
    cached_phase: int,
    actual_phase: int,
) -> bool:
    if actual_signature != cached_signature:
        return True
    if ((actual_signature + 1) & 0xFF) == 0:
        return True
    return actual_phase != cached_phase


def require_static_bytes(rom: bytes) -> None:
    require(len(rom) == ROM_SIZE,
            f"candidate is not exactly 512 KiB: {len(rom)} bytes")
    require(
        rom[SELECTOR_ADDR:SELECTOR_ADDR + len(SELECTOR_NEW)] == SELECTOR_NEW,
        "fixed $200E selector is not the live-LCDC implementation",
    )
    require(
        rom[
            SELECTOR_ADDR + len(SELECTOR_NEW):
            SELECTOR_ADDR + len(SELECTOR_NEW) + len(SELECTOR_TAIL)
        ] == SELECTOR_TAIL,
        "fixed $200E selector tail changed; truth-table proof is stale",
    )
    menu_off = bank_offset_for(MENU_BANK, MENU_COMMON_ADDR)
    require(rom[menu_off:menu_off + len(MENU_COMMON)] == MENU_COMMON,
            "bank20 menu post-copy map owner changed")
    for address in (MENU_FIRST_FLAG_ADDR, MENU_INTERACTIVE_FLAG_ADDR):
        require(rom[address:address + len(MENU_FLAG_SET)] == MENU_FLAG_SET,
                f"menu ownership flag setup changed at ${address:04X}")
    require(
        rom[
            MENU_FIRST_WRAPPER_ADDR:
            MENU_FIRST_WRAPPER_ADDR + len(MENU_FIRST_WRAPPER)
        ] == MENU_FIRST_WRAPPER,
        "first item-menu bank20 route changed",
    )
    require(
        rom[
            MENU_INTERACTIVE_WRAPPER_ADDR:
            MENU_INTERACTIVE_WRAPPER_ADDR + len(MENU_INTERACTIVE_WRAPPER)
        ] == MENU_INTERACTIVE_WRAPPER,
        "interactive item-menu bank20 route changed",
    )
    require(
        rom[MENU_REDRAW_ADDR:MENU_REDRAW_ADDR + len(MENU_REDRAW)]
        == MENU_REDRAW,
        "item-menu redraw route changed",
    )
    for address in (MENU_FIRST_CLOSE_ADDR, MENU_INTERACTIVE_CLOSE_ADDR):
        require(rom[address:address + len(MENU_CLOSE)] == MENU_CLOSE,
                f"menu close lifecycle changed at ${address:04X}")
    require_menu_reset_lifecycle(rom)

    sentinel_off = bank_offset_for(SENTINEL_BANK, SENTINEL_ADDR)
    require(rom[sentinel_off:sentinel_off + len(SENTINEL_NEW)] == SENTINEL_NEW,
            "bank13 Stage-1 menu sentinel helper changed")
    caller_off = bank_offset_for(SENTINEL_BANK, SENTINEL_CALLER_ADDR)
    require(rom[caller_off:caller_off + len(SENTINEL_CALLER)] == SENTINEL_CALLER,
            "bank13 sentinel caller/map pin changed")

    require(
        rom[ATTR_DECIDER_ADDR:ATTR_DECIDER_ADDR + 4]
        == ATTR_DECIDER_MENU_SHORT_CIRCUIT,
        "menu-owned attribute short-circuit changed",
    )
    publisher = rom[
        PUBLISHER_ADDR:PUBLISHER_ADDR + len(PUBLISHER_PREFIX_RELOCATED)
    ]
    require(
        publisher in {PUBLISHER_PREFIX_LEGACY, PUBLISHER_PREFIX_RELOCATED},
        "DC0B publication ordering changed; race proof requires re-audit",
    )
    decider_off = bank_offset_for(STAGE1_DECIDER_BANK, STAGE1_DECIDER_ADDR)
    decider = rom[
        decider_off:
        decider_off + max(len(STAGE1_DECIDER), len(STAGE1_SOURCE_TRACKED_DECIDER))
    ]
    require(
        decider[:len(STAGE1_DECIDER)] == STAGE1_DECIDER
        or decider[:len(STAGE1_SOURCE_TRACKED_DECIDER)]
        == STAGE1_SOURCE_TRACKED_DECIDER,
        "Stage-1 split decider/sentinel contract changed",
    )

    call_pattern = bytes.fromhex("CD 0E 20")
    calls: set[int] = set()
    cursor = 0
    while True:
        found = rom.find(call_pattern, cursor)
        if found < 0:
            break
        calls.add(found)
        cursor = found + 1
    require(calls == EXPECTED_SELECTOR_CALLS,
            f"fixed $200E call set changed: {sorted(calls)}")

    header = 0
    for value in rom[0x0134:0x014D]:
        header = (header - value - 1) & 0xFF
    require(rom[0x014D] == header,
            "candidate header checksum is invalid")
    total = (sum(rom[:0x014E]) + sum(rom[0x0150:])) & 0xFFFF
    require(rom[0x014E:0x0150] == total.to_bytes(2, "big"),
            "candidate global checksum is invalid")


def static_proof(rom: bytes) -> dict[str, Any]:
    require_static_bytes(rom)

    selector = rom[SELECTOR_ADDR:SELECTOR_END]
    menu_off = bank_offset_for(MENU_BANK, MENU_POSTCOPY_ADDR)
    postcopy = rom[menu_off:menu_off + MENU_POSTCOPY_END - MENU_POSTCOPY_ADDR]
    current_selector_failures = selector_violations(selector, postcopy)
    if current_selector_failures:
        raise StaticGateError(
            "live-LCDC selector truth table failed: "
            + current_selector_failures[0]
        )

    old_selector = SELECTOR_OLD + SELECTOR_TAIL
    old_selector_failures = selector_violations(old_selector, postcopy)
    require(len(old_selector_failures) == 32768,
            "old-selector negative control did not fail exactly the divergent half")
    for lcdc, dc0b in ((0x00, 0x01), (0x08, 0x00)):
        result = selector_result(old_selector, postcopy, lcdc, dc0b)
        require(((result["after_postcopy"] ^ lcdc) & 0x08) != 0,
                "old-selector canonical mismatch negative control passed")

    bit2_selector = bytes.fromhex("F0 40 CB 57") + SELECTOR_TAIL
    bit2_failures = selector_violations(bit2_selector, postcopy)
    require(bool(bit2_failures),
            "wrong-LCDC-bit negative control unexpectedly passed")

    sentinel_off = bank_offset_for(SENTINEL_BANK, SENTINEL_ADDR)
    helper = rom[sentinel_off:sentinel_off + len(SENTINEL_NEW)]
    current_sentinel_failures = sentinel_violations(helper)
    if current_sentinel_failures:
        raise StaticGateError(
            "Stage-1 sentinel truth table failed: "
            + current_sentinel_failures[0]
        )

    old_sentinel_failures = sentinel_violations(
        SENTINEL_OLD, enforce_r289_timing=False
    )
    require(len(old_sentinel_failures) == 255,
            "zero-sentinel negative control did not fail every nonzero FFE4 Stage-1 case")

    sentinel_forced_repaints = sum(
        decider_repaints(0xFF, signature, phase, phase)
        for signature in range(256)
        for phase in range(256)
    )
    require(sentinel_forced_repaints == 65536,
            "$FF is no longer fail-closed for every signature/phase")
    zero_false_hits = sum(
        not decider_repaints(0x00, signature, phase, phase)
        for signature in range(256)
        for phase in range(256)
    )
    require(zero_false_hits == 256,
            "zero-sentinel collision negative control lost its false-hit cases")

    mutated_decider = bytearray(rom)
    decider_off = bank_offset_for(STAGE1_DECIDER_BANK, STAGE1_DECIDER_ADDR)
    installed_decider = rom[
        decider_off:decider_off + len(STAGE1_SOURCE_TRACKED_DECIDER)
    ]
    if installed_decider == STAGE1_SOURCE_TRACKED_DECIDER:
        sentinel_jr_offset = decider_off + 0x17
        require(mutated_decider[sentinel_jr_offset] == 0x20,
                "source-tracked Stage-1 JR NZ audit drifted")
        mutated_decider[sentinel_jr_offset] = 0x28
    else:
        sentinel_jr_offset = decider_off + 0x1D
        require(mutated_decider[sentinel_jr_offset] == 0x28,
                "internal Stage-1 JR Z offset audit drifted")
        mutated_decider[sentinel_jr_offset] = 0x20
    mutated_total = (
        sum(mutated_decider[:0x014E]) + sum(mutated_decider[0x0150:])
    ) & 0xFFFF
    mutated_decider[0x014E:0x0150] = mutated_total.to_bytes(2, "big")
    try:
        require_static_bytes(bytes(mutated_decider))
    except StaticGateError as error:
        decider_negative_rejected = (
            "split decider/sentinel contract changed" in str(error)
        )
    else:
        decider_negative_rejected = False
    require(decider_negative_rejected,
            "mutated Stage-1 sentinel decider negative control passed")

    sample_zero = selector_result(selector, postcopy, 0x83, 0x00)
    sample_one = selector_result(selector, postcopy, 0x8B, 0x01)
    return {
        "schema": SCHEMA,
        "status": "PASS",
        "candidate_sha256": digest(rom),
        "checks": {
            "relevant_machine_code_exact": True,
            "rom_checksums_valid": True,
            "selector_all_lcdc_dc0b_bytes": True,
            "selector_live_bg_never_changes": True,
            "selector_window_always_opposite_live_bg": True,
            "stage1_sentinel_all_ffe4_scene_bytes": True,
            "stage1_ff_always_forces_repaint": True,
        },
        "coverage": {
            "selector_byte_pairs": 256 * 256,
            "selector_canonical_bit_pairs": 4,
            "sentinel_state_pairs": 256 * 256,
            "ff_decider_signature_phase_pairs": 256 * 256,
        },
        "selector_samples": {
            "live_9800": sample_zero,
            "live_9C00": sample_one,
        },
        "negative_controls": {
            "old_dc0b_selector_rejected_cases": len(old_selector_failures),
            "wrong_lcdc_bit_rejected_cases": len(bit2_failures),
            "old_zero_sentinel_rejected_cases": len(old_sentinel_failures),
            "zero_sentinel_false_hit_cases": zero_false_hits,
            "mutated_decider_rejected": decider_negative_rejected,
        },
    }


def output_path(path: Path) -> Path:
    resolved = path.resolve()
    roots = ((ROOT / "tmp").resolve(), Path("/mnt/data/tmp").resolve())
    require(
        any(
            root.exists()
            and resolved != root
            and resolved.is_relative_to(root)
            for root in roots
        ),
        "output must be below repository tmp/ or /mnt/data/tmp/",
    )
    return resolved


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("rom", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    receipt_path: Path | None = None
    try:
        receipt_path = output_path(args.output)
        rom = args.rom.resolve().read_bytes()
        receipt = static_proof(rom)
        receipt["candidate"] = str(args.rom.resolve())
        receipt_path.parent.mkdir(parents=True, exist_ok=True)
        receipt_path.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n")
        print(json.dumps(receipt, indent=2, sort_keys=True))
        return 0
    except (OSError, StaticGateError, ValueError) as error:
        failure = {
            "schema": SCHEMA,
            "status": "FAIL",
            "candidate": str(args.rom.resolve()),
            "reason": str(error),
        }
        if receipt_path is not None:
            receipt_path.parent.mkdir(parents=True, exist_ok=True)
            receipt_path.write_text(
                json.dumps(failure, indent=2, sort_keys=True) + "\n"
            )
        print(json.dumps(failure, indent=2, sort_keys=True))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
