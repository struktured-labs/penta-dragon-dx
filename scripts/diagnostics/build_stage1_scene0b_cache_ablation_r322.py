#!/usr/bin/env python3
"""Build r322: A/B only r313's Scene-$0B semantic-cache invalidation.

This diagnostic candidate is intentionally non-promotable.  It retains r320's
atomic publisher and r313's normal return path, while replacing only the
eight-byte ``DF53/DF57 = FF`` invalidation sequence in the stale repair path
with NOPs.  It distinguishes a bad r314 stack return from the cache-driven
native menu transition regression without changing any other game code.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import build_stage1_scene0b_menu_return_r321 as r321


ROOT = r321.ROOT
TMP = r321.TMP
BASE = r321.BASE
BASE_RECEIPT = r321.BASE_RECEIPT
OUTPUT = TMP / "stage1-scene0b-cache-ablation-r322/candidate.gb"
RECEIPT = TMP / "stage1-scene0b-cache-ablation-r322/build-receipt.json"

# r313's exact repair bytes are: LD A,$FF; LD (DF53),A; LD (DF57),A.
CACHE_INVALIDATION_SIZE = 8
CACHE_INVALIDATION_ADDR = r321.r313.HANDLER_LABELS["repair_effect"] - CACHE_INVALIDATION_SIZE


def digest(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def build(source: bytes, receipt_bytes: bytes) -> tuple[bytes, dict]:
    r321.validate_preimages(source, receipt_bytes)
    handler = bytearray(r321.HANDLER)
    local = CACHE_INVALIDATION_ADDR - r321.HANDLER_ADDR
    if handler[local:local + CACHE_INVALIDATION_SIZE] != bytes.fromhex("3E FF EA 53 DF EA 57 DF"):
        raise AssertionError("r313 cache invalidation preimage changed")
    handler[local:local + CACHE_INVALIDATION_SIZE] = bytes(CACHE_INVALIDATION_SIZE)
    rom = bytearray(source)
    offset = r321.handler_offset()
    rom[offset:offset + len(handler)] = handler
    r321.r320.r319.r318.r317.r305.r304.update_checksums(rom)
    candidate = bytes(rom)
    changed = r321.functional_offsets(source, candidate)
    expected = {offset + index for index, (before, after) in enumerate(
        zip(source[offset:offset + len(handler)], handler, strict=True)
    ) if before != after}
    if changed != expected:
        raise AssertionError("r322 functional delta escaped handler")
    checked = bytearray(candidate)
    r321.r320.r319.r318.r317.r305.r304.update_checksums(checked)
    if bytes(checked) != candidate:
        raise AssertionError("r322 checksums not canonical")
    sha = digest(candidate)
    return candidate, {
        "schema": "penta-stage1-scene0b-cache-ablation-r322-build-v1",
        "status": "STATIC_PASS_ABLATION_LIVE_GATE_REQUIRED",
        "promotable": False,
        "emulator_invoked": False,
        "candidate_sha256": sha,
        "patch": {
            "r320_atomic_publisher": "unchanged",
            "r313_return": "exact except cache invalidation",
            "ablated_bytes": f"bank31:${CACHE_INVALIDATION_ADDR:04X}-${CACHE_INVALIDATION_ADDR + CACHE_INVALIDATION_SIZE - 1:04X}",
            "old": "3E FF EA 53 DF EA 57 DF",
            "new": "00 00 00 00 00 00 00 00",
        },
        "functional_changed_bytes_from_r320": len(changed),
        "required_live_gate": "menu-loaded close/reopen acknowledgement only",
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", type=Path, default=BASE)
    parser.add_argument("--base-receipt", type=Path, default=BASE_RECEIPT)
    parser.add_argument("--output", type=Path, default=OUTPUT)
    parser.add_argument("--receipt", type=Path, default=RECEIPT)
    args = parser.parse_args()
    candidate, receipt = build(args.base.read_bytes(), args.base_receipt.read_bytes())
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.receipt.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(candidate)
    args.receipt.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"candidate_sha256": receipt["candidate_sha256"], "output": str(args.output)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
