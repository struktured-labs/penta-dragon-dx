#!/usr/bin/env python3
"""Build the default-off Stage-1 hazard batch-publication diagnostic.

This experiment is intentionally based on the exact r101 diagnostic ROM.  It
keeps r101's relocated phase classifier and guarded room-$03 scanner bypass,
but stages at most four complete semantic rows in SVBK2 and publishes their
aligned blocks only after the dynamic scanner has finished.  Overflow rows
fall back to r101's original per-cell HBlank writer.

Nothing in this module is imported by a production builder.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

from arena_position import _Asm


BANK_SIZE = 0x4000
PRIVATE_BANK = 19
HELPER_BANK = 20
BASE_SHA256 = "233ece9fbc18e22b5f1c69090cbc0f895c304a99f3227902f6261348569b88b8"

SCANNER_ENTRY = 0x61B7
SCANNER_BODY = 0x61BC
SCANNER_TAIL_JP = 0x620B
MAPPER_LEAF = 0x6D99
MAPPER_RETURN = 0x6D9E
OLD_SEMANTIC_HELPER = 0x4300
RELOCATED_CLASSIFIER = 0x4380
RETURN_BRIDGE = 0x6CDF
TRANSITION_REPAIR = 0x55C0

DISPATCH_WRAPPER = 0x4500
INIT_HELPER = 0x4520
STAGE_HELPER = 0x4580
PUBLISH_HELPER = 0x4680

SVBK = 0x70
VBK = 0x4F
LCDC = 0x40
HDMA1 = 0x51
HDMA2 = 0x52
HDMA3 = 0x53
HDMA4 = 0x54
HDMA5 = 0x55

STAGING_BANK = 2
STAGING_BASE = 0xD600
STAGING_END = 0xD680
COUNT_ADDR = 0xD680
DESCRIPTOR_BASE = 0xD681
INDEX_ADDR = 0xD689
MAX_ROWS = 4

CANONICAL_LUT_BANK = 13
CANONICAL_LUT_ADDR = 0x7000
EXPANDED_LUT_ADDR = 0x4400
TOOTH_IDS = frozenset((*range(0x64, 0x6A), *range(0x74, 0x7A)))


def digest(data: bytes | bytearray) -> str:
    return hashlib.sha256(data).hexdigest()


def bank_offset(bank: int, address: int) -> int:
    if not 0x4000 <= address < 0x8000:
        raise ValueError(f"switchable address out of range: ${address:04X}")
    return bank * BANK_SIZE + address - 0x4000


def patch(
    rom: bytearray,
    bank: int,
    address: int,
    expected: bytes,
    replacement: bytes,
) -> None:
    if len(expected) != len(replacement):
        raise AssertionError(f"bank {bank}:${address:04X}: width changed")
    off = bank_offset(bank, address)
    actual = bytes(rom[off:off + len(expected)])
    if actual != expected:
        raise AssertionError(
            f"bank {bank}:${address:04X}: expected {expected.hex(' ')}, "
            f"got {actual.hex(' ')}"
        )
    rom[off:off + len(replacement)] = replacement


def header_checksum(rom: bytes | bytearray) -> int:
    value = 0
    for byte in rom[0x0134:0x014D]:
        value = (value - byte - 1) & 0xFF
    return value


def global_checksum(rom: bytes | bytearray) -> int:
    return (sum(rom[:0x014E]) + sum(rom[0x0150:])) & 0xFFFF


class AbsAsm(_Asm):
    """Tiny assembler with local absolute-label fixups."""

    def __init__(self, base: int):
        super().__init__()
        self.base = base
        self.absolute_fixups: list[tuple[int, str]] = []

    def absolute(self, opcode: int, label: str) -> None:
        self.db(opcode, 0x00, 0x00)
        self.absolute_fixups.append((len(self.code) - 2, label))

    def finish(self) -> bytes:
        code = bytearray(super().finish())
        for operand, label in self.absolute_fixups:
            target = self.base + self.labels[label]
            code[operand] = target & 0xFF
            code[operand + 1] = target >> 8
        return bytes(code)


def build_dispatch_wrapper() -> bytes:
    """Route restored C=$FF to batch publication; retain r101 C=0 scan."""
    return bytes([
        0x79, 0x3C,                       # LD A,C; INC A
        0xCA, PUBLISH_HELPER & 0xFF, PUBLISH_HELPER >> 8,
        0xC3, RELOCATED_CLASSIFIER & 0xFF,
        RELOCATED_CLASSIFIER >> 8,
    ])


def build_init_helper() -> bytes:
    """Clear the per-scan batch state without crossing the banked stack."""
    return bytes([
        0x3E, STAGING_BANK, 0xE0, SVBK,
        0xAF,
        0xEA, COUNT_ADDR & 0xFF, COUNT_ADDR >> 8,
        0xEA, INDEX_ADDR & 0xFF, INDEX_ADDR >> 8,
        0x3C, 0xE0, SVBK,                 # restore SVBK1
        0x11, 0xA0, 0xC1,                # displaced LD DE,$C1A0
        0x06, 0x18,                       # displaced LD B,$18
        0x0E, 0xFF,                       # completion discriminator
        0xC3, SCANNER_ENTRY & 0xFF, SCANNER_ENTRY >> 8,
    ])


def build_stage_helper() -> tuple[bytes, dict[str, int]]:
    """Stage one exact semantic row; overflow uses r101's safe writer."""
    a = AbsAsm(STAGE_HELPER)
    a.label("entry")
    a.db(0x3E, STAGING_BANK, 0xE0, SVBK)
    a.label("svbk2_begin")
    a.db(0xFA, COUNT_ADDR & 0xFF, COUNT_ADDR >> 8, 0xFE, MAX_ROWS)
    a.absolute(0xD2, "overflow")          # JP NC

    # Descriptor = exact destination H/L. Its low nibble retains the span
    # class: 0/4 uses one aligned block; 8 uses two.
    a.db(0x87, 0xC6, DESCRIPTOR_BASE & 0xFF, 0x4F,
         0x06, DESCRIPTOR_BASE >> 8)
    a.db(0x7C, 0x02, 0x03, 0x7D, 0x02)

    # DE points at the first semantic cell. Normalize it to packed row column
    # zero using the destination's exact low nibble before HL becomes staging.
    a.db(0x7D, 0xE6, 0x0F, 0x4F, 0x7B, 0x91, 0x5F)
    a.jr(0x30, "source_ready")             # JR NC
    a.db(0x15)                             # DEC D
    a.label("source_ready")

    # Reserve one of four aligned 32-byte slots.
    a.db(0xFA, COUNT_ADDR & 0xFF, COUNT_ADDR >> 8,
         0x3C, 0xEA, COUNT_ADDR & 0xFF, COUNT_ADDR >> 8, 0x3D)
    a.db(0x0F, 0x0F, 0x0F, 0x6F, 0x26, STAGING_BASE >> 8)

    # Compile the whole current 24-cell row from the canonical C600 table.
    # Tooth IDs get VRAM-bank bit 3, exactly matching r101's expanded LUT.
    a.label("compile")
    a.db(0x1A, 0x13, 0x4F, 0xE6, 0xEF, 0xD6, 0x64, 0xFE, 0x06)
    a.jr(0x30, "neutral")                 # JR NC
    a.db(0x06, 0xC6, 0x0A, 0xF6, 0x08)
    a.jr(0x18, "store")
    a.label("neutral")
    a.db(0x06, 0xC6, 0x0A)
    a.label("store")
    a.db(0x22, 0x7D, 0xE6, 0x1F, 0xFE, 0x18)
    a.jr(0x20, "compile")

    # A two-block row publishes all 32 cells; neutralize packed-row padding.
    a.db(0xAF)
    for _ in range(8):
        a.db(0x22)
    a.label("restore")
    a.db(0x3C, 0xE0, SVBK,
         0xC3, RETURN_BRIDGE & 0xFF, RETURN_BRIDGE >> 8)

    a.label("overflow")
    a.db(0x3E, 0x01, 0xE0, SVBK,
         0xC3, OLD_SEMANTIC_HELPER & 0xFF, OLD_SEMANTIC_HELPER >> 8)
    code = a.finish()
    labels = {name: STAGE_HELPER + offset for name, offset in a.labels.items()}
    return code, labels


