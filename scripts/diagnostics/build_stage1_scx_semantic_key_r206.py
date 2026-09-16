#!/usr/bin/env python3
"""Replace Stage 1's colliding packed-cell key with the live SCX phase.

Exact r199 can publish a horizontally shifted tile plane without publishing
its matching attributes: raw packed layouts changed while SCY, DC02, C1BB,
and C29F produced the same eight-bit XOR key.  The first rendered failure is
an exact two-cell pickup/wall displacement at native-play frame 24.

The existing 41-byte runtime has no free expansion space.  Replace only the
five-byte C1BB sample with ``SCX XOR B`` plus one timing pad.  The resulting
key is SCX ^ SCY ^ DC02 ^ C29F.  The checked-in Stage-1 transition corpus has
zero false negatives for that key; live raster verification remains the
promotion authority.
"""

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
OLD_RUNTIME = bytes.fromhex(
    "FA80D8E6F7FE02201D16DF7CEECB5F1A4FF04247FA02DCA847FABB"
    "C1A847FA9FC2A8B9C812C9C3B9DA"
)
NEW_RUNTIME = bytes.fromhex(
    "FA80D8E6F7FE02201D16DF7CEECB5F1A4FF04247FA02DCA847F043"
    "A84700FA9FC2A8B9C812C9C3B9DA"
)
CORPUS_ROOT = Path("tmp/stage1-semantic-key-r74/transition-key-rerun")


def digest(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def audit_corpus(root: Path) -> dict:
    profiles = {}
    total_events = total_transitions = total_publications = 0
    total_false_negatives = total_false_positives = 0
    traces = sorted(root.glob("*/events.tsv"))
    if len(traces) != 5:
        raise SystemExit(f"expected five transition traces under {root}, found {len(traces)}")
    for trace in traces:
        last_key: dict[int, int] = {}
        last_plane: dict[int, bytes] = {}
        events = transitions = publications = 0
        false_negatives = false_positives = 0
        with trace.open(newline="") as handle:
            for row in csv.DictReader(handle, delimiter="\t"):
                events += 1
                destination = int(row["destination"], 16)
                raw = bytes.fromhex(row["raw"])
                plane = bytes.fromhex(row["plane"])
                key = (
                    int(row["scx"], 16)
                    ^ int(row["scy"], 16)
                    ^ int(row["dc02"], 16)
                    ^ raw[255]
                ) & 0x7F
                published = last_key.get(destination, 0xFF) != key
                transitioned = last_plane.get(destination) != plane
                publications += int(published)
                transitions += int(transitioned)
                false_negatives += int(transitioned and not published)
                false_positives += int(published and not transitioned)
                last_key[destination] = key
                last_plane[destination] = plane
        profiles[trace.parent.name] = {
            "events": events,
            "semantic_transitions": transitions,
            "publications": publications,
            "false_negatives": false_negatives,
            "false_positives": false_positives,
        }
        total_events += events
        total_transitions += transitions
        total_publications += publications
        total_false_negatives += false_negatives
        total_false_positives += false_positives
    if total_false_negatives:
        raise SystemExit(f"SCX semantic key misses {total_false_negatives} corpus transitions")
    return {
        "profiles": profiles,
        "totals": {
            "events": total_events,
            "semantic_transitions": total_transitions,
            "publications": total_publications,
            "false_negatives": total_false_negatives,
            "false_positives": total_false_positives,
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("base", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--receipt", type=Path, required=True)
    parser.add_argument("--corpus", type=Path, default=CORPUS_ROOT)
    args = parser.parse_args()

    source = args.base.read_bytes()
    if digest(source) != BASE_SHA256:
        raise SystemExit(f"unqualified exact r199 base: {digest(source)}")
    if len(OLD_RUNTIME) != RUNTIME_LENGTH or len(NEW_RUNTIME) != RUNTIME_LENGTH:
        raise SystemExit("internal runtime length error")
    rom = bytearray(source)
    for offset in RUNTIME_OFFSETS:
        if rom[offset:offset + RUNTIME_LENGTH] != OLD_RUNTIME:
            raise SystemExit(f"Stage-1 runtime preimage moved at ${offset:06X}")
        rom[offset:offset + RUNTIME_LENGTH] = NEW_RUNTIME
    update_checksums(rom)
    candidate = bytes(rom)
    corpus = audit_corpus(args.corpus)
    receipt = {
        "schema": "penta-stage1-scx-semantic-key-r206-v1",
        "status": "STATIC_PASS_EMULATOR_REQUIRED",
        "promotable": False,
        "base_sha256": digest(source),
        "candidate_sha256": digest(candidate),
        "runtime_offsets": [f"0x{offset:X}" for offset in RUNTIME_OFFSETS],
        "old_features": ["SCY", "DC02", "C1BB", "C29F"],
        "new_features": ["SCX", "SCY", "DC02", "C29F"],
        "corpus": corpus,
        "required_first_gate": "3600-frame native Stage-1 rendered no-bleed",
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.receipt.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(candidate)
    args.receipt.write_text(json.dumps(receipt, indent=2) + "\n")
    print(json.dumps(receipt, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
