#!/usr/bin/env python3
"""Restore the last rendered-clean Stage-1 semantic key on exact r120.

This is a narrow attribution candidate.  It replaces both installer copies of
the 41-byte Stage-1 decision runtime with the receipt-qualified r74 runtime,
which keys each physical map from SCY, DC02, and packed source cells C1BB/C29F.
No copier, DMA, palette, hazard scanner, or later-stage code is changed.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from build_later_gdma_upper_bound import update_checksums


BASE_SHA256 = "029a413b4ef5c0d3fdb6d9d39902821e8b0d9f35a36bed20ab82973f2ab10742"
R74_SHA256 = "6d4223e941a82c4ffd6833d8033fb1e04f6388dbc1f104de92532335f1f480e2"
RUNTIME_OFFSETS = (0x37C96, 0x43C96)
RUNTIME_LENGTH = 41
R120_RUNTIME = bytes.fromhex(
    "FA80D8E6F7FE02201D16DF7CEECB5F1A4FFAFDDC3DC0F04247FA02DCA847"
    "FA7CDFA8B9C812C9C3B9DA"
)
R74_RUNTIME = bytes.fromhex(
    "FA80D8E6F7FE02201D16DF7CEECB5F1A4FF04247FA02DCA847FABB"
    "C1A847FA9FC2A8B9C812C9C3B9DA"
)


def sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def build(source: bytes) -> tuple[bytes, dict[str, object]]:
    digest = sha256(source)
    if digest != BASE_SHA256:
        raise SystemExit(f"unqualified exact r120 base: {digest}")
    if len(R120_RUNTIME) != RUNTIME_LENGTH or len(R74_RUNTIME) != RUNTIME_LENGTH:
        raise SystemExit("internal runtime shape error")

    rom = bytearray(source)
    for offset in RUNTIME_OFFSETS:
        if rom[offset:offset + RUNTIME_LENGTH] != R120_RUNTIME:
            raise SystemExit(f"Stage-1 runtime preimage moved at ${offset:06X}")
        rom[offset:offset + RUNTIME_LENGTH] = R74_RUNTIME
    update_checksums(rom)
    candidate = bytes(rom)

    report = {
        "schema": "penta-stage1-r74-semantic-key-r190-v1",
        "status": "ATTRIBUTION_CANDIDATE_EMULATOR_REQUIRED",
        "promotable": False,
        "base_sha256": digest,
        "rendered_clean_oracle_sha256": R74_SHA256,
        "candidate_sha256": sha256(candidate),
        "runtime_copies": [f"${offset:06X}" for offset in RUNTIME_OFFSETS],
        "changed_subsystem": "Stage-1 per-physical-map semantic decision key only",
        "copier_changed": False,
        "dma_changed": False,
        "palette_table_changed": False,
        "hazard_scanner_changed": False,
        "required_first_gate": "Stage-1 1200-frame rendered no-bleed route",
    }
    return candidate, report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("base", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--receipt", type=Path, required=True)
    args = parser.parse_args()
    candidate, report = build(args.base.read_bytes())
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.receipt.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(candidate)
    args.receipt.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
