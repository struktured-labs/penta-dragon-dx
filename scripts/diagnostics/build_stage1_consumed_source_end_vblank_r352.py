#!/usr/bin/env python3
"""Build r352: consume and clear r351's source-end target mailbox."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import build_stage1_completed_source_end_vblank_r351 as r351


ROOT = Path(__file__).resolve().parents[2]
TMP = ROOT / "tmp"
DEFAULT_OUTPUT = TMP / "stage1-consumed-source-end-vblank-r352/candidate.gb"
DEFAULT_RECEIPT = TMP / "stage1-consumed-source-end-vblank-r352/build-receipt.json"
EXPECTED_CANDIDATE_SHA256 = (
    "19931b74fbc42280921c759c96d7ead8a2aa9731edd83c1e55f0222c520555dd"
)

COMMIT_HELPER = bytes.fromhex(
    "FA 5C DF B7 CA 1D 6F AF EA 5C DF "
    "F0 97 FE 02 28 07 FA 00 DC E6 0F E0 43 "
    "FA 02 DC E6 0F E0 42 "
    "FA E0 C3 E6 04 07 47 AF EA E0 C3 "     # consume target mailbox
    "F0 40 E6 F7 B0 E0 40 C3 1D 6F"
)


def build(source: bytes, receipt_bytes: bytes) -> tuple[bytes, dict[str, object]]:
    old_helper = r351.COMMIT_HELPER
    old_expected = r351.EXPECTED_CANDIDATE_SHA256
    try:
        r351.COMMIT_HELPER = COMMIT_HELPER
        r351.EXPECTED_CANDIDATE_SHA256 = "TO_BE_BOUND"
        candidate, receipt = r351.build(source, receipt_bytes)
    finally:
        r351.COMMIT_HELPER = old_helper
        r351.EXPECTED_CANDIDATE_SHA256 = old_expected
    sha = r351.r347.digest(candidate)
    if EXPECTED_CANDIDATE_SHA256 != "TO_BE_BOUND":
        r351.r347.require(sha == EXPECTED_CANDIDATE_SHA256,
                         f"candidate identity drift: {sha}")
    receipt.update({
        "schema": "penta-stage1-consumed-source-end-vblank-r352-build-v1",
        "candidate_sha256": sha,
        "replaces_r351_sha256": r351.EXPECTED_CANDIDATE_SHA256,
        "mailbox_lifecycle": {
            "write": "bank1:$42F0 LD (DE),A with DE=$C3E0",
            "read": "bank13:$741B LD A,($C3E0)",
            "clear": "bank13:$7422 XOR A; LD ($C3E0),A",
            "maximum_intended_lifetime": "map completion to next VBlank",
        },
    })
    receipt["publisher"]["commit_pc"] = "bank13:$742B"
    return candidate, receipt


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", type=Path, default=r351.r347.BASE)
    parser.add_argument("--base-receipt", type=Path, default=r351.r347.BASE_RECEIPT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--receipt", type=Path, default=DEFAULT_RECEIPT)
    args = parser.parse_args()
    output = r351.r347.checked_output(args.output, "candidate")
    receipt_path = r351.r347.checked_output(args.receipt, "receipt")
    candidate, receipt = build(args.base.read_bytes(), args.base_receipt.read_bytes())
    output.parent.mkdir(parents=True, exist_ok=True)
    receipt_path.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(candidate)
    receipt_path.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"candidate_sha256": receipt["candidate_sha256"],
                      "output": str(output), "status": receipt["status"]},
                     sort_keys=True))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except AssertionError as error:
        print(f"FAIL: {error}")
        raise SystemExit(1)
