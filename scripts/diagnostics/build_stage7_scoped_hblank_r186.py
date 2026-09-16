#!/usr/bin/env python3
"""Build an exact-r120 Stage-7-only 42-block HBlank experiment.

The bank-1 DMA selector has no room for a fail-closed scene discriminator.
This diagnostic maps an erased expansion-bank helper only on dirty attribute
publications.  The helper retains the established LCD-off 48-block GDMA and
LCD-on 48-block HBlank modes for every scene except exact Stage 7 ($08), where
it uses the visually-qualified 42-block prefix.  It then restores bank 1 at
the original post-wait continuation.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from build_later_gdma_upper_bound import ALLOWED_BASES, update_checksums
from build_later_hdma_overlap import Asm, BANK_SIZE


HELPER_BANK = 21
PATCH_ADDR = 0x433C
PATCH_END = 0x434E
# The last byte of the replaced selector is free after the mapper entry.  Use
# it to restore the caller's BC before the byte-exact native cleanup at $434E.
RESUME_ADDR = PATCH_END - 1
HELPER_ADDR = RESUME_ADDR
MAPPER = 0x0061
PATCH_PREIMAGE = bytes.fromhex(
    "F0 40 CB 7F 3E 2F 28 02 3E AF E0 55 F0 55 CB 7F 28 FA"
)


def bank_offset(bank: int, address: int) -> int:
    return bank * BANK_SIZE + address - 0x4000


def sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def build_helper() -> bytes:
    a = Asm(HELPER_ADDR)
    a.db(0xF0, 0x40, 0xCB, 0x7F)          # LCDC.7
    a.db(0x3E, 0x2F)                      # LCD off: full 48-block GDMA
    a.jr(0x28, "command")
    a.db(0xFA, 0x80, 0xD8, 0xFE, 0x08)   # exact Stage-7 scene only
    a.db(0x3E, 0xAF)                      # default: full HBlank plane
    a.jr(0x20, "command")
    a.db(0x3E, 0xA9)                      # Stage 7: 42 HBlank blocks
    a.label("command")
    a.db(0xE0, 0x55)
    a.label("wait")
    a.db(0xF0, 0x55, 0xCB, 0x7F)
    a.jr(0x28, "wait")
    # The entry saved the caller's BC below the helper's mapper frame.  This
    # synthetic frame returns to a one-byte POP BC at $434D, after which the
    # byte-exact native cleanup starts at $434E.
    a.db(
        0x01, RESUME_ADDR & 0xFF, RESUME_ADDR >> 8,
        0xC5, 0x3E, 0x01,
        0xC3, MAPPER & 0xFF, MAPPER >> 8,
    )
    return a.finish()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("base", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--receipt", type=Path, required=True)
    args = parser.parse_args()

    source = args.base.read_bytes()
    digest = sha256(source)
    if digest not in ALLOWED_BASES or ALLOWED_BASES[digest] != "r120":
        raise SystemExit(f"unqualified exact r120 base: {digest}")
    rom = bytearray(source)
    if rom[PATCH_ADDR:PATCH_END] != PATCH_PREIMAGE:
        raise SystemExit("bank-1 LCD-aware DMA selector preimage moved")

    # Mapper RET enters the helper at the same logical address in bank 21.
    entry = bytes((
        0xC5,                         # preserve BC for the post-copy callback
        0x3E, HELPER_BANK,
        0x01, HELPER_ADDR & 0xFF, HELPER_ADDR >> 8,
        0xC5,
        0xC3, MAPPER & 0xFF, MAPPER >> 8,
    ))
    padding = PATCH_END - PATCH_ADDR - len(entry) - 1
    if padding < 0:
        raise SystemExit("bank-1 selector entry no longer fits")
    rom[PATCH_ADDR:PATCH_END] = entry + bytes(padding) + bytes((0xC1,))

    helper = build_helper()
    helper_offset = bank_offset(HELPER_BANK, HELPER_ADDR)
    if rom[helper_offset:helper_offset + len(helper)] != bytes([0xFF]) * len(helper):
        raise SystemExit("bank-21 Stage-7 DMA helper cave is not erased")
    rom[helper_offset:helper_offset + len(helper)] = helper
    update_checksums(rom)
    output = bytes(rom)
    report = {
        "schema": "penta-stage7-scoped-hblank-r187-v1",
        "status": "PASS_STATIC_EMULATOR_AND_HARDWARE_REQUIRED",
        "promotable": False,
        "base_sha256": digest,
        "candidate_sha256": sha256(output),
        "helper": f"bank{HELPER_BANK}:${HELPER_ADDR:04X}, {len(helper)} bytes",
        "stage7_lcd_on_command": "$A9 (42 blocks)",
        "other_lcd_on_command": "$AF (48 blocks)",
        "lcd_off_command": "$2F (48 blocks)",
        "compiler_changed": False,
        "cache_changed": False,
        "stage1_semantics_changed": False,
        "caller_bc": "saved at selector entry; restored at $434D before native cleanup",
        "risk": "dirty-publication mapper overhead and stack balance need live proof",
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.receipt.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(output)
    args.receipt.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
