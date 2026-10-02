#!/usr/bin/env python3
"""Build a Stage-7-only HBlank-DMA/tile-copy overlap experiment.

This is intentionally non-promotable.  It relocates the dirty later-dungeon
path into erased expansion bank 21, compiles the complete attribute plane, and
then pauses/resumes HBlank DMA around each stock-width four-tile bank-0 write.
The goal is to measure whether the 48 attribute blocks can share the tile
copier's first 48 HBlanks instead of adding 48 more.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


BASE_SHA256 = "029a413b4ef5c0d3fdb6d9d39902821e8b0d9f35a36bed20ab82973f2ab10742"
BANK_SIZE = 0x4000
HELPER_BANK = 21
HELPER_ADDR = 0x42B8
MAPPER = 0x0061
ATOMIC_SETUP = 0xDA13
NATIVE_DIRTY_TAIL = 0x4354


class Asm:
    def __init__(self, base: int) -> None:
        self.base = base
        self.code = bytearray()
        self.labels: dict[str, int] = {}
        self.fixups: list[tuple[int, str, str]] = []

    def db(self, *values: int) -> None:
        self.code.extend(value & 0xFF for value in values)

    def label(self, name: str) -> None:
        if name in self.labels:
            raise AssertionError(name)
        self.labels[name] = self.base + len(self.code)

    def jr(self, opcode: int, label: str) -> None:
        self.db(opcode, 0)
        self.fixups.append((len(self.code) - 1, label, "jr"))

    def jp(self, opcode: int, label: str) -> None:
        self.db(opcode, 0, 0)
        self.fixups.append((len(self.code) - 2, label, "jp"))

    def finish(self) -> bytes:
        for operand, label, kind in self.fixups:
            if kind == "jr":
                delta = self.labels[label] - (self.base + operand + 1)
                if not -128 <= delta <= 127:
                    raise AssertionError((label, delta))
                self.code[operand] = delta & 0xFF
            else:
                address = self.labels[label]
                self.code[operand] = address & 0xFF
                self.code[operand + 1] = address >> 8
        return bytes(self.code)


def emit_wait_hblank(a: Asm, prefix: str) -> None:
    a.label(prefix + "_mode3")
    a.db(0xF0, 0x41, 0xE6, 0x03, 0xFE, 0x03)
    a.jr(0x20, prefix + "_mode3")
    a.label(prefix + "_mode0")
    a.db(0xF0, 0x41, 0xE6, 0x03)
    a.jr(0x20, prefix + "_mode0")


def emit_wait_mode3(a: Asm, label: str) -> None:
    a.label(label)
    a.db(0xF0, 0x41, 0xE6, 0x03, 0xFE, 0x03)
    a.jr(0x20, label)


def emit_four_tiles(a: Asm) -> None:
    for _ in range(4):
        a.db(0x1A, 0x13, 0x22)             # [HL+] = [DE++]


def build_helper() -> bytes:
    a = Asm(HELPER_ADDR)
    # Reproduce the displaced tagged dirty setup while still on SVBK1.
    a.db(0xF3, 0xCD, ATOMIC_SETUP & 0xFF, ATOMIC_SETUP >> 8, 0x00)

    # Compile all 24 packed rows into SVBK3:D000-D2FF before tile publication.
    a.db(
        0x11, 0xA0, 0xC1,                 # DE = packed source
        0x21, 0x00, 0xD0,                 # HL = staged attr plane
        0x3E, 0x03, 0xE0, 0x70,           # SVBK3
        0x06, 0xC6,                       # BC = C600 LUT page
        0x3E, 0x18, 0xE0, 0xE0,           # 24 rows
    )
    a.label("compile_row")
    a.db(0xCD, 0x00, 0xD4)
    a.db(
        0x7D, 0xC6, 0x08, 0x6F,
        0x30, 0x01, 0x24,
        0xF0, 0xE0, 0x3D, 0xE0, 0xE0,
    )
    a.jr(0x20, "compile_row")

    # Exact tagged destination and complete-plane DMA registers.
    a.db(
        0xF0, 0xA5, 0x3D, 0x67,           # H = even $98/$9C
        0xE0, 0x53,                        # HDMA destination high
        0xAF, 0x6F, 0xE0, 0x54,           # L/HDMA4 = 0
        0x3E, 0x01, 0xE0, 0x4F,           # VBK1
        0x3E, 0xD0, 0xE0, 0x51,
        0xAF, 0xE0, 0x52,
        0xF0, 0x40, 0xCB, 0x7F,
    )
    a.jr(0x20, "rendered")
    a.jp(0xC3, "lcd_off")

    # Start outside HBlank. FFE0 tracks the command for the next block.
    a.label("rendered")
    emit_wait_mode3(a, "initial_mode3")
    a.db(0x3E, 0xAF, 0xE0, 0xE0, 0xE0, 0x55)
    a.db(0x11, 0xA0, 0xC1, 0x0E, 0x06)

    a.label("active_group")
    a.db(0xF0, 0xE0, 0xFE, 0x80)
    a.jr(0x28, "final_block")
    emit_wait_hblank(a, "active_wait")
    # Pause the still-active transfer, select bank 0, and spend only the
    # remaining HBlank/mode-2 window on the four stock tile stores.
    a.db(0xAF, 0xE0, 0x55, 0xE0, 0x4F)
    emit_four_tiles(a)
    a.db(0x0D)
    a.jr(0x20, "active_row_ready")
    a.db(0x7D, 0xC6, 0x08, 0x6F, 0x30, 0x01, 0x24, 0x0E, 0x06)
    a.label("active_row_ready")
    # Mode 3 blocks CPU VRAM access but is safe for VBK/restart setup.
    emit_wait_mode3(a, "resume_mode3")
    a.db(
        0x3E, 0x01, 0xE0, 0x4F,
        0xF0, 0xE0, 0x3D, 0xE0, 0xE0, 0xE0, 0x55,
    )
    a.jr(0x18, "active_group")

    a.label("final_block")
    emit_wait_hblank(a, "final_wait")
    a.db(0xAF, 0xE0, 0x4F)
    emit_four_tiles(a)
    # The 48th block is exactly group six of row eight.
    a.db(0x7D, 0xC6, 0x08, 0x6F, 0x30, 0x01, 0x24)
    a.db(0x06, 0x10)                       # sixteen tile-only rows remain

    a.label("stock_row")
    a.db(0x0E, 0x06)
    a.label("stock_group")
    emit_wait_hblank(a, "stock_wait")
    emit_four_tiles(a)
    a.db(0x0D)
    a.jr(0x20, "stock_group")
    a.db(0x7D, 0xC6, 0x08, 0x6F, 0x30, 0x01, 0x24, 0x05)
    a.jr(0x20, "stock_row")
    a.jr(0x18, "finish")

    a.label("lcd_off")
    # With LCD disabled, publish attrs immediately and copy tiles without
    # STAT waits; HBlank never advances in this mode.
    a.db(0x3E, 0x2F, 0xE0, 0x55, 0xAF, 0xE0, 0x4F)
    a.db(0x11, 0xA0, 0xC1, 0x06, 0x18)
    a.label("off_row")
    a.db(0x0E, 0x18)
    a.label("off_cell")
    a.db(0x1A, 0x13, 0x22, 0x0D)
    a.jr(0x20, "off_cell")
    a.db(0x7D, 0xC6, 0x08, 0x6F, 0x30, 0x01, 0x24, 0x05)
    a.jr(0x20, "off_row")

    a.label("finish")
    a.db(0x3E, 0x01, 0xE0, 0x70)           # restore SVBK1
    # Map bank 1 and land on its byte-exact CALL DBF1 / JP DBDF tail. The
    # native tail owns the sole post-copy call. The mapper RET consumes this
    # synthetic frame; the original caller remains.
    a.db(
        0x3E, 0x01,
        0x01, NATIVE_DIRTY_TAIL & 0xFF, NATIVE_DIRTY_TAIL >> 8,
        0xC5,
        0xC3, MAPPER & 0xFF, MAPPER >> 8,
    )
    return a.finish()


def checksum(rom: bytearray) -> None:
    value = 0
    for byte in rom[0x0134:0x014D]:
        value = (value - byte - 1) & 0xFF
    rom[0x014D] = value
    total = (sum(rom[:0x014E]) + sum(rom[0x0150:])) & 0xFFFF
    rom[0x014E:0x0150] = total.to_bytes(2, "big")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("base", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--receipt", type=Path, required=True)
    args = parser.parse_args()
    source = args.base.read_bytes()
    digest = hashlib.sha256(source).hexdigest()
    if digest != BASE_SHA256:
        raise SystemExit(f"wrong exact r120 base: {digest}")
    rom = bytearray(source)
    if rom[0x42B3:0x42B8] != bytes.fromhex("F3 CD 13 DA 00"):
        raise SystemExit("dirty setup preimage moved")
    if rom[0x4354:0x435A] != bytes.fromhex("CD F1 DB C3 DF DB"):
        raise SystemExit("native dirty tail moved")
    helper = build_helper()
    offset = HELPER_BANK * BANK_SIZE + HELPER_ADDR - 0x4000
    if rom[offset:offset + len(helper)] != bytes([0xFF]) * len(helper):
        raise SystemExit("bank-21 overlap helper cave is not erased")
    rom[offset:offset + len(helper)] = helper
    rom[0x42B3:0x42B8] = bytes.fromhex("3E 15 CD 61 00")
    checksum(rom)
    output = bytes(rom)
    report = {
        "schema": "penta-later-hdma-overlap-v1",
        "status": "non-promotable-stage7-control",
        "base_sha256": digest,
        "candidate_sha256": hashlib.sha256(output).hexdigest(),
        "helper": f"bank{HELPER_BANK}:${HELPER_ADDR:04X}, {len(helper)} bytes",
        "contracts": {
            "attr_blocks": 48,
            "overlapped_tile_groups": 48,
            "remaining_stock_tile_groups": 96,
            "vbk_switch_only_while_hdma_paused": True,
            "hdma_restart_only_in_mode3": True,
            "lcd_off_uses_gdma_and_no_stat_wait": True,
            "postcopy_calls_per_dirty_publication": 1,
        },
        "known_scope_limit": "Stage 1 dirty route is not qualified",
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.receipt.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(output)
    args.receipt.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
