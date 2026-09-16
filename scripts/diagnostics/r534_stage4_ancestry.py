"""Replay r273 -> r287 in memory with explicit, authentic historical evidence.

Historical captures constrain the old builders; they are not fresh live gates.
The r279/r281 references and all static receipts are generated, never loaded.
"""
from __future__ import annotations

import importlib
import json

from r534_lineage_ancestry import BuildPin
from r534_lineage_prefix import digest, serialize_receipt

BASE_SHA256 = "09d75d4461d911f4ed55c929c676346b1f7851e015bdbd867f307f8d9f1cc1d8"
OUTPUT_SHA256 = "a9bc2d2d5d7112584797229d03bfb2fe55a9bcb5fa3c1a33d30cddc3a8364898"
SOURCE_CONTRACT_SHA256 = {
    "r285": "3e33c76314d15d4854fcac33a203fe7109a2516ca80104a89c1beb38701fc812",
    "r286": "b89810af84aa78bc3ca8411c23a6fd8fe2ad0274bd4ca9f49c16628352189c55",
    "r287": "b00820f2522ba72af914d1d7a07b8cdcef9a3d8f0ecbb9cec0ac49fa4a1d010a",
}
HISTORICAL_INPUTS = {
    "stage4_canonical": (
        "tmp/stage2-isolated-entry-r263/stage346-semantic-soak-8000/stage4.layout-events.tsv",
        "54becf276a33dc9f51cce123d39c8ce80f58be04f4b186a534c34ae2a672c90a"),
    "stage4_live": (
        "tmp/stage7-lazy-disarm-r279/stages134567-speed-right-strict99-r1/stage4-dx-a-right/attr-events.tsv",
        "d23a6cb7699a82bc6c7f0fe99c189fa6a34d9dd019a2b1389257e72de8af18fb"),
    "stage4_speed": (
        "tmp/stage7-lazy-disarm-r279/stages134567-speed-right-strict99-r1/manifest.json",
        "c644b20b24f71dd28cdf1268a18c9adad9ed44b75d56c540b01925fb662db8a9"),
}
for stage, meta_sha in enumerate((
    "878723632f89b3736a3b2c46c1a0033d24be5023bd3867acb8ad032cafa0ff6e",
    "447f9048aada73625d3408f426fec00101aa4dd60134df62cde6f76ee4b1ef42",
    "75cab893f07707c39d9f6c76bc88cc8d3a8b4c474c515ed901aa595860d4fbeb",
    "390962a176205d26a4bdfa2591d778c298f4ac93d9f5936c0ed8a6a29bd9735f",
    "03941c3fd77ba70140e950db216b9b349d5960b3b3af541068e5833052b879b9",
    "67829504e78570db78a0368bd2402ef48473abc3f05f8765286992b690636779",
), start=2):
    HISTORICAL_INPUTS[f"stage4_wram{stage}"] = (
        f"tmp/r285-wram-ownership-r281/stage{stage}.wram1-db.bin",
        "38723a2e5e8a17aa7950dc008209944e898f69a7bd10a23c839d341e935fd5ca")
    HISTORICAL_INPUTS[f"stage4_meta{stage}"] = (
        f"tmp/r285-wram-ownership-r281/stage{stage}.meta", meta_sha)

STEPS = (
    BuildPin("build_stage7_isolated_router_r277",
             "0c317aa69425ca3ca6f49b3e65a1671fb4fc4ee50d8b15d4900f12cf4493eb3f",
             "6e9fa21d7b2c5d68251e1ffbf9ba4d01dfd53c119c1ea62777414b3098307a6c"),
    BuildPin("build_stage7_pointer_advance_r278",
             "1bb98e252995a4da9080bcc7aeeb27237762eb2d0713d9ed7e43409c978efd47",
             "e6f9c93d148881b14c6a10e4abaca33149c272f27a6f79526d81fb03aa079b5d"),
    BuildPin("build_stage7_lazy_disarm_r279",
             "649dab3b8895e680ff9e64005641de89b3ac1f66bcb417d6a1c42ce98bc30a9d",
             "90842bca233226bcc2cc19d8f0f81e87ade4b6644f315c9552327c55e3f55018"),
    BuildPin("build_stage1_metallic_teeth_r281",
             "6b2bb22129011d06a1d5f5eb07a34c04f5dc09c35d9df65afa4a000546a8cf49",
             "0d38a4e16dbc919ebf39542bb9c1e46a33d2c6879ca0ed261fc74ffabda5b0a6"),
    BuildPin("build_stage4_lazy_departure_r285",
             "f93cbfd20760ec88363b039c47373422e90453116a841a872e22ef293d29ce75",
             "668b20cc7d4eb3954572e6002f6ee6cb94091ee56096cb61f64f848d51a76e74"),
    BuildPin("build_stage4_lazy_departure_r286",
             "a5521815ee25ca1c35a063198aec5f6a69609f99df7554201e41ab73699fc3c1",
             "4a1209778c471dc833ab574d6bac46e70e8f8d925a80a4ec48dd61099f117d49"),
    BuildPin("build_stage4_menu_exit_invalidation_r287", OUTPUT_SHA256,
             "cf44305b10189d5549b2c2a2bc555a5c9729450b8d948acaf8b68258c58f1f4c"),
)


