#!/usr/bin/env python3
"""Combine r190's live semantic key with an explicit attract dirty result.

The r190 key removes live pickup/wall trails, but prerecorded Stage 1 contains
moving semantic cells which are not represented by that compact key.  The
production trampoline formerly entered the decider and forced DCFD=0 dirty.
Return the same A=1/NZ and B=5 route contract directly for attract mode while
leaving r190's live decision runtime byte-exact.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from build_later_gdma_upper_bound import update_checksums


BASE_SHA256 = "04fd5e0db57f3cbe959265359442efa1102a60d258adf5718fe86e2feb669893"
TRAMPOLINE_OFFSET = 0x10E7
OLD_TRAMPOLINE = bytes.fromhex("03 CD E0 DA 06 05 C9")
NEW_TRAMPOLINE = bytes.fromhex("3E 01 B7 06 05 C9 00")


def digest(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def build(source: bytes) -> tuple[bytes, dict[str, object]]:
    if digest(source) != BASE_SHA256:
        raise SystemExit(f"unqualified exact r190 base: {digest(source)}")
    rom = bytearray(source)
    end = TRAMPOLINE_OFFSET + len(OLD_TRAMPOLINE)
    if rom[TRAMPOLINE_OFFSET:end] != OLD_TRAMPOLINE:
        raise SystemExit("attract trampoline preimage moved")
    rom[TRAMPOLINE_OFFSET:end] = NEW_TRAMPOLINE
    update_checksums(rom)
    candidate = bytes(rom)

    report = {
        "schema": "penta-stage1-live-key-demo-dirty-r194-v1",
        "status": "ATTRIBUTION_CANDIDATE_EMULATOR_REQUIRED",
        "promotable": False,
        "base_sha256": digest(source),
        "candidate_sha256": digest(candidate),
        "live_runtime_changed": False,
        "attract_result": "A=1/NZ, B=5",
        "timing_risk": "attract decision returns earlier than r120",
        "required_first_gate": "natural attract pickup palettes and route",
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
