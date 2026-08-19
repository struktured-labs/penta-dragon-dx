#!/usr/bin/env python3
"""Static fail-closed contract for the experimental Ted cell sanitizer."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from scripts import build_v302_title_fix as build  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    model = json.loads(args.model.read_text())
    classifier, fragments = build.build_ted_incremental_cell_classifier_draft()
    build.validate_ted_incremental_cell_layout(classifier, fragments)
    publication_gate = build.build_ted_incremental_mask_publication_gate_draft()
    mask_builder = build.build_ted_incremental_mask_builder_draft()
    fit_gate, fit_builder, fit_delta = (
        build.build_ted_incremental_specialized_fit_draft()
    )
    packed_table, packed_builder = (
        build.build_ted_incremental_packed_geometry_draft()
    )

    private = {
        address: payload
        for address, payload in fragments.items()
        if address >= 0x8000
    }
    rom = {
        address: payload
        for address, payload in fragments.items()
        if address < 0x8000
    }
    classifier_code_bytes = len(classifier.rstrip(b"\0"))
    sparse_lut = tuple(
        build.ARENA_TILE_PAL["ted"].get(tile, 0)
        for tile in range(0x77, 0x87)
    )
    sparse_lut_expected = (
        6, 7, 7, 6, 5, 0, 1, 0, 0, 2, 0, 5, 1, 2, 5, 1,
    )
    sparse_lut_contract = sparse_lut == sparse_lut_expected

    # A selected runtime build must remain impossible until these private
    # payloads have a qualified ROM source and installer copy route.
    names = (
        "PENTA_TED_DIRECT_PLANE",
        "PENTA_TED_INWINDOW_GDMA",
        build.TED_INCREMENTAL_CELL_ENV,
    )
    saved = {name: os.environ.get(name) for name in names}
    blocked = False
    block_reason = ""
    try:
        os.environ.update({name: "1" for name in names})
        try:
            build.build_ted_incremental_runtime_sources()
        except AssertionError as error:
            block_reason = str(error)
            blocked = "no receipt-qualified" in block_reason
    finally:
        for name, value in saved.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value

    status = (
        model.get("schema") == "penta-ted-incremental-mask-model-v2"
        and model.get("status") == "pass"
        and model.get("candidate_total") == 0
        and model.get("negative_no_repair_total", 0) > 0
        and model.get("negative_high_leak_total", 0) > 0
        and model.get("negative_wide_geometry_total", 0) > 0
        and model.get("negative_byte_mask_total", 0) > 0
        and model.get("no_crown_fail_closed") is True
        and model.get("ambiguous_crown_fail_closed") is True
        and model.get("palette_roundtrip") is True
        and sparse_lut_contract
        and blocked
    )
    receipt = {
        "schema": "penta-ted-incremental-cell-contract-v2",
        "status": "pass" if status else "fail",
        "model_status": model.get("status"),
        "classifier": {
            "publication_entry": f"{build.TED_INWINDOW_SANITIZER_ADDR:04X}",
            "cell_entry": f"{build.TED_INWINDOW_MASK_CLASSIFIER_ADDR:04X}",
            "bytes": len(classifier),
            "sha256": hashlib.sha256(classifier).hexdigest(),
        },
        "private_helpers": [
            {
                "address": f"{address:04X}",
                "bytes": len(payload),
                "sha256": hashlib.sha256(payload).hexdigest(),
            }
            for address, payload in sorted(private.items())
        ],
        "body_mask": {
            "address": f"{build.TED_INWINDOW_BODY_MASK_ADDR:04X}",
            "bytes": build.TED_INWINDOW_BODY_MASK_SIZE,
            "classifier_code_bytes": classifier_code_bytes,
            "private_executable_helpers": len(private),
        },
        "sparse_lut_contract": {
            "status": "pass" if sparse_lut_contract else "fail",
            "range": "77-86",
            "values": list(sparse_lut),
            "floor_77_7a_nonzero": all(sparse_lut[:4]),
            "sparse_nonzero_ids": [
                f"{tile:02X}"
                for tile in range(0x7B, 0x87)
                if build.ARENA_TILE_PAL["ted"].get(tile, 0)
            ],
        },
        "rom_repair_fragments": [
            {"address": f"{address:04X}", "bytes": len(payload)}
            for address, payload in sorted(rom.items())
        ],
        "publication_fit": {
            "candidate_gate_bytes": len(publication_gate),
            "naive_mask_builder_bytes": len(mask_builder),
            "assembled_bytes_before_delta_repair": (
                len(publication_gate) + len(mask_builder)
            ),
            "known_rom_capacity_bytes": 178,
            "shared_classifier_code_bytes": classifier_code_bytes,
            "shared_classifier_tail_bytes": len(classifier) - classifier_code_bytes,
            "specialized_unfragmented": {
                "gate_bytes": len(fit_gate),
                "builder_bytes": len(fit_builder),
                "fused_delta_bytes": len(fit_delta),
                "total_bytes": len(fit_gate) + len(fit_builder) + len(fit_delta),
            },
            "verified_effective_pool_bytes": 205,
            "fragmented_exact": {
                "gate_bytes": 50,
                "builder_fragments": [20, 12, 16, 19, 14],
                "delta_fragments": [12, 22, 24, 24, 17],
                "total_bytes": 230,
                "overage_bytes": 25,
                "shape_fit": False,
            },
            "packed_geometry_negative": {
                "table_bytes": len(packed_table),
                "builder_bytes": len(packed_builder),
                "combined_bytes": len(packed_table) + len(packed_builder),
            },
            "complete": False,
        },
        "runtime_candidate_blocked_without_ownership_receipt": blocked,
        "block_reason": block_reason,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(receipt, indent=2) + "\n")
    print(json.dumps(receipt, indent=2))
    return 0 if status else 2


if __name__ == "__main__":
    raise SystemExit(main())
