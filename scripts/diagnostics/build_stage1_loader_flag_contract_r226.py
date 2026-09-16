#!/usr/bin/env python3
"""Build exact-r210 Stage-1 loader dispatch with the wrapper flag ABI retained.

The seven-byte wrapper site changes from DCFD/CALL-NZ to FFBA/CALL-Z and ends
with CP A.  Both paths retain the original total wrapper cycles:

* Stage 1: the 4-cycle faster LDH load pays for the final CP A.
* Stages 2-7: CALL-Z-not-taken plus CP A costs the same as the old three-byte
  CALL slot replaced by NOPs in the measured 99.7% upper bound.

The final CP A restores Z=1/N=1/H=0/C=0, matching the observed later-stage
loader phase-cache return.  A differs (FFBA rather than $03), so the full
matrix remains mandatory before promotion.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


BASE_SHA256 = "dbc1001bdeef221ed1611a1e728f63050e25111f81cdadbcd8f900f628e02273"
BANK13 = 13 * 0x4000
ADDR = 0x6F85
OLD = bytes.fromhex("FA FD DC B7 C4 0E 6A")
NEW = bytes.fromhex("F0 BA B7 CC 0E 6A BF")


def off(a: int) -> int:
    return BANK13 + a - 0x4000


def sha(data: bytes | bytearray) -> str:
    return hashlib.sha256(data).hexdigest()


def checksums(rom: bytearray) -> None:
    h = 0
    for byte in rom[0x134:0x14D]:
        h = (h - byte - 1) & 0xFF
    rom[0x14D] = h
    total = (sum(rom[:0x14E]) + sum(rom[0x150:])) & 0xFFFF
    rom[0x14E:0x150] = total.to_bytes(2, "big")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("base", type=Path)
    ap.add_argument("output", type=Path)
    ap.add_argument("--receipt", type=Path, required=True)
    args = ap.parse_args()
    source = args.base.read_bytes()
    if sha(source) != BASE_SHA256:
        raise SystemExit(f"unqualified exact r210 base: {sha(source)}")
    if source[off(ADDR):off(ADDR) + len(OLD)] != OLD:
        raise SystemExit("wrapper loader dispatch preimage moved")
    if len(OLD) != len(NEW):
        raise SystemExit("dispatch width changed")

    rom = bytearray(source)
    rom[off(ADDR):off(ADDR) + len(NEW)] = NEW
    checksums(rom)
    candidate = bytes(rom)
    report = {
        "schema": "penta-stage1-loader-flag-contract-r226-v1",
        "status": "PASS_STATIC_EMULATOR_REQUIRED",
        "promotable": False,
        "base_sha256": sha(source),
        "candidate_sha256": sha(candidate),
        "same_width": True,
        "stage1_wrapper_cycles": "44T old == 44T new before callee body",
        "later_wrapper_cycles": "32T measured no-call upper bound",
        "later_flags": "CP A => Z1 N1 H0 C0",
        "trace_evidence": "Stage6 $6A0E=793, $6A16=0: phase cache returns before scene check",
        "known_uncertainty": "later A is FFBA rather than observed $03",
        "required_gates": [
            "Stage 6 >=0.99",
            "Stage 1 speed plus current hazard/menu and low-health",
            "title and attract",
            "seven-stage matrix",
        ],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.receipt.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(candidate)
    args.receipt.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
