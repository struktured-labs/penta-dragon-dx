#!/usr/bin/env python3
"""Fail-closed static audit of the r264 Stage 4 room-$01 key collision.

The audit binds the exact r264 ROM, the exact archived every-frame Stage 4
layout trace, and the installed two-byte dungeon cache implementation.  It
does not launch an emulator or build/patch a ROM.  Scratch outputs are exact
raw/attribute planes plus a machine-readable receipt under repository-local
``tmp/``.
"""

from __future__ import annotations

import argparse
from collections import defaultdict
import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
RAW_SIZE = 24 * 24
R264_SHA256 = (
    "aa4c15602af5a1d0bf332c17de25fd2132d7fb45b327cc2d8d9bf25255dbf5a1"
)
TRACE_SHA256 = (
    "54becf276a33dc9f51cce123d39c8ce80f58be04f4b186a534c34ae2a672c90a"
)
RAW_A_SHA256 = (
    "16617ed35129ce24f6757899080481203a955db9dea045e1cab3b8c7b10706d6"
)
RAW_B_SHA256 = (
    "fe09ce2e85f1e7ed8352b6a0112c725c9620e9f0f8afcfc59516142559024a82"
)
PLANE_A_SHA256 = (
    "155fb16e076c9198dbac15bfb701ecd0dbdc268a29464edef5dd02df7a343dd9"
)
PLANE_B_SHA256 = (
    "9ea6c09fdcd274b0b12624fac854734fcaa869eccb131449c10b49298436517b"
)
CURRENT_A = (444, 149, 19, 251)
CURRENT_B = (0, 59, 333, 201)
SPECIAL_A = (1,)
SPECIAL_B = (357,)


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def xor_key(raw: bytes, offsets: tuple[int, ...]) -> int:
    result = 0
    for offset in offsets:
        result ^= raw[offset]
    return result


def stage4_plane(raw: bytes) -> bytes:
    lut = bytearray(256)
    for tile in range(0x01, 0x09):
        lut[tile] = 4
    lut[0x2D] = lut[0x2E] = 2
    return bytes(lut[tile] for tile in raw)


def parse_trace(path: Path) -> list[dict[str, object]]:
    rows = []
    for line_number, line in enumerate(path.read_text().splitlines(), 1):
        fields = line.split("\t")
        if len(fields) != 14:
            raise AssertionError(
                f"{path}:{line_number}: expected 14 fields, got {len(fields)}"
            )
        raw = bytes.fromhex(fields[13])
        if len(raw) != RAW_SIZE:
            raise AssertionError(
                f"{path}:{line_number}: expected {RAW_SIZE} raw bytes"
            )
        rows.append(
            {
                "line": line_number,
                "frame": int(fields[0]),
                "room": int(fields[1], 16),
                "active_map": int(fields[2], 16),
                "trace_signature_a": int(fields[3], 16),
                "trace_signature_b": int(fields[4], 16),
                # DF53-55 is the complete $9800 record.  The historical
                # trace's next field is DF56-58, so it contains only padding
                # plus the first two bytes of the $9C00 record (DF57-59).
                "cache_9800": bytes.fromhex(fields[5]),
                "cache_9c00_partial_df56_58": bytes.fromhex(fields[6]),
                "scx": int(fields[7], 16),
                "scy": int(fields[8], 16),
                "dc00_03": bytes.fromhex(fields[9]),
                "dc0b": int(fields[10], 16),
                "ffcf": int(fields[11], 16),
                "ffe8_eb": bytes.fromhex(fields[12]),
                "raw": raw,
                "raw_sha256": sha256(raw),
                "plane": stage4_plane(raw),
                "plane_sha256": sha256(stage4_plane(raw)),
            }
        )
    return rows


