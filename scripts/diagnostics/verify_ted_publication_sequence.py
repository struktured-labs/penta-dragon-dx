#!/usr/bin/env python3
"""Lock Ted's stock partial-to-complete physical-map publication contract."""
from __future__ import annotations
import argparse, hashlib, json
from pathlib import Path

PLANE = 24 * 24
FRAME_SIZE = 4 + PLANE + 2 * 0x400
SCHEMA = "penta-ted-publication-sequence-v1"

def records(data: bytes):
    if len(data) % FRAME_SIZE:
        raise ValueError(f"trace size {len(data)} is not divisible by {FRAME_SIZE}")
    result = []
    for start in range(0, len(data), FRAME_SIZE):
        row = data[start:start + FRAME_SIZE]
        source, maps = row[4:4 + PLANE], []
        for page in range(2):
            raw = row[4 + PLANE + page * 0x400:4 + PLANE + (page + 1) * 0x400]
            maps.append(b"".join(raw[y * 32:y * 32 + 24] for y in range(24)))
        result.append((source, (maps[0], maps[1])))
    return result

def analyze(rows):
    events = exact = partial = foreign_cells = late = 0
    examples = []
    previous = list(rows[0][1])
    for frame in range(1, len(rows)):
        source, maps = rows[frame]
        for page, physical in enumerate(maps):
            old = previous[page]
            if physical == old:
                continue
            events += 1
            if physical == source:
                exact += 1
            else:
                partial += 1
                foreign = sum(v != o and v != s for v, o, s in zip(physical, old, source))
                foreign_cells += foreign
                completes = frame + 1 < len(rows) and rows[frame + 1][1][page] == rows[frame + 1][0]
                late += not completes
                if len(examples) < 12:
                    examples.append({"frame": frame, "map": page,
                        "changed_cells": sum(a != b for a, b in zip(old, physical)),
                        "source_equal_cells": sum(a == b for a, b in zip(source, physical)),
                        "foreign_cells": foreign, "completed_next_frame": int(completes)})
            previous[page] = physical
    failures = {}
    if not partial: failures["partial-path-not-exercised"] = 1
    if foreign_cells: failures["partial-map-foreign-cells"] = foreign_cells
    if late: failures["partial-map-not-complete-next-frame"] = late
    return {"status": "pass" if not failures else "fail", "frames": len(rows),
        "map_change_events": events, "source_exact_events": exact,
        "partial_events": partial, "partial_foreign_cells": foreign_cells,
        "partial_not_complete_next_frame": late, "failures": failures,
        "examples": examples}

def negative_controls(rows):
    previous, found = list(rows[0][1]), None
    for frame in range(1, len(rows)):
        source, maps = rows[frame]
        for page, physical in enumerate(maps):
            if physical != previous[page] and physical != source:
                found = frame, page
                break
            previous[page] = physical
        if found: break
    if not found:
        return {"foreign_cell_rejected": False, "missing_completion_rejected": False}
    frame, page = found
    corrupted = [(s, (m[0], m[1])) for s, m in rows]
    physical = bytearray(corrupted[frame][1][page]); old = rows[frame - 1][1][page]; source = rows[frame][0]
    cell = next(i for i, (a, b) in enumerate(zip(old, source)) if a != b)
    physical[cell] = next(v for v in range(256) if v not in (old[cell], source[cell]))
    pair = list(corrupted[frame][1]); pair[page] = bytes(physical)
    corrupted[frame] = (corrupted[frame][0], (pair[0], pair[1]))
    delayed = [(s, (m[0], m[1])) for s, m in rows]
    pair = list(delayed[frame + 1][1]); pair[page] = rows[frame][1][page]
    delayed[frame + 1] = (delayed[frame + 1][0], (pair[0], pair[1]))
    return {"foreign_cell_rejected": analyze(corrupted)["status"] == "fail",
        "missing_completion_rejected": analyze(delayed)["status"] == "fail"}

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("trace", type=Path); parser.add_argument("--replay", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--receipt-only", action="store_true",
        help="write evidence and defer pass/fail to an aggregate gate")
    args = parser.parse_args()
    first, second = args.trace.read_bytes(), args.replay.read_bytes(); parsed = records(first)
    metrics, controls = analyze(parsed), negative_controls(parsed); deterministic = first == second
    passed = metrics["status"] == "pass" and deterministic and all(controls.values())
    receipt = {"schema": SCHEMA, "status": "pass" if passed else "fail",
        "trace_sha256": hashlib.sha256(first).hexdigest(), "deterministic_replay": deterministic,
        "replay_trace_sha256": hashlib.sha256(second).hexdigest(),
        "negative_controls": controls, "metrics": metrics}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n")
    print(json.dumps(receipt, indent=2, sort_keys=True))
    return 0 if args.receipt_only or passed else 1

if __name__ == "__main__": raise SystemExit(main())
