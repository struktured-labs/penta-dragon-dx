"""Regenerate r210 from retained r120/r199 and six historical transition traces."""
from __future__ import annotations

import importlib
import json
from pathlib import Path

from r534_lineage_ancestry import BuildPin
from r534_lineage_prefix import digest

BASE_SHA256 = "0ebae52b5c74ecb5e0cd2bbee11c4ee4fa6aca118aeb0515333722e0273518e8"
EARLY_BASE_SHA256 = "029a413b4ef5c0d3fdb6d9d39902821e8b0d9f35a36bed20ab82973f2ab10742"
OUTPUT_SHA256 = "dbc1001bdeef221ed1611a1e728f63050e25111f81cdadbcd8f900f628e02273"
HISTORICAL_INPUTS = {
    "phase_cold_attract": (
        "tmp/stage1-semantic-key-r74/transition-key-rerun/cold-attract/events.tsv",
        "1622b1514f1d6813c957bce3900fff1a70618c51eea8b93b6a9e79dc52a7fe84"),
    "phase_cold_live": (
        "tmp/stage1-semantic-key-r74/transition-key-rerun/cold-live/events.tsv",
        "fc99515f4bf6557b68474b55052dae21c77c90002bcf7f33e0458376124b5ef8"),
    "phase_sara_alone": (
        "tmp/stage1-semantic-key-r74/transition-key-rerun/level1_sara_w_alone/events.tsv",
        "5db28b8aaf97314ac73ed4f95262cd8d55050135df180a01bfc6df5be8c7d7e2"),
    "phase_sara_gargoyle": (
        "tmp/stage1-semantic-key-r74/transition-key-rerun/level1_sara_w_gargoyle_mini_boss/events.tsv",
        "86fc3e681f636144e6005261cc4662e6f29723e884a4127785dd3478fda8ebc1"),
    "phase_sara_low_health": (
        "tmp/stage1-semantic-key-r74/transition-key-rerun/level1_sara_w_spiral_power_active_health1/events.tsv",
        "0404db2f6574b373c3d7844a41082c4ac49c35719c4cfd186dc45a86707ea122"),
    "phase_box_cold_live": (
        "tmp/stage1-key-box-copy-corpus-r199/cold-live/events.tsv",
        "707052364823f4a4a810628ba16d08b1ced5eb5d6c2b1378472df4a304dd9535"),
}
EARLY_STEPS = (
    BuildPin("build_stage1_r74_semantic_key_r190",
             "04fd5e0db57f3cbe959265359442efa1102a60d258adf5718fe86e2feb669893",
             "ccaaaa9e185068c207564a7f7e01c728a1b0c0ef63a27c24d3c48e956c9fa7f2"),
    BuildPin("build_stage1_live_key_demo_dirty_r194",
             "c6bd39a4eac5bcce00bd621a19af13c0a54f87f51ea89aec5fde8a3b42593272",
             "6514ed713ecf03453897fd6f9029cc70c8806011989349a1658f66e916f6640a"),
    # The r197-named source contains the final cycle-balanced r199 recipe.
    BuildPin("build_stage1_stale_window_hide_r197", BASE_SHA256,
             "1b49a17224a950835b268de2073327af83db741f6556f816843224146b1f0a94"),
)
STEPS = (
    BuildPin("build_stage1_phase_content_key_r208",
             "cc5baaaddd063f5c943b65d9a09f05afb40c71982405de81fc5e5d4a9cff5840",
             "04be214c5da7554aeca2fd54d5882cbae6d0a8f57f18f52d12cc7a14ab586681"),
    BuildPin("build_stage1_split_phase_key_r209",
             "83b2f90f87e3dafcdc168bd85a89104cd60b59483dd2f46666affd35020a9a68",
             "682f8af2d4f86fc66145eddf923c6a87f4c6589625a92ff174856a2b6df75913"),
    BuildPin("build_stage1_deferred_palette_r210", OUTPUT_SHA256,
             "95ae30aa4d9d963af9ada2f31637f6bfdf5af251d3af76ffb47e146d0051dc62"),
)


