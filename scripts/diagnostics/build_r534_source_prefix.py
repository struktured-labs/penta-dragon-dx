#!/usr/bin/env python3
"""Construct the r534 factory -> r287 prefix without historical observations.

This is an intermediate source-integration component, not a deployable ROM or
a qualification receipt. The factory image must match the existing exact
profile. Its upstream original-cartridge provenance is a separate obligation.
The remaining r287 -> r534 audit still requires five historical inputs.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / "scripts/diagnostics"), str(ROOT / "scripts")]
import r120_historical_profile as baseline
import r534_stage1_phase_ancestry as phase
import r534_stage2_ancestry as stage2
import r534_stage7_ancestry as stage7
import r534_stage4_ancestry as stage4
from suite_contract import source_snapshot


def build(factory: bytes) -> tuple[bytes, dict]:
    """Pure construction with no evidence-file reads or historical pass claims."""
    r120, baseline_receipt = baseline.build(factory)
    r210, phase_receipt = phase.construct(r120)
    r264, stage2_steps = stage2.build(r210)
    if baseline.digest(r264) != stage2.OUTPUT_SHA256:
        raise ValueError("source prefix did not reproduce exact repaired r264")
    r273, stage7_receipt = stage7.construct(r264)
    if baseline.digest(r273) != stage7.OUTPUT_SHA256:
        raise ValueError("source prefix did not reproduce exact r273")
    r287, stage4_receipt = stage4.construct(r273)
    if baseline.digest(r287) != stage4.OUTPUT_SHA256:
        raise ValueError("source prefix did not reproduce exact r287")
    return r287, {
        "schema": "penta-r534-source-prefix-v3",
        "status": "construction-only", "promotable": False,
        "factory_sha256": baseline.digest(factory),
        "output_revision": "r287",
        "output_sha256": baseline.digest(r287),
        "historical_evidence_consumed": False,
        "historical_transition_checks_rerun": False,
        "fresh_live_qualification": False,
        "baseline": baseline_receipt, "phase": phase_receipt,
        "stage2_steps": stage2_steps,
        "stage7": stage7_receipt,
        "stage4": stage4_receipt,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--factory-image", type=Path, required=True)
    parser.add_argument("--out-dir", type=Path, required=True)
    args = parser.parse_args()
    output = args.out_dir.resolve()
    if output == ROOT / "tmp" or not output.is_relative_to(ROOT / "tmp") or output.exists():
        raise ValueError("use a fresh repository-local tmp output directory")
    factory = args.factory_image.read_bytes()
    fingerprint, sources = source_snapshot()
    result, receipt = build(factory)
    again, second = build(factory)
    if (result, receipt) != (again, second):
        raise ValueError("source-prefix double build differs")
    if (fingerprint, sources) != source_snapshot() or args.factory_image.read_bytes() != factory:
        raise ValueError("source-prefix inputs changed during construction")
    receipt.update({"factory_path": str(args.factory_image.resolve()),
                    "double_build_identical": True,
                    "source_fingerprint": fingerprint, "source_files": sources})
    output.mkdir(parents=True)
    (output / "intermediate-r287.gb").write_bytes(result)
    (output / "construction-receipt.json").write_text(json.dumps(receipt, indent=2) + "\n")
    print(json.dumps({"output_sha256": receipt["output_sha256"],
                      "double_build_identical": True, "historical_evidence_consumed": False,
                      "status": receipt["status"], "promotable": False}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
