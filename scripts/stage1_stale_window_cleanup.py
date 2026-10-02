#!/usr/bin/env python3
"""Install the phase-balanced stale Stage-1 hardware-Window cleanup."""

from __future__ import annotations

from dataclasses import dataclass


BANK = 13
BANK_SIZE = 0x4000
STALE_BRANCH_ADDR = 0x6EB4
CAVE_ADDR = 0x6EC4
CAVE_END = 0x6EF4
FINISH_ADDR = 0x6EF4
HELPER_ADDR = CAVE_ADDR + 2


def _offset(address: int) -> int:
    return BANK * BANK_SIZE + address - 0x4000


@dataclass(frozen=True)
class StaleWindowCleanupReport:
    branch_address: int
    helper_address: int
    normal_cycles_before: int
    normal_cycles_after: int


def install(rom: bytearray) -> StaleWindowCleanupReport:
    branch_off = _offset(STALE_BRANCH_ADDR)
    cave_off = _offset(CAVE_ADDR)
    if bytes(rom[branch_off:branch_off + 2]) != bytes.fromhex("28 F6"):
        raise AssertionError("stale-Window branch preimage moved")
    if bytes(rom[cave_off:_offset(CAVE_END)]) != bytes(CAVE_END - CAVE_ADDR):
        raise AssertionError("stale-Window phase-balance cave is not empty")
    if bytes(rom[cave_off - 2:cave_off]) != bytes.fromhex("E0 40"):
        raise AssertionError("normal stale-Window prelude fallthrough moved")
    if bytes(rom[_offset(FINISH_ADDR):_offset(FINISH_ADDR) + 5]) != bytes.fromhex(
        "23 2B C3 2C 57"
    ):
        raise AssertionError("semantic finish tail moved")

    helper = bytes.fromhex(
        "AF EA 0F DF "       # DF0F = 0
        "F0 40 CB AF E0 40 " # clear LCDC.5 (Window enable)
        "C3 F4 6E"           # rejoin semantic finish
    )
    landing = HELPER_ADDR + len(helper)
    phase_balance = bytes.fromhex("18 00 " * 12)
    cave = bytearray(CAVE_END - CAVE_ADDR)
    cave[0:2] = bytes([0x18, len(helper)])
    cave[2:2 + len(helper)] = helper
    cave[landing - CAVE_ADDR:landing - CAVE_ADDR + len(phase_balance)] = phase_balance
    rom[cave_off:_offset(CAVE_END)] = cave

    delta = HELPER_ADDR - (STALE_BRANCH_ADDR + 2)
    if not -128 <= delta <= 127:
        raise AssertionError("stale-Window helper is outside JR range")
    rom[branch_off + 1] = delta & 0xFF

    original_cycles = (CAVE_END - CAVE_ADDR) * 4
    balanced_cycles = 12 + 12 * 12
    balanced_cycles += (CAVE_END - landing - len(phase_balance)) * 4
    if balanced_cycles != original_cycles:
        raise AssertionError("normal stale-Window path changed phase")
    return StaleWindowCleanupReport(
        branch_address=STALE_BRANCH_ADDR,
        helper_address=HELPER_ADDR,
        normal_cycles_before=original_cycles,
        normal_cycles_after=balanced_cycles,
    )
