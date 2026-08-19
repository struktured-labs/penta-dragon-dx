#!/usr/bin/env python3
"""Validate Ted's 47 settled poses against the pinned stock source corpus."""

from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path

from ted_native_pose_contract_v2 import (
    MAX_BODY_CELLS,
    MIN_BODY_CELLS,
    NATIVE_POSE_SHA256,
    NON_PUBLISHABLE_MAX_PUBLICATION_RUN,
    SETTLED_POSE_INDICES,
    TRANSIENT_POSE_INDICES,
)
from ted_native_sparse_pose_data import (
    POSE_DECISION_TREE,
    SOURCE_RECORDS,
    SOURCE_SHA256,
)


RECORD_SIZE = 4 + 24 * 24
SCHEMA = "penta-ted-settled-pose-contract-v1"


def classify(source: bytes) -> int:
    node = POSE_DECISION_TREE
    while not isinstance(node, int):
        offset, branches = node
        node = branches.get(source[offset], 1)
    return node


def runs(values: list[int], target: int) -> list[int]:
    result = []
    active = 0
    for value in (*values, -1):
        if value == target:
            active += 1
        elif active:
            result.append(active)
            active = 0
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source_trace", type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    data = args.source_trace.read_bytes()
    source_hash = hashlib.sha256(data).hexdigest()
    record_count = len(data) // RECORD_SIZE
    aligned = len(data) == record_count * RECORD_SIZE
    poses = [
        classify(data[index * RECORD_SIZE + 4:(index + 1) * RECORD_SIZE])
        for index in range(record_count)
    ] if aligned else []
    histogram = Counter(poses)
    measured_runs = {
        index: runs(poses, index) for index in sorted(TRANSIENT_POSE_INDICES)
    }
    checks = {
        "pinned_source_hash": source_hash == SOURCE_SHA256,
        "pinned_source_records": record_count == SOURCE_RECORDS and aligned,
        "forty_seven_unique_settled_poses": (
            len(SETTLED_POSE_INDICES) == len(NATIVE_POSE_SHA256) == 47
        ),
        "settled_body_bounds": (MIN_BODY_CELLS, MAX_BODY_CELLS) == (117, 147),
        "non_publishable_states_observed": all(
            histogram[index] > 0 for index in TRANSIENT_POSE_INDICES
        ),
        "non_publishable_runs_exact": all(
            max(measured_runs[index], default=0) == maximum
            for index, maximum in NON_PUBLISHABLE_MAX_PUBLICATION_RUN.items()
        ),
        "all_classifier_keys_known": set(poses) <= set(range(49)),
    }
    receipt = {
        "schema": SCHEMA,
        "status": "pass" if all(checks.values()) else "fail",
        "source_trace": str(args.source_trace.resolve()),
        "source_sha256": source_hash,
        "source_records": record_count,
        "pose_histogram": {str(key): value for key, value in sorted(histogram.items())},
        "non_publishable_runs": {
            str(key): value for key, value in measured_runs.items()
        },
        "non_publishable_maximums": {
            str(key): value
            for key, value in NON_PUBLISHABLE_MAX_PUBLICATION_RUN.items()
        },
        "checks": checks,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n")
    print(json.dumps(receipt, indent=2, sort_keys=True))
    return 0 if receipt["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