def key_metrics(
    rows: list[dict[str, object]],
    samples_a: tuple[int, ...],
    samples_b: tuple[int, ...],
) -> tuple[int, int, int]:
    unique: dict[tuple[int, bytes], bytes] = {}
    for row in rows:
        unique[(int(row["room"]), bytes(row["raw"]))] = bytes(row["plane"])
    semantics_by_key: dict[tuple[int, int, int], set[bytes]] = defaultdict(set)
    keys_by_semantic: dict[tuple[int, bytes], set[tuple[int, int, int]]] = (
        defaultdict(set)
    )
    for (room, raw), plane in unique.items():
        key = (room, xor_key(raw, samples_a), xor_key(raw, samples_b))
        semantics_by_key[key].add(plane)
        keys_by_semantic[(room, plane)].add(key)
    collisions = sum(len(values) - 1 for values in semantics_by_key.values())
    false_variants = sum(len(values) - 1 for values in keys_by_semantic.values())
    return collisions, false_variants, len(unique)


def row_summary(row: dict[str, object]) -> dict[str, object]:
    return {
        "line": row["line"],
        "frame": row["frame"],
        "room": f"${int(row['room']):02X}",
        "active_map": f"${int(row['active_map']):04X}",
        "scx": f"${int(row['scx']):02X}",
        "scy": f"${int(row['scy']):02X}",
        "raw_sha256": row["raw_sha256"],
        "plane_sha256": row["plane_sha256"],
        "computed_key": [
            f"${xor_key(bytes(row['raw']), CURRENT_A):02X}",
            f"${xor_key(bytes(row['raw']), CURRENT_B):02X}",
            f"${int(row['room']):02X}",
        ],
        "cache_9800_df53_55": bytes(row["cache_9800"]).hex().upper(),
        "cache_9c00_partial_df56_58": bytes(
            row["cache_9c00_partial_df56_58"]
        ).hex().upper(),
    }


