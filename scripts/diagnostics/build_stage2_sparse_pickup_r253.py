#!/usr/bin/env python3
"""Rebase the default-off Stage-2 sparse publisher onto qualified r231.

This is an isolated speed experiment.  It preserves r231 byte-for-byte except
for the r113 Stage-2-only publisher, relocated around r231's occupied bank-21
stage-card helper.  It is not a release builder and must pass live scroll,
semantic-plane, pickup-trail, and visual gates before promotion.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from build_stage2_sparse_pickup_r113 import (
    Asm,
    COMPILER_CONTINUATION,
    HELPER_BANK,
    MARKER,
    MAPPER,
    bank_offset,
    build_compiler_continuation,
    checksum,
)


BASE_SHA256 = "1e51c4801bfbc8ff961b81e09958e7ce4ba55de0ec4f8644e36f897d6aebc09c"
RARE_HELPER = 0x4200


def build_rare_helper() -> bytes:
    """Reproduce the exact Stage-2 rare LUT and restore mapped bank 13."""
    code = bytes.fromhex(
        "21 AE C6 3E 02 22 77 2E BE 22 77 2E C6 22 77 2E D6 22 77"
    )
    a = Asm(RARE_HELPER + len(code))
    a.db(0x3E, 0x0D, 0xC3, MAPPER & 0xFF, MAPPER >> 8)
    return code + a.finish()


def install(base: bytes) -> tuple[bytes, dict[str, object]]:
    digest = hashlib.sha256(base).hexdigest()
    if digest != BASE_SHA256:
        raise AssertionError(f"wrong qualified r231 base: {digest}")
    rom = bytearray(base)

    rare_off = bank_offset(13, 0x5422)
    rare_preimage = bytes.fromhex(
        "21 AE C6 3E 02 22 77 2E BE 22 77 2E C6 22 77 2E D6 22 77 C9"
    )
    if rom[rare_off:rare_off + len(rare_preimage)] != rare_preimage:
        raise AssertionError("Stage-2 rare-LUT preimage changed")
    wrapper = bytes.fromhex(
        "B7 20 03 EA 56 DF 3E 15 01 00 42 C5 C3 61 00"
    )
    rom[rare_off:rare_off + len(rare_preimage)] = (
        wrapper + bytes(len(rare_preimage) - len(wrapper))
    )

    compiler_off = bank_offset(1, 0x4302)
    compiler_preimage = bytes.fromhex("F3 11 A0 C1 21")
    if rom[compiler_off:compiler_off + 5] != compiler_preimage:
        raise AssertionError("dirty compiler preimage changed")
    rom[compiler_off:compiler_off + 5] = bytes.fromhex("3E 15 CD 61 00")

    rare = build_rare_helper()
    compiler = build_compiler_continuation()
    regions = (
        (bank_offset(HELPER_BANK, RARE_HELPER), rare, "rare helper"),
        (
            bank_offset(HELPER_BANK, COMPILER_CONTINUATION),
            compiler,
            "sparse compiler",
        ),
    )
    for destination, payload, label in regions:
        if rom[destination:destination + len(payload)] != bytes([0xFF]) * len(payload):
            raise AssertionError(f"{label} cave is not erased")
        rom[destination:destination + len(payload)] = payload

    checksum(rom)
    candidate_sha = hashlib.sha256(rom).hexdigest()
    changed = [i for i, (old, new) in enumerate(zip(base, rom)) if old != new]
    receipt = {
        "schema": "penta-stage2-sparse-pickup-r253-build-v1",
        "status": "static-pass-emulator-required",
        "qualified_base_sha256": digest,
        "candidate_sha256": candidate_sha,
        "default_off": True,
        "changed_byte_count_including_checksums": len(changed),
        "helper_bank": HELPER_BANK,
        "rare_helper": f"${RARE_HELPER:04X}",
        "sparse_compiler": f"${COMPILER_CONTINUATION:04X}",
        "marker": f"${MARKER:04X}",
        "qualification": [
            "Stage 2 strict speed and exact scroll",
            "dual-map semantic equality",
            "pickup movement/removal trail",
            "full r231 visual incident suite",
        ],
    }
    return bytes(rom), receipt


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("base", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--receipt", type=Path, required=True)
    args = parser.parse_args()
    candidate, receipt = install(args.base.read_bytes())
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(candidate)
    args.receipt.parent.mkdir(parents=True, exist_ok=True)
    args.receipt.write_text(json.dumps(receipt, indent=2) + "\n")
    print(json.dumps(receipt, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
