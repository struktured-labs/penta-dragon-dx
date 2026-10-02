"""Replay repaired r264 -> r273 without saved intermediate ROMs.

Two authentic static receipts are historical inputs, not regenerated corpus
or reachability evidence. Source-only checks are rerun and compared with the
first receipt before construction. No live qualification is conferred.
"""
from __future__ import annotations

import importlib
import json
from pathlib import Path

from r534_lineage_ancestry import BuildPin
from r534_lineage_prefix import digest, serialize_receipt

BASE_SHA256 = "aa4c15602af5a1d0bf332c17de25fd2132d7fb45b327cc2d8d9bf25255dbf5a1"
OUTPUT_SHA256 = "09d75d4461d911f4ed55c929c676346b1f7851e015bdbd867f307f8d9f1cc1d8"
# Pins cover freshly evaluated source contracts only, never archived corpus
# observations. Keep these distinct from the historical receipt identities.
SOURCE_CONTRACT_SHA256 = {
    "r264": "6805ef639d8be95ee3ce5585232ed288256b0cb19dd9322e0d39236194400b38",
    "r265": "71163cb49c3ebe6ba7090bdda1c840463a68311e4865b91e35e824091edaa090",
    "r269": "bff95f976255b9048671d0a7c1b6157545eeeb8cb48ede2dec90b0ed52441745",
}
HISTORICAL_INPUTS = {
    "stage7_dual_plane_static": (
        "tmp/stage7-dual-plane-hdma-r264/static-receipt.json",
        "b724cfae07e8e72cda8629778bef9d4f85a9ad7c3f1413eb691a06e6e1ef7272"),
    "stage7_transferred_static": (
        "tmp/stage7-menu-signature-invalidation-r265/transferred-stage7-static-receipt.json",
        "3bf962c18274ba8c5efe1e1ee9673ba19401dbebfc970782efed5e9e96673661"),
}
STEPS = (
    BuildPin("audit_stage7_dual_plane_hdma_r264",
             "e04801c8b8b0c1eb5ddaddce31a9581ad5c1fc83e3f1b043c581afa33df216a0",
             "0536dd8990a0de1429a74d90407c9aece77b924be96350897df3e468d2a99a2a"),
    BuildPin("build_stage7_menu_signature_invalidation_r265",
             "a4c772624f16bc9ef23873726cbbafa169ee93869a95a17431367895273bd273",
             "9567c8babe7be863ecbd5a7c6ba9a8234cd81aef7508a1f6e3c184773c3a6ab7"),
    BuildPin("build_stage7_transition_state_r269",
             "4abe94ee1d782c66c1ee79f5c45c5a0875f66ee384c60161db712bff17b87711",
             "9163baf17bc7a1cd13cd56aa4b74074c4cb59a2d6c8226a7ac24b19eae3e06c4"),
    BuildPin("build_stage7_visible_rows_r271",
             "1eefb4bd7963928303ffe7dda9ff4875d6f438eda3721934b4fb439ae09e97e9",
             "dc56587cdb434dbce681157689fbbdae15457deb708d6549e0b962c5f653071d"),
    BuildPin("build_stage7_skip_invisible_padding_r273", OUTPUT_SHA256,
             "5db8dabe87170fd20d3938ff576718c6be60da6a4d58c9fa100a69dd24de7218"),
)


def construct_dual_plane_source(builder, source: bytes):
    """Run source-only guards and construct; no historical corpus is loaded."""
    if digest(source) != BASE_SHA256:
        raise ValueError("dual-plane source construction requires exact repaired r264")
    helper, labels = builder.build_helper()
    tail = builder.build_router_tail()
    descriptors = builder.build_descriptors()
    lut = bytes(builder.semantic_lut(7))
    if builder.HELPER + len(helper) > builder.DESCRIPTORS:
        raise ValueError("dual-plane helper overlaps descriptor table")
    checks = {
        "strict_r264_preimages": builder.require_preimages(source),
        "runtime_guards": builder.guard_contract(),
        "emitted_guard_verification": builder.emitted_guard_contract(helper, labels),
        "caller_and_camera_contract": builder.caller_camera_contract(source),
        "banked_stack_contract": builder.banked_stack_contract(helper, labels),
        "timing": builder.timing_contract(),
        "dma_contract": builder.dma_contract(labels),
        "timer_service": builder.timer_contract(source),
        "mutation_controls": builder.mutation_controls(source),
    }
    runtime = builder.require_runtime(source)
    runtime.update({"tail_bytes": tail.hex(" ").upper(), "tail_sha256": digest(tail)})
    result, metadata = builder.build_in_memory_candidate(source, helper, tail, descriptors, lut)
    return result, metadata, {**checks, "runtime_router": runtime, "in_memory_candidate": metadata}


