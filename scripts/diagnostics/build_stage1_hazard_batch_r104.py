#!/usr/bin/env python3
"""Build r104: normalize batch destinations by semantic route.

r103 preserved the callers' historical ``OR start`` address calculation.
When the completed map's row base already had low nibble $8, left start $4
became $C.  This diagnostic gives start-0, left-4, and right-8 routes distinct
bank-20 normalizers before they enter the unchanged shared stager.
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


BASE_SHA256 = "29b0a9906be3ecebebf58d06e52b18d93038c058f72eb7dd3787e8197bd7337a"

NORMALIZE_START0 = 0x4740
NORMALIZE_LEFT4 = 0x4750
NORMALIZE_RIGHT8 = 0x4760

START0_TRAMPOLINES = (0x61A0, 0x67ED)
LEFT4_TRAMPOLINE = 0x6B70
CLASSIFIER_ADDR = r102.RELOCATED_CLASSIFIER
CLASSIFIER_SIZE = 60
CLASSIFIER_LEFT_TAIL = 43
CLASSIFIER_RIGHT_TAIL = 57


def digest(data: bytes | bytearray) -> str:
    return hashlib.sha256(data).hexdigest()


def normalizer(start: int) -> bytes:
    code = bytearray((0x7D, 0xE6, 0xF0))   # LD A,L; AND $F0
    if start:
        code.extend((0xF6, start))         # OR exact semantic start
    code.extend((
        0x6F,                              # LD L,A
        0xC3, r102.STAGE_HELPER & 0xFF, r102.STAGE_HELPER >> 8,
    ))
    return bytes(code)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--receipt", type=Path, required=True)
    args = parser.parse_args()

    source = args.base.read_bytes()
    if digest(source) != BASE_SHA256:
        raise SystemExit("base is not exact rejected r103")
    rom = bytearray(source)

    routes = {
        "start0": (NORMALIZE_START0, normalizer(0)),
        "left4": (NORMALIZE_LEFT4, normalizer(4)),
        "right8": (NORMALIZE_RIGHT8, normalizer(8)),
    }
    for label, (address, code) in routes.items():
        off = r102.bank_offset(r102.HELPER_BANK, address)
        if rom[off:off + len(code)] != bytes([0xFF]) * len(code):
            raise AssertionError(f"{label} normalizer cave is not FF")
        rom[off:off + len(code)] = code

    old_stage_jump = bytes([
        0xC3, r102.STAGE_HELPER & 0xFF, r102.STAGE_HELPER >> 8,
    ])
    for address in START0_TRAMPOLINES:
        r102.patch(
            rom, r102.HELPER_BANK, address, old_stage_jump,
            bytes([0xC3, NORMALIZE_START0 & 0xFF, NORMALIZE_START0 >> 8]),
        )
    r102.patch(
        rom, r102.HELPER_BANK, LEFT4_TRAMPOLINE, old_stage_jump,
        bytes([0xC3, NORMALIZE_LEFT4 & 0xFF, NORMALIZE_LEFT4 >> 8]),
    )

    classifier_off = r102.bank_offset(r102.HELPER_BANK, CLASSIFIER_ADDR)
    classifier = bytearray(rom[
        classifier_off:classifier_off + CLASSIFIER_SIZE
    ])
    for offset, target in (
        (CLASSIFIER_LEFT_TAIL, NORMALIZE_LEFT4),
        (CLASSIFIER_RIGHT_TAIL, NORMALIZE_RIGHT8),
    ):
        if classifier[offset:offset + 3] != old_stage_jump:
            raise AssertionError(f"classifier tail +{offset} changed")
        classifier[offset:offset + 3] = bytes([
            0xC3, target & 0xFF, target >> 8,
        ])
    rom[classifier_off:classifier_off + CLASSIFIER_SIZE] = classifier

    rom[0x014D] = r102.header_checksum(rom)
    checksum = r102.global_checksum(rom)
    rom[0x014E] = checksum >> 8
    rom[0x014F] = checksum & 0xFF
    receipt = {
        "schema": "penta-stage1-hazard-batch-r104-static-v1",
        "status": "PASS_STATIC_EMULATOR_REQUIRED",
        "promotable": False,
        "base": str(args.base),
        "base_sha256": digest(source),
        "output": str(args.output),
        "output_sha256": digest(rom),
        "normalizers": {
            label: {
                "bank": r102.HELPER_BANK,
                "address": f"0x{address:04X}",
                "size": len(code),
                "bytes": code.hex(" "),
            }
            for label, (address, code) in routes.items()
        },
        "route_ownership": {
            "bank20:$61A0,$67ED": "start0",
            "bank20:$6B70,classifier-left": "left4",
            "classifier-right": "right8",
        },
        "shared_stager": f"0x{r102.STAGE_HELPER:04X}",
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