def construct(source: bytes) -> tuple[bytes, dict]:
    """Construct r287 from source and generated references, without observations."""
    if digest(source) != BASE_SHA256:
        raise ValueError("Stage-4 source construction requires exact r273")
    if set(SOURCE_CONTRACT_SHA256) != {"r285", "r286", "r287"}:
        raise ValueError("Stage-4 source contract pin inventory differs")
    result, records, checkpoints = source, [], {}
    for pin in STEPS:
        builder = importlib.import_module(pin.module)
        revision = pin.module.rsplit("_", 1)[1]
        previous = result
        references = {}
        if revision == "r285":
            references = {"r279": checkpoints["r279"]}
            result, metadata = builder.construct(previous, references["r279"])
        elif revision == "r286":
            references = {name: checkpoints[name] for name in ("r281", "r279")}
            result, metadata = builder.construct(previous, references["r281"], references["r279"])
        elif revision == "r287":
            result, metadata = builder.construct(previous)
        elif revision in ("r277", "r278", "r279", "r281"):
            result, metadata = builder.install(previous)
        else:
            raise ValueError(f"unknown Stage-4 source step: {revision}")
        if not isinstance(result, bytes) or len(result) != len(source) or digest(result) != pin.rom:
            raise ValueError(f"{pin.module}: source-only generated ROM differs")
        source_only = revision in SOURCE_CONTRACT_SHA256
        encoded = serialize_receipt(metadata) if source_only else (json.dumps(metadata, indent=2) + "\n").encode()
        expected = SOURCE_CONTRACT_SHA256[revision] if source_only else pin.receipt
        if digest(encoded) != expected:
            raise ValueError(f"{pin.module}: source-only contract receipt differs")
        records.append({"name": pin.module, "base_sha256": digest(previous),
                        "candidate_sha256": digest(result),
                        "generated_receipt_sha256": digest(encoded),
                        "generated_receipt_kind": "construction-only" if source_only else "static-build",
                        "source_contracts": metadata if source_only else {},
                        "reference_sha256": {name: digest(data) for name, data in references.items()},
                        "changed_bytes": sum(a != b for a, b in zip(previous, result))})
        if revision in ("r279", "r281"):
            checkpoints[revision] = result
    if digest(result) != OUTPUT_SHA256:
        raise ValueError("Stage-4 source construction did not reproduce exact r287")
    return result, {
        "schema": "penta-stage4-source-construction-v1", "status": "construction-only",
        "promotable": False, "base_sha256": digest(source), "candidate_sha256": digest(result),
        "historical_evidence_consumed": False, "historical_corpora_rechecked": False,
        "historical_wram_snapshots_checked": False, "fresh_live_qualification": False,
        "steps": records,
    }


def build(source: bytes, evidence: dict[str, bytes]) -> tuple[bytes, list[dict]]:
    if digest(source) != BASE_SHA256:
        raise ValueError("Stage-4 ancestry requires exact retained r273")
    if set(evidence) != set(HISTORICAL_INPUTS):
        raise ValueError("Stage-4 ancestry requires exactly the fifteen historical inputs")
    for name, (_, expected) in HISTORICAL_INPUTS.items():
        if digest(evidence[name]) != expected:
            raise ValueError(f"{name}: historical evidence identity differs")
    # Original builder labels are preserved in its byte-exact static receipts.
    supplied = {path: evidence[name] for name, (path, _) in HISTORICAL_INPUTS.items()}
    result, encoded, records, checkpoints = source, None, [], {}
    for pin in STEPS:
        builder = importlib.import_module(pin.module)
        revision = pin.module.rsplit("_", 1)[1]
        previous = result
        input_receipt = None
        references = {}
        uses_evidence = revision in ("r285", "r286")
        if revision == "r285":
            references = {"r279": checkpoints["r279"]}
            result, metadata = builder.install(previous, references["r279"], evidence=supplied)
        elif revision == "r286":
            input_receipt = encoded
            references = {name: checkpoints[name] for name in ("r281", "r279")}
            result, metadata = builder.install(previous, references["r281"], references["r279"],
                                                input_receipt, evidence=supplied)
        elif revision == "r287":
            input_receipt = encoded
            result, metadata = builder.build(previous, input_receipt)
        else:
            result, metadata = builder.install(previous)
        if not isinstance(result, bytes) or len(result) != len(source) or digest(result) != pin.rom:
            raise ValueError(f"{pin.module}: generated ROM differs")
        # These historical CLIs used insertion order until r287 switched to sorted JSON.
        encoded = (json.dumps(metadata, indent=2, sort_keys=revision == "r287") + "\n").encode()
        if metadata.get("candidate_sha256") != pin.rom or digest(encoded) != pin.receipt:
            raise ValueError(f"{pin.module}: generated static receipt differs")
        changed = [i for i, (a, b) in enumerate(zip(previous, result)) if a != b]
        records.append({
            "name": pin.module, "base_sha256": digest(previous),
            "candidate_sha256": digest(result),
            "input_receipt_sha256": digest(input_receipt) if input_receipt is not None else None,
            "generated_receipt_sha256": digest(encoded),
            "generated_references": {name: digest(data) for name, data in references.items()},
            "historical_evidence_sha256": {name: digest(data) for name, data in evidence.items()}
                if uses_evidence else {},
            "fresh_live_qualification": False,
            "changed_bytes": len(changed),
            "changed_banks_excluding_checksums": sorted({
                i // 0x4000 for i in changed if i not in (0x14D, 0x14E, 0x14F)}),
        })
        if revision in ("r279", "r281"):
            checkpoints[revision] = result
    if digest(result) != OUTPUT_SHA256:
        raise ValueError("Stage-4 ancestry did not reproduce exact r287")
    return result, records
