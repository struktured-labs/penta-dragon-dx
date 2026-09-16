#!/usr/bin/env python3
"""Build a default-off Stage-2 sparse attribute publication experiment.

The source-built r112 lineage compiles and publishes all 24x24 attributes on
every changed Stage-2 packed map.  Stage 2's installed C600 table is simpler:
all terrain is BG0 and only the two complete rare-pickup families use BG2.

This diagnostic preserves the stock-width tile copier and the first complete
attribute publication for each physical map.  Later changed Stage-2 copies
rewrite the first 20 cells of packed rows 0/1 from C600.  The capture corpus
proves that those forty cells contain every Stage-2 semantic pickup cell; the
rewrite therefore removes old pickup attrs as well as publishing new ones.

The experiment is deliberately isolated from the production builders.  It
claims only erased space in expansion bank 21 and patches exact preimages in
the r112 ROM.  It must not be promoted without the live speed, map-equality,
trail, menu, and multi-room gates described by its static receipt.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


BANK_SIZE = 0x4000
BASE_SHA256 = "01feebc9a8d1309e9aa47e1a54ad1db19fa19877face963fd8832d97eed2f94b"
HELPER_BANK = 21
RARE_HELPER = 0x4100
COMPILER_CONTINUATION = 0x4307
COMPILER_RESUME = 0x4309
POSTCOMPILER = 0x4353
MAPPER = 0x0061
MARKER = 0xDF56
ATOMIC_DEST = 0xA5
STAGE = 0xBA


def bank_offset(bank: int, address: int) -> int:
    assert 0x4000 <= address < 0x8000
    return bank * BANK_SIZE + address - 0x4000


def checksum(rom: bytearray) -> None:
    value = 0
    for byte in rom[0x0134:0x014D]:
        value = (value - byte - 1) & 0xFF
    rom[0x014D] = value
    total = (sum(rom[:0x014E]) + sum(rom[0x0150:])) & 0xFFFF
    rom[0x014E] = total >> 8
    rom[0x014F] = total & 0xFF


class Asm:
    def __init__(self, base: int) -> None:
        self.base = base
        self.code = bytearray()
        self.labels: dict[str, int] = {}
        self.fixups: list[tuple[int, str, str]] = []

    def db(self, *values: int) -> None:
        self.code.extend(value & 0xFF for value in values)

    def label(self, name: str) -> None:
        assert name not in self.labels
        self.labels[name] = self.base + len(self.code)

    def jr(self, opcode: int, label: str) -> None:
        self.db(opcode, 0)
        self.fixups.append((len(self.code) - 1, label, "jr"))

    def finish(self) -> bytes:
        for operand, label, kind in self.fixups:
            assert kind == "jr"
            delta = self.labels[label] - (self.base + operand + 1)
            assert -128 <= delta <= 127, (label, delta)
            self.code[operand] = delta & 0xFF
        return bytes(self.code)


def map_return(a: Asm, bank: int, address: int) -> None:
    """Map ``bank`` and let the mapper RET to ``address`` in that bank."""
    a.db(
        0x3E, bank,
        0x01, address & 0xFF, address >> 8,
        0xC5,
        0xC3, MAPPER & 0xFF, MAPPER >> 8,
    )


def build_rare_helper() -> bytes:
    """Reproduce the exact Stage-2 rare LUT and restore mapped bank 13."""
    code = bytes.fromhex(
        "21 AE C6 3E 02 22 77 2E BE 22 77 2E C6 22 77 2E D6 22 77"
    )
    a = Asm(RARE_HELPER + len(code))
    # The old helper RET would return directly to the transition caller.  A
    # tail mapper does the same after restoring the bank-13 caller image.
    a.db(0x3E, 0x0D, 0xC3, MAPPER & 0xFF, MAPPER >> 8)
    return code + a.finish()


def build_compiler_continuation() -> bytes:
    """Select first-full or later sparse publication at compiler entry."""
    a = Asm(COMPILER_CONTINUATION)
    # Only FFBA=1 (Stage 2) may consume this optimization.  All other dirty
    # publishers execute the displaced compiler prologue and resume unchanged.
    a.db(0xF0, STAGE, 0xFE, 0x01)
    a.jr(0x20, "full")
    a.db(
        0xFA, MARKER & 0xFF, MARKER >> 8,  # C = two physical-map ready bits
        0x4F,
        0xF0, ATOMIC_DEST,
        0xCB, 0x57,                        # BIT 2,A: $99 vs $9D
    )
    a.jr(0x20, "map_9c")
    a.db(0x79, 0xCB, 0x47)                 # BIT 0,C
    a.jr(0x20, "sparse")
    a.db(0xCB, 0xC1)                       # SET 0,C
    a.jr(0x18, "mark_full")
    a.label("map_9c")
    a.db(0x79, 0xCB, 0x4F)                 # BIT 1,A
    a.jr(0x20, "sparse")
    a.db(0xCB, 0xC9)                       # SET 1,C
    a.label("mark_full")
    a.db(0x79, 0xEA, MARKER & 0xFF, MARKER >> 8)
    a.label("full")
    # Exact displaced bank-1:$4302-$4308 compiler prologue.
    a.db(0xF3, 0x11, 0xA0, 0xC1, 0x21, 0x00, 0xD0)
    map_return(a, 1, COMPILER_RESUME)

    a.label("sparse")
    # A second publication can occur during a blank transition in a migrated
    # state.  STAT never reaches mode 3 while LCD is off, so fail closed to the
    # established full compiler instead of entering an HBlank wait loop.
    a.db(0xF0, 0x40, 0xCB, 0x7F)
    a.jr(0x28, "full")
    a.db(
        0xF3,                              # retain atomic dirty-copy window
        0x11, 0xA0, 0xC1,                  # DE = packed source
        0xF0, ATOMIC_DEST, 0xE6, 0xFE,     # strip dirty tag
        0x67, 0x2E, 0x00,                  # HL = exact physical BG map
        0x06, 0xC6,                        # BC = C600 + tile ID
        0x3E, 0x01, 0xE0, 0x4F,            # VBK = attribute plane
    )
    # Rewrite the complete corpus-owned semantic envelope.  Neutral writes
    # are intentional: they erase the preceding room's pickup attrs and make
    # pickup removal/movement trail-free without reading active VRAM.
    for row in range(2):
        for column in range(20):
            wait3 = f"r{row}_c{column}_wait3"
            wait0 = f"r{row}_c{column}_wait0"
            a.db(0x1A, 0x13, 0x4F, 0x0A, 0xF5)
            a.label(wait3)
            a.db(0xF0, 0x41, 0xE6, 0x03, 0xFE, 0x03)
            a.jr(0x20, wait3)
            a.label(wait0)
            a.db(0xF0, 0x41, 0xE6, 0x03)
            a.jr(0x20, wait0)
            a.db(0xF1, 0x22)
        if row == 0:
            # Packed rows are 24 cells; VRAM rows are 32 cells.
            a.db(0x7B, 0xC6, 0x04, 0x5F, 0x7D, 0xC6, 0x0C, 0x6F)
    a.db(0xAF, 0xE0, 0x4F)                 # restore tile plane
    # Rejoin the exact dirty completion: Stage-2's DBF1 guard clears FFA5,
    # then DBDF restores the saved outer HL/interrupt contract.
    map_return(a, 1, POSTCOMPILER)
    return a.finish()


def install(base: bytes) -> tuple[bytes, dict[str, object]]:
    digest = hashlib.sha256(base).hexdigest()
    assert digest == BASE_SHA256, f"wrong base ROM: {digest}"
    rom = bytearray(base)

    # Stage transition rare helper.  A is zero only on Stage 2's direct path;
    # Stage 5 arrives with A=1 and Stage 7 with A=4.  Reset the private ready
    # bits only for Stage 2, then relocate the byte-exact LUT publication.
    rare_off = bank_offset(13, 0x5422)
    rare_preimage = bytes.fromhex(
        "21 AE C6 3E 02 22 77 2E BE 22 77 2E C6 22 77 2E D6 22 77 C9"
    )
    assert rom[rare_off:rare_off + len(rare_preimage)] == rare_preimage
    wrapper = bytes.fromhex(
        "B7 20 03 EA 56 DF 3E 15 01 00 41 C5 C3 61 00"
    )
    assert len(wrapper) <= len(rare_preimage)
    rom[rare_off:rare_off + len(rare_preimage)] = (
        wrapper + bytes(len(rare_preimage) - len(wrapper))
    )

    # Dirty compiler start.  CALL $0061 returns at the same logical address
    # in bank 21, whose continuation either performs the displaced prologue or
    # completes the Stage-2 sparse publication.
    compiler_off = bank_offset(1, 0x4302)
    compiler_preimage = bytes.fromhex("F3 11 A0 C1 21")
    assert rom[compiler_off:compiler_off + 5] == compiler_preimage
    rom[compiler_off:compiler_off + 5] = bytes.fromhex("3E 15 CD 61 00")

    rare = build_rare_helper()
    compiler = build_compiler_continuation()
    rare_dst = bank_offset(HELPER_BANK, RARE_HELPER)
    compiler_dst = bank_offset(HELPER_BANK, COMPILER_CONTINUATION)
    for destination, payload in ((rare_dst, rare), (compiler_dst, compiler)):
        assert rom[destination:destination + len(payload)] == bytes(
            [0xFF]
        ) * len(payload)
        rom[destination:destination + len(payload)] = payload

    checksum(rom)
    receipt = {
        "schema": "penta-stage2-sparse-pickup-r113-build-v1",
        "base_sha256": digest,
        "candidate_sha256": hashlib.sha256(rom).hexdigest(),
        "default_off": True,
        "helper_bank": HELPER_BANK,
        "patches": {
            "stage2_transition_marker_reset": "bank13:$5422",
            "dirty_compiler_mapper": "bank1:$4302",
            "relocated_rare_lut": f"bank{HELPER_BANK}:${RARE_HELPER:04X}",
            "sparse_compiler": (
                f"bank{HELPER_BANK}:${COMPILER_CONTINUATION:04X}-"
                f"${COMPILER_CONTINUATION + len(compiler) - 1:04X}"
            ),
        },
        "state": {
            "address": f"${MARKER:04X}",
            "reset": 0,
            "bit0": "$9800 received one full publication",
            "bit1": "$9C00 received one full publication",
        },
        "sparse_envelope": {
            "packed_rows": [0, 1],
            "columns": [0, 19],
            "cells_per_publication": 40,
            "lookup": "C600[tile]",
            "trail_policy": "rewrite neutral and semantic cells",
        },
    }
    return bytes(rom), receipt


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("base", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--receipt", type=Path)
    args = parser.parse_args()
    candidate, receipt = install(args.base.read_bytes())
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(candidate)
    receipt_path = args.receipt or args.output.with_suffix(".build.json")
    receipt_path.write_text(json.dumps(receipt, indent=2) + "\n")
    print(json.dumps(receipt, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