def construct_dual_plane(builder, source: bytes, historical: bytes):
    """Recheck source contracts without claiming to rerun historical corpora."""
    old = json.loads(historical)
    if old.get("base_sha256") != digest(source):
        raise ValueError("dual-plane static receipt targets another base")
    result, metadata, checks = construct_dual_plane_source(builder, source)
    for name, actual in checks.items():
        if name not in ("runtime_router", "in_memory_candidate"):
            if json.loads(json.dumps(actual)) != old.get(name):
                raise ValueError(f"{name}: source contract differs from historical identity")
    runtime = checks["runtime_router"]
    for name, actual in runtime.items():
        if json.loads(json.dumps(actual)) != old["runtime_router"].get(name):
            raise ValueError(f"runtime_router.{name}: source contract differs")
    historical_construction = dict(old["in_memory_candidate"])
    historical_construction.pop("path")
    historical_construction["rom_emitted"] = False
    if metadata != historical_construction:
        raise ValueError("dual-plane construction differs from historical identity")
    return result, metadata, list(checks)


def construct(source: bytes) -> tuple[bytes, dict]:
    """Construct r273 with source contracts and generated references only."""
    if digest(source) != BASE_SHA256:
        raise ValueError("Stage-7 source construction requires exact repaired r264")
    result, records, r265 = source, [], None
    for pin in STEPS:
        builder = importlib.import_module(pin.module)
        revision = pin.module.rsplit("_", 1)[1]
        previous = result
        references = {}
        if revision == "r264":
            result, metadata, checks = construct_dual_plane_source(builder, previous)
            encoded = serialize_receipt(metadata)
        elif revision == "r265":
            result, metadata = builder.construct(previous)
            checks = metadata
            encoded = None
            r265 = result
        elif revision == "r269":
            references = {"source_r264": digest(source)}
            result, metadata = builder.construct(previous, source)
            checks = metadata
            encoded = None
        elif revision == "r271":
            if r265 is None:
                raise ValueError("r271 requires generated r265 reference")
            references = {"generated_r265": digest(r265)}
            result, metadata = builder.install(previous, r265)
            checks = {"static_build_receipt_sha256": digest((json.dumps(metadata, indent=2) + "\n").encode())}
            encoded = (json.dumps(metadata, indent=2) + "\n").encode()
        elif revision == "r273":
            result, metadata = builder.install(previous)
            checks = {"static_build_receipt_sha256": digest((json.dumps(metadata, indent=2) + "\n").encode())}
            encoded = (json.dumps(metadata, indent=2) + "\n").encode()
        else:
            raise ValueError(f"unknown Stage-7 source step: {revision}")
        if not isinstance(result, bytes) or len(result) != len(source) or digest(result) != pin.rom:
            raise ValueError(f"{pin.module}: source-only generated ROM differs")
        if encoded is not None and digest(encoded) != pin.receipt:
            raise ValueError(f"{pin.module}: source-only static receipt differs")
        if revision in SOURCE_CONTRACT_SHA256:
            if digest(serialize_receipt(checks)) != SOURCE_CONTRACT_SHA256[revision]:
                raise ValueError(f"{pin.module}: source-only contract receipt differs")
        records.append({"name": pin.module, "base_sha256": digest(previous),
                        "candidate_sha256": digest(result), "source_contracts": checks,
                        "reference_sha256": references,
                        "changed_bytes": sum(a != b for a, b in zip(previous, result))})
    if digest(result) != OUTPUT_SHA256:
        raise ValueError("Stage-7 source construction did not reproduce exact r273")
    return result, {
        "schema": "penta-stage7-source-construction-v1", "status": "construction-only",
        "promotable": False, "base_sha256": digest(source), "candidate_sha256": digest(result),
        "historical_evidence_consumed": False, "historical_corpora_rechecked": False,
        "fresh_live_qualification": False, "steps": records,
    }


