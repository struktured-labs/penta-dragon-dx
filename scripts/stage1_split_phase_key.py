#!/usr/bin/env python3
"""Install independent Stage-1 semantic-content and native-phase keys.

The former one-byte cache XORed the phase and content together.  Two changes
could therefore cancel and incorrectly authorize a pure publication.  This
installer retains separate per-map bytes for semantic content and exact DC00
phase, while preserving the adjacent hazard-cache bytes.
"""

from __future__ import annotations

from dataclasses import dataclass


BANK_SIZE = 0x4000
PRIVATE_BANK = 21
PRIVATE_ADDR = 0x4100
PRIVATE_OFFSET = PRIVATE_BANK * BANK_SIZE + PRIVATE_ADDR - 0x4000
RUNTIME_OFFSETS = (0x37C96, 0x43C96)
RUNTIME_LENGTH = 41
OLD_RUNTIME = bytes.fromhex(
    "FA80D8E6F7FE02201D16DF7CEECB5F1A4FF04247FA02DCA847FA00"
    "DCA847FA97C2A8B9C812C9C3B9DA"
)


class _Asm:
    def __init__(self, origin: int) -> None:
        self.origin = origin
        self.code = bytearray()
        self.labels: dict[str, int] = {}
        self.rel8: list[tuple[int, str]] = []

    @property
    def pc(self) -> int:
        return self.origin + len(self.code)

    def db(self, *values: int) -> None:
        self.code.extend(value & 0xFF for value in values)

    def label(self, name: str) -> None:
        if name in self.labels:
            raise AssertionError(f"duplicate label: {name}")
        self.labels[name] = self.pc

    def jr(self, opcode: int, label: str) -> None:
        self.db(opcode, 0)
        self.rel8.append((len(self.code) - 1, label))

    def finish(self) -> bytes:
        for operand, label in self.rel8:
            source_after = self.origin + operand + 1
            delta = self.labels[label] - source_after
            if not -128 <= delta <= 127:
                raise AssertionError((label, delta))
            self.code[operand] = delta & 0xFF
        return bytes(self.code)


@dataclass(frozen=True)
class SplitPhaseKeyReport:
    private_bank: int
    private_entry: int
    helper_size: int
    runtime_offsets: tuple[int, ...]
    semantic_key: str
    phase_key: str


def build_gateway() -> bytes:
    code = bytes.fromhex(
        # Exact Stage-1 and Gargoyle scenes use the private split decider.
        # Every other scene keeps the existing later-stage WRAM dispatcher.
        "FA 80 D8 E6 F7 FE 02 C2 B9 DA "
        "3E 15 CD 61 00 C3 00 41"
    )
    if len(code) > RUNTIME_LENGTH:
        raise AssertionError("split-key gateway exceeds WRAM runtime slot")
    return code + bytes(RUNTIME_LENGTH - len(code))


def build_private_decider() -> bytes:
    a = _Asm(PRIVATE_ADDR)
    # Select DF53/DF57 from exact physical destination H. DF54/DF58 hold the
    # phase byte; DF55/DF59 remain owned by the hazard scanner.
    a.db(0x16, 0xDF, 0x7C, 0xEE, 0xCB, 0x5F, 0x1A, 0x4F)
    # B = SCY ^ DC02 ^ raw[123] ^ raw[280].
    a.db(
        0xF0, 0x42, 0x47,
        0xFA, 0x02, 0xDC, 0xA8, 0x47,
        0xFA, 0x1B, 0xC2, 0xA8, 0x47,
        0xFA, 0xB8, 0xC2, 0xA8,
        0xB9,
    )
    a.jr(0x20, "changed_a")
    # $FF is the uninitialized sentinel; fail closed even when it equals the
    # real signature so cache B can never authorize an uninitialized hit.
    a.db(0x3C)
    a.jr(0x28, "sentinel_changed")
    a.db(0x13, 0x1A, 0x4F, 0xFA, 0x00, 0xDC, 0xB9)
    a.jr(0x20, "changed_b")
    a.db(0x3E, 0x01, 0xC3, 0x61, 0x00)  # preserve Z; restore ROM bank 1

    a.label("sentinel_changed")
    a.db(0x3D)
    a.jr(0x18, "changed_a")

    a.label("changed_b")
    a.db(0x12)
    a.jr(0x18, "dirty_return")

    a.label("changed_a")
    a.db(0x12, 0x13, 0xFA, 0x00, 0xDC, 0x12)

    a.label("dirty_return")
    a.db(0x3E, 0x01, 0xB7, 0xC3, 0x61, 0x00)  # NZ; restore ROM bank 1
    return a.finish()


def install(rom: bytearray) -> SplitPhaseKeyReport:
    gateway = build_gateway()
    private = build_private_decider()
    for offset in RUNTIME_OFFSETS:
        actual = bytes(rom[offset:offset + RUNTIME_LENGTH])
        if actual != OLD_RUNTIME:
            raise AssertionError(
                f"Stage-1 runtime preimage changed at 0x{offset:05X}: "
                f"{actual.hex()}"
            )
        rom[offset:offset + RUNTIME_LENGTH] = gateway
    private_actual = bytes(rom[PRIVATE_OFFSET:PRIVATE_OFFSET + len(private)])
    if private_actual != bytes([0xFF]) * len(private):
        raise AssertionError("expansion-bank split-key cave is not erased")
    rom[PRIVATE_OFFSET:PRIVATE_OFFSET + len(private)] = private
    return SplitPhaseKeyReport(
        private_bank=PRIVATE_BANK,
        private_entry=PRIVATE_ADDR,
        helper_size=len(private),
        runtime_offsets=RUNTIME_OFFSETS,
        semantic_key="SCY ^ DC02 ^ raw123 ^ raw280",
        phase_key="DC00",
    )
