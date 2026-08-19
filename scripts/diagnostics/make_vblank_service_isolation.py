#!/usr/bin/env python3
"""Create a byte-confined VBlank-service attribution ROM.

This is diagnostic tooling, never a release builder. It replaces exactly one
three-byte CALL in the qualified bank-13 wrapper with NOPs, updates the global
checksum, and emits a receipt proving that no other byte changed.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


BANK = 13
WRAPPER_ADDR = 0x6F1D
WRAPPER_SIZE = 114
SERVICES = {
    "death": bytes.fromhex("CD 00 71"),
    "title-palette": bytes.fromhex("CD 60 6A"),
    "palette-pending": bytes.fromhex("CD 90 6C"),
    "palette-idle": bytes.fromhex("CC 90 6C"),
    "prelude": bytes.fromhex("C4 80 6E"),
    "colorizer": bytes.fromhex("D4 00 6E"),
    "glyph-copy": bytes.fromhex("CD A7 6D"),
}


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def global_checksum(rom: bytearray) -> int:
    return sum(rom[:0x14E]) + sum(rom[0x150:]) & 0xFFFF


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("rom", type=Path)
    parser.add_argument("service", choices=SERVICES)
    parser.add_argument("output", type=Path)
    parser.add_argument("--receipt", type=Path)
    args = parser.parse_args()

    source_path, output_path = args.rom.resolve(), args.output.resolve()
    source = source_path.read_bytes()
    rom = bytearray(source)
    wrapper_offset = BANK * 0x4000 + (WRAPPER_ADDR - 0x4000)
    wrapper = bytes(rom[wrapper_offset:wrapper_offset + WRAPPER_SIZE])
    call = SERVICES[args.service]
    if wrapper.count(call) != 1:
        raise SystemExit(
            f"expected one {args.service} call {call.hex()}, found {wrapper.count(call)}"
        )
    relative = wrapper.index(call)
    offset = wrapper_offset + relative
    rom[offset:offset + len(call)] = bytes(len(call))
    checksum = global_checksum(rom)
    rom[0x14E:0x150] = checksum.to_bytes(2, "big")

    changed = [index for index, (old, new) in enumerate(zip(source, rom)) if old != new]
    allowed = set(range(offset, offset + 3)) | {0x14E, 0x14F}
    if not set(changed) <= allowed or rom[offset:offset + 3] != bytes(3):
        raise SystemExit(f"unconfined byte delta: {[hex(index) for index in changed]}")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(rom)
    receipt_path = (
        args.receipt.resolve()
        if args.receipt
        else output_path.with_suffix(output_path.suffix + ".json")
    )
    receipt = {
        "schema": "penta-vblank-service-isolation-v1",
        "status": "pass",
        "source": str(source_path),
        "source_sha256": sha256(source),
        "output": str(output_path),
        "output_sha256": sha256(rom),
        "service": args.service,
        "wrapper_bank": BANK,
        "wrapper_address": f"0x{WRAPPER_ADDR:04X}",
        "call_address": f"0x{WRAPPER_ADDR + relative:04X}",
        "call_bytes": call.hex().upper(),
        "replacement_bytes": "000000",
        "changed_offsets": [f"0x{index:06X}" for index in changed],
        "global_checksum": f"0x{checksum:04X}",
        "checks": {
            "one_call_matched": True,
            "three_call_bytes_nopped": True,
            "all_other_changes_are_global_checksum": True,
            "rom_size_preserved": len(rom) == len(source),
        },
    }
    receipt_path.parent.mkdir(parents=True, exist_ok=True)
    receipt_path.write_text(json.dumps(receipt, indent=2) + "\n")
    print(
        f"PASS: {args.service} disabled at bank13:${WRAPPER_ADDR + relative:04X}; "
        f"{len(changed)} confined byte changes; receipt={receipt_path}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
