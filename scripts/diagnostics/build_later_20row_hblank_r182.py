#!/usr/bin/env python3
"""Build an exact-r120 20-row later-stage HBlank publication control.

The packed later-dungeon source has 20 populated rows.  The existing compiler
still rebuilds the complete 24x32 staging plane, including four neutral tail
rows; this diagnostic changes only the rendered-LCD HBlank command from 48 to
40 blocks.  LCD-off publication remains the established complete 48-block
GDMA.  Promotion requires cold, transition, dual-map, and long-soak proof that
the omitted tail remains neutral on both physical maps.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from build_later_gdma_upper_bound import ALLOWED_BASES, update_checksums


LCD_ON_COMMAND_ADDR = 0x4345
PREIMAGE = 0xAF                         # 48 blocks, HBlank DMA
DEFAULT_BLOCKS = 40
COMPILER_ROW_COUNT_ADDR = 0x4310
COMPILER_ROW_COUNT_PREIMAGE = 0x18


def sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("base", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--receipt", type=Path, required=True)
    parser.add_argument("--blocks", type=int, default=DEFAULT_BLOCKS)
    parser.add_argument("--compile-rows", type=int, default=24)
    args = parser.parse_args()
    if not 40 <= args.blocks <= 48:
        parser.error("--blocks must be in the bounded 40..48 range")
    if not 20 <= args.compile_rows <= 24:
        parser.error("--compile-rows must be in the bounded 20..24 range")
    if args.blocks > args.compile_rows * 2:
        parser.error("HBlank transfer cannot exceed the compiled row prefix")

    source = args.base.read_bytes()
    digest = sha256(source)
    if digest not in ALLOWED_BASES or ALLOWED_BASES[digest] != "r120":
        raise SystemExit(f"unqualified exact r120 base: {digest}")
    rom = bytearray(source)
    if rom[LCD_ON_COMMAND_ADDR] != PREIMAGE:
        raise SystemExit("LCD-on HBlank command preimage moved")
    if rom[COMPILER_ROW_COUNT_ADDR] != COMPILER_ROW_COUNT_PREIMAGE:
        raise SystemExit("attribute compiler row-count preimage moved")
    # Bind the full selector shape: LCD-off keeps $2F and only LCD-on changes.
    if rom[0x4340:0x4348] != bytes.fromhex("3E 2F 28 02 3E AF E0 55"):
        raise SystemExit("LCD-aware DMA selector changed")
    replacement = 0x80 | (args.blocks - 1)
    rom[LCD_ON_COMMAND_ADDR] = replacement
    rom[COMPILER_ROW_COUNT_ADDR] = args.compile_rows
    update_checksums(rom)
    output = bytes(rom)
    report = {
        "schema": "penta-later-20row-hblank-r182-v1",
        "status": "PASS_STATIC_EMULATOR_AND_HARDWARE_REQUIRED",
        "promotable": False,
        "base_sha256": digest,
        "candidate_sha256": sha256(output),
        "patch": (
            f"$4345: HBlank $AF (48 blocks) -> "
            f"${replacement:02X} ({args.blocks} blocks)"
        ),
        "hblank_blocks": args.blocks,
        "compiled_rows": args.compile_rows,
        "compiler_changed": False,
        "cache_changed": False,
        "lcd_off_gdma": "unchanged 48 blocks",
        "semantic_tail_contract": "rows 20-23 must remain BG0 on both maps",
        "required_next_gate": "Stage-7 patrol, then cold/transition 8k soak",
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.receipt.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(output)
    args.receipt.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
