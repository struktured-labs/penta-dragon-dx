#!/usr/bin/env python3
"""Source-only r319 -> r336 atomic presentation and admission-art component.

Every nested recipe is pinned independently. This does not claim historical
capture equivalence, live qualification, or promotion readiness.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / "scripts/diagnostics"), str(ROOT / "scripts")]
import build_stage1_scene0b_admission_art_repair_r336 as admission
from r534_lineage_prefix import EARLY_STEPS, digest, serialize_receipt
from suite_contract import source_snapshot

delta = admission.r335
runtime = delta.r331
menu = runtime.r325
phase = menu.r324
return_route = phase.r321
atomic = return_route.r320
BASE_SHA256 = EARLY_STEPS[2].output_sha256
OUTPUT_SHA256 = EARLY_STEPS[4].output_sha256
COMPONENTS = (
    ("r320", atomic, "1bbe2d1d3950b1a6f1a194de42fbf5b5e31b26671b037635c42cbd3013d35ae7",
     "55b1acaf22feb05985246830dc5e8b2db9778a3041037f7be8071975e80024f6"),
    ("r321", return_route, "3fe6b19b9dfdfb3b305bfb811ce62b8ea1551bbdd0f1e0e3fe571ded4ccb1e3d",
     "cf8e8bfc97b9602e2f31ce424d4fab31581666cd3e7cd92c71fb250897fcf034"),
    ("r324", phase, "90c74092768ce2916d06ebdbd52d2b4fe2b0077642d31ede40a325ae76760bf4",
     "cebe1cf974206011b422c3a04b96c211276cff603811ffa1ace7835d1962c76b"),
    ("r325", menu, "c38749f6909fdd1b55538ad6f9e2815a542a01ae3ce227604232d65d6a8ac221",
     "195bdadb55747e185ee10eeb67cab8a4a9a110bcb4ea1f529fc8301053d40d28"),
    ("r331", runtime, "eb2c87a36943b518ff4f1dba533d2bf7681211a1f2801fd145db9c86c2b66348",
     "0bb2622efd4702c3267465c62f3de5948f260fb2b223b643c68fdcc6b4539fa7"),
    ("r335", delta, "f48cef9ee3f662c66445c08af65eca55fd7cc402f1b78a570e635a5db3a88c27",
     "424c5f54c27911a786324d9cecb37ddc17b29f6c2482bfa21214de53a7f6e93b"),
    ("r336", admission, "484cd678bd6724f7ab9c128a985a0a50db1c523ad406103a8f57bd84784f4611",
     "4b7b25beb60f26b2b86354e854522622f99b52a6dcd2f2d1cc07dd37d646edbd"),
)


def construct(source: bytes) -> tuple[bytes, dict]:
    if digest(source) != BASE_SHA256:
        raise ValueError("admission construction requires exact r319")
    if tuple(item[0] for item in COMPONENTS) != ("r320", "r321", "r324", "r325", "r331", "r335", "r336"):
        raise ValueError("admission source component pin inventory differs")
    components, steps = {}, []
    base = source
    for revision, builder, rom_sha, receipt_sha in COMPONENTS:
        result, metadata = builder.construct(base)
        if not isinstance(result, bytes) or len(result) != len(source) or digest(result) != rom_sha:
            raise ValueError(f"{revision}: source-only generated ROM differs")
        if digest(serialize_receipt(metadata)) != receipt_sha:
            raise ValueError(f"{revision}: source-only contract receipt differs")
        components[revision] = metadata
        if revision in {"r320", "r336"}:
            steps.append({"name": builder.__name__, "base_sha256": digest(base),
                          "candidate_sha256": digest(result), "generated_receipt_sha256": receipt_sha})
        if revision == "r320":
            base = result
    if digest(result) != OUTPUT_SHA256:
        raise ValueError("admission final ROM pin differs")
    return result, {
        "schema": "penta-stage1-admission-source-construction-v1",
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
        raise ValueError("admission construction double build differs")
    if snapshot != source_snapshot() or args.base.read_bytes() != source:
        raise ValueError("admission construction inputs changed")
    receipt.update({"base_path": str(args.base.resolve()), "double_build_identical": True,
                    "source_fingerprint": snapshot[0], "source_files": snapshot[1]})
    output.mkdir(parents=True)
    (output / "intermediate-r336.gb").write_bytes(result)
    (output / "construction-receipt.json").write_text(json.dumps(receipt, indent=2) + "\n")
    print(json.dumps({"candidate_sha256": digest(result), "double_build_identical": True,
                      "historical_evidence_consumed": False, "status": "construction-only"}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
