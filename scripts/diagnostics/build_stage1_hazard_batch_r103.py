#!/usr/bin/env python3
"""Build r103: make r102's batch compiler use immutable bank-20 LUT data.

r102 read the runtime C600 table while the item handler temporarily owns that
fixed-WRAM region.  The old semantic writer never had that dependency: its
expanded LUT is immutable ROM at bank20:$4400.  This isolated diagnostic
changes only the row compiler's lookup source and the ROM checksums.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).resolve().parent))

import build_stage1_hazard_batch_r102 as r102


BASE_SHA256 = "6691a8ed2785e44641d00acf311b0ab89750c7a82e55e0136dcf8b3b784fcb59"
COMPILE_ADDR = 0x45AF
TAIL_ADDR = 0x45C5
OLD_COMPILE = bytes.fromhex(
    "1A 13 4F E6 EF D6 64 FE 06 30 07 06 C6 0A F6 08 "
    "18 03 06 C6 0A 22"
)
NEW_COMPILE = bytes.fromhex(
    "1A 13 4F 06 44 0A 22 C3 C5 45"
) + bytes(len(OLD_COMPILE) - 10)


def digest(data: bytes | bytearray) -> str:
    return hashlib.sha256(data).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--receipt", type=Path, required=True)
    args = parser.parse_args()

    source = args.base.read_bytes()
    if digest(source) != BASE_SHA256:
        raise SystemExit("base is not exact rejected r102")
    rom = bytearray(source)
    r102.patch(
        rom, r102.HELPER_BANK, COMPILE_ADDR, OLD_COMPILE, NEW_COMPILE
    )
    rom[0x014D] = r102.header_checksum(rom)
    checksum = r102.global_checksum(rom)
    rom[0x014E] = checksum >> 8
    rom[0x014F] = checksum & 0xFF

    receipt = {
        "schema": "penta-stage1-hazard-batch-r103-static-v1",
        "status": "PASS_STATIC_EMULATOR_REQUIRED",
        "promotable": False,
        "base": str(args.base),
        "base_sha256": digest(source),
        "output": str(args.output),
        "output_sha256": digest(rom),
        "single_change": {
            "bank": r102.HELPER_BANK,
            "address": f"0x{COMPILE_ADDR:04X}",
            "size": len(OLD_COMPILE),
            "old": OLD_COMPILE.hex(" "),
            "new": NEW_COMPILE.hex(" "),
            "runtime_dependency_removed": "fixed WRAM C600",
            "immutable_dependency": "bank20 ROM $4400",
            "tail": f"0x{TAIL_ADDR:04X}",
        },
        "r102_batch_contract_preserved": True,
        "global_checksum": f"0x{checksum:04X}",
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.receipt.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(rom)
    args.receipt.write_text(json.dumps(receipt, indent=2) + "\n")
    print(json.dumps(receipt, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
