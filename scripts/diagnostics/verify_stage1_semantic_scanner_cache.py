#!/usr/bin/env python3
"""Reproduce the rejected Stage-1 ordinary-room scanner experiment.

The optimized path may bypass the 24-row hazard scanner only in exact live
scene $02, room $03. Every captured source in that class must have an empty
scanner contract. Gargoyle scene $0A and every other room remain scanner-owned.
The installed ROM is also inspected so a repair-needed bypass cannot omit
$55C0, while a proven zero-effect path must pop the saved HL before its direct
exit. Synthetic nonempty and repair-needed room-$03 records are required
negative controls.

This verifier is historical diagnostic coverage, not a production qualifier.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path


PLANE_SIZE = 24 * 24
BANK_SIZE = 0x4000


def is_tooth(tile: int) -> bool:
    """Match the ROM's ``(tile & $EF) - $64 < 6`` classifier."""
    return (((tile & 0xEF) - 0x64) & 0xFF) < 6


def scanner_output(source: bytes, dc0e: int) -> tuple[object, ...]:
    """Return the conservative source-span contract stamped by the scanner."""
    if len(source) != PLANE_SIZE:
        raise ValueError(f"expected {PLANE_SIZE} source bytes")
    output: list[object] = []
    for row in range(24):
        cells = source[row * 24:(row + 1) * 24]
        if is_tooth(cells[0]):
            start, width = 0, 9 + 2 * (dc0e & 1)
        elif is_tooth(cells[1]):
            start, width = 0, 11
        elif is_tooth(cells[2]):
            start, width = 0, 15
        elif cells[4] == 0x6A or is_tooth(cells[4]) or is_tooth(cells[5]):
            start, width = 4, 11
        elif is_tooth(cells[6]):
            start, width = 4, 10
        else:
            continue
        output.append((row, start, width, cells[start:start + width].hex()))
    return tuple(output)


def load_layout_directory(directory: Path) -> list[dict[str, object]]:
    events_path = directory / "low-health.layout-events.tsv"
    layouts_path = directory / "low-health.layouts.bin"
    layouts = layouts_path.read_bytes()
    if len(layouts) % PLANE_SIZE:
        raise ValueError(f"{layouts_path}: partial packed layout")
    with events_path.open(newline="") as handle:
        events = list(csv.DictReader(handle, delimiter="\t"))
    count = len(layouts) // PLANE_SIZE
    if len(events) < count:
        raise ValueError(f"{events_path}: {len(events)} events for {count} layouts")
    records = []
    for index, event in enumerate(events[:count]):
        source = layouts[index * PLANE_SIZE:(index + 1) * PLANE_SIZE]
        dc0e = int(event["dc0e"])
        records.append({
            "origin": f"{directory}:{index}",
            "destination": int(event["destination"]) << 8,
            "scy": int(event["scy"]),
            "dc02": int(event["dc02"]),
            "dc0e": dc0e,
            "room": int(event["room"]),
            # These probes are live Stage 1. Exact Gargoyle scene probes are
            # independently represented by transition traces below.
            "scene": 0x02,
            "source": source,
            "output": scanner_output(source, dc0e),
        })
    return records


def load_transition_trace(path: Path) -> list[dict[str, object]]:
    records = []
    with path.open(newline="") as handle:
        for index, event in enumerate(csv.DictReader(handle, delimiter="\t")):
            source = bytes.fromhex(event["raw"])
            output0 = scanner_output(source, 0)
            if output0 != scanner_output(source, 1):
                raise ValueError(f"{path}:{index}: DC0E required but absent")
            records.append({
                "origin": f"{path}:{index}",
                "destination": int(event["destination"], 16),
                "scy": int(event["scy"], 16),
                "dc02": int(event["dc02"], 16),
                "dc0e": 0,
                "room": int(event["room"], 16),
                "scene": int(event["scene"], 16),
                "source": source,
                "output": output0,
            })
    return records


def bypasses(record: dict[str, object]) -> bool:
    return int(record["scene"]) == 0x02 and int(record["room"]) == 0x03


def transition_repair_writes(record: dict[str, object]) -> int:
    """Model the exact bounded writes reachable from fixed:$55C0."""
    source = record["source"]
    assert isinstance(source, bytes)
    writes = 4 if int(record["room"]) == 0x12 else 0
    # C321 = packed row $10 / column 1; Carry publishes the neutral pair.
    writes += 2 if is_tooth(source[0x181]) else 0
    # C35A = packed row $12 / column 10; $01 and teeth publish one cell.
    writes += int(source[0x1BA] == 0x01 or is_tooth(source[0x1BA]))
    return writes


