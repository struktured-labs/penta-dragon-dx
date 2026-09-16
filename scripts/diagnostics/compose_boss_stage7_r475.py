#!/usr/bin/env python3
"""Combine the independently verified r462 boss and r467 Stage-7 repairs."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / "scripts/diagnostics"), str(ROOT / "scripts")]
import compose_boss_repairs_r462 as boss

# Build code belongs to the fingerprinted source tree; only ROM inputs and
# generated artifacts remain in ignored scratch storage.
import compose_stage7_guarded_services_r467 as stage7
import compose_stage7_pure_six_r465 as pure_six


BASE = ROOT / "tmp/attract-blank-r456d/candidate.gb"
BASE_SHA256 = (
    "69896bb1ba8f60fee7f5fd8c9044b90972f16255c726f2b00beaffec320d6722"
)
OUT = ROOT / "tmp/boss-stage7-r475"
CHECKSUM_OFFSETS = {0x14D, 0x14E, 0x14F}


def digest(payload: bytes | bytearray) -> str:
    return hashlib.sha256(payload).hexdigest()


def changed_offsets(source: bytes, candidate: bytes) -> set[int]:
    if len(source) != len(candidate):
        raise ValueError("component changed ROM size")
    return {
        index for index, (before, after) in enumerate(zip(source, candidate))
        if before != after and index not in CHECKSUM_OFFSETS
    }


def build(source: bytes) -> tuple[bytes, dict[str, object]]:
    if digest(source) != BASE_SHA256:
        raise ValueError("requires exact retained r456d base")

    boss_candidate = boss.build(source)
    pure_candidate, pure_evidence = pure_six.build(source)
    stage_candidate, stage_evidence = stage7.build(pure_candidate)
    boss_changes = changed_offsets(source, boss_candidate)
    stage_changes = changed_offsets(source, stage_candidate)
    if boss_changes & stage_changes:
        raise ValueError("boss and Stage-7 repair footprints overlap")

    boss_banks = {offset // 0x4000 for offset in boss_changes}
    stage_banks = {offset // 0x4000 for offset in stage_changes}
    if boss_banks != {20}:
        raise ValueError(f"unexpected boss repair banks: {sorted(boss_banks)}")
    if stage_banks != {13, 28}:
        raise ValueError(f"unexpected Stage-7 repair banks: {sorted(stage_banks)}")

    result = bytearray(source)
    for component, offsets in (
        (boss_candidate, boss_changes),
        (stage_candidate, stage_changes),
    ):
        for offset in offsets:
            result[offset] = component[offset]
    stage7.update_checksums(result)
    candidate = bytes(result)

    combined_changes = changed_offsets(source, candidate)
    if combined_changes != boss_changes | stage_changes:
        raise AssertionError("combined candidate is not the exact component union")
    if any(candidate[offset] != boss_candidate[offset]
           for offset in boss_changes):
        raise AssertionError("combined candidate lost a boss byte")
    if any(candidate[offset] != stage_candidate[offset]
           for offset in stage_changes):
        raise AssertionError("combined candidate lost a Stage-7 byte")

    evidence: dict[str, object] = {
        "schema": "penta-boss-stage7-r475-build-v1",
        "experimental": True,
        "promotable": False,
        "base_sha256": BASE_SHA256,
        "candidate_sha256": digest(candidate),
        "component_sha256": {
            "boss_r462": digest(boss_candidate),
            "stage7_r467": digest(stage_candidate),
        },
        "changed_byte_count_excluding_checksums": len(combined_changes),
        "boss_changed_byte_count": len(boss_changes),
        "stage7_changed_byte_count": len(stage_changes),
        "boss_banks": sorted(boss_banks),
        "stage7_banks": sorted(stage_banks),
        "disjoint_component_footprints": True,
        "exact_component_union": True,
        "stage7_fast_address": pure_evidence["fast_address"],
        "stage7_service_guard": stage_evidence["guard_address"],
    }
    return candidate, evidence


def main() -> int:
    candidate, evidence = build(BASE.read_bytes())
    OUT.mkdir(exist_ok=True)
    candidate_path = OUT / "candidate.gb"
    if candidate_path.exists() and candidate_path.read_bytes() != candidate:
        raise ValueError("immutable candidate collision")
    candidate_path.write_bytes(candidate)
    receipt_path = OUT / "build-receipt.json"
    receipt = json.dumps(evidence, indent=2) + "\n"
    if receipt_path.exists() and receipt_path.read_text() != receipt:
        raise ValueError("immutable build receipt collision")
    receipt_path.write_text(receipt)
    print(receipt, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
