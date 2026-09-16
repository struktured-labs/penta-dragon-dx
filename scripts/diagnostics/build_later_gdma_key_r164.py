#!/usr/bin/env python3
"""Build an exact-r120 fixed-width cache-key plus GDMA experiment.

The eight-sample replacement occupies exactly the existing runtime shape and
has zero semantic collisions in the bound 1,218-layout Stage 2-7 corpus.  The
only other change is the already isolated LCD-on HDMA5 command AF -> 2F.
Diagnostic only: active-LCD GDMA still requires emulator and real-hardware
visual qualification.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import analyze_later_attr_signature as signature_audit
from build_later_gdma_upper_bound import (
    ALLOWED_BASES,
    DMA_SELECT,
    PREIMAGE as DMA_PREIMAGE,
    REPLACEMENT as DMA_REPLACEMENT,
    update_checksums,
)


SIGNATURE_A = (444, 4, 74, 426)
SIGNATURE_B = (184, 59, 379, 203)
SOURCE_A = 0x7BB2
SOURCE_B = 0x7C4D
BANKS = (13, 16)
PATCHES = (
    (SOURCE_A + 22, bytes.fromhex("35 C2"), bytes.fromhex("A4 C1")),
    (SOURCE_A + 26, bytes.fromhex("B3 C1"), bytes.fromhex("EA C1")),
    (SOURCE_A + 30, bytes.fromhex("9B C2"), bytes.fromhex("4A C3")),
    (SOURCE_A + 35, bytes.fromhex("A0 C1"), bytes.fromhex("58 C2")),
    (SOURCE_A + 42, bytes.fromhex("ED C2"), bytes.fromhex("1B C3")),
    (SOURCE_B, bytes.fromhex("69 C2"), bytes.fromhex("6B C2")),
)


def sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def verify_corpus(paths: list[Path]) -> dict:
    observed = []
    digest = hashlib.sha256()
    for path in paths:
        payload = path.read_bytes()
        digest.update(payload)
        observed.extend(signature_audit.parse_layout_trace(path))
    records = [
        (stage, room, features,
         signature_audit.desired_plane(stage, features[:576]))
        for stage, room, features in sorted(set(observed))
    ]
    collisions, variants = signature_audit.metrics(
        records, SIGNATURE_A, SIGNATURE_B
    )
    if len(records) != 1218 or collisions != 0:
        raise SystemExit(
            f"fixed-width key corpus failed: records={len(records)} "
            f"collisions={collisions}"
        )
    return {
        "records": len(records),
        "sha256": digest.hexdigest(),
        "signature_a": SIGNATURE_A,
        "signature_b": SIGNATURE_B,
        "collisions": collisions,
        "false_variants": variants,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("base", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--receipt", type=Path, required=True)
    parser.add_argument("--layout-trace", action="append", type=Path,
                        required=True)
    args = parser.parse_args()

    source = args.base.read_bytes()
    digest = sha256(source)
    if digest not in ALLOWED_BASES or ALLOWED_BASES[digest] != "r120":
        raise SystemExit(f"unqualified exact r120 base: {digest}")
    corpus = verify_corpus(args.layout_trace)
    rom = bytearray(source)
    changed = []
    for bank in BANKS:
        for cpu, before, after in PATCHES:
            offset = bank * 0x4000 + cpu - 0x4000
            if rom[offset:offset + len(before)] != before:
                raise SystemExit(
                    f"bank{bank}:${cpu:04X} signature preimage moved"
                )
            rom[offset:offset + len(after)] = after
            changed.extend(range(offset, offset + len(after)))
    if rom[DMA_SELECT:DMA_SELECT + len(DMA_PREIMAGE)] != DMA_PREIMAGE:
        raise SystemExit("native DMA selector preimage moved")
    rom[DMA_SELECT:DMA_SELECT + len(DMA_REPLACEMENT)] = DMA_REPLACEMENT
    changed.append(DMA_SELECT + 5)
    update_checksums(rom)
    output = bytes(rom)
    report = {
        "schema": "penta-later-fixed-key-gdma-r164-v1",
        "status": "PASS_STATIC_EMULATOR_AND_HARDWARE_REQUIRED",
        "promotable": False,
        "base_sha256": digest,
        "candidate_sha256": sha256(output),
        "key_contract": corpus,
        "runtime_shape_changed": False,
        "runtime_cycle_shape_changed": False,
        "patched_runtime_sources": [f"bank{bank}" for bank in BANKS],
        "functional_payload_bytes_changed": len(set(changed)),
        "dma_patch": "$4345 LCD-on HDMA5 command $AF -> $2F",
        "hardware_risk": "active-LCD GDMA display stall requires Pocket/MiSTer audit",
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.receipt.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(output)
    args.receipt.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
