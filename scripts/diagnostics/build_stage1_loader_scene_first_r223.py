#!/usr/bin/env python3
"""Build exact-r210 scene-first Stage-1 live-loader gating.

The loader's two independent early-return predicates commute.  r210 checks a
Stage-1 phase field before checking scene ownership, so every later live stage
pays both checks.  This same-width candidate checks D880 first.  Stage-1 calls
that pass both predicates execute the same body with the same total check cost.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


BASE_SHA256 = "dbc1001bdeef221ed1611a1e728f63050e25111f81cdadbcd8f900f628e02273"
BANK13 = 13 * 0x4000
ADDR = 0x6A0E
OLD = bytes.fromhex("FA 5B DF E6 03 FE 03 C8 FA 80 D8 E6 F7 FE 02 C0")
NEW = bytes.fromhex("FA 80 D8 E6 F7 FE 02 C0 FA 5B DF E6 03 FE 03 C8")


def off(address: int) -> int:
    return BANK13 + address - 0x4000


def sha(data: bytes | bytearray) -> str:
    return hashlib.sha256(data).hexdigest()


def fix_checksums(rom: bytearray) -> None:
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
        raise SystemExit("Stage-1 live-loader gate preimage moved")
    if len(OLD) != len(NEW):
        raise SystemExit("gate reorder changed instruction width")

    rom = bytearray(source)
    rom[off(ADDR):off(ADDR) + len(NEW)] = NEW
    fix_checksums(rom)
    candidate = bytes(rom)
    changed = [i for i, pair in enumerate(zip(source, candidate)) if pair[0] != pair[1]]
    allowed = set(range(off(ADDR), off(ADDR) + len(NEW))) | {0x14D, 0x14E, 0x14F}
    if set(changed) - allowed:
        raise SystemExit("candidate changed bytes outside the gate and checksums")

    report = {
        "schema": "penta-stage1-loader-scene-first-r223-v1",
        "status": "PASS_STATIC_EMULATOR_REQUIRED",
        "promotable": False,
        "base_sha256": sha(source),
        "candidate_sha256": sha(candidate),
        "same_width": True,
        "logical_contract": "(D880 & $F7) == $02 AND (DF5B & 3) != 3",
        "stage1_passing_path_check_cycles_preserved": True,
        "later_stage_path": "scene check then RET NZ before DF5B",
        "renderer_map_palette_data_untouched": True,
        "required_gates": [
            "Stage 6 >=0.99",
            "Stage 1 speed and exact scroll",
            "Stage 1 current hazard/menu and low-health fixtures",
            "all-stage speed matrix",
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
