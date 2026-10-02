#!/usr/bin/env python3
"""Build an exact-r120 Stage-1 always-dirty correctness control.

This replaces only the middle decision block in both installer copies of the
41-byte Stage-1 runtime. Exact live scene $02 returns dirty immediately.
Gargoyle scene $0A retains its original prerecorded DCFD rule and uses the
existing pickup-build key in live play. It changes no compiler, DMA, palette,
or post-copy code and is intentionally non-promotable.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from build_later_gdma_upper_bound import update_checksums


BASE_SHA256 = "029a413b4ef5c0d3fdb6d9d39902821e8b0d9f35a36bed20ab82973f2ab10742"
RUNTIME_OFFSETS = (0x37C96, 0x43C96)
RUNTIME_LENGTH = 41
RUNTIME_PREIMAGE = bytes.fromhex(
    "FA80D8E6F7FE02201D16DF7CEECB5F1A4FFAFDDC3DC0F04247FA02DCA847"
    "FA7CDFA8B9C812C9C3B9DA"
)
CONTROL_RUNTIME = bytes.fromhex(
    # Exact Stage 1 -> dirty leaf; exact Gargoyle -> cache body; others pure.
    "FA80D8FE02281EFE0A2018"
    # Existing per-physical-map cache selector and cached byte.
    "16DF7CEECB5F1A4F"
    # Preserve prerecorded Gargoyle's DCFD=0 always-dirty rule.
    "FAFDDC3DC0"
    # Compact live Gargoyle key: SCY XOR room-return pickup-build key.
    "F04247FA7CDFA8"
    # Existing compare/store return tail.
    "B9C812C9"
    # Neutral leaf; dirty leaf; reserved padding.
    "AFC93CC90000"
)


def sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("base", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--receipt", type=Path, required=True)
    args = parser.parse_args()

    source = args.base.read_bytes()
    digest = sha256(source)
    if digest != BASE_SHA256:
        raise SystemExit(f"unqualified exact r120 base: {digest}")
    if len(RUNTIME_PREIMAGE) != RUNTIME_LENGTH or len(CONTROL_RUNTIME) != 41:
        raise SystemExit("internal runtime shape error")
    rom = bytearray(source)
    for offset in RUNTIME_OFFSETS:
        if rom[offset:offset + RUNTIME_LENGTH] != RUNTIME_PREIMAGE:
            raise SystemExit(f"Stage-1 decision runtime preimage moved at ${offset:06X}")
        rom[offset:offset + RUNTIME_LENGTH] = CONTROL_RUNTIME
    update_checksums(rom)
    output = bytes(rom)
    report = {
        "schema": "penta-stage1-always-dirty-r189-v1",
        "status": "CORRECTNESS_CONTROL_EMULATOR_REQUIRED",
        "promotable": False,
        "base_sha256": digest,
        "candidate_sha256": sha256(output),
        "runtime_copies": [f"${offset:06X}" for offset in RUNTIME_OFFSETS],
        "compiler_changed": False,
        "dma_changed": False,
        "postcopy_changed": False,
        "required_first_gate": "Stage-1 1200-frame rendered no-bleed route",
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.receipt.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(output)
    args.receipt.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
