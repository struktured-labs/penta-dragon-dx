#!/usr/bin/env python3
"""Source-only r314 -> r319 latch and row repair component for r534.

Construction does not qualify executed register access, hardware behavior, or
release readiness. Historical builders retain their exact receipt requirements.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / "scripts/diagnostics"), str(ROOT / "scripts")]
import build_stage1_selector_latch_relocation_r316 as relocation
import build_stage1_selector_latch_cold_init_r317 as cold
import build_stage1_row_gate_abi_speed_r318 as row
import build_stage1_effective_row_context_r319 as effective
from r534_lineage_prefix import EARLY_BASE_SHA256, EARLY_STEPS, digest, serialize_receipt
from suite_contract import source_snapshot

OUTPUT_SHA256 = EARLY_STEPS[2].output_sha256
RELOCATION_SHA256 = "1373479e5a63c1adfa958ae1e278d99d32032b1d3d08386fc3a4d7641496dc2e"
SOURCE_CONTRACT_SHA256 = {
    "r316": "083e5a3252791d2d12edbefb1c30524320d684a99980838d35756976a1a7aa62",
    "r317": "ca026276bd2589bdedfd1b3411a364238f3e131f622f48bd687696777ca70ff5",
    "r318": "63c8ffe9ef3015937b98b831d1f1dde31e5d14773c91d383492eae2cbb390558",
    "r319": "6ea084548808bc4bc86087d7e7394a1d76ac858edc88f78884817ad8ba937071",
}


def construct(source: bytes) -> tuple[bytes, dict]:
    if digest(source) != EARLY_BASE_SHA256:
        raise ValueError("latch construction requires exact r314")
    if set(SOURCE_CONTRACT_SHA256) != {"r316", "r317", "r318", "r319"}:
        raise ValueError("latch source contract pin inventory differs")
    components, steps = {}, []
    result = source
    for revision, builder, expected in (
        ("r316", relocation, RELOCATION_SHA256),
        ("r317", cold, EARLY_STEPS[0].output_sha256),
        ("r318", row, EARLY_STEPS[1].output_sha256),
        ("r319", effective, EARLY_STEPS[2].output_sha256),
    ):
        # r316 is an independently checked component of r317, not its input.
        previous = source if revision in {"r316", "r317"} else result
        result, metadata = builder.construct(previous)
        if not isinstance(result, bytes) or len(result) != len(source) or digest(result) != expected:
            raise ValueError(f"{revision}: source-only generated ROM differs")
        receipt_sha = digest(serialize_receipt(metadata))
        if receipt_sha != SOURCE_CONTRACT_SHA256[revision]:
            raise ValueError(f"{revision}: source-only contract receipt differs")
        components[revision] = metadata
        if revision != "r316":
            steps.append({"name": builder.__name__, "base_sha256": digest(previous),
                          "candidate_sha256": digest(result), "generated_receipt_sha256": receipt_sha})
    return result, {
        "schema": "penta-stage1-latch-source-construction-v1",
        "status": "construction-only", "promotable": False,
        "historical_evidence_consumed": False, "fresh_live_qualification": False,
        "base_sha256": digest(source), "candidate_sha256": digest(result),
        "steps": steps, "components": components,
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
        raise ValueError("latch construction double build differs")
    if snapshot != source_snapshot() or args.base.read_bytes() != source:
        raise ValueError("latch construction inputs changed")
    receipt.update({"base_path": str(args.base.resolve()), "double_build_identical": True,
                    "source_fingerprint": snapshot[0], "source_files": snapshot[1]})
    output.mkdir(parents=True)
    (output / "intermediate-r319.gb").write_bytes(result)
    (output / "construction-receipt.json").write_text(json.dumps(receipt, indent=2) + "\n")
    print(json.dumps({"candidate_sha256": digest(result), "double_build_identical": True,
                      "historical_evidence_consumed": False, "status": "construction-only"}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
