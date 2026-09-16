#!/usr/bin/env python3
"""Build an ABI-correct stock central-OAM upper bound on exact r210.

The historical r203 control copied the stock emitter into the WRAM body but
forgot that the installed fixed-bank wrapper enters it with DI.  The DX body
owns the matching EI; stock does not.  This control appends EI immediately
before the stock RET so it measures only semantic palette-emitter overhead,
not the accidental suppression of all later interrupts.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


BASE_SHA256 = "dbc1001bdeef221ed1611a1e728f63050e25111f81cdadbcd8f900f628e02273"
SOURCE_OFFSET = 0x37B21
SOURCE_SIZE = 60
STOCK_START, STOCK_END = 0x10D1, 0x10EE
EXPECTED_DX = bytes.fromhex(
    "3E0AEAFF1F781213791213C52A1213474F06D90AFEFF281A4F2ACDA211CD8811"
    "E6F8B11213C179C6084F3E00EAFF1FFB79C9F0BEB70E0228E00D18DD"
)


def digest(payload: bytes | bytearray) -> str:
    return hashlib.sha256(payload).hexdigest()


def update_checksums(rom: bytearray) -> None:
    header = 0
    for value in rom[0x0134:0x014D]:
        header = (header - value - 1) & 0xFF
    rom[0x014D] = header
    total = (sum(rom[:0x014E]) + sum(rom[0x0150:])) & 0xFFFF
    rom[0x014E:0x0150] = total.to_bytes(2, "big")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("base", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--receipt", type=Path, required=True)
    args = parser.parse_args()

    source = args.base.read_bytes()
    if digest(source) != BASE_SHA256:
        raise SystemExit(f"unqualified exact r210 base: {digest(source)}")
    if source[SOURCE_OFFSET:SOURCE_OFFSET + SOURCE_SIZE] != EXPECTED_DX:
        raise SystemExit("r210 semantic central-OAM body preimage moved")
    vanilla = (Path(__file__).resolve().parents[2] / "rom/Penta Dragon (J).gb").read_bytes()
    stock = vanilla[STOCK_START:STOCK_END]
    if len(stock) != 29 or stock[-1] != 0xC9:
        raise SystemExit("stock central-OAM emitter preimage moved")

    # Fixed $10D1 is `DI; JP $DA21`; match the production body's ownership of
    # EI and preserve the stock return value/register contract.
    replacement = stock[:-1] + bytes.fromhex("FB C9")
    replacement += bytes(SOURCE_SIZE - len(replacement))
    rom = bytearray(source)
    rom[SOURCE_OFFSET:SOURCE_OFFSET + SOURCE_SIZE] = replacement
    update_checksums(rom)
    candidate = bytes(rom)
    receipt = {
        "schema": "penta-oam-stock-ime-upper-bound-r211-v1",
        "status": "NON_PROMOTABLE_ATTRIBUTION_ONLY",
        "promotable": False,
        "base_sha256": digest(source),
        "candidate_sha256": digest(candidate),
        "fixed_wrapper_contract": "DI; JP $DA21",
        "replacement_contract": "stock emitter; EI; RET",
        "interrupt_balance_preserved": True,
        "semantic_obj_palettes_preserved": False,
        "changed_functional_bytes": SOURCE_SIZE,
        "required_use": "Stage 5 central-OAM performance upper bound only",
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.receipt.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(candidate)
    args.receipt.write_text(json.dumps(receipt, indent=2) + "\n")
    print(json.dumps(receipt, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
