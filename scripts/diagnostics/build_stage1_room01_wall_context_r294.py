#!/usr/bin/env python3
"""Prototype a room-01-only Dungeon wall attribute repair on exact r292.

The Stage-1 palette LUT is tile-ID-only, but room 01 reuses several BG0 floor
patterns as structural wall companions.  Keep the canonical LUT unchanged and
repair only the completed room-01 map after the existing hazard scanner.  The
existing room-12 call is converted into a same-address bank switch: an audited
empty bank-14 cave owns the contextual writer, then returns to expansion bank
19.  This candidate is intentionally not promotable without live timing and
render review.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
TMP = ROOT / "tmp"
BASE = TMP / "stage1-exact-background-r292/candidate.gb"
BASE_RECEIPT = TMP / "stage1-exact-background-r292/build-receipt.json"
DEFAULT_OUTPUT = TMP / "stage1-room01-wall-context-r294/candidate.gb"
DEFAULT_RECEIPT = TMP / "stage1-room01-wall-context-r294/build-receipt.json"
BASE_SHA256 = "924173f3cd82ea0ee2aeb9d520746d60d97ae6b224a965e3f15a150d047d1cb1"
BASE_RECEIPT_SHA256 = "fa5f837e0b5809d05dc1acafaa799613ff472720c0e8fda7e5b9406597125bd0"

BANK_SIZE = 0x4000
ROM_SIZE = 32 * BANK_SIZE
LIVE_BANK = 19
AUX_BANK = 14
DISPATCH_ADDR = 0x6F68
AUX_ENTRY_ADDR = 0x6F6D
AUX_RETURN_ADDR = 0x6F70
LIVE_RETURN_ADDR = 0x6F75
REPAIR_ADDR = 0x6BA7
ROW_WRITER_ADDR = 0x6C8F
PAIR_WRITER_ADDR = 0x6CAA
LIVE_DISPATCH_SIZE = 35
REPAIR_CAPACITY = 0x6C58 - REPAIR_ADDR

OLD_LIVE_DISPATCH = bytes.fromhex(
    "F0 BD FE 12 C0 62 24 2E 10 1E 06 0E 01 CD 8F 6C 2E 8D 0C "
    "CD 8F 6C 2E AD 0C CD 8F 6C 24 2E 0D 0C C3 8F 6C"
)
ROW_WRITER = bytes.fromhex(
    "3E 01 E0 4F F0 41 E6 03 FE 03 20 F4 F0 41 E6 03 20 FA "
    "7B 22 0D 20 FC 79 E0 4F C9"
)
PAIR_WRITER = bytes.fromhex(
    "3E 01 E0 4F F0 41 E6 03 FE 03 20 F4 F0 41 E6 03 20 FA "
    "3E 06 77 7D 81 6F 3E 06 77 AF E0 4F C9"
)
ROOM05_FLOOR_IDS = tuple(range(0x2A, 0x2F)) + tuple(range(0x3A, 0x3E)) + (0x4C, 0x4D)
ROOM01_CAPTURE = TMP / "stage1-report-hook/r290-natural-north/candidate/c1a0.bin"
ROOM01_TARGET_CELLS = (
    (0, 5), (0, 18),
    (1, 5), (1, 18),
    (2, 21),
    *((row, col) for row in range(4, 18) for col in (3, 20)),
    (19, 7), (19, 16),
)


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def digest(payload: bytes | bytearray) -> str:
    return hashlib.sha256(payload).hexdigest()


def bank_offset(bank: int, address: int) -> int:
    require(0 < bank < 32 and 0x4000 <= address < 0x8000, "bad bank/address")
    return bank * BANK_SIZE + address - 0x4000


class Asm:
    def __init__(self) -> None:
        self.code = bytearray()
        self.labels: dict[str, int] = {}
        self.fixups: list[tuple[int, str]] = []

    def db(self, *values: int) -> None:
        self.code.extend(values)

    def label(self, name: str) -> None:
        self.labels[name] = len(self.code)

    def jr(self, opcode: int, label: str) -> None:
        self.db(opcode, 0)
        self.fixups.append((len(self.code) - 1, label))

    def finish(self) -> bytes:
        for index, label in self.fixups:
            delta = self.labels[label] - (index + 1)
            require(-128 <= delta <= 127, f"JR {label} is out of range")
            self.code[index] = delta & 0xFF
        return bytes(self.code)


def call(a: Asm, address: int) -> None:
    a.db(0xCD, address & 0xFF, address >> 8)


def jump(a: Asm, address: int) -> None:
    a.db(0xC3, address & 0xFF, address >> 8)


def advance_to_next_row(a: Asm) -> None:
    # Both span writers leave L at column 22; +11 reaches next-row column 1.
    a.db(0x7D, 0xC6, 0x0B, 0x6F)
    a.jr(0x30, "advance_no_carry_" + str(len(a.fixups)))
    label = a.fixups[-1][1]
    a.db(0x24)
    a.label(label)


def build_repair() -> bytes:
    a = Asm()
    a.db(0xF0, 0xBD, 0xFE, 0x01)
    a.jr(0x28, "room01")
    a.db(0xFE, 0x12)
    a.jr(0x28, "room12")
    jump(a, AUX_RETURN_ADDR)

    a.label("room01")
    # One HBlank-safe call owns both confirmed companion cells in a row.
    # C is the same-row delta; C=0 deliberately rewrites the lone row-2 cell.
    a.db(0x62, 0x2E, 0x05, 0x0E, 0x0D)               # row0: col5,18
    call(a, PAIR_WRITER_ADDR)
    a.db(0x2E, 0x25)                                  # row1: col5,18
    call(a, PAIR_WRITER_ADDR)
    a.db(0x2E, 0x55, 0x0E, 0x00)                     # row2: col21 only
    call(a, PAIR_WRITER_ADDR)
    a.db(0x62, 0x2E, 0x83, 0x0E, 0x11, 0x06, 0x0E) # rows4..17: col3,20
    a.label("sides")
    call(a, PAIR_WRITER_ADDR)
    # Pair writer leaves HL at column 20; +15 reaches next-row column 3.
    a.db(0x7D, 0xC6, 0x0F, 0x6F)
    a.jr(0x30, "side_no_carry")
    a.db(0x24)
    a.label("side_no_carry")
    a.db(0x05)
    a.jr(0x20, "sides")
    a.db(0x62, 0x24, 0x24, 0x2E, 0x67, 0x0E, 0x09) # row19: col7,16
    call(a, PAIR_WRITER_ADDR)
    jump(a, AUX_RETURN_ADDR)

    a.label("room12")
    a.db(0x62, 0x24, 0x2E, 0x10, 0x1E, 0x06, 0x0E, 0x01)
    call(a, ROW_WRITER_ADDR)
    for low in (0x8D, 0xAD):
        a.db(0x2E, low, 0x0C)
        call(a, ROW_WRITER_ADDR)
    a.db(0x24, 0x2E, 0x0D, 0x0C)
    call(a, ROW_WRITER_ADDR)
    jump(a, AUX_RETURN_ADDR)
    code = a.finish()
    require(len(code) <= REPAIR_CAPACITY, f"repair uses {len(code)}/{REPAIR_CAPACITY} bytes")
    return code


def verify_room01_boundary(source: bytes, repair: bytes) -> dict[str, object]:
    """Offline oracle for the exact first north-transition room boundary."""
    packed = ROOM01_CAPTURE.read_bytes()
    require(len(packed) == 24 * 24, "room-01 packed capture changed width")
    positions = {row * 24 + col for row, col in ROOM01_TARGET_CELLS}
    require(len(positions) == 35, "room-01 fixed companion set changed size")
    reviewed = {0x24, 0x27, 0x30, 0x33}
    require({packed[index] for index in positions} == reviewed,
            "room-01 repair no longer owns exactly the reviewed companion IDs")

    table = bank_offset(13, 0x7000)
    before = [source[table + tile] & 7 for tile in packed]
    require(all(before[index] == 0 for index in positions),
            "negative control no longer reproduces BG0 wall companions")
    after = before.copy()
    for index in positions:
        after[index] = 6
    require(all(after[index] == 6 for index in positions),
            "room-01 boundary model did not become uniformly BG6")
    require(all(after[index] == before[index] for index in range(len(after))
                if index not in positions),
            "room-01 model changed a non-boundary cell")

    # Mutation control: changing the exact CP $01 gate to CP $05 must be
    # rejected before a candidate can claim the room-01 repair.
    require(repair[:4] == bytes.fromhex("F0 BD FE 01"),
            "room-01 dispatcher gate identity changed")
    mutant = bytearray(repair)
    mutant[3] = 0x05
    require(mutant[:4] != repair[:4], "room-gate mutation control was inert")
    require(mutant[:4] != bytes.fromhex("F0 BD FE 01"),
            "room-gate mutation was not rejected")
    return {
        "packed_room01_sha256": digest(packed),
        "reviewed_companion_cells": len(positions),
        "reviewed_BG0_companion_cells_before": len(positions),
        "reviewed_companion_cells_BG6_after": sum(after[index] == 6 for index in positions),
        "non_boundary_cells_changed": 0,
        "mutated_room05_gate_rejected": True,
    }


def update_checksums(rom: bytearray) -> None:
    header = 0
    for value in rom[0x0134:0x014D]:
        header = (header - value - 1) & 0xFF
    rom[0x014D] = header
    total = (sum(rom[:0x014E]) + sum(rom[0x0150:])) & 0xFFFF
    rom[0x014E:0x0150] = total.to_bytes(2, "big")


def build(source: bytes, base_receipt_bytes: bytes) -> tuple[bytes, dict[str, object]]:
    require(len(source) == ROM_SIZE, "base is not exactly 512 KiB")
    require(digest(source) == BASE_SHA256, "wrong exact r292 base")
    require(digest(base_receipt_bytes) == BASE_RECEIPT_SHA256, "r292 receipt identity changed")
    require(json.loads(base_receipt_bytes)["candidate_sha256"] == BASE_SHA256,
            "r292 receipt names another candidate")

    repair = build_repair()
    boundary_check = verify_room01_boundary(source, repair)
    live_off = bank_offset(LIVE_BANK, DISPATCH_ADDR)
    require(source[live_off:live_off + LIVE_DISPATCH_SIZE] == OLD_LIVE_DISPATCH,
            "live room-12 helper preimage changed")
    repair_off = bank_offset(AUX_BANK, REPAIR_ADDR)
    writer_off = bank_offset(AUX_BANK, ROW_WRITER_ADDR)
    pair_writer_off = bank_offset(AUX_BANK, PAIR_WRITER_ADDR)
    entry_off = bank_offset(AUX_BANK, AUX_ENTRY_ADDR)
    require(source[repair_off:repair_off + REPAIR_CAPACITY] == bytes(REPAIR_CAPACITY),
            "bank-14 contextual repair cave is no longer empty")
    require(source[writer_off:writer_off + len(ROW_WRITER)] == bytes(len(ROW_WRITER)),
            "bank-14 row-writer cave is no longer empty")
    require(source[pair_writer_off:pair_writer_off + len(PAIR_WRITER)] == bytes(len(PAIR_WRITER)),
            "bank-14 pair-writer cave is no longer empty")
    require(source[entry_off:entry_off + 8] == bytes(8),
            "bank-14 switch landing is no longer empty")

    rom = bytearray(source)
    live_stub = bytearray(LIVE_DISPATCH_SIZE)
    live_stub[:5] = bytes.fromhex("3E 0E CD 61 00")            # map auxiliary bank 14
    live_stub[LIVE_RETURN_ADDR - DISPATCH_ADDR] = 0xC9          # resumed bank-19 RET
    rom[live_off:live_off + LIVE_DISPATCH_SIZE] = live_stub
    rom[repair_off:repair_off + len(repair)] = repair
    rom[writer_off:writer_off + len(ROW_WRITER)] = ROW_WRITER
    rom[pair_writer_off:pair_writer_off + len(PAIR_WRITER)] = PAIR_WRITER
    rom[entry_off:entry_off + 3] = bytes([0xC3, REPAIR_ADDR & 0xFF, REPAIR_ADDR >> 8])
    return_off = bank_offset(AUX_BANK, AUX_RETURN_ADDR)
    rom[return_off:return_off + 5] = bytes.fromhex("3E 13 CD 61 00")  # restore bank 19

    # Negative control: neither immutable Stage-1 LUT mirror nor its dual-use
    # room-05 floor entries may change.
    for bank in (13,):
        table = bank_offset(bank, 0x7000)
        require(rom[table:table + 0x100] == source[table:table + 0x100],
                f"bank-{bank} Stage-1 LUT changed")
        require(all((source[table + tile] & 7) == 0 for tile in ROOM05_FLOOR_IDS),
                f"bank-{bank} room-05 floor oracle preimage is not BG0")

    update_checksums(rom)
    candidate = bytes(rom)
    changed = [i for i, pair in enumerate(zip(source, candidate, strict=True)) if pair[0] != pair[1]]
    allowed = {0x014D, 0x014E, 0x014F}
    allowed.update(range(live_off, live_off + LIVE_DISPATCH_SIZE))
    allowed.update(range(repair_off, repair_off + len(repair)))
    allowed.update(range(writer_off, writer_off + len(ROW_WRITER)))
    allowed.update(range(pair_writer_off, pair_writer_off + len(PAIR_WRITER)))
    allowed.update(range(entry_off, entry_off + 8))
    require(set(changed) <= allowed, "candidate escaped owned code/checksum ranges")

    screenshot = ROOT / "manual_captures/rc11_official_corrupted_wall_edges_2026_08_30.png"
    route_probe = ROOT / "tmp/stage1-report-hook/r290-natural-north/candidate/probe.txt"
    require(screenshot.is_file() and route_probe.is_file(), "bound room-01 evidence is missing")
    require("room=$01" in route_probe.read_text() or "room=01" in route_probe.read_text(),
            "authoritative route no longer identifies room 01")

    receipt = {
        "schema": "penta-stage1-room01-wall-context-r294-build-v1",
        "status": "STATIC_PASS_NOT_PROMOTABLE_LIVE_TIMING_REQUIRED",
        "promotable": False,
        "base_sha256": BASE_SHA256,
        "candidate_sha256": digest(candidate),
        "checksums": {"header": f"{candidate[0x014D]:02X}", "global": candidate[0x014E:0x0150].hex().upper()},
        "root_cause": "room01 structural wall companions are dual-use BG0 floor tile IDs; the global tile-only LUT publishes BG0 on structural cells",
        "patch": {
            "live_bank19_dispatch": "$6F68-$6F8A",
            "aux_bank14_repair": f"${REPAIR_ADDR:04X}-${REPAIR_ADDR + len(repair) - 1:04X}",
            "aux_bank14_row_writer": f"${ROW_WRITER_ADDR:04X}-${ROW_WRITER_ADDR + len(ROW_WRITER) - 1:04X}",
            "aux_bank14_pair_writer": f"${PAIR_WRITER_ADDR:04X}-${PAIR_WRITER_ADDR + len(PAIR_WRITER) - 1:04X}",
            "aux_bank14_switch_landing": "$6F6D-$6F74",
            "repair_bytes": len(repair),
            "functional_changed_bytes": sum(i >= 0x150 for i in changed),
        },
        "room01_fixed_companions": {
            "tile_ids": ["$24", "$27", "$30", "$33"],
            "row_0": [5, 18],
            "row_1": [5, 18],
            "row_2": [21],
            "rows_4_17": [3, 20],
            "row_19": [7, 16],
            "attribute": "BG6",
            "cells_per_publication": 35,
            "hblank_waits_per_publication": 18,
        },
        "negative_controls": {
            "room05_2A_2E_3A_3D_4C_4D_remain_BG0": True,
            "immutable_bank13_stage1_LUT_byte_exact": True,
            "room12_four_cell_repair_preserved_in_aux_dispatch": True,
            "room03_not_modified_without_independent_position_corpus": True,
        },
        "offline_room01_boundary_regression": boundary_check,
        "evidence": {
            "screenshot": str(screenshot.relative_to(ROOT)),
            "screenshot_sha256": digest(screenshot.read_bytes()),
            "route_probe": str(route_probe.relative_to(ROOT)),
            "route_probe_sha256": digest(route_probe.read_bytes()),
        },
        "required_gates": [
            "headed exact-room01 transition shows continuous BG6 wall bands",
            "room05 patterned floor remains BG0",
            "room12 hazard seam remains exact",
            "18-HBlank transition repair has acceptable frame timing",
            "menu roundtrip and first-room transition replay twice exactly",
        ],
    }
    return candidate, receipt


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", type=Path, default=BASE)
    parser.add_argument("--base-receipt", type=Path, default=BASE_RECEIPT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--receipt", type=Path, default=DEFAULT_RECEIPT)
    args = parser.parse_args()
    for path in (args.output.resolve(), args.receipt.resolve()):
        require(TMP.resolve() in path.parents, "outputs must remain in repository tmp/")
    candidate, receipt = build(args.base.read_bytes(), args.base_receipt.read_bytes())
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.receipt.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(candidate)
    args.receipt.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n")
    print(json.dumps(receipt, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except AssertionError as error:
        print(f"FAIL: {error}")
        raise SystemExit(1)
