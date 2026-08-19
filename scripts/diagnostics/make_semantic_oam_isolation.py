#!/usr/bin/env python3
"""Replace only the hot central semantic OAM body with the stock emitter."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


BANK = 13
SOURCE_ADDR = 0x7B21
SOURCE_SIZE = 60
STOCK_START, STOCK_END = 0x10D1, 0x10EE
EXPECTED_DX = bytes.fromhex(
    "3E0AEAFF1F781213791213C52A1213474F06D90AFEFF281A4F2ACDA211CD8811"
    "E6F8B11213C179C6084F3E00EAFF1FFB79C9F0BEB70E0228E00D18DD"
)


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def update_global_checksum(rom: bytearray) -> int:
    checksum = (sum(rom[:0x14E]) + sum(rom[0x150:])) & 0xFFFF
    rom[0x14E:0x150] = checksum.to_bytes(2, "big")
    return checksum


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("rom", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--receipt", type=Path)
    args = parser.parse_args()

    source_path, output_path = args.rom.resolve(), args.output.resolve()
    source = source_path.read_bytes()
    vanilla = (Path(__file__).resolve().parents[2] / "rom/Penta Dragon (J).gb").read_bytes()
    stock = vanilla[STOCK_START:STOCK_END]
    if len(stock) != 29:
        raise SystemExit("stock central OAM emitter is not 29 bytes")
    offset = BANK * 0x4000 + SOURCE_ADDR - 0x4000
    if source[offset:offset + SOURCE_SIZE] != EXPECTED_DX:
        raise SystemExit("qualified ROM central OAM source does not match the audited DX body")

    rom = bytearray(source)
    replacement = stock + bytes(SOURCE_SIZE - len(stock))
    rom[offset:offset + SOURCE_SIZE] = replacement
    checksum = update_global_checksum(rom)
    changed = [index for index, (old, new) in enumerate(zip(source, rom)) if old != new]
    allowed = set(range(offset, offset + SOURCE_SIZE)) | {0x14E, 0x14F}
    if not set(changed) <= allowed:
        raise SystemExit(f"unconfined delta: {[hex(index) for index in changed]}")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(rom)
    receipt_path = (
        args.receipt.resolve()
        if args.receipt
        else output_path.with_suffix(output_path.suffix + ".json")
    )
    receipt = {
        "schema": "penta-semantic-oam-isolation-v1", "status": "pass",
        "source": str(source_path), "source_sha256": sha256(source),
        "output": str(output_path), "output_sha256": sha256(rom),
        "source_bank": BANK, "source_address": f"0x{SOURCE_ADDR:04X}",
        "runtime_address": "0xDA21",
        "stock_source_range": [f"0x{STOCK_START:04X}", f"0x{STOCK_END:04X}"],
        "dx_body_sha256": sha256(EXPECTED_DX),
        "stock_body_sha256": sha256(stock),
        "changed_offsets": [f"0x{index:06X}" for index in changed],
        "global_checksum": f"0x{checksum:04X}",
        "checks": {
            "qualified_dx_body_exact": True,
            "stock_body_exact": True,
            "runtime_copy_width_preserved": True,
            "all_changes_confined_to_source_and_checksum": True,
            "rom_size_preserved": len(rom) == len(source),
        },
    }
    receipt_path.write_text(json.dumps(receipt, indent=2) + "\n")
    print(
        f"PASS: stock central OAM body staged at bank13:${SOURCE_ADDR:04X}; "
        f"receipt={receipt_path}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
