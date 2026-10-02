#!/usr/bin/env python3
"""Source-only r287 -> r314 room/semantic/scene component for r534 integration.

This intermediate is not deployable. Subsequent Stage-1 builders still require
historical build-receipt integration. Neither those audits nor final release
qualification are replaced by this construction component.
"""
from __future__ import annotations

import argparse
import importlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / "scripts/diagnostics"), str(ROOT / "scripts")]
import r534_lineage_ancestry as ancestry
import build_stage1_room01_locked_wall_r297 as wall
import build_stage1_room01_semantic_row_r300 as semantic
import build_stage1_fast_scene0b_gates_r303 as scene
import build_stage1_unified_scene0b_r305 as unified
import build_stage1_precompile_effective_room_r310 as precompile
import build_stage1_bank16_installer_mirror_r307 as mirror
import build_stage1_final_scene0b_r311 as final_scene
import build_stage1_runtime_epoch_r312 as epoch
import build_stage1_scene0b_runtime_selfheal_r313 as selfheal
import build_stage1_scene0b_publication_commit_r314 as publication
from r534_lineage_prefix import digest, serialize_receipt
from suite_contract import source_snapshot

OUTPUT_SHA256 = ancestry.R314.rom
SOURCE_CONTRACT_SHA256 = {
    "r297": "e9f68f0db492c7f8f787df6d7c80f335195917ca390ff05d4a12cd4d842265e2",
    "r300": "f5c1f1f7aa61d8c3acf72063bbd258cb2d03d6b014faf27cf3e9b714ce19a80e",
    "r303": "5e30798a16787e7c18f3386a0fc5e68b5144504d931e0ee19b1cbc92e81b92ad",
    "r305": "7027912358a6fd99fe50b7e3f1fea633f9e4b3e1983bf946c3faed78bfdb6828",
    "r310": "a79d1c9fdd67d6610a36d96b07ec683bb5ccfad3267f390e81d2fdce57bcf38d",
    "r307": "5eb58cb858962742525ce9491fc1777770ded6a6919b728f7797ee3e2bff4a1c",
    "r311": "aaee5dfec15e29ecd2e46587d1ea8c7e2302bd2ba8a53b7f32fde4e28099e27b",
    "r312": "6b240e150234c2227289f75d52fbe220271484462efc4cfbf3d9d2ff87124a79",
    "r313": "765d19830491d5ec7c4293e32242e22f793e31b7af900d50fd5305a8c0070d15",
    "r314": "06e07bfaa88b812914a7c7c883e685eb64fa3eb9b240a1335d36b1b6623b9927",
}


