#!/usr/bin/env python3
"""Find a collision-free two-byte Stage 1 semantic publication key.

The runtime key has a fixed ``SCY ^ DC02`` prefix and samples two bytes from
the packed 24x24 source plane.  A candidate is accepted only when every
observed attribute-plane transition changes the key in both the established
publication corpus and a long rendered-scroll corpus.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import itertools
import json
from pathlib import Path

import numpy as np


PLANE_SIZE = 24 * 24
LAYOUT_RECORD_SIZE = PLANE_SIZE * 2
STAGE1_LUT_OFFSET = 13 * 0x4000 + (0x7000 - 0x4000)
EXTRA_FEATURES = ("scx", "dc00", "dc01", "dc03")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_transition_events(root: Path) -> list[dict[str, object]]:
    events: list[dict[str, object]] = []
    for path in sorted(root.glob("*/events.tsv")):
        with path.open(newline="") as handle:
            for row in csv.DictReader(handle, delimiter="\t"):
                raw = bytes.fromhex(row["raw"])
                plane = bytes.fromhex(row["plane"])
                if len(raw) != PLANE_SIZE or len(plane) != PLANE_SIZE:
                    raise ValueError(f"invalid plane size in {path}")
                events.append(
                    {
                        "corpus": f"{root.name}/{path.relative_to(root)}",
                        "destination": row["destination"],
                        "scy": int(row["scy"], 16),
                        "dc02": int(row["dc02"], 16),
                        **{field: int(row[field], 16) for field in EXTRA_FEATURES},
                        "raw": raw,
                        "plane": plane,
                    }
                )
    if not events:
        raise ValueError(f"no events.tsv files below {root}")
    return events


def load_rendered_events(
    receipt_path: Path, layouts_path: Path, canonical_lut: bytes
) -> list[dict[str, object]]:
    blob = layouts_path.read_bytes()
    if len(blob) % LAYOUT_RECORD_SIZE:
        raise ValueError("layouts.bin is not an integral sequence of 1152-byte records")
    layouts = [
        (blob[pos : pos + PLANE_SIZE], blob[pos + PLANE_SIZE : pos + LAYOUT_RECORD_SIZE])
        for pos in range(0, len(blob), LAYOUT_RECORD_SIZE)
    ]
    receipt = json.loads(receipt_path.read_text())
    captures = receipt["probe"]["raster_captures"]
    events: list[dict[str, object]] = []
    for capture in captures:
        layout_id = int(capture["layout_id"])
        if not 1 <= layout_id <= len(layouts):
            raise ValueError(f"layout_id {layout_id} is outside layouts.bin")
        raw, _live_plane = layouts[layout_id - 1]
        plane = bytes(canonical_lut[tile] & 0x07 for tile in raw)
        events.append(
            {
                "corpus": "rendered-scroll",
                "destination": "9C00" if int(capture["lcdc"]) & 0x08 else "9800",
                "scy": int(capture["scy"]),
                "dc02": int(capture["dc02"]),
                **{field: int(capture[field]) for field in EXTRA_FEATURES},
                "raw": raw,
                "plane": plane,
            }
        )
    if not events:
        raise ValueError("receipt has no raster captures")
    return events


def transitions(events: list[dict[str, object]]) -> list[dict[str, object]]:
    previous: dict[tuple[str, str], dict[str, object]] = {}
    result: list[dict[str, object]] = []
    for event in events:
        identity = (str(event["corpus"]), str(event["destination"]))
        prior = previous.get(identity)
        previous[identity] = event
        if prior is None:
            continue
        if (
            prior["raw"] == event["raw"]
            and prior["plane"] == event["plane"]
            and prior["scy"] == event["scy"]
            and prior["dc02"] == event["dc02"]
            and all(prior[field] == event[field] for field in EXTRA_FEATURES)
        ):
            continue
        result.append(
            {
                "corpus": event["corpus"],
                "semantic": prior["plane"] != event["plane"],
                "fixed_delta": int(prior["scy"]) ^ int(event["scy"]) ^ int(prior["dc02"]) ^ int(event["dc02"]),
                "scy_before": int(prior["scy"]),
                "scy_after": int(event["scy"]),
                "dc02_before": int(prior["dc02"]),
                "dc02_after": int(event["dc02"]),
                "raw_delta": bytes(a ^ b for a, b in zip(prior["raw"], event["raw"])),
                "raw_before": prior["raw"],
                "raw_after": event["raw"],
                "extra_delta": bytes(
                    int(prior[field]) ^ int(event[field]) for field in EXTRA_FEATURES
                ),
            }
        )
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--transition-root", type=Path, action="append", required=True)
    parser.add_argument("--rom", type=Path, required=True)
    parser.add_argument("--no-bleed-receipt", type=Path)
    parser.add_argument("--layouts", type=Path)
    parser.add_argument("--skip-rendered", action="store_true")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    rom = args.rom.read_bytes()
    canonical_lut = rom[STAGE1_LUT_OFFSET : STAGE1_LUT_OFFSET + 256]
    if len(canonical_lut) != 256:
        raise ValueError("ROM does not contain the Stage 1 canonical LUT")
    established = []
    for root in args.transition_root:
        established.extend(load_transition_events(root))
    for event in established:
        event["plane"] = bytes(canonical_lut[tile] & 0x07 for tile in event["raw"])
    if args.skip_rendered:
        rendered = []
    else:
        if args.no_bleed_receipt is None or args.layouts is None:
            parser.error("--no-bleed-receipt and --layouts are required unless --skip-rendered")
        rendered = load_rendered_events(args.no_bleed_receipt, args.layouts, canonical_lut)
    observed = transitions(established) + transitions(rendered)
    semantic = [item for item in observed if item["semantic"]]
    if not semantic:
        raise ValueError("corpus has no semantic transitions")

    feature_names = [f"raw{offset}" for offset in range(PLANE_SIZE)] + list(EXTRA_FEATURES)
    deltas = np.frombuffer(
        b"".join(item["raw_delta"] + item["extra_delta"] for item in semantic),
        dtype=np.uint8,
    )
    deltas = deltas.reshape(len(semantic), len(feature_names))
    fixed = np.array([item["fixed_delta"] for item in semantic], dtype=np.uint8)

    raw_before_all = np.frombuffer(
        b"".join(item["raw_before"] for item in observed), dtype=np.uint8
    ).reshape(len(observed), PLANE_SIZE)
    raw_after_all = np.frombuffer(
        b"".join(item["raw_after"] for item in observed), dtype=np.uint8
    ).reshape(len(observed), PLANE_SIZE)
    phase_before = np.array(
        [(int(item["scy_before"]) + int(item["dc02_before"])) & 0xFF for item in observed],
        dtype=np.uint8,
    )
    phase_after = np.array(
        [(int(item["scy_after"]) + int(item["dc02_after"])) & 0xFF for item in observed],
        dtype=np.uint8,
    )
    phase_required = np.array(
        [
            bool(item["semantic"])
            or item["scy_before"] != item["scy_after"]
            or item["dc02_before"] != item["dc02_after"]
            for item in observed
        ],
        dtype=bool,
    )
    phase_candidates: list[dict[str, int]] = []
    for first in range(PLANE_SIZE - 1):
        key_before_first = np.bitwise_xor(phase_before, raw_before_all[:, first])
        key_after_first = np.bitwise_xor(phase_after, raw_after_all[:, first])
        for second in range(first + 1, PLANE_SIZE):
            key_before = np.bitwise_xor(key_before_first, raw_before_all[:, second])
            key_after = np.bitwise_xor(key_after_first, raw_after_all[:, second])
            changed = key_before != key_after
            if np.any(np.logical_and(phase_required, np.logical_not(changed))):
                continue
            phase_candidates.append(
                {
                    "first": first,
                    "second": second,
                    "extra_publications": int(np.count_nonzero(np.logical_and(changed, ~phase_required))),
                    "required_publications": int(np.count_nonzero(phase_required)),
                }
            )
    phase_candidates.sort(
        key=lambda item: (item["extra_publications"], item["first"], item["second"])
    )

    candidates: list[dict[str, object]] = []
    for first in range(len(feature_names) - 1):
        first_delta = deltas[:, first]
        for second in range(first + 1, len(feature_names)):
            key_delta = np.bitwise_xor(np.bitwise_xor(first_delta, deltas[:, second]), fixed)
            if np.any(key_delta == 0):
                continue
            false_positives = 0
            for item in observed:
                if item["semantic"]:
                    continue
                feature_delta = item["raw_delta"] + item["extra_delta"]
                if feature_delta[first] ^ feature_delta[second] ^ int(item["fixed_delta"]):
                    false_positives += 1
            candidates.append(
                {
                    "first": feature_names[first],
                    "second": feature_names[second],
                    "safe_false_positives": false_positives,
                }
            )

    key_width = 2
    if not candidates:
        # Exhaust the 128 features that participate in the most required
        # transitions. This deterministic fallback establishes whether one
        # additional packed-source sample can make the single-byte XOR safe.
        coverage = np.count_nonzero(deltas, axis=0)
        ranked = sorted(
            range(len(feature_names)), key=lambda index: (-int(coverage[index]), feature_names[index])
        )[:128]
        for first, second, third in itertools.combinations(ranked, 3):
            key_delta = np.bitwise_xor(
                np.bitwise_xor(np.bitwise_xor(deltas[:, first], deltas[:, second]), deltas[:, third]),
                fixed,
            )
            if np.any(key_delta == 0):
                continue
            false_positives = 0
            for item in observed:
                if item["semantic"]:
                    continue
                feature_delta = item["raw_delta"] + item["extra_delta"]
                if (
                    feature_delta[first]
                    ^ feature_delta[second]
                    ^ feature_delta[third]
                    ^ int(item["fixed_delta"])
                ):
                    false_positives += 1
            candidates.append(
                {
                    "first": feature_names[first],
                    "second": feature_names[second],
                    "third": feature_names[third],
                    "safe_false_positives": false_positives,
                }
            )
        key_width = 3
    candidates.sort(
        key=lambda item: (
            item["safe_false_positives"], item["first"], item["second"], item.get("third", "")
        )
    )
    production_delta = np.bitwise_xor(
        np.bitwise_xor(deltas[:, 27], deltas[:, 255]), fixed
    )
    production_collision_rows = production_delta == 0
    secondary_candidates: list[dict[str, object]] = []
    for feature, name in enumerate(feature_names):
        if np.any(deltas[production_collision_rows, feature] == 0):
            continue
        false_positives = 0
        for item in observed:
            if item["semantic"]:
                continue
            feature_delta = item["raw_delta"] + item["extra_delta"]
            production_changed = (
                item["raw_delta"][27]
                ^ item["raw_delta"][255]
                ^ int(item["fixed_delta"])
            )
            if production_changed or feature_delta[feature]:
                false_positives += 1
        secondary_candidates.append(
            {"feature": name, "safe_false_positives": false_positives}
        )
    if not secondary_candidates:
        for first in range(len(feature_names) - 1):
            first_delta = deltas[production_collision_rows, first]
            for second in range(first + 1, len(feature_names)):
                second_delta = np.bitwise_xor(
                    first_delta, deltas[production_collision_rows, second]
                )
                if np.any(second_delta == 0):
                    continue
                false_positives = 0
                for item in observed:
                    if item["semantic"]:
                        continue
                    feature_delta = item["raw_delta"] + item["extra_delta"]
                    production_changed = (
                        item["raw_delta"][27]
                        ^ item["raw_delta"][255]
                        ^ int(item["fixed_delta"])
                    )
                    secondary_changed = feature_delta[first] ^ feature_delta[second]
                    if production_changed or secondary_changed:
                        false_positives += 1
                secondary_candidates.append(
                    {
                        "feature": f"{feature_names[first]} ^ {feature_names[second]}",
                        "safe_false_positives": false_positives,
                    }
                )
    if not secondary_candidates:
        collision_items = [item for item in semantic if (
            item["raw_delta"][27] ^ item["raw_delta"][255] ^ int(item["fixed_delta"])
        ) == 0]
        for first in range(PLANE_SIZE - 1):
            for second in range(first + 1, PLANE_SIZE):
                if any(
                    (
                        (item["raw_after"][first] + item["raw_after"][second])
                        - (item["raw_before"][first] + item["raw_before"][second])
                    ) & 0xFF == 0
                    for item in collision_items
                ):
                    continue
                false_positives = 0
                for item in observed:
                    if item["semantic"]:
                        continue
                    production_changed = (
                        item["raw_delta"][27]
                        ^ item["raw_delta"][255]
                        ^ int(item["fixed_delta"])
                    )
                    secondary_changed = (
                        (item["raw_after"][first] + item["raw_after"][second])
                        - (item["raw_before"][first] + item["raw_before"][second])
                    ) & 0xFF
                    if production_changed or secondary_changed:
                        false_positives += 1
                secondary_candidates.append(
                    {
                        "feature": f"sum(raw{first}, raw{second})",
                        "safe_false_positives": false_positives,
                    }
                )
    secondary_candidates.sort(
        key=lambda item: (item["safe_false_positives"], item["feature"])
    )
    if not candidates and not secondary_candidates:
        collision_items = [item for item in semantic if (
            item["raw_delta"][27] ^ item["raw_delta"][255] ^ int(item["fixed_delta"])
        ) == 0]
        uncovered = set(range(len(collision_items)))
        greedy_samples: list[int] = []
        while uncovered:
            best = max(
                range(PLANE_SIZE),
                key=lambda offset: sum(
                    collision_items[index]["raw_before"][offset]
                    != collision_items[index]["raw_after"][offset]
                    for index in uncovered
                ),
            )
            covered = {
                index for index in uncovered
                if collision_items[index]["raw_before"][best]
                != collision_items[index]["raw_after"][best]
            }
            if not covered:
                break
            greedy_samples.append(best)
            uncovered -= covered
        print(
            "INFO: production collisions=", len(collision_items),
            " greedy direct-sample cover=", greedy_samples,
            " uncovered=", len(uncovered),
        )
        raise SystemExit("FAIL: neither XOR key nor two-byte production extension is collision-free")

    corpus_counts: dict[str, dict[str, int]] = {}
    for item in observed:
        name = str(item["corpus"])
        counts = corpus_counts.setdefault(name, {"transitions": 0, "semantic_transitions": 0})
        counts["transitions"] += 1
        counts["semantic_transitions"] += int(bool(item["semantic"]))

    output = {
        "schema": "penta-dragon-dx-stage1-semantic-key-search-v1",
        "status": "pass",
        "key_form": f"SCY ^ DC02 ^ {key_width} selected features",
        "transition_roots": [str(path.resolve()) for path in args.transition_root],
        "rom": str(args.rom.resolve()),
        "rom_sha256": sha256(args.rom),
        "canonical_lut_sha256": hashlib.sha256(canonical_lut).hexdigest(),
        "no_bleed_receipt": str(args.no_bleed_receipt.resolve()) if args.no_bleed_receipt else None,
        "no_bleed_receipt_sha256": sha256(args.no_bleed_receipt) if args.no_bleed_receipt else None,
        "layouts": str(args.layouts.resolve()) if args.layouts else None,
        "layouts_sha256": sha256(args.layouts) if args.layouts else None,
        "established_events": len(established),
        "rendered_events": len(rendered),
        "corpora": corpus_counts,
        "observed_transitions": len(observed),
        "semantic_transitions": len(semantic),
        "collision_free_candidates": len(candidates),
        "best_candidates": candidates[:32],
        "production_key_semantic_collisions": int(np.count_nonzero(production_collision_rows)),
        "collision_free_secondary_features": len(secondary_candidates),
        "best_secondary_features": secondary_candidates[:32],
        "phase_add_key_form": "(SCY + DC02) ^ raw[first] ^ raw[second]",
        "phase_collision_free_candidates": len(phase_candidates),
        "best_phase_candidates": phase_candidates[:32],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(output, indent=2) + "\n")
    print(f"PASS: {len(candidates)} collision-free XOR keys")
    if candidates:
        print(f"BEST XOR: {candidates[0]}")
    print(f"PASS: {len(secondary_candidates)} collision-free secondary features")
    if secondary_candidates:
        print(f"BEST SECONDARY: {secondary_candidates[0]}")
    print(f"PASS: {len(phase_candidates)} phase-safe additive candidates")
    if phase_candidates:
        print(f"BEST PHASE: {phase_candidates[0]}")
    print(f"Receipt: {args.output.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
