#!/usr/bin/env python3
"""Build r325: restore signed wall art at the shared native menu invalidator.

r324's phase-safe gateway repair reaches the real wall-art failure, but the
corrupted-walls capture does not execute that stale-runtime repair before its
menu round-trip.  The native menu invalidation is common to both captures.
r325 wraps only those eight invalidation bytes with the audited VBlank GDMA
restore, then resumes the original menu-close tail unchanged.  r324's deferred
gateway repair and r320's atomic publisher remain intact.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import build_stage1_scene0b_phase_art_repair_r324 as r324


ROOT = r324.ROOT
TMP = r324.TMP
BASE = r324.BASE
BASE_RECEIPT = r324.BASE_RECEIPT
OUTPUT = TMP / "stage1-scene0b-menu-art-phase-repair-r325/candidate.gb"
RECEIPT = TMP / "stage1-scene0b-menu-art-phase-repair-r325/build-receipt.json"

MENU_HOOK_ADDR = 0x6CDA
MENU_INVALIDATION = bytes.fromhex("3E FF EA 53 DF EA 57 DF")
MENU_EXIT_ADDR = 0x6CE2
MENU_CAVE_ADDR = 0x6ED0


def digest(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def construct(source: bytes) -> tuple[bytes, dict]:
    base_candidate, base_receipt = r324.construct(source)
    rom = bytearray(base_candidate)
    hook = r324.offset(MENU_HOOK_ADDR)
    if rom[hook:hook + len(MENU_INVALIDATION)] != MENU_INVALIDATION:
        raise AssertionError("r325 native menu invalidation preimage changed")
    # Preserve the menu tail's AF exactly, cover the display while the helper
    # waits for a safe VBlank, retry on a non-idle HDMA result, and then replay
    # the original two physical-map cache invalidations before $6CE2.
    helper = r324.ART_HELPER_ADDR
    cave = (
        bytes.fromhex("F3 F0 40 F5 CB EF E0 40")
        + MENU_INVALIDATION
        + bytes((0xCD,)) + helper.to_bytes(2, "little")
        + bytes.fromhex("20 FB F1 CB AF E0 40 FB C3")
        + MENU_EXIT_ADDR.to_bytes(2, "little")
    )
    if len(cave) != 30:
        raise AssertionError("r325 menu cave width changed")
    cave_offset = r324.offset(MENU_CAVE_ADDR)
    if rom[cave_offset:cave_offset + len(cave)] != bytes([0xFF]) * len(cave):
        raise AssertionError("r325 menu cave preimage is not erased")
    rom[hook:hook + len(MENU_INVALIDATION)] = bytes((0xC3,)) + MENU_CAVE_ADDR.to_bytes(2, "little") + bytes(5)
    rom[cave_offset:cave_offset + len(cave)] = cave
    r324.r321.r320.r319.r318.r317.r305.r304.update_checksums(rom)
    candidate = bytes(rom)
    changed = r324.r321.functional_offsets(source, candidate)
    base_changed = r324.r321.functional_offsets(source, base_candidate)
    extra = changed - base_changed
    allowed_extra = set(range(hook, hook + len(MENU_INVALIDATION))) | set(range(cave_offset, cave_offset + len(cave)))
    if not extra <= allowed_extra:
        raise AssertionError("r325 functional delta escaped menu ownership")
    if candidate[r324.r321.r320.PRIMARY_ADDR:r324.r321.r320.PRIMARY_END] != r324.r321.r320.NEW_PRIMARY:
        raise AssertionError("r325 changed r320 atomic publisher")
    checked = bytearray(candidate)
    r324.r321.r320.r319.r318.r317.r305.r304.update_checksums(checked)
    if bytes(checked) != candidate:
        raise AssertionError("r325 checksums not canonical")
    sha = digest(candidate)
    return candidate, {
        "schema": "penta-stage1-scene0b-menu-art-phase-repair-r325-construction-v1",
        "status": "construction-only",
        "historical_evidence_consumed": False,
        "fresh_live_qualification": False,
        "promotable": False,
        "emulator_invoked": False,
        "candidate_sha256": sha,
        "base_r324": base_receipt["candidate_sha256"],
        "patch": {
            "r320_atomic_publisher": "unchanged",
            "phase_safe_gateway_repair": "retained from r324",
            "menu_hook": f"bank31:${MENU_HOOK_ADDR:04X} -> ${MENU_CAVE_ADDR:04X}",
            "menu_art_restore": "VBlank GDMA canonical $7000->$9100 before native close tail",
        },
        "functional_changed_bytes_from_r320": len(changed),
        "required_live_gates": ["full scene0B menu visual gate", "hazard", "north", "speed"],
    }


def build(source: bytes, receipt_bytes: bytes) -> tuple[bytes, dict]:
    _, parent = r324.build(source, receipt_bytes)
    candidate, receipt = construct(source)
    receipt.update({"schema": "penta-stage1-scene0b-menu-art-phase-repair-r325-build-v1",
                    "status": "STATIC_PASS_EXPERIMENT_LIVE_GATES_REQUIRED",
                    "base_r324": parent["candidate_sha256"]})
    del receipt["historical_evidence_consumed"], receipt["fresh_live_qualification"]
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