def build_publish_helper() -> tuple[bytes, dict[str, int]]:
    """Publish staged rows in 1/2-block HBlank batches, then run repairs."""
    a = AbsAsm(PUBLISH_HELPER)
    a.label("entry")
    a.db(0x3E, STAGING_BANK, 0xE0, SVBK)
    a.label("svbk2_begin")
    a.db(0xFA, COUNT_ADDR & 0xFF, COUNT_ADDR >> 8,
         0xFE, MAX_ROWS + 1)
    a.absolute(0xD2, "corrupt")            # impossible count: fail closed
    a.db(0xB7)
    a.absolute(0xCA, "done")
    a.db(0xAF, 0xEA, INDEX_ADDR & 0xFF, INDEX_ADDR >> 8)
    a.db(0x3C, 0xE0, VBK)                 # attributes

    a.label("row")
    # Do not collide with an earlier native transfer. The postcopy contract
    # says idle; this bounded wait preserves it if completion is one cycle late.
    a.label("prior_hdma")
    a.db(0xF0, HDMA5, 0xCB, 0x7F)
    a.jr(0x28, "prior_hdma")

    # Source = D600 + index*32.
    a.db(0x3E, STAGING_BASE >> 8, 0xE0, HDMA1)
    a.db(0xFA, INDEX_ADDR & 0xFF, INDEX_ADDR >> 8,
         0x0F, 0x0F, 0x0F, 0xE0, HDMA2)

    # Descriptor supplies exact physical map/row. Hardware aligns low nibble.
    a.db(0xFA, INDEX_ADDR & 0xFF, INDEX_ADDR >> 8,
         0x87, 0xC6, DESCRIPTOR_BASE & 0xFF, 0x6F,
         0x26, DESCRIPTOR_BASE >> 8)
    a.db(0x2A, 0xE0, HDMA3, 0x7E, 0x47, 0xE6, 0xF0, 0xE0, HDMA4)

    # Start-column 8 crosses an aligned boundary and needs two blocks.
    a.db(0x78, 0xE6, 0x0F, 0xFE, 0x08, 0x0E, 0x00)
    a.jr(0x20, "blocks_ready")
    a.db(0x0C)
    a.label("blocks_ready")

    # LCD off has no HBlank, so use immediate GDMA. Rendered gameplay uses
    # bit7=1 and waits for the bounded one/two-block HBlank transfer.
    a.db(0xF0, LCDC, 0xCB, 0x7F, 0x79)
    a.jr(0x28, "command")
    a.db(0xF6, 0x80)
    a.label("command")
    a.db(0xE0, HDMA5)
    a.label("wait")
    a.db(0xF0, HDMA5, 0xCB, 0x7F)
    a.jr(0x28, "wait")

    a.db(0xFA, INDEX_ADDR & 0xFF, INDEX_ADDR >> 8, 0x3C,
         0xEA, INDEX_ADDR & 0xFF, INDEX_ADDR >> 8, 0x47)
    a.db(0xFA, COUNT_ADDR & 0xFF, COUNT_ADDR >> 8, 0xB8)
    a.jr(0x20, "row")

    a.label("done")
    a.db(0xAF,
         0xEA, COUNT_ADDR & 0xFF, COUNT_ADDR >> 8,
         0xEA, INDEX_ADDR & 0xFF, INDEX_ADDR >> 8,
         0xE0, VBK, 0x3C, 0xE0, SVBK)
    a.label("svbk1_restored")
    # Synthetic bank-1 return: mapper RET consumes this frame and lands at
    # the unchanged seam/wall repair with its original outer frames intact.
    a.db(0x01, TRANSITION_REPAIR & 0xFF, TRANSITION_REPAIR >> 8,
         0xC5, 0x3E, PRIVATE_BANK, 0xC3, 0x61, 0x00)

    a.label("corrupt")
    # Count corruption cannot arise with DI and the capped stager. Avoid an
    # out-of-range DMA, restore both banks, and retain the seam/wall repair.
    a.db(0xAF,
         0xEA, COUNT_ADDR & 0xFF, COUNT_ADDR >> 8,
         0xEA, INDEX_ADDR & 0xFF, INDEX_ADDR >> 8,
         0xE0, VBK, 0x3C, 0xE0, SVBK)
    a.db(0x01, TRANSITION_REPAIR & 0xFF, TRANSITION_REPAIR >> 8,
         0xC5, 0x3E, PRIVATE_BANK, 0xC3, 0x61, 0x00)
    code = a.finish()
    labels = {name: PUBLISH_HELPER + offset for name, offset in a.labels.items()}
    return code, labels


