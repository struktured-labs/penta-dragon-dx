#!/usr/bin/env python3
"""Build r337: cover stale wall art until its admission repair completes."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import build_stage1_scene0b_exact_runtime_delta_r335 as r335

ROOT = r335.ROOT
TMP = r335.TMP
BASE = r335.BASE
BASE_RECEIPT = r335.BASE_RECEIPT
OUTPUT = TMP / "stage1-scene0b-covered-admission-r337/candidate.gb"
RECEIPT = TMP / "stage1-scene0b-covered-admission-r337/build-receipt.json"


def build(source: bytes, receipt_bytes: bytes) -> tuple[bytes, dict]:
    candidate, parent = r335.build(source, receipt_bytes)
    rom = bytearray(candidate)
    cave_offset = r335.r331.o(r335.r331.CAVE_ADDR)
    chunks = r335.selected(source)
    cave_size = 1 + 14 * len(chunks) + r335.r331.REPAIR_SIZE + 3
    cave = bytearray(rom[cave_offset:cave_offset + cave_size])
    if cave[0] != 0xF3:
        raise AssertionError("r337 transaction no longer begins DI")
    tail_size = r335.r331.REPAIR_SIZE + 3
    insertion = len(cave) - tail_size
    helper = r335.r331.r325.r324.ART_HELPER_ADDR
    # Save LCDC, enable the already prepared Window cover, and restore the
    # exact LCDC only after the signed art transfer.  Keep the cover up while
    # the small resident-runtime copy runs so no stale edge glyph can become
    # visible between admission and GDMA completion.
    cover_and_art = (
        bytes.fromhex("F0 40 F5 CB EF E0 40")
        + bytes((0xCD,)) + helper.to_bytes(2, "little")
        + bytes.fromhex("20 FB")
    )
    uncover = bytes.fromhex("F1 E0 40")
    extended = (
        cave[:1] + cover_and_art + cave[1:insertion]
        + uncover + cave[insertion:]
    )
    payload_boundary = r335.r331.o(r335.r331.PAYLOAD_ADDR)
    if cave_offset + len(extended) > payload_boundary:
        raise AssertionError("r337 transaction cave overlaps payload")
    extra = len(extended) - len(cave)
    if rom[cave_offset + cave_size:cave_offset + cave_size + extra] != bytes([0xFF]) * extra:
        raise AssertionError("r337 covered-admission preimage changed")
    rom[cave_offset:cave_offset + len(extended)] = extended
    r335.r331.r325.r324.r321.r320.r319.r318.r317.r305.r304.update_checksums(rom)
    candidate = bytes(rom)
    sha = hashlib.sha256(candidate).hexdigest()
    return candidate, {
        "schema": "penta-stage1-scene0b-covered-admission-r337-build-v1",
        "status": "STATIC_PASS_LIVE_GATES_REQUIRED",
        "promotable": False,
        "emulator_invoked": False,
        "candidate_sha256": sha,
        "authenticated_da00_delta": parent["authenticated_da00_delta"],
        "patch": {
            "window_cover": "LCDC.5 set before art/runtime transaction and restored exactly after",
            "art_helper": f"bank31:${helper:04X} retry until FF55 exact",
            "ordering": "cover; art; runtime delta; uncover; gateway/cache repair",
        },
        "required_live_gates": parent["required_live_gates"],
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
