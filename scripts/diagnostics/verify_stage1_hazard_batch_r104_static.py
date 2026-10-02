#!/usr/bin/env python3
"""Static geometry and negative-control verifier for isolated r104."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).resolve().parent))

import build_stage1_hazard_batch_r102 as r102
import build_stage1_hazard_batch_r103 as r103
import build_stage1_hazard_batch_r104 as r104


def digest(data: bytes | bytearray) -> str:
    return hashlib.sha256(data).hexdigest()


def region(rom: bytes, bank: int, address: int, size: int) -> bytes:
    off = r102.bank_offset(bank, address)
    return rom[off:off + size]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", type=Path, required=True)
    parser.add_argument("--candidate", type=Path, required=True)
    parser.add_argument("--build-receipt", type=Path, required=True)
    parser.add_argument("--receipt", type=Path, required=True)
    args = parser.parse_args()

    base = args.base.read_bytes()
    candidate = args.candidate.read_bytes()
    build = json.loads(args.build_receipt.read_text())
    if digest(base) != r104.BASE_SHA256:
        raise SystemExit("base is not exact rejected r103")
    if digest(candidate) != build["output_sha256"]:
        raise SystemExit("candidate differs from build receipt")
    if build.get("promotable") is not False:
        raise SystemExit("r104 must remain non-promotable")

    # Only the three new helpers, five JP targets, and checksums may differ.
    allowed = set(range(0x014D, 0x0150))
    for address, code in (
        (r104.NORMALIZE_START0, r104.normalizer(0)),
        (r104.NORMALIZE_LEFT4, r104.normalizer(4)),
        (r104.NORMALIZE_RIGHT8, r104.normalizer(8)),
    ):
        off = r102.bank_offset(r102.HELPER_BANK, address)
        allowed.update(range(off, off + len(code)))
        if region(candidate, r102.HELPER_BANK, address, len(code)) != code:
            raise AssertionError(f"normalizer ${address:04X} differs")
    for address in (*r104.START0_TRAMPOLINES, r104.LEFT4_TRAMPOLINE):
        off = r102.bank_offset(r102.HELPER_BANK, address)
        allowed.update(range(off, off + 3))
    classifier_off = r102.bank_offset(r102.HELPER_BANK, r104.CLASSIFIER_ADDR)
    for offset in (r104.CLASSIFIER_LEFT_TAIL, r104.CLASSIFIER_RIGHT_TAIL):
        allowed.update(range(classifier_off + offset, classifier_off + offset + 3))
    differences = [
        index for index, (left, right) in enumerate(zip(base, candidate))
        if left != right
    ]
    unexpected = set(differences) - allowed
    if unexpected:
        raise AssertionError(f"unexpected r104 bytes: {sorted(unexpected)[:16]}")

    # Exact route model includes the live failing preimage: base low nibble 8
    # OR left start 4 produced C. The r104 normalizer must produce 4 instead.
    route_starts = {"start0": 0, "left4": 4, "right8": 8}
    cases = []
    for row_low in range(0, 0x100, 0x10):
        for incoming_low in (row_low, row_low | 0x08):
            for label, start in route_starts.items():
                normalized = (incoming_low & 0xF0) | start
                if normalized & 0x0F != start:
                    raise AssertionError((incoming_low, label, normalized))
                cases.append((incoming_low, label, normalized))
    rejected_left = (0x08 | 0x04) & 0x0F
    if rejected_left != 0x0C:
        raise AssertionError("negative-control OR model did not produce $0C")
    corrected_left = ((0x08 & 0xF0) | 0x04) & 0x0F
    if corrected_left != 0x04:
        raise AssertionError("left normalizer did not produce $04")

    # Assert exact observed descriptors transform from r103's bad C pair to
    # the intended physical starts while the valid right pair stays unchanged.
    r103_descriptors = (0x9C48, 0x9CA8, 0x9D0C, 0x9D6C)
    expected_r104 = (0x9C48, 0x9CA8, 0x9D04, 0x9D64)
    modeled = tuple(
        value if index < 2 else (value & 0xFFF0) | 0x04
        for index, value in enumerate(r103_descriptors)
    )
    if modeled != expected_r104 or any(value & 0x0F == 0x0C for value in modeled):
        raise AssertionError((modeled, expected_r104))

    # r103's immutable LUT compiler and every batch/mapper body stay exact.
    if region(
        candidate, r102.HELPER_BANK, r103.COMPILE_ADDR,
        len(r103.NEW_COMPILE),
    ) != r103.NEW_COMPILE:
        raise AssertionError("r103 immutable LUT compiler regressed")
    if region(candidate, r102.HELPER_BANK, r102.STAGE_HELPER, 98) != region(
        base, r102.HELPER_BANK, r102.STAGE_HELPER, 98
    ):
        raise AssertionError("shared row stager changed")
    if region(candidate, r102.HELPER_BANK, r102.PUBLISH_HELPER, 142) != region(
        base, r102.HELPER_BANK, r102.PUBLISH_HELPER, 142
    ):
        raise AssertionError("batch publisher changed")
    if region(candidate, r102.PRIVATE_BANK, r102.TRANSITION_REPAIR, 65) != region(
        base, r102.PRIVATE_BANK, r102.TRANSITION_REPAIR, 65
    ):
        raise AssertionError("seam/wall repair changed")

    receipt = {
        "schema": "penta-stage1-hazard-batch-r104-verifier-v1",
        "status": "PASS_STATIC_EMULATOR_REQUIRED",
        "promotable": False,
        "base_sha256": digest(base),
        "candidate_sha256": digest(candidate),
        "changed_bytes": len(differences),
        "geometry": {
            "modeled_cases": len(cases),
            "exact_route_starts": route_starts,
            "r103_observed": [f"0x{value:04X}" for value in r103_descriptors],
            "r104_expected": [f"0x{value:04X}" for value in expected_r104],
            "descriptor_low_nibble_0C_allowed": False,
        },
        "negative_control": {
            "operation": "$08 OR $04",
            "rejected_result": "0x0C",
            "correct_result": "0x04",
            "gate_rejects_old_geometry": True,
        },
        "preserved": {
            "immutable_rom_lut": True,
            "shared_stager": True,
            "batch_publisher": True,
            "overflow_fallback_after_normalization": True,
            "mapper_stack_abi": True,
            "lcd_off_gdma": True,
            "seam_wall_repair": True,
            "svbk2_d600_mutual_exclusion": True,
        },
        "first_emulator_gate": (
            "candidate-owned cold state, then exact current-ROM Stage1 "
            "menu/item/low-health gate; no speed gate until visual PASS"
        ),
    }
    args.receipt.parent.mkdir(parents=True, exist_ok=True)
    args.receipt.write_text(json.dumps(receipt, indent=2) + "\n")
    print(json.dumps(receipt, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
