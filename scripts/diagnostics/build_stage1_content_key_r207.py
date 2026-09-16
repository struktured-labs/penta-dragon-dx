#!/usr/bin/env python3
"""Install the receipt-qualified Stage 1 packed-content key on exact r199."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path

from build_later_gdma_upper_bound import update_checksums


BASE_SHA256 = "0ebae52b5c74ecb5e0cd2bbee11c4ee4fa6aca118aeb0515333722e0273518e8"
RUNTIME_OFFSETS = (0x37C96, 0x43C96)
RUNTIME_LENGTH = 41
STAGE1_LUT_OFFSET = 13 * 0x4000 + (0x7000 - 0x4000)
FEATURE_OFFSETS = (123, 280)
OLD_RUNTIME = bytes.fromhex(
    "FA80D8E6F7FE02201D16DF7CEECB5F1A4FF04247FA02DCA847FABB"
    "C1A847FA9FC2A8B9C812C9C3B9DA"
)
NEW_RUNTIME = bytes.fromhex(
    "FA80D8E6F7FE02201D16DF7CEECB5F1A4FF04247FA02DCA847FA1B"
    "C2A847FAB8C2A8B9C812C9C3B9DA"
)
DEFAULT_CORPORA = (
    Path("tmp/stage1-semantic-key-r74/transition-key-rerun"),
    Path("tmp/stage1-key-box-copy-corpus-r199"),
)


def digest(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def audit_profile(path: Path, canonical_lut: bytes) -> dict[str, object]:
    last_key: dict[int, int] = {}
    last_plane: dict[int, bytes] = {}
    events = transitions = publications = false_negatives = false_positives = 0
    first_false_negative = None
    with path.open(newline="") as handle:
        for row in csv.DictReader(handle, delimiter="\t"):
            events += 1
            destination = int(row["destination"], 16)
            raw = bytes.fromhex(row["raw"])
            plane = bytes(canonical_lut[tile] & 0x07 for tile in raw)
            key = (
                int(row["scy"], 16)
                ^ int(row["dc02"], 16)
                ^ raw[FEATURE_OFFSETS[0]]
                ^ raw[FEATURE_OFFSETS[1]]
            )
            published = last_key.get(destination, 0xFF) != key
            transitioned = last_plane.get(destination) != plane
            publications += int(published)
            transitions += int(transitioned)
            false_negatives += int(transitioned and not published)
            false_positives += int(published and not transitioned)
            if transitioned and not published and first_false_negative is None:
                first_false_negative = {
                    "event": events,
                    "frame": int(row["frame"]),
                    "destination": row["destination"],
                    "room": row["room"],
                    "key": key,
                }
            last_key[destination] = key
            last_plane[destination] = plane
    return {
        "events": events,
        "semantic_transitions": transitions,
        "publications": publications,
        "false_negatives": false_negatives,
        "false_positives": false_positives,
        "first_false_negative": first_false_negative,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("base", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--receipt", type=Path, required=True)
    parser.add_argument("--corpus", type=Path, action="append")
    args = parser.parse_args()

    source = args.base.read_bytes()
    if digest(source) != BASE_SHA256:
        raise SystemExit(f"unqualified exact r199 base: {digest(source)}")
    if len(OLD_RUNTIME) != RUNTIME_LENGTH or len(NEW_RUNTIME) != RUNTIME_LENGTH:
        raise SystemExit("internal runtime length error")
    canonical_lut = source[STAGE1_LUT_OFFSET : STAGE1_LUT_OFFSET + 256]
    if len(canonical_lut) != 256:
        raise SystemExit("missing canonical Stage 1 LUT")

    profiles: dict[str, object] = {}
    for root in tuple(args.corpus or DEFAULT_CORPORA):
        traces = sorted(root.glob("*/events.tsv"))
        if not traces:
            raise SystemExit(f"no transition traces below {root}")
        for trace in traces:
            name = f"{root.name}/{trace.parent.name}"
            profile = audit_profile(trace, canonical_lut)
            if profile["false_negatives"]:
                raise SystemExit(f"content key misses transitions in {name}: {profile}")
            profiles[name] = profile

    rom = bytearray(source)
    for offset in RUNTIME_OFFSETS:
        if rom[offset : offset + RUNTIME_LENGTH] != OLD_RUNTIME:
            raise SystemExit(f"Stage 1 runtime preimage moved at ${offset:06X}")
        rom[offset : offset + RUNTIME_LENGTH] = NEW_RUNTIME
    update_checksums(rom)
    candidate = bytes(rom)
    receipt = {
        "schema": "penta-stage1-content-key-r207-v1",
        "status": "STATIC_PASS_EMULATOR_REQUIRED",
        "promotable": False,
        "base_sha256": digest(source),
        "candidate_sha256": digest(candidate),
        "runtime_offsets": [f"0x{offset:X}" for offset in RUNTIME_OFFSETS],
        "old_features": ["SCY", "DC02", "raw27", "raw255"],
        "new_features": ["SCY", "DC02", "raw123", "raw280"],
        "runtime_length_unchanged": True,
        "runtime_timing_shape_unchanged": True,
        "profiles": profiles,
        "required_first_gates": [
            "3600-frame native no-bleed",
            "low-health deterministic replay",
        ],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.receipt.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(candidate)
    args.receipt.write_text(json.dumps(receipt, indent=2) + "\n")
    print(json.dumps(receipt, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
