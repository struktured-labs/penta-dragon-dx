#!/usr/bin/env python3
"""Construct exact r534 from factory+original bytes without historical evidence.

The factory image must be built separately from the original cartridge using
the pinned source profile. This experimental integration does not yet replace
the production approval profile or confer fresh live/hardware qualification.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / "scripts/diagnostics"), str(ROOT / "scripts")]
import build_r534_source_prefix as prefix
import r534_stage1_room_source as room
import r534_stage1_latch_source as latch
import r534_stage1_admission_source as admission
import build_stage1_hazard_terminal_caps_r341 as caps
import build_stage1_hazard_terminal_resume_r342 as resume
import build_stage1_hazard_terminal_silhouette_r343 as silhouette
import rebuild_r534_lineage as continuation
from r534_lineage_prefix import ORIGINAL_SHA256, digest, serialize_receipt
from suite_contract import source_snapshot

HAZARD_COMPONENTS = (
    ("r341", caps, "30ba055bc4cdd7468994d8dbe017a9c73ec82d09184f792e690ffd22a95e73cf",
     "01a6370fcf8de248b9ddefaa3c7982b03519074c6b15c81bfca413ed1a1f7088"),
    ("r342", resume, "84bf020e4a9006e0ce9a3e79fec6687a281620108d5337ab8fddb99d0093dd1f",
     "5b5a637b0d8821b2717ed3d444168765207372c2b8d7a012fac1281f1beeb4a3"),
    ("r343", silhouette, "df359624edb86adfdc88d78e81b4a9d7c8e251956fb29512e2a0402b6c604d48",
     "9271b25e23da0eb28f5305a66175452cfcf2092ab1dcb39a7bf53a3183f1e8da"),
)


def construct_hazards(source: bytes, original: bytes) -> tuple[bytes, dict]:
    if digest(source) != admission.OUTPUT_SHA256:
        raise ValueError("hazard construction requires exact r336")
    if digest(original) != ORIGINAL_SHA256:
        raise ValueError("hazard construction requires exact original cartridge")
    if tuple(item[0] for item in HAZARD_COMPONENTS) != ("r341", "r342", "r343"):
        raise ValueError("hazard source component pin inventory differs")
    result, steps, components = source, [], {}
    for revision, builder, rom_sha, receipt_sha in HAZARD_COMPONENTS:
        previous = result
        options = {"stock": original} if revision == "r343" else {}
        result, metadata = builder.construct(previous, **options)
        if not isinstance(result, bytes) or len(result) != len(source) or digest(result) != rom_sha:
            raise ValueError(f"{revision}: source-only generated ROM differs")
        if digest(serialize_receipt(metadata)) != receipt_sha:
            raise ValueError(f"{revision}: source-only contract receipt differs")
        components[revision] = metadata
        steps.append({"name": builder.__name__, "base_sha256": digest(previous),
                      "candidate_sha256": digest(result), "generated_receipt_sha256": receipt_sha})
    return result, {"steps": steps, "components": components}


def build(factory: bytes, original: bytes) -> tuple[bytes, dict]:
    if digest(original) != ORIGINAL_SHA256:
        raise ValueError("source construction requires exact original cartridge")
    r287, prefix_receipt = prefix.build(factory)
    r314, room_receipt = room.construct(r287)
    r319, latch_receipt = latch.construct(r314)
    r336, admission_receipt = admission.construct(r319)
    r343, hazard_receipt = construct_hazards(r336, original)
    if digest(r343) != continuation.prefix.BASE_SHA256:
        raise ValueError("generated r343 does not match continuation input")
    result, following = continuation.build(r343)
    if following["historical_evidence"] or following["component_builds"]:
        raise ValueError("r343 continuation unexpectedly consumed historical evidence")
    if following["base_sha256"] != digest(r343) or digest(result) != continuation.CANDIDATE_SHA256:
        raise ValueError("source construction did not reproduce exact r534")
    prefix_count = sum(len(part) for part in (
        prefix_receipt["phase"]["steps"], prefix_receipt["stage2_steps"],
        prefix_receipt["stage7"]["steps"], prefix_receipt["stage4"]["steps"],
    ))
    early_count = prefix_count + sum(len(part["steps"]) for part in (
        room_receipt, latch_receipt, admission_receipt, hazard_receipt,
    ))
    if early_count != 45 or len(following["steps"]) != 60:
        raise ValueError("source construction step inventory differs")
    return result, {
        "schema": "penta-r534-source-candidate-v1", "status": "construction-only",
        "experimental": True, "promotable": False,
        "historical_evidence_consumed": False, "fresh_live_qualification": False,
        "factory_sha256": digest(factory), "original_sha256": digest(original),
        "candidate_sha256": digest(result), "construction_steps": early_count,
        "continuation_steps": following["steps"], "total_steps": early_count + len(following["steps"]),
        "generated_continuation_base_sha256": digest(r343),
        "prefix": prefix_receipt, "room": room_receipt, "latch": latch_receipt,
        "admission": admission_receipt, "hazards": hazard_receipt,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--factory-image", type=Path, required=True)
    parser.add_argument("--original-rom", type=Path, required=True)
    parser.add_argument("--out-dir", type=Path, required=True)
    args = parser.parse_args()
    output = args.out_dir.resolve()
    if output == ROOT / "tmp" or not output.is_relative_to(ROOT / "tmp") or output.exists():
        raise ValueError("use a fresh repository-local tmp output directory")
    factory, original = args.factory_image.read_bytes(), args.original_rom.read_bytes()
    snapshot = source_snapshot()
    guard_active = False
    def audit(event, arguments):
        if guard_active and event == "open" and isinstance(arguments[0], (str, bytes)):
            path = Path(arguments[0].decode() if isinstance(arguments[0], bytes) else arguments[0]).resolve()
            if path.is_relative_to(ROOT / "tmp") or path.suffix.lower() in {".gb", ".gbc", ".ss0", ".ss1"}:
                raise ValueError(f"construction accessed an undeclared artifact: {path}")
    sys.addaudithook(audit)
    try:
        guard_active = True
        result, receipt = build(factory, original)
        if (result, receipt) != build(factory, original):
            raise ValueError("source candidate double build differs")
    finally:
        guard_active = False
    if snapshot != source_snapshot() or args.factory_image.read_bytes() != factory or args.original_rom.read_bytes() != original:
        raise ValueError("source candidate inputs changed")
    receipt.update({"factory_path": str(args.factory_image.resolve()),
                    "original_path": str(args.original_rom.resolve()),
                    "double_build_identical": True, "in_memory_artifact_reads_forbidden": True,
                    "source_fingerprint": snapshot[0], "source_files": snapshot[1]})
    output.mkdir(parents=True)
    (output / "candidate.gb").write_bytes(result)
    (output / "construction-receipt.json").write_text(json.dumps(receipt, indent=2) + "\n")
    print(json.dumps({"candidate_sha256": digest(result), "double_build_identical": True,
                      "historical_evidence_consumed": False, "total_steps": receipt["total_steps"],
                      "status": "construction-only", "promotable": False}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