def install(rom: bytearray) -> dict[str, object]:
    if digest(rom) != BASE_SHA256:
        raise AssertionError("input is not exact r101")

    # r101 does not install the mutually exclusive Ted direct-plane writer.
    direct_signature = bytes.fromhex("F3 F5 D5 E5 62 6B 01 60 14 09 4E 23 46")
    if direct_signature in rom:
        raise AssertionError("r101 unexpectedly contains Ted direct-plane D600 owner")

    wrapper = build_dispatch_wrapper()
    init = build_init_helper()
    stage, stage_labels = build_stage_helper()
    publish, publish_labels = build_publish_helper()
    regions = (
        (DISPATCH_WRAPPER, wrapper, "dispatch-wrapper"),
        (INIT_HELPER, init, "scan-init"),
        (STAGE_HELPER, stage, "row-stager"),
        (PUBLISH_HELPER, publish, "batch-publisher"),
    )
    for address, payload, label in regions:
        if address + len(payload) > 0x6000:
            raise AssertionError(f"{label} exceeds audited bank20 FF cave")
        off = bank_offset(HELPER_BANK, address)
        if rom[off:off + len(payload)] != bytes([0xFF]) * len(payload):
            raise AssertionError(f"{label} bank20:${address:04X} is not FF")
        rom[off:off + len(payload)] = payload

    # Every scanner invocation initializes batch state through a dual-bank
    # mapper bridge. The bank20 return stub maps bank19 back at $61BC.
    patch(
        rom, PRIVATE_BANK, SCANNER_ENTRY,
        bytes.fromhex("11 A0 C1 06 18"),
        bytes.fromhex("3E 14 CD 61 00"),
    )
    patch(
        rom, HELPER_BANK, SCANNER_ENTRY,
        bytes([0xFF]) * 5,
        bytes.fromhex("3E 13 CD 61 00"),
    )
    patch(
        rom, HELPER_BANK, SCANNER_BODY,
        bytes([0xFF]) * 3,
        bytes([0xC3, INIT_HELPER & 0xFF, INIT_HELPER >> 8]),
    )

    # Direct matched-row mapper returns now stage; the original $4300 helper
    # remains byte-identical as the overflow/LCD-safe fallback.
    staged_trampolines = (0x61A0, 0x67ED, 0x6B70)
    for address in staged_trampolines:
        patch(
            rom, HELPER_BANK, address,
            bytes.fromhex("C3 00 43"),
            bytes([0xC3, STAGE_HELPER & 0xFF, STAGE_HELPER >> 8]),
        )
    patch(
        rom, HELPER_BANK, MAPPER_RETURN,
        bytes.fromhex("C3 80 43"),
        bytes([0xC3, DISPATCH_WRAPPER & 0xFF, DISPATCH_WRAPPER >> 8]),
    )

    # r101's expanded classifier has two matched tails into $4300.
    dispatcher_off = bank_offset(HELPER_BANK, RELOCATED_CLASSIFIER)
    dispatcher = bytearray(rom[dispatcher_off:dispatcher_off + 60])
    needle = bytes.fromhex("C3 00 43")
    match_offsets: list[int] = []
    cursor = 0
    while True:
        found = dispatcher.find(needle, cursor)
        if found < 0:
            break
        match_offsets.append(found)
        cursor = found + len(needle)
    if match_offsets != [43, 57]:
        raise AssertionError(f"r101 classifier tails changed: {match_offsets}")
    for found in match_offsets:
        dispatcher[found:found + 3] = bytes([
            0xC3, STAGE_HELPER & 0xFF, STAGE_HELPER >> 8,
        ])
    rom[dispatcher_off:dispatcher_off + len(dispatcher)] = dispatcher

    # C=$FF is restored from the scanner's outer BC frame at completion.
    patch(
        rom, PRIVATE_BANK, SCANNER_TAIL_JP,
        bytes([0xC3, TRANSITION_REPAIR & 0xFF, TRANSITION_REPAIR >> 8]),
        bytes([0xC3, MAPPER_LEAF & 0xFF, MAPPER_LEAF >> 8]),
    )

    rom[0x014D] = header_checksum(rom)
    checksum = global_checksum(rom)
    rom[0x014E] = checksum >> 8
    rom[0x014F] = checksum & 0xFF
    return {
        "schema": "penta-stage1-hazard-batch-r102-static-v1",
        "status": "PASS_STATIC_EMULATOR_REQUIRED",
        "promotable": False,
        "base_sha256": BASE_SHA256,
        "candidate_sha256": digest(rom),
        "mutual_exclusion": {
            "wram": "SVBK2:D600-D689",
            "ted_direct_plane_signature_present": False,
            "production_option": "PENTA_TED_DIRECT_PLANE must remain 0",
        },
        "regions": {
            label: {
                "bank": HELPER_BANK,
                "address": f"0x{address:04X}",
                "size": len(payload),
                "sha256": digest(payload),
            }
            for address, payload, label in regions
        },
        "stage_labels": {key: f"0x{value:04X}" for key, value in stage_labels.items()},
        "publish_labels": {
            key: f"0x{value:04X}" for key, value in publish_labels.items()
        },
        "semantic_rows": {
            "max_staged": MAX_ROWS,
            "overflow": "r101 per-cell helper $4300",
            "left_blocks": 1,
            "right_blocks": 2,
            "settled_total_hblanks": 6,
            "tooth_ids": [f"0x{value:02X}" for value in sorted(TOOTH_IDS)],
            "tooth_attr": "0x0F",
            "padding_bytes_per_row": 8,
        },
        "mapper_abi": {
            "init": "bank19 CALL mapper -> bank20 init -> bank20 CALL mapper -> bank19 $61BC",
            "row": "existing mapper frame -> bank20 stage -> existing $6CDF bridge -> bank19 $61F6",
            "completion": "existing mapper frame -> bank20 batch -> synthetic $55C0 frame -> bank19 repair",
            "stack_access_while_svbk2": False,
            "ime": "inherited DI; no EI added",
        },
        "global_checksum": f"0x{checksum:04X}",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--receipt", type=Path, required=True)
    args = parser.parse_args()
    rom = bytearray(args.base.read_bytes())
    receipt = install(rom)
    receipt["base"] = str(args.base)
    receipt["output"] = str(args.output)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.receipt.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(rom)
    args.receipt.write_text(json.dumps(receipt, indent=2) + "\n")
    print(json.dumps(receipt, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