def direct_exits(record: dict[str, object]) -> bool:
    return bypasses(record) and transition_repair_writes(record) == 0


def assess_gate(records: list[dict[str, object]]) -> dict[str, object]:
    bypassed = [record for record in records if bypasses(record)]
    unsafe = [record for record in bypassed if tuple(record["output"])]
    direct = [record for record in bypassed if direct_exits(record)]
    repaired = [record for record in bypassed if not direct_exits(record)]
    return {
        "records": len(records),
        "distinct_outputs": len({tuple(record["output"]) for record in records}),
        "bypassed_records": len(bypassed),
        "unsafe_bypassed_records": len(unsafe),
        "direct_exit_records": len(direct),
        "repair_routed_records": len(repaired),
        "direct_exit_repair_writes": sum(
            transition_repair_writes(record) for record in direct
        ),
        "first_unsafe_origins": [str(record["origin"]) for record in unsafe[:8]],
        "gargoyle_records_bypassed": sum(
            bypasses(record) and int(record["scene"]) == 0x0A
            for record in records
        ),
    }


def negative_control(records: list[dict[str, object]]) -> dict[str, object]:
    source = next((record for record in records if bypasses(record)), None)
    if source is None:
        raise ValueError("corpus contains no scene-$02/room-$03 record")
    mutated = dict(source)
    mutated["origin"] = "synthetic:forced-nonempty-room03"
    mutated["output"] = ((0, 0, 1, "64"),)
    result = assess_gate([*records, mutated])
    return {
        "mutation": "force one bypassed output nonempty",
        "unsafe_bypassed_records": result["unsafe_bypassed_records"],
        "gate_rejects": result["unsafe_bypassed_records"] > 0,
    }


def repair_negative_control(records: list[dict[str, object]]) -> dict[str, object]:
    source = next((record for record in records if direct_exits(record)), None)
    if source is None:
        raise ValueError("corpus contains no direct-exit room-$03 record")
    mutated = dict(source)
    raw = bytearray(source["source"])
    raw[0x1BA] = 0x01
    mutated["source"] = bytes(raw)
    writes = transition_repair_writes(mutated)
    return {
        "mutation": "force source[$1BA]=$01 in direct-exit room03 record",
        "scanner_still_bypassed": bypasses(mutated),
        "transition_repair_writes": writes,
        "direct_exit_rejected": not direct_exits(mutated),
        "routes_55c0": bypasses(mutated) and not direct_exits(mutated),
    }


def speed_projection(path: Path) -> dict[str, object]:
    rows = []
    for index, line in enumerate(path.read_text().splitlines()):
        columns = line.split("\t")
        if len(columns) < 30:
            raise ValueError(f"{path}:{index + 1}: short speed trace row")
        source = bytes.fromhex(columns[-1])
        rows.append({
            "scene": 0x02,
            "room": int(columns[3], 16),
            "source": source,
            "output": scanner_output(source, 0),
        })
    skipped = sum(bypasses(row) for row in rows)
    direct = sum(direct_exits(row) for row in rows)
    return {
        "records": len(rows),
        "bypassed_scans": skipped,
        "direct_exits": direct,
        "bypass_fraction": skipped / len(rows) if rows else 0.0,
        "expected_records": 264,
        "expected_bypassed_scans": 263,
        "expected_direct_exits": 263,
    }