def construct(source: bytes) -> tuple[bytes, dict]:
    """Source-only r120/r199 -> r210; never synthesize historical receipts.

    Historical build() below still requires and rechecks all six traces.
    This API emits fixed instructions with full per-step ROM pins and labels
    its evidence as construction only, not a transition-corpus pass.
    """
    input_sha = digest(source)
    if input_sha not in (BASE_SHA256, EARLY_BASE_SHA256):
        raise ValueError("Stage-1 phase construction requires exact r120 or r199")
    steps = EARLY_STEPS + STEPS if input_sha == EARLY_BASE_SHA256 else STEPS
    result, records = source, []
    for pin in steps:
        builder = importlib.import_module(pin.module)
        previous = result
        if pin.module in ("build_stage1_phase_content_key_r208", "build_stage1_split_phase_key_r209"):
            result = builder.construct(previous)
        else:
            result, metadata = builder.build(previous)
            encoded = (json.dumps(metadata, indent=2) + "\n").encode()
            if (metadata.get("base_sha256") != digest(previous)
                    or metadata.get("candidate_sha256") != pin.rom or digest(encoded) != pin.receipt):
                raise ValueError(f"{pin.module}: source-only static receipt differs")
        if not isinstance(result, bytes) or len(result) != len(source) or digest(result) != pin.rom:
            raise ValueError(f"{pin.module}: source-only generated ROM differs")
        records.append({"name": pin.module, "base_sha256": digest(previous),
                        "candidate_sha256": digest(result),
                        "changed_bytes": sum(a != b for a, b in zip(previous, result))})
    if digest(result) != OUTPUT_SHA256:
        raise ValueError("Stage-1 phase construction did not reproduce exact r210")
    return result, {
        "schema": "penta-stage1-phase-source-construction-v1",
        "status": "construction-only", "promotable": False,
        "base_sha256": input_sha, "candidate_sha256": digest(result),
        "historical_evidence_consumed": False,
        "historical_transition_checks_rerun": False,
        "fresh_live_qualification": False, "steps": records,
    }


def build(source: bytes, evidence: dict[str, bytes]) -> tuple[bytes, list[dict]]:
    input_sha = digest(source)
    if input_sha not in (BASE_SHA256, EARLY_BASE_SHA256):
        raise ValueError("Stage-1 phase ancestry requires exact retained r120 or r199")
    if set(evidence) != set(HISTORICAL_INPUTS):
        raise ValueError("Stage-1 phase ancestry requires exactly the six historical traces")
    for name, (_, expected) in HISTORICAL_INPUTS.items():
        if digest(evidence[name]) != expected:
            raise ValueError(f"{name}: historical evidence identity differs")
    traces = {Path(path): evidence[name] for name, (path, _) in HISTORICAL_INPUTS.items()}
    result, records = source, []
    steps = EARLY_STEPS + STEPS if input_sha == EARLY_BASE_SHA256 else STEPS
    for pin in steps:
        builder = importlib.import_module(pin.module)
        uses_traces = pin.module in ("build_stage1_phase_content_key_r208", "build_stage1_split_phase_key_r209")
        previous = result
        result, metadata = builder.build(previous, **({"traces": traces} if uses_traces else {}))
        if not isinstance(result, bytes) or len(result) != len(source) or digest(result) != pin.rom:
            raise ValueError(f"{pin.module}: generated ROM differs")
        encoded = (json.dumps(metadata, indent=2) + "\n").encode()
        if (metadata.get("base_sha256") != digest(previous)
                or metadata.get("candidate_sha256") != pin.rom or digest(encoded) != pin.receipt):
            raise ValueError(f"{pin.module}: generated static receipt differs")
        changed = [i for i, (a, b) in enumerate(zip(previous, result)) if a != b]
        records.append({
            "name": pin.module, "base_sha256": digest(previous),
            "candidate_sha256": digest(result),
            "generated_receipt_sha256": digest(encoded),
            "historical_evidence_sha256": {name: digest(data) for name, data in evidence.items()}
                if uses_traces else {},
            "historical_transition_checks_rerun": uses_traces,
            "fresh_live_qualification": False,
            "changed_bytes": len(changed),
            "changed_banks_excluding_checksums": sorted({
                i // 0x4000 for i in changed if i not in (0x14D, 0x14E, 0x14F)}),
        })
    if digest(result) != OUTPUT_SHA256:
        raise ValueError("Stage-1 phase ancestry did not reproduce exact r210")
    return result, records
