#!/usr/bin/env python3
"""Build r336: repair signed wall art at stale-room admission.

r335 proves the exact resident-runtime compatibility delta, but its inherited
r325 art repair runs only at menu close.  A corrupted room can consequently
render the bad signed wall/entrance glyphs until the player opens and closes
the menu.  r336 retains r335 byte-for-byte and adds the already audited r315
VBlank GDMA helper to the unconditional stale-runtime transaction, before the
gateway/cache repair makes the room current.
"""
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
OUTPUT = TMP / "stage1-scene0b-admission-art-repair-r336/candidate.gb"
RECEIPT = TMP / "stage1-scene0b-admission-art-repair-r336/build-receipt.json"


def construct(source: bytes) -> tuple[bytes, dict]:
    candidate, parent = r335.construct(source)
    rom = bytearray(candidate)
    cave_offset = r335.r331.o(r335.r331.CAVE_ADDR)
    chunks = r335.selected(source)
    cave_size = 1 + 14 * len(chunks) + r335.r331.REPAIR_SIZE + 3
    cave = bytearray(rom[cave_offset:cave_offset + cave_size])
    tail_size = r335.r331.REPAIR_SIZE + 3  # repair stream; JP resume
    insertion = len(cave) - tail_size
    helper = r335.r331.r325.r324.ART_HELPER_ADDR
    # CALL helper; JR NZ back to CALL.  The helper waits for a fresh safe
    # VBlank and returns Z only after exact FF55 completion.
    art_call = bytes((0xCD,)) + helper.to_bytes(2, "little") + bytes((0x20, 0xFB))
    extended = cave[:insertion] + art_call + cave[insertion:]
    payload_boundary = r335.r331.o(r335.r331.PAYLOAD_ADDR)
    if cave_offset + len(extended) > payload_boundary:
        raise AssertionError("r336 transaction cave overlaps its payload")
    if rom[cave_offset + cave_size:cave_offset + len(extended)] != bytes([0xFF]) * len(art_call):
        raise AssertionError("r336 admission-art extension preimage changed")
    rom[cave_offset:cave_offset + len(extended)] = extended
    r335.r331.r325.r324.r321.r320.r319.r318.r317.r305.r304.update_checksums(rom)
    candidate = bytes(rom)
    sha = hashlib.sha256(candidate).hexdigest()
    return candidate, {
        "schema": "penta-stage1-scene0b-admission-art-repair-r336-construction-v1",
        "status": "construction-only",
        "historical_evidence_consumed": False,
        "fresh_live_qualification": False,
        "promotable": False,
        "emulator_invoked": False,
        "candidate_sha256": sha,
        "base_r335_runtime_regions": parent["runtime_regions"],
        "source_selected_da00_delta": parent["source_selected_da00_delta"],
        "admission_art_repair": {
            "helper": f"bank31:${helper:04X}",
            "ordering": "runtime delta; VBlank GDMA signed art; gateway/cache repair",
            "retry_until_FF55_exact": True,
        },
        "required_live_gates": parent["required_live_gates"],
    }


def build(source: bytes, receipt_bytes: bytes) -> tuple[bytes, dict]:
    _, parent = r335.build(source, receipt_bytes)
    candidate, receipt = construct(source)
    receipt.update({"schema": "penta-stage1-scene0b-admission-art-repair-r336-build-v1",
                    "status": "STATIC_PASS_LIVE_GATES_REQUIRED",
                    "base_r335_runtime_regions": parent["runtime_regions"],
                    "authenticated_da00_delta": parent["authenticated_da00_delta"]})
    del receipt["historical_evidence_consumed"], receipt["fresh_live_qualification"], receipt["source_selected_da00_delta"]
    return candidate, receipt


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
