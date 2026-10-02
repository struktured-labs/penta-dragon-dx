#!/usr/bin/env python3
"""Build a Stage-7 semantic-class cache plus HBlank-overlap control.

Non-promotable diagnostic: each physical BG map owns a banked 110-byte cache
of metatile attribute classes and a complete padded attribute plane. Dirty
publications scan all 110 metatiles but rewrite only class changes. A 2,800-
frame raw-plane trace is replayed offline before the ROM is emitted.
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


CLASS_ADDR = 0x5000
QUARTET_ADDR = 0x5100
POINTER_ADDR = 0x5200
CAPTURE_SIZE = 1390
SIGNATURE = bytes.fromhex("50 44 58 07")


def add_hl(a: Asm, amount: int) -> None:
    a.db(0x7D, 0xC6, amount, 0x6F, 0x30, 0x01, 0x24)


def add_de(a: Asm, amount: int) -> None:
    a.db(0x7B, 0xC6, amount, 0x5F, 0x30, 0x01, 0x14)


def build_tables(capture: bytes) -> tuple[bytes, bytes, bytes, list[tuple[int, ...]]]:
    if len(capture) != CAPTURE_SIZE:
        raise ValueError(f"expected {CAPTURE_SIZE}-byte capture, got {len(capture)}")
    definitions, lut = capture[:1024], capture[1024:1280]
    quartets = [
        tuple(lut[tile] for tile in definitions[index * 4:index * 4 + 4])
        for index in range(256)
    ]
    unique = sorted(set(quartets))
    if len(unique) >= 0xFF:
        raise ValueError("semantic-class sentinel is no longer exclusive")
    class_ids = {quartet: index for index, quartet in enumerate(unique)}
    class_map = bytes(class_ids[quartet] for quartet in quartets)
    quartet_table = b"".join(bytes(quartet) for quartet in unique)
    pointers = bytearray()
    for row in range(10):
        for column in range(11):
            address = 0xD000 + row * 64 + column * 2
            pointers.extend(address.to_bytes(2, "little"))
    return class_map, quartet_table, bytes(pointers), unique


def build_helper(
    class_count: int,
    *,
    skip_scan_control: bool = False,
    publication_mode: str = "overlap",
) -> bytes:
    a = Asm(HELPER_ADDR)
    a.db(0xF3, 0xCD, ATOMIC_SETUP & 0xFF, ATOMIC_SETUP >> 8, 0x00)
    # DC0E/F live in banked WRAM1. Capture the fixed-C000 source pointer before
    # selecting the destination map's private plane/cache bank.
    a.db(0xFA, 0x0E, 0xDC, 0x5F, 0xFA, 0x0F, 0xDC, 0x57)
    # Odd tagged destination -> exact map and dedicated plane/cache bank.
    a.db(0xF0, 0xA5, 0x3D, 0xE0, 0xE2, 0xFE, 0x98, 0x3E, 0x02)
    a.jr(0x28, "bank_selected")
    a.db(0x3C)
    a.label("bank_selected")
    a.db(0xE0, 0x70)

    # Four-byte fail-closed validity tag; initialize the complete plane and
    # force all 110 semantic classes to miss on first use of each map bank.
    for index, value in enumerate(SIGNATURE):
        a.db(0xFA, (0xD3FC + index) & 0xFF, 0xD3, 0xFE, value)
        a.jr(0x20, "initialize")
    a.jr(0x18, "scan_setup")

    a.label("initialize")
    a.db(0x21, 0x00, 0xD0, 0x06, 0x03, 0xAF)
    a.label("clear_page")
    a.db(0x0E, 0x00)
    a.label("clear_byte")
    a.db(0x22, 0x0D)
    a.jr(0x20, "clear_byte")
    a.db(0x05)
    a.jr(0x20, "clear_page")
    a.db(0x21, 0x00, 0xD3, 0x0E, 0x6E, 0x3E, 0xFF)
    a.label("invalidate_class")
    a.db(0x22, 0x0D)
    a.jr(0x20, "invalidate_class")
    for index, value in enumerate(SIGNATURE):
        a.db(0x3E, value, 0xEA, (0xD3FC + index) & 0xFF, 0xD3)

    a.label("scan_setup")
    if skip_scan_control:
        a.jp(0xC3, "compile_done")
    else:
        a.db(0x21, 0x00, 0xD3, 0x06, CLASS_ADDR >> 8)
        # Fully unroll the fixed 10x11 grid. This removes 110 HRAM counter
        # round-trips and keeps B on the class-table page across cache hits.
        for row in range(10):
            for column in range(11):
                done = f"class_done_{row}_{column}"
                a.db(0x1A, 0x13, 0x4F, 0x0A, 0xBE)
                a.jr(0x28, done)
                a.db(0xE0, 0xE4)
                a.jp(0xCD, "update_class")
                a.label(done)
                a.db(0x23)
            add_de(a, 5)
        a.jp(0xC3, "compile_done")

    a.label("update_class")
    a.db(0x77, 0xD5, 0xE5)                # cache class; save source/cache
    # Cache L is the packed grid index. Resolve its precomputed padded output.
    a.db(0x7D, 0x87, 0x6F, 0x26, 0x00)
    a.db(0x11, POINTER_ADDR & 0xFF, POINTER_ADDR >> 8, 0x19)
    a.db(0x5E, 0x23, 0x56)
    # Resolve the changed class's four-byte quartet.
    a.db(0xF0, 0xE4, 0x6F, 0x26, 0x00, 0x29, 0x29)
    # class*4 is at most 52, so adding the aligned ROM page to H cannot carry
    # through L. BC remains pinned to the class-map page for the next cell.
    a.db(0x7C, 0xC6, QUARTET_ADDR >> 8, 0x67)
    a.db(0x2A, 0x12, 0x13, 0x2A, 0x12, 0x13)
    add_de(a, 30)
    a.db(0x2A, 0x12, 0x13, 0x7E, 0x12, 0xE1, 0xD1, 0xC9)

    a.label("compile_done")
    if class_count >= 0xFF:
        raise AssertionError(class_count)
    # Exact destination and complete-plane DMA registers; current SVBK2/3 is
    # deliberately retained until the transfer and all tile writes finish.
    a.db(0xF0, 0xE2, 0x67, 0xE0, 0x53, 0xAF, 0x6F, 0xE0, 0x54)
    a.db(0x3E, 0x01, 0xE0, 0x4F, 0x3E, 0xD0, 0xE0, 0x51, 0xAF, 0xE0, 0x52)
    if publication_mode == "gdma":
        # Deliberately bounded hardware control: publish the complete offscreen
        # attribute plane in one GDMA, then retain the exact stock-width tile
        # copier. No active HBlank DMA is paused, restarted, or bank-switched.
        a.db(0x3E, 0x2F, 0xE0, 0x55)
        a.label("gdma_wait")
        a.db(0xF0, 0x55, 0xCB, 0x7F)
        a.jr(0x28, "gdma_wait")
        a.db(0xAF, 0xE0, 0x4F)
        a.db(0x11, 0xA0, 0xC1, 0xF0, 0xE2, 0x67, 0xAF, 0x6F, 0x06, 0x18)
        a.label("gdma_tile_row")
        a.db(0x0E, 0x06)
        a.label("gdma_tile_group")
        emit_wait_hblank(a, "gdma_tile_wait")
        emit_four_tiles(a)
        a.db(0x0D)
        a.jr(0x20, "gdma_tile_group")
        add_hl(a, 8)
        a.db(0x05)
        a.jr(0x20, "gdma_tile_row")
        a.jp(0xC3, "finish")
    elif publication_mode != "overlap":
        raise ValueError(publication_mode)

    if publication_mode == "overlap":
        a.db(0xF0, 0x40, 0xCB, 0x7F)
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
    a.db(0x3E, 0x01, 0x01, NATIVE_DIRTY_TAIL & 0xFF,
         NATIVE_DIRTY_TAIL >> 8, 0xC5, 0xC3, MAPPER & 0xFF, MAPPER >> 8)
    return a.finish()


def replay_trace(
    trace: Path,
    result: Path,
    definitions: bytes,
    lut: bytes,
    class_map: bytes,
    unique: list[tuple[int, ...]],
) -> dict:
    planes = {0x98: bytearray(768), 0x9C: bytearray(768)}
    caches = {0x98: bytearray([0xFF] * 110), 0x9C: bytearray([0xFF] * 110)}
    dirty_indices = set(json.loads(result.read_text())["compiler_tile_copy_indices"])
    events = changes = checked = 0
    initialized: set[int] = set()
    for event_index, line in enumerate(trace.read_text().splitlines(), 1):
        fields = line.split("\t")
        destination = int(fields[2], 16)
        raw = bytes.fromhex(fields[29])
        if destination not in planes or len(raw) != 576:
            raise ValueError("invalid attr-event trace row")
        desired = bytearray(768)
        for row in range(24):
            for column in range(24):
                desired[row * 32 + column] = lut[raw[row * 24 + column]]
        plane, cache = planes[destination], caches[destination]
        if event_index in dirty_indices:
            initialized.add(destination)
            for row in range(10):
                for column in range(11):
                    pos = row * 11 + column
                    quartet = tuple(
                        desired[(row * 2 + dy) * 32 + column * 2 + dx]
                        for dy, dx in ((0, 0), (0, 1), (1, 0), (1, 1))
                    )
                    try:
                        class_id = unique.index(quartet)
                    except ValueError as error:
                        raise ValueError(
                            f"trace quartet missing from class table: {quartet}"
                        ) from error
                    if cache[pos] != class_id:
                        cache[pos] = class_id
                        changes += 1
                        for value, (dy, dx) in zip(
                            unique[class_id], ((0, 0), (0, 1), (1, 0), (1, 1))
                        ):
                            plane[(row * 2 + dy) * 32 + column * 2 + dx] = value
        # The stock copier can publish a new off-screen tile plane one copy
        # before its dirty attribute decision. Preserve that established
        # cadence; require byte-exact attrs at every actual compiler event.
        if event_index in dirty_indices and plane != desired:
            mismatch = next(i for i, (a, b) in enumerate(zip(plane, desired)) if a != b)
            raise ValueError(f"incremental replay mismatch event {events} offset {mismatch}")
        if event_index in dirty_indices:
            checked += 1
        events += 1
    if len(dirty_indices) != 303 or not dirty_indices.issubset(range(1, events + 1)):
        raise ValueError("compiler-index receipt no longer matches the 819-event trace")
    return {
        "events": events,
        "dirty_publications": len(dirty_indices),
        "checked_dirty_publications": checked,
        "semantic_class_updates": changes,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("base", type=Path)
    parser.add_argument("capture", type=Path)
    parser.add_argument("trace", type=Path)
    parser.add_argument("result", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--receipt", type=Path, required=True)
    parser.add_argument("--skip-scan-control", action="store_true")
    parser.add_argument(
        "--publication-mode", choices=("overlap", "gdma"), default="overlap"
    )
    args = parser.parse_args()
    source, capture = args.base.read_bytes(), args.capture.read_bytes()
    digest = hashlib.sha256(source).hexdigest()
    if digest != BASE_SHA256:
        raise SystemExit(f"wrong exact r120 base: {digest}")
    class_map, quartets, pointers, unique = build_tables(capture)
    definitions, lut = capture[:1024], capture[1024:1280]
    replay = replay_trace(
        args.trace, args.result, definitions, lut, class_map, unique
    )
    helper = build_helper(
        len(unique),
        skip_scan_control=args.skip_scan_control,
        publication_mode=args.publication_mode,
    )
    if HELPER_ADDR + len(helper) > CLASS_ADDR:
        raise SystemExit("incremental helper overlaps its tables")

    rom = bytearray(source)
    if rom[0x42B3:0x42B8] != bytes.fromhex("F3 CD 13 DA 00"):
        raise SystemExit("dirty setup preimage moved")
    if rom[0x4354:0x435A] != bytes.fromhex("CD F1 DB C3 DF DB"):
        raise SystemExit("native dirty tail moved")
    helper_offset = HELPER_BANK * BANK_SIZE + HELPER_ADDR - 0x4000
    end = POINTER_ADDR + len(pointers)
    region_end = HELPER_BANK * BANK_SIZE + end - 0x4000
    if rom[helper_offset:region_end] != bytes([0xFF]) * (region_end - helper_offset):
        raise SystemExit("bank-21 helper/table cave is not erased")
    rom[helper_offset:helper_offset + len(helper)] = helper
    for address, payload in (
        (CLASS_ADDR, class_map), (QUARTET_ADDR, quartets), (POINTER_ADDR, pointers)
    ):
        offset = HELPER_BANK * BANK_SIZE + address - 0x4000
        rom[offset:offset + len(payload)] = payload
    rom[0x42B3:0x42B8] = bytes.fromhex("3E 15 CD 61 00")
    checksum(rom)
    output = bytes(rom)
    report = {
        "schema": "penta-later-incremental-overlap-v1",
        "status": (
            "invalid-visual-upper-bound"
            if args.skip_scan_control else "non-promotable-stage7-control"
        ),
        "base_sha256": digest,
        "capture_sha256": hashlib.sha256(capture).hexdigest(),
        "trace_sha256": hashlib.sha256(args.trace.read_bytes()).hexdigest(),
        "result_sha256": hashlib.sha256(args.result.read_bytes()).hexdigest(),
        "candidate_sha256": hashlib.sha256(output).hexdigest(),
        "helper": f"bank{HELPER_BANK}:${HELPER_ADDR:04X}, {len(helper)} bytes",
        "semantic_classes": len(unique),
        "replay": replay,
        "contracts": {
            "per_physical_map_plane": True,
            "per_physical_map_class_cache": True,
            "cold_plane_and_cache_initialization": True,
            "trace_replay_byte_exact": True,
            "postcopy_calls_per_dirty_publication": 1,
            "attribute_blocks": 48,
            "hdma_overlap_enabled": args.publication_mode == "overlap",
            "publication_mode": args.publication_mode,
            "semantic_scan_executed": not args.skip_scan_control,
        },
        "known_scope_limit": "Stage-7-only receipt-bound diagnostic",
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.receipt.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(output)
    args.receipt.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
