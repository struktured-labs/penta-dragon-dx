#!/usr/bin/env python3
"""Build a Stage-7-only metatile-compiler plus HBlank-overlap control.

This is deliberately non-promotable.  It derives a four-plane metatile
attribute table from a receipt-bound live Stage 7 capture, then replaces the
576 tile classifications in the r120 dirty path with 110 metatile lookups.
All 768 staging bytes are still written on every publication, including the
same row padding, before the overlap publisher starts.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from build_later_hdma_overlap import (
    ATOMIC_SETUP,
    BANK_SIZE,
    BASE_SHA256,
    HELPER_ADDR,
    HELPER_BANK,
    MAPPER,
    NATIVE_DIRTY_TAIL,
    Asm,
    checksum,
    emit_four_tiles,
    emit_wait_hblank,
    emit_wait_mode3,
)


TABLE_ADDR = 0x4800
CAPTURE_SIZE = 1024 + 256 + 110


def build_planar_table(capture: bytes) -> tuple[bytes, bytes, bytes]:
    if len(capture) != CAPTURE_SIZE:
        raise ValueError(f"expected {CAPTURE_SIZE}-byte capture, got {len(capture)}")
    definitions = capture[:1024]
    lut = capture[1024:1280]
    grid = capture[1280:]
    planes = bytearray(1024)
    for metatile in range(256):
        for quadrant in range(4):
            tile = definitions[metatile * 4 + quadrant]
            planes[quadrant * 256 + metatile] = lut[tile]
    return bytes(planes), definitions, grid


def add_hl(a: Asm, amount: int) -> None:
    a.db(0x7D, 0xC6, amount, 0x6F, 0x30, 0x01, 0x24)


def sub_hl(a: Asm, amount: int) -> None:
    a.db(0x7D, 0xD6, amount, 0x6F, 0x30, 0x01, 0x25)


def emit_zero_cells(a: Asm, count: int, label: str) -> None:
    a.db(0x0E, count, 0xAF)
    a.label(label)
    a.db(0x22, 0x0D)
    a.jr(0x20, label)


def build_helper() -> bytes:
    a = Asm(HELPER_ADDR)
    # Preserve r120's exact tagged dirty setup while still on SVBK1, and save
    # the fixed-WRAM 10x16 source pointer before selecting staging bank 3.
    a.db(0xF3, 0xCD, ATOMIC_SETUP & 0xFF, ATOMIC_SETUP >> 8, 0x00)
    a.db(0xFA, 0x0E, 0xDC, 0x5F, 0xFA, 0x0F, 0xDC, 0x57)
    a.db(0x21, 0x00, 0xD0, 0x3E, 0x03, 0xE0, 0x70)
    a.db(0x3E, 0x0A, 0xE0, 0xE0)          # ten metatile rows

    a.label("metatile_row")
    a.db(0x3E, 0x0B, 0xE0, 0xE1)          # eleven IDs per row
    a.label("metatile")
    a.db(0x1A, 0x13, 0x4F, 0x06, TABLE_ADDR >> 8)
    a.db(0x0A, 0x22, 0x04, 0x0A, 0x22)    # top-left, top-right
    add_hl(a, 30)                           # top+2 -> bottom
    a.db(0x04, 0x0A, 0x22, 0x04, 0x0A, 0x22)
    sub_hl(a, 32)                           # bottom+2 -> next top
    a.db(0xF0, 0xE1, 0x3D, 0xE0, 0xE1)
    a.jr(0x20, "metatile")

    # Finish the ten zero padding bytes on both expanded rows.  This retains
    # a complete deterministic 32-byte staging row, not a stale-plane cache.
    emit_zero_cells(a, 10, "zero_top_padding")
    add_hl(a, 22)
    emit_zero_cells(a, 10, "zero_bottom_padding")
    # The stock source advances five unused bytes after each 11-ID row.
    a.db(0x7B, 0xC6, 0x05, 0x5F, 0x30, 0x01, 0x14)
    a.db(0xF0, 0xE0, 0x3D, 0xE0, 0xE0)
    a.jr(0x20, "metatile_row")

    # Rows 20..23 are outside the stock 10x11 expansion and remain zero.
    emit_zero_cells(a, 128, "zero_tail_rows")

    # Exact tagged destination and complete-plane DMA registers.
    a.db(
        0xF0, 0xA5, 0x3D, 0x67, 0xE0, 0x53,
        0xAF, 0x6F, 0xE0, 0x54,
        0x3E, 0x01, 0xE0, 0x4F,
        0x3E, 0xD0, 0xE0, 0x51,
        0xAF, 0xE0, 0x52,
        0xF0, 0x40, 0xCB, 0x7F,
    )
    a.jr(0x20, "rendered")
    a.jp(0xC3, "lcd_off")

    a.label("rendered")
    emit_wait_mode3(a, "initial_mode3")
    a.db(0x3E, 0xAF, 0xE0, 0xE0, 0xE0, 0x55)
    a.db(0x11, 0xA0, 0xC1, 0x0E, 0x06)

    a.label("active_group")
    a.db(0xF0, 0xE0, 0xFE, 0x80)
    a.jr(0x28, "final_block")
    emit_wait_hblank(a, "active_wait")
    a.db(0xAF, 0xE0, 0x55, 0xE0, 0x4F)
    emit_four_tiles(a)
    a.db(0x0D)
    a.jr(0x20, "active_row_ready")
    add_hl(a, 8)
    a.db(0x0E, 0x06)
    a.label("active_row_ready")
    emit_wait_mode3(a, "resume_mode3")
    a.db(0x3E, 0x01, 0xE0, 0x4F)
    a.db(0xF0, 0xE0, 0x3D, 0xE0, 0xE0, 0xE0, 0x55)
    a.jr(0x18, "active_group")

    a.label("final_block")
    emit_wait_hblank(a, "final_wait")
    a.db(0xAF, 0xE0, 0x4F)
    emit_four_tiles(a)
    add_hl(a, 8)
    a.db(0x06, 0x10)

    a.label("stock_row")
    a.db(0x0E, 0x06)
    a.label("stock_group")
    emit_wait_hblank(a, "stock_wait")
    emit_four_tiles(a)
    a.db(0x0D)
    a.jr(0x20, "stock_group")
    add_hl(a, 8)
    a.db(0x05)
    a.jr(0x20, "stock_row")
    a.jr(0x18, "finish")

    a.label("lcd_off")
    a.db(0x3E, 0x2F, 0xE0, 0x55, 0xAF, 0xE0, 0x4F)
    a.db(0x11, 0xA0, 0xC1, 0x06, 0x18)
    a.label("off_row")
    a.db(0x0E, 0x18)
    a.label("off_cell")
    a.db(0x1A, 0x13, 0x22, 0x0D)
    a.jr(0x20, "off_cell")
    add_hl(a, 8)
    a.db(0x05)
    a.jr(0x20, "off_row")

    a.label("finish")
    a.db(0x3E, 0x01, 0xE0, 0x70)
    # The native tail owns the sole DBF1 post-copy call and atomic restore.
    a.db(
        0x3E, 0x01,
        0x01, NATIVE_DIRTY_TAIL & 0xFF, NATIVE_DIRTY_TAIL >> 8,
        0xC5,
        0xC3, MAPPER & 0xFF, MAPPER >> 8,
    )
    return a.finish()


def reconstruct_plane(definitions: bytes, lut: bytes, grid: bytes) -> bytes:
    plane = bytearray(768)
    for row in range(10):
        for column in range(11):
            metatile = grid[row * 11 + column]
            for quadrant, (dy, dx) in enumerate(((0, 0), (0, 1), (1, 0), (1, 1))):
                tile = definitions[metatile * 4 + quadrant]
                plane[(row * 2 + dy) * 32 + column * 2 + dx] = lut[tile]
    return bytes(plane)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("base", type=Path)
    parser.add_argument("capture", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--receipt", type=Path, required=True)
    args = parser.parse_args()

    source = args.base.read_bytes()
    base_digest = hashlib.sha256(source).hexdigest()
    if base_digest != BASE_SHA256:
        raise SystemExit(f"wrong exact r120 base: {base_digest}")
    capture = args.capture.read_bytes()
    planes, definitions, grid = build_planar_table(capture)
    lut = capture[1024:1280]
    helper = build_helper()
    if HELPER_ADDR + len(helper) > TABLE_ADDR:
        raise SystemExit("helper overlaps planar metatile table")

    rom = bytearray(source)
    if rom[0x42B3:0x42B8] != bytes.fromhex("F3 CD 13 DA 00"):
        raise SystemExit("dirty setup preimage moved")
    if rom[0x4354:0x435A] != bytes.fromhex("CD F1 DB C3 DF DB"):
        raise SystemExit("native dirty tail moved")
    helper_offset = HELPER_BANK * BANK_SIZE + HELPER_ADDR - 0x4000
    table_offset = HELPER_BANK * BANK_SIZE + TABLE_ADDR - 0x4000
    if rom[helper_offset:helper_offset + len(helper)] != bytes([0xFF]) * len(helper):
        raise SystemExit("bank-21 metatile helper cave is not erased")
    if rom[table_offset:table_offset + len(planes)] != bytes([0xFF]) * len(planes):
        raise SystemExit("bank-21 metatile table cave is not erased")
    rom[helper_offset:helper_offset + len(helper)] = helper
    rom[table_offset:table_offset + len(planes)] = planes
    rom[0x42B3:0x42B8] = bytes.fromhex("3E 15 CD 61 00")
    checksum(rom)
    output = bytes(rom)

    direct = reconstruct_plane(definitions, lut, grid)
    planar_lut = bytearray(768)
    for row in range(10):
        for column in range(11):
            metatile = grid[row * 11 + column]
            for quadrant, (dy, dx) in enumerate(((0, 0), (0, 1), (1, 0), (1, 1))):
                planar_lut[(row * 2 + dy) * 32 + column * 2 + dx] = (
                    planes[quadrant * 256 + metatile]
                )
    if bytes(planar_lut) != direct:
        raise SystemExit("planar table model disagrees with tile LUT model")

    report = {
        "schema": "penta-later-metatile-overlap-v1",
        "status": "non-promotable-stage7-control",
        "base_sha256": base_digest,
        "capture_sha256": hashlib.sha256(capture).hexdigest(),
        "candidate_sha256": hashlib.sha256(output).hexdigest(),
        "helper": f"bank{HELPER_BANK}:${HELPER_ADDR:04X}, {len(helper)} bytes",
        "table": f"bank{HELPER_BANK}:${TABLE_ADDR:04X}, {len(planes)} bytes",
        "contracts": {
            "metatile_definitions": 256,
            "metatile_grid_cells": 110,
            "staging_bytes_written": 768,
            "staging_padding_zero": direct.count(0) >= 328,
            "planar_table_matches_tile_lut": True,
            "postcopy_calls_per_dirty_publication": 1,
            "attr_blocks": 48,
            "overlapped_tile_groups": 48,
        },
        "known_scope_limit": (
            "Hard-coded from one receipt-bound Stage 7 palette capture; "
            "not palette-editable and not valid outside Stage 7"
        ),
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.receipt.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(output)
    args.receipt.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
