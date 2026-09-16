#!/usr/bin/env python3
"""Add r194's attract dirty route to the exact r193 hybrid live key.

The r194 artifact accidentally used r190's compact key and therefore omitted
DF7C, the live pickup-build discriminator.  This isolated candidate retains
r193's SCY/DC02/C1BB/DF7C per-map key and changes only the prerecorded attract
trampoline to return dirty directly.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from build_later_gdma_upper_bound import update_checksums


BASE_SHA256 = "687d078aaabaad03f2c09fc17808e0974094ce88549cdb25924c2826b55df158"
TRAMPOLINE_OFFSET = 0x10E7
OLD_TRAMPOLINE = bytes.fromhex("03 CD E0 DA 06 05 C9")
NEW_TRAMPOLINE = bytes.fromhex("3E 01 B7 06 05 C9 00")


def sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("base", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--receipt", type=Path, required=True)
    args = parser.parse_args()

    source = args.base.read_bytes()
    if sha256(source) != BASE_SHA256:
        raise SystemExit(f"unqualified exact r193 base: {sha256(source)}")
    rom = bytearray(source)
    end = TRAMPOLINE_OFFSET + len(OLD_TRAMPOLINE)
    if rom[TRAMPOLINE_OFFSET:end] != OLD_TRAMPOLINE:
        raise SystemExit("attract trampoline preimage moved")
    rom[TRAMPOLINE_OFFSET:end] = NEW_TRAMPOLINE
    update_checksums(rom)
    candidate = bytes(rom)

    report = {
        "schema": "penta-stage1-hybrid-key-demo-dirty-r196-v1",
        "status": "ATTRIBUTION_CANDIDATE_EMULATOR_REQUIRED",
        "promotable": False,
        "base_sha256": sha256(source),
        "candidate_sha256": sha256(candidate),
        "live_key": ["SCY", "DC02", "C1BB", "DF7C"],
        "attract_result": "A=1/NZ, B=5",
        "copier_changed": False,
        "publisher_changed": False,
        "required_first_gate": "live pickup attributes on both physical maps",
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.receipt.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(candidate)
    args.receipt.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