def audit(base: bytes, trace_path: Path, scan_root: Path, out: Path) -> dict:
    if sha256(base) != R264_SHA256:
        raise AssertionError("base is not exact r264 aa4c1560")
    if sha256(trace_path.read_bytes()) != TRACE_SHA256:
        raise AssertionError("canonical Stage 4 trace preimage changed")

    rows = parse_trace(trace_path)
    selected = {
        row["raw_sha256"]: row
        for row in rows
        if row["raw_sha256"] in (RAW_A_SHA256, RAW_B_SHA256)
    }
    if set(selected) != {RAW_A_SHA256, RAW_B_SHA256}:
        raise AssertionError("canonical trace no longer contains both collision raws")
    raw_a = bytes(selected[RAW_A_SHA256]["raw"])
    raw_b = bytes(selected[RAW_B_SHA256]["raw"])
    plane_a = stage4_plane(raw_a)
    plane_b = stage4_plane(raw_b)
    if sha256(plane_a) != PLANE_A_SHA256 or sha256(plane_b) != PLANE_B_SHA256:
        raise AssertionError("Stage 4 semantic planes changed")

    occurrences = [
        row for row in rows if row["raw_sha256"] in (RAW_A_SHA256, RAW_B_SHA256)
    ]
    a_occurrences = [row for row in occurrences if row["raw_sha256"] == RAW_A_SHA256]
    b_occurrences = [row for row in occurrences if row["raw_sha256"] == RAW_B_SHA256]
    if len(a_occurrences) != 1:
        raise AssertionError("expected exactly one ephemeral A occurrence")
    first_a = a_occurrences[0]
    immediate_b = next(
        row
        for row in b_occurrences
        if int(row["line"]) == int(first_a["line"]) + 1
    )
    if not (
        first_a["frame"] == 131
        and immediate_b["frame"] == 132
        and first_a["active_map"] == immediate_b["active_map"] == 0x9800
    ):
        raise AssertionError("expected consecutive frame-131/132 $9800 pair")

    raw_diffs = []
    attr_diffs = []
    first_col = int(first_a["scx"]) // 8
    first_row = int(first_a["scy"]) // 8
    visible_cols = 20 if int(first_a["scx"]) % 8 == 0 else 21
    visible_rows = 18 if int(first_a["scy"]) % 8 == 0 else 19
    for offset, (tile_a, tile_b, attr_a, attr_b) in enumerate(
        zip(raw_a, raw_b, plane_a, plane_b)
    ):
        if tile_a != tile_b:
            raw_diffs.append(offset)
        if attr_a == attr_b:
            continue
        row, col = divmod(offset, 24)
        visible = (
            first_col <= col < first_col + visible_cols
            and first_row <= row < first_row + visible_rows
        )
        attr_diffs.append(
            {
                "offset": offset,
                "row": row,
                "column": col,
                "tile_a": f"${tile_a:02X}",
                "tile_b": f"${tile_b:02X}",
                "attr_a": attr_a,
                "attr_b": attr_b,
                "vram_9800": f"${0x9800 + row * 32 + col:04X}",
                "vram_9c00": f"${0x9C00 + row * 32 + col:04X}",
                "visible_at_frame_131_132": visible,
                "screen_cell": (
                    [col - first_col, row - first_row] if visible else None
                ),
            }
        )

    current = key_metrics(rows, CURRENT_A, CURRENT_B)
    special = key_metrics(rows, SPECIAL_A, SPECIAL_B)
    append_357 = key_metrics(rows, CURRENT_A, CURRENT_B + (357,))
    replace_201 = key_metrics(rows, CURRENT_A, (0, 59, 333, 357))
    if current[:2] != (1, 0) or special[:2] != (0, 0):
        raise AssertionError("collision/key metrics changed")

    # Prove two raw samples are minimal on this corpus: no one-cell key is
    # collision-free and variant-free; record the total number of valid
    # unordered two-cell pairs as an additional deterministic cross-check.
    single_safe = []
    pair_safe_count = 0
    for offset in range(RAW_SIZE):
        if key_metrics(rows, (), (offset,))[:2] == (0, 0):
            single_safe.append(offset)
    for offset_a in range(RAW_SIZE):
        for offset_b in range(offset_a + 1, RAW_SIZE):
            if key_metrics(rows, (offset_a,), (offset_b,))[:2] == (0, 0):
                pair_safe_count += 1
    if single_safe or pair_safe_count != 667:
        raise AssertionError("minimal-key exhaustive result changed")

    # Historical trace schema can fully verify only the $9800 record.  It
    # shows why the collision is a fail-closed risk rather than proof that a
    # stale hit actually occurred: both colliding samples saw the older
    # $01/$34/$01 cache; $01/$40/$01 first appeared after B had stabilized.
    collision_key_bytes = bytes((0x01, 0x40, 0x01))
    first_cache_match = next(
        row for row in rows if bytes(row["cache_9800"]) == collision_key_bytes
    )
    if bytes(first_a["cache_9800"]) == collision_key_bytes:
        raise AssertionError("A unexpectedly observed a matching live cache")
    if bytes(immediate_b["cache_9800"]) == collision_key_bytes:
        raise AssertionError("immediate B unexpectedly observed a matching live cache")
    if first_cache_match["frame"] != 136:
        raise AssertionError("first $9800 collision-key cache match moved")

    all_trace_occurrences = []
    for path in sorted(scan_root.glob("**/stage4.layout-events.tsv")):
        for line_number, line in enumerate(path.read_text().splitlines(), 1):
            fields = line.split("\t")
            if len(fields) != 14:
                continue
            try:
                raw = bytes.fromhex(fields[-1])
            except ValueError:
                continue
            if len(raw) != RAW_SIZE:
                continue
            digest = sha256(raw)
            if digest not in (RAW_A_SHA256, RAW_B_SHA256):
                continue
            all_trace_occurrences.append(
                {
                    "path": str(path.relative_to(ROOT)),
                    "trace_sha256": sha256(path.read_bytes()),
                    "line": line_number,
                    "frame": int(fields[0]),
                    "room": f"${int(fields[1], 16):02X}",
                    "active_map": f"${int(fields[2], 16):04X}",
                    "layout": "A" if digest == RAW_A_SHA256 else "B",
                }
            )

    artifacts = {
        "layout_a_raw": out / "layout-a.raw.bin",
        "layout_b_raw": out / "layout-b.raw.bin",
        "layout_a_attr": out / "layout-a.attr.bin",
        "layout_b_attr": out / "layout-b.attr.bin",
    }
    out.mkdir(parents=True, exist_ok=True)
    artifacts["layout_a_raw"].write_bytes(raw_a)
    artifacts["layout_b_raw"].write_bytes(raw_b)
    artifacts["layout_a_attr"].write_bytes(plane_a)
    artifacts["layout_b_attr"].write_bytes(plane_b)

    return {
        "schema": "penta-stage4-room01-collision-r264-v1",
        "status": "FAIL_KEYSPACE_COLLISION_RUNTIME_STALE_NOT_OBSERVED",
        "emulator_invoked": False,
        "rom_written": False,
        "base": {"path": "tmp/stage1-menu-hidden-repair-r264/candidate.gb", "sha256": R264_SHA256},
        "canonical_trace": {
            "path": str(trace_path.relative_to(ROOT)),
            "sha256": TRACE_SHA256,
            "rows": len(rows),
            "unique_room_raw_records": current[2],
        },
        "collision": {
            "room": "$01",
            "key": ["$01", "$40", "$01"],
            "layout_a": {
                "raw_sha256": RAW_A_SHA256,
                "attr_sha256": PLANE_A_SHA256,
                "palette_counts": {"0": plane_a.count(0), "4": plane_a.count(4)},
                "first_occurrence": row_summary(first_a),
            },
            "layout_b": {
                "raw_sha256": RAW_B_SHA256,
                "attr_sha256": PLANE_B_SHA256,
                "palette_counts": {"0": plane_b.count(0), "4": plane_b.count(4)},
                "immediate_occurrence": row_summary(immediate_b),
            },
            "raw_cells_changed": len(raw_diffs),
            "raw_changed_offsets": raw_diffs,
            "attribute_cells_changed": len(attr_diffs),
            "attribute_cells_visible_at_transition": sum(
                bool(item["visible_at_frame_131_132"]) for item in attr_diffs
            ),
            "attribute_differences": attr_diffs,
        },
        "trace_order": {
            "same_physical_map_consecutive": True,
            "sequence": [row_summary(first_a), row_summary(immediate_b)],
            "layout_a_occurrences_in_canonical_trace": len(a_occurrences),
            "layout_b_occurrences_in_canonical_trace": len(b_occurrences),
            "first_9800_cache_match_for_collision_key": row_summary(first_cache_match),
            "cache_evidence": (
                "Frames 131 and 132 both carry $9800 cache $01/$34/$01, not "
                "$01/$40/$01. The latter first appears at sampled frame 136, "
                "after layout B is stable. The trace therefore does not prove "
                "an actual stale cache hit."
            ),
            "historical_9c00_limitation": (
                "The schema recorded DF56-58, but the $9C00 record is DF57-59; "
                "its room byte is absent, so no exact three-byte $9C00 hit claim is made."
            ),
        },
        "potential_visible_failure": {
            "direction_observed": "A -> B",
            "if_a_plane_were_cached": (
                "28 cells that changed from neutral BG0 to Stage4 floor BG4 "
                "would retain stale BG0; 26 are in the active 21x18 viewport."
            ),
            "reverse_direction": (
                "B -> A would leave BG4 on 28 neutral cells (palette bleed)."
            ),
            "runtime_failure_observed_in_this_trace": False,
            "fail_closed_reason": (
                "The key aliases two visibly different desired planes and both "
                "raws occur consecutively on one physical map. Absence of a "
                "matching cache pre-state in this run is not a correctness proof."
            ),
        },
        "all_existing_trace_occurrences": {
            "scan_root": str(scan_root.relative_to(ROOT)),
            "layout_a_count": sum(x["layout"] == "A" for x in all_trace_occurrences),
            "layout_b_count": sum(x["layout"] == "B" for x in all_trace_occurrences),
            "records": all_trace_occurrences,
        },
        "key_design": {
            "current": {
                "a": list(CURRENT_A),
                "b": list(CURRENT_B),
                "collisions": current[0],
                "false_variants": current[1],
            },
            "minimal_stage4_specialization": {
                "a": list(SPECIAL_A),
                "b": list(SPECIAL_B),
                "addresses": ["$C1A1", "$C305"],
                "collisions": special[0],
                "false_variants": special[1],
                "single_sample_solution_count": len(single_safe),
                "two_sample_solution_count": pair_safe_count,
                "saved_signature_bytes": 24,
                "saved_signature_t_cycles_per_decision": 120,
                "scope": "exact canonical 8,000-frame Stage 4 corpus only",
            },
            "smallest_correctness_addition": {
                "operation": "append raw offset 357 ($C305) to signature B",
                "collisions": append_357[0],
                "false_variants": append_357[1],
                "cost": "+4 runtime bytes and +20 T-cycles per shared decision",
                "blocked": True,
                "why": (
                    "The exact runtime has only one padding byte before DAB9, "
                    "and a shared addition touches Stages 2/5/7."
                ),
            },
            "same_size_substitution": {
                "operation": "replace B offset 201 with 357",
                "canonical_stage4_collisions": replace_201[0],
                "canonical_stage4_false_variants": replace_201[1],
                "qualified": False,
                "why": (
                    "Offset 201 was added to remove six collisions in the wider "
                    "every-frame corpus; Stage4-only evidence cannot prove a "
                    "shared substitution safe."
                ),
            },
        },
        "ffe0_safe_specialization_assessment": {
            "design": (
                "Route normalized Stage4 identity A=$02 before XOR A; the Stage4 "
                "stub must execute XOR A / LDH [$E0],A before its 1+1 key. Every "
                "generic arm retains the same explicit zero write; dirty arms "
                "retain the later value-one write."
            ),
            "ffe0_touched_by_stage_identity": False,
            "semantic_isolation_possible": True,
            "strict_other_stage_cycle_isolation_possible_from_current_layout": False,
            "blocker": (
                "DA60 has one free byte and DAB9-DAD6 is a packed 30-byte "
                "dispatcher. Distinguishing A=$02 and then clearing A costs at "
                "least 4 extra T-cycles on another nonzero dungeon arm unless "
                "an upstream Stage4-exclusive entry is proven. No such entry is "
                "established by the static receipts."
            ),
            "stage4_speed_outlook": (
                "The 1+1 key removes six LD HL,nn / XOR [HL] pairs (120 T-cycles). "
                "Even after an explicit FFE0-safe route, the prior static bound "
                "is about 72 T-cycles net saved, plausibly enough for the single "
                "missing 757th loop, but emulator measurement is required."
            ),
            "candidate_emitted": False,
            "verdict": "BLOCKED_PENDING_STAGE4_EXCLUSIVE_ROUTE_OR_CYCLE_COMPROMISE",
        },
        "artifacts": {
            name: {
                "path": str(path.relative_to(ROOT)),
                "sha256": sha256(path.read_bytes()),
                "bytes": path.stat().st_size,
            }
            for name, path in artifacts.items()
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--base",
        type=Path,
        default=ROOT / "tmp/stage1-menu-hidden-repair-r264/candidate.gb",
    )
    parser.add_argument(
        "--trace",
        type=Path,
        default=(
            ROOT
            / "tmp/stage2-isolated-entry-r263/stage346-semantic-soak-8000/"
            "stage4.layout-events.tsv"
        ),
    )
    parser.add_argument("--scan-root", type=Path, default=ROOT / "tmp")
    parser.add_argument(
        "--out",
        type=Path,
        default=ROOT / "tmp/stage4-room01-collision-r264",
    )
    args = parser.parse_args()
    receipt = audit(args.base.read_bytes(), args.trace, args.scan_root, args.out)
    receipt_path = args.out / "receipt.json"
    receipt_path.write_text(json.dumps(receipt, indent=2) + "\n")
    print(json.dumps(receipt, indent=2))
    # This is deliberately a failing gate: the collision is real even though
    # the archived run did not establish the matching stale-cache pre-state.
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
