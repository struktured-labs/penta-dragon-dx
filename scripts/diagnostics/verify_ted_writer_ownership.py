#!/usr/bin/env python3
"""Verify canonical and staging Ted cells share the native fixed-bank blitter."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

SCHEMA = "penta-ted-writer-ownership-v1"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("probe_report", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    lines = args.probe_report.read_text().splitlines()
    header = lines[0] if lines else ""
    body = [line for line in lines if line.startswith("body_writer=")]
    scratch = [line for line in lines if line.startswith("scratch_writer=")]

    def writers(rows: list[str]) -> list[str]:
        return sorted({row.split()[0].split("=", 1)[1] for row in rows})

    body_writers, scratch_writers = writers(body), writers(scratch)
    checks = {
        "probe_status_ok": header.startswith("status=ok "),
        "no_missing_writers": "missing_writers=0" in header,
        "canonical_samples_present": bool(body),
        "staging_samples_present": bool(scratch),
        "single_canonical_writer": body_writers == ["0E:3127"],
        "single_staging_writer": scratch_writers == ["0E:3127"],
        "writer_is_shared": body_writers == scratch_writers,
    }
    receipt = {
        "schema": SCHEMA,
        "status": "pass" if all(checks.values()) else "fail",
        "checks": checks,
        "canonical_writer_records": len(body),
        "staging_writer_records": len(scratch),
        "canonical_writers": body_writers,
        "staging_writers": scratch_writers,
        "conclusion": (
            "source-writer suppression cannot distinguish canonical from "
            "staging art at the shared $3127 blitter"
        ),
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n")
    print(json.dumps(receipt, indent=2, sort_keys=True))
    return 0 if receipt["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