def construct(source: bytes) -> tuple[bytes, dict]:
    if digest(source) != ancestry.BASE_SHA256:
        raise ValueError("room construction requires exact r287")
    if set(SOURCE_CONTRACT_SHA256) != {
        "r297", "r300", "r303", "r305", "r307", "r310", "r311", "r312", "r313", "r314",
    }:
        raise ValueError("room source contract pin inventory differs")
    result, receipt, steps = source, None, []
    for pin in ancestry.PRE_BRANCH[:4]:
        previous = result
        args = [previous] + ([receipt] if receipt is not None else [])
        result, metadata = importlib.import_module(pin.module).build(*args)
        receipt = serialize_receipt(metadata)
        if not isinstance(result, bytes) or len(result) != len(source) or digest(result) != pin.rom:
            raise ValueError(f"{pin.module}: source-only generated ROM differs")
        if digest(receipt) != pin.receipt:
            raise ValueError(f"{pin.module}: source-only static receipt differs")
        steps.append({"name": pin.module, "base_sha256": digest(previous),
                      "candidate_sha256": digest(result), "generated_receipt_sha256": digest(receipt)})
    r292 = result
    components = {}
    for revision, builder, expected in (
        ("r297", wall, scene.r302.R297_FULL_SHA256),
        ("r300", semantic, scene.r302.R300_SHA256),
        ("r303", scene, ancestry.PRE_BRANCH[4].rom),
    ):
        result, metadata = builder.construct(r292)
        if not isinstance(result, bytes) or len(result) != len(source) or digest(result) != expected:
            raise ValueError(f"{revision}: source-only generated ROM differs")
        if digest(serialize_receipt(metadata)) != SOURCE_CONTRACT_SHA256[revision]:
            raise ValueError(f"{revision}: source-only contract receipt differs")
        components[revision] = metadata
    steps.append({"name": "build_stage1_fast_scene0b_gates_r303",
                  "base_sha256": digest(r292), "candidate_sha256": digest(result),
                  "generated_receipt_sha256": SOURCE_CONTRACT_SHA256["r303"]})
    for revision, builder, pin in (
        ("r305", unified, ancestry.PRE_BRANCH[5]),
        ("r310", precompile, ancestry.R310),
    ):
        previous = result
        result, metadata = builder.construct(previous)
        if not isinstance(result, bytes) or len(result) != len(source) or digest(result) != pin.rom:
            raise ValueError(f"{revision}: source-only generated ROM differs")
        if digest(serialize_receipt(metadata)) != SOURCE_CONTRACT_SHA256[revision]:
            raise ValueError(f"{revision}: source-only contract receipt differs")
        components[revision] = metadata
        if revision == "r305":
            r305_reference = result
        steps.append({"name": pin.module, "base_sha256": digest(previous),
                      "candidate_sha256": digest(result),
                      "generated_receipt_sha256": SOURCE_CONTRACT_SHA256[revision]})
    r310 = result
    for revision, builder, pin, base, options in (
        ("r307", mirror, ancestry.BRANCH, r305_reference, {}),
        ("r311", final_scene, ancestry.R311, r310, {"reference": r305_reference}),
    ):
        result, metadata = builder.construct(base, **options)
        if not isinstance(result, bytes) or len(result) != len(source) or digest(result) != pin.rom:
            raise ValueError(f"{revision}: source-only generated ROM differs")
        if digest(serialize_receipt(metadata)) != SOURCE_CONTRACT_SHA256[revision]:
            raise ValueError(f"{revision}: source-only contract receipt differs")
        components[revision] = metadata
    steps.append({"name": ancestry.R311.module, "base_sha256": digest(r310),
                  "candidate_sha256": digest(result),
                  "generated_receipt_sha256": SOURCE_CONTRACT_SHA256["r311"]})
    for revision, builder, pin in (
        ("r312", epoch, ancestry.R312),
        ("r313", selfheal, ancestry.R313),
        ("r314", publication, ancestry.R314),
    ):
        previous = result
        result, metadata = builder.construct(previous)
        if not isinstance(result, bytes) or len(result) != len(source) or digest(result) != pin.rom:
            raise ValueError(f"{revision}: source-only generated ROM differs")
        if digest(serialize_receipt(metadata)) != SOURCE_CONTRACT_SHA256[revision]:
            raise ValueError(f"{revision}: source-only contract receipt differs")
        components[revision] = metadata
        steps.append({"name": pin.module, "base_sha256": digest(previous),
                      "candidate_sha256": digest(result),
                      "generated_receipt_sha256": SOURCE_CONTRACT_SHA256[revision]})
    return result, {
        "schema": "penta-stage1-room-source-construction-v4", "status": "construction-only",
        "promotable": False, "base_sha256": digest(source), "candidate_sha256": digest(result),
        "historical_evidence_consumed": False, "room_capture_population_checked": False,
        "fresh_live_qualification": False, "steps": steps, "components": components,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", type=Path, required=True)
    parser.add_argument("--out-dir", type=Path, required=True)
    args = parser.parse_args()
    output = args.out_dir.resolve()
    if output == ROOT / "tmp" or not output.is_relative_to(ROOT / "tmp") or output.exists():
        raise ValueError("use a fresh repository-local tmp output directory")
    source = args.base.read_bytes()
    snapshot = source_snapshot()
    result, receipt = construct(source)
    if (result, receipt) != construct(source):
        raise ValueError("room construction double build differs")
    if snapshot != source_snapshot() or args.base.read_bytes() != source:
        raise ValueError("room construction inputs changed")
    receipt.update({"base_path": str(args.base.resolve()), "double_build_identical": True,
                    "source_fingerprint": snapshot[0], "source_files": snapshot[1]})
    output.mkdir(parents=True)
    (output / "intermediate-r314.gb").write_bytes(result)
    (output / "construction-receipt.json").write_text(json.dumps(receipt, indent=2) + "\n")
    print(json.dumps({"candidate_sha256": digest(result), "double_build_identical": True,
                      "historical_evidence_consumed": False, "status": "construction-only"}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