def inspect_rom(path: Path) -> dict[str, object]:
    rom = path.read_bytes()
    if len(rom) != 32 * BANK_SIZE:
        raise ValueError(f"{path}: expected 512 KiB ROM")
    base = 19 * BANK_SIZE - 0x4000
    hook = rom[base + 0x6BE3:base + 0x6BED]
    dispatcher = rom[base + 0x6DB5:base + 0x6DC9]
    first_classifier = rom[base + 0x61A0:base + 0x61AF]
    decision = rom[base + 0x6D9E:base + 0x6DAF]
    second_classifier = rom[base + 0x6CEF:base + 0x6CFC]
    expected_hook = bytes.fromhex("F3 AF E0 4F C3 B5 6D 00 00 00")
    expected_dispatcher_long = bytes.fromhex(
        "CB 58 20 07 F0 BD FE 03 CA 9E 6D "
        "CD B7 61 C3 50 6C 00 00 00"
    )
    # $6D9E is 34 bytes behind the end of the three-byte conditional JP, so
    # the width-preserving JR form is exactly equivalent and four clocks
    # faster on the admitted room-$03 arm.  Accept no other encoding.
    expected_dispatcher_short = bytes.fromhex(
        "CB 58 20 07 F0 BD FE 03 28 DE 00 "
        "CD B7 61 C3 50 6C 00 00 00"
    )
    expected_first = bytes.fromhex(
        "FA 21 C3 CD 88 6C C9 CD C0 55 C3 50 6C 00 00"
    )
    expected_decision = bytes.fromhex(
        "CD A0 61 DA A7 61 CD EF 6C DA A7 61 E1 C3 50 6C 00"
    )
    expected_second = bytes.fromhex(
        "FA 5A C3 FE 01 37 C8 CD 88 6C C9 00 00"
    )
    return {
        "sha256": hashlib.sha256(rom).hexdigest(),
        "hook_exact": hook == expected_hook,
        "dispatcher_exact": dispatcher in {
            expected_dispatcher_long,
            expected_dispatcher_short,
        },
        "dispatcher_variant": (
            "jr-z-fast" if dispatcher == expected_dispatcher_short
            else "jp-z-reference" if dispatcher == expected_dispatcher_long
            else "unknown"
        ),
        "first_classifier_exact": first_classifier == expected_first,
        "decision_exact": decision == expected_decision,
        "second_classifier_exact": second_classifier == expected_second,
        "repair_leaf_calls_55c0": first_classifier[7:10] == bytes.fromhex(
            "CD C0 55"
        ),
        "direct_exit_pops_saved_hl": bytes.fromhex("E1 C3 50 6C") in decision,
        "non_bypass_calls_61b7": bytes.fromhex("CD B7 61") in dispatcher,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--layout-dir", type=Path, action="append", default=[])
    parser.add_argument("--transition-trace", type=Path, action="append", default=[])
    parser.add_argument("--speed-trace", type=Path, required=True)
    parser.add_argument("--rom", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    records: list[dict[str, object]] = []
    corpus_hash = hashlib.sha256()
    for directory in args.layout_dir:
        records.extend(load_layout_directory(directory))
        corpus_hash.update((directory / "low-health.layouts.bin").read_bytes())
        corpus_hash.update((directory / "low-health.layout-events.tsv").read_bytes())
    for trace in args.transition_trace:
        records.extend(load_transition_trace(trace))
        corpus_hash.update(trace.read_bytes())
    if not records:
        raise SystemExit("no scanner corpus supplied")

    candidate = assess_gate(records)
    negative = negative_control(records)
    repair_negative = repair_negative_control(records)
    projection = speed_projection(args.speed_trace)
    rom_contract = inspect_rom(args.rom)
    passed = (
        candidate["records"] == 2182
        and candidate["distinct_outputs"] == 57
        and candidate["bypassed_records"] == 124
        and candidate["unsafe_bypassed_records"] == 0
        and candidate["direct_exit_records"] == 50
        and candidate["repair_routed_records"] == 74
        and candidate["direct_exit_repair_writes"] == 0
        and candidate["gargoyle_records_bypassed"] == 0
        and negative["gate_rejects"]
        and repair_negative["direct_exit_rejected"]
        and repair_negative["routes_55c0"]
        and projection["records"] == projection["expected_records"]
        and projection["bypassed_scans"] == projection["expected_bypassed_scans"]
        and projection["direct_exits"] == projection["expected_direct_exits"]
        and all(
            value for key, value in rom_contract.items()
            if key not in {"sha256", "dispatcher_variant"}
        )
    )
    receipt = {
        "schema": "penta-stage1-ordinary-room-scanner-bypass-v1",
        "status": "pass" if passed else "fail",
        "corpus_sha256": corpus_hash.hexdigest(),
        "policy": {
            "bypass_only": {"scene": "02", "room": "03"},
            "all_other_scene_room_pairs_scan": True,
            "repair-needed_bypass_must_call_transition_repair_55C0": True,
            "zero-effect_bypass_must_pop_saved_hl_before_exit": True,
        },
        "candidate": candidate,
        "forced_nonempty_negative_control": negative,
        "forced_repair_negative_control": repair_negative,
        "speed_projection": projection,
        "rom_contract": rom_contract,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(receipt, indent=2) + "\n")
    print(("PASS" if passed else "FAIL") + ": Stage-1 room-$03 scanner bypass")
    print(f"Receipt: {args.output.resolve()}")
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