def build(source: bytes, evidence: dict[str, bytes], *, base_is_generated: bool = False
          ) -> tuple[bytes, list[dict]]:
    if digest(source) != BASE_SHA256:
        raise ValueError("Stage-7 ancestry requires exact repaired r264")
    if set(evidence) != set(HISTORICAL_INPUTS):
        raise ValueError("Stage-7 ancestry requires exactly the two historical static receipts")
    for name, (_, expected) in HISTORICAL_INPUTS.items():
        if digest(evidence[name]) != expected:
            raise ValueError(f"{name}: historical evidence identity differs")
    result, records, r265 = source, [], None
    base_reference = "generated_r264" if base_is_generated else "retained_r264"
    for pin in STEPS:
        builder = importlib.import_module(pin.module)
        revision = pin.module.rsplit("_", 1)[1]
        previous = result
        history, references, source_checks = [], {}, []
        if revision == "r264":
            history = ["stage7_dual_plane_static"]
            result, metadata, source_checks = construct_dual_plane(builder, source, evidence[history[0]])
            encoded = serialize_receipt(metadata)
        elif revision == "r265":
            history = ["stage7_dual_plane_static"]
            references = {base_reference: digest(source)}
            result, metadata = builder.build(previous, base_receipt=evidence[history[0]], control=source)
            # Preserve the historical CLI label, not a claim that this file was read/written.
            metadata["candidate_path"] = "tmp/stage7-menu-signature-invalidation-r265/candidate.gb"
            encoded = serialize_receipt(metadata)
            r265 = result
        elif revision == "r269":
            history = ["stage7_transferred_static"]
            references = {base_reference: digest(source)}
            result, metadata, rebound = builder.install(previous, source, Path("in-memory/r269.gb"),
                                                        evidence[history[0]])
            if rebound["in_memory_candidate"]["sha256"] != digest(result):
                raise ValueError("r269 rebound static receipt targets another ROM")
            encoded = (json.dumps(metadata, indent=2) + "\n").encode()
        elif revision == "r271":
            if r265 is None:
                raise ValueError("r271 requires generated r265 reference")
            references = {"generated_r265": digest(r265)}
            result, metadata = builder.install(previous, r265)
            encoded = (json.dumps(metadata, indent=2) + "\n").encode()
        elif revision == "r273":
            result, metadata = builder.install(previous)
            encoded = (json.dumps(metadata, indent=2) + "\n").encode()
        else:
            raise ValueError(f"unknown Stage-7 ancestry step: {revision}")
        if not isinstance(result, bytes) or len(result) != len(source) or digest(result) != pin.rom:
            raise ValueError(f"{pin.module}: generated ROM differs")
        if digest(encoded) != pin.receipt:
            raise ValueError(f"{pin.module}: generated receipt differs")
        changed = [i for i, (a, b) in enumerate(zip(previous, result)) if a != b]
        records.append({
            "name": pin.module, "base_sha256": digest(previous),
            "candidate_sha256": digest(result),
            "generated_receipt_sha256": digest(encoded),
            "generated_receipt_kind": "construction-only" if revision == "r264" else "static-build",
            "reference_sha256": references,
            "source_contracts_rechecked": source_checks,
            "historical_evidence_sha256": {name: digest(evidence[name]) for name in history},
            "historical_corpora_rechecked": False,
            "fresh_live_qualification": False,
            "changed_bytes": len(changed),
            "changed_banks_excluding_checksums": sorted({
                i // 0x4000 for i in changed if i not in (0x14D, 0x14E, 0x14F)}),
        })
    if digest(result) != OUTPUT_SHA256:
        raise ValueError("Stage-7 ancestry did not reproduce exact r273")
    return result, records
