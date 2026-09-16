#!/usr/bin/env python3
"""Build exact-r120 Stage 5 VBlank-prelude attribution controls.

These ROMs are deliberately non-promotable. They remove one steady per-frame
service at a time while preserving instruction width, allowing the guarded
speed verifier to identify which service owns the measured Stage 5 tax.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from build_later_hdma_overlap import BASE_SHA256, BANK_SIZE, checksum


BANK = 13
BG0_CALL_ADDR = 0x6E93
BG0_CALL = bytes.fromhex("CD B8 69")
SEMANTIC_TAIL_ADDR = 0x6EF4
SEMANTIC_TAIL = bytes.fromhex("23 2B C3 2C 57")
LIVE_WINDOW_BRANCH_ADDR = 0x6EFC
LIVE_WINDOW_BRANCH = bytes.fromhex("18 A8")


def bank_offset(address: int) -> int:
    return BANK * BANK_SIZE + address - 0x4000


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("base", type=Path)
    parser.add_argument("output_dir", type=Path)
    args = parser.parse_args()
    source = args.base.read_bytes()
    source_sha = hashlib.sha256(source).hexdigest()
    if source_sha != BASE_SHA256:
        raise SystemExit(f"wrong exact r120 base: {source_sha}")

    args.output_dir.mkdir(parents=True, exist_ok=True)
    controls = {
        "no-bg0-check": (True, False, False),
        "no-semantic-tail": (False, True, False),
        "no-bg0-or-semantic": (True, True, False),
        "no-window-check": (False, False, True),
        "no-bg0-or-window": (True, False, True),
    }
    report = {
        "schema": "penta-stage5-prelude-controls-v1",
        "status": "NON_PROMOTABLE_ATTRIBUTION_ONLY",
        "base_sha256": source_sha,
        "controls": {},
    }
    for name, (skip_bg0, skip_semantic, skip_window) in controls.items():
        rom = bytearray(source)
        bg0 = bank_offset(BG0_CALL_ADDR)
        semantic = bank_offset(SEMANTIC_TAIL_ADDR)
        live_window = bank_offset(LIVE_WINDOW_BRANCH_ADDR)
        if rom[bg0:bg0 + len(BG0_CALL)] != BG0_CALL:
            raise SystemExit("Stage 5 BG0 call preimage moved")
        if rom[semantic:semantic + len(SEMANTIC_TAIL)] != SEMANTIC_TAIL:
            raise SystemExit("Stage 5 semantic tail preimage moved")
        if rom[live_window:live_window + 2] != LIVE_WINDOW_BRANCH:
            raise SystemExit("Stage 5 live-window branch preimage moved")
        if skip_bg0:
            rom[bg0:bg0 + len(BG0_CALL)] = bytes(len(BG0_CALL))
        if skip_semantic:
            # Keep the receipt-locked INC HL/DEC HL pair, then return from the
            # prelude instead of tail-jumping into the semantic decider.
            rom[semantic + 2:semantic + 5] = bytes.fromhex("C9 00 00")
        if skip_window:
            # The live arm already executed NOP/INC HL/DEC HL. Retarget its
            # backward jump to the unchanged semantic JP at $6EF6.
            rom[live_window:live_window + 2] = bytes.fromhex("18 F8")
        checksum(rom)
        output = args.output_dir / f"{name}.gb"
        output.write_bytes(rom)
        report["controls"][name] = {
            "sha256": hashlib.sha256(rom).hexdigest(),
            "skip_bg0_check": skip_bg0,
            "skip_semantic_tail": skip_semantic,
            "skip_window_check": skip_window,
        }
    (args.output_dir / "receipt.json").write_text(
        json.dumps(report, indent=2) + "\n"
    )
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
