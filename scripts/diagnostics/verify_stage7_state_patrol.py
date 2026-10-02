#!/usr/bin/env python3
"""Verify Stage-7 movement speed over deterministic equal world-space work.

The ordinary speed matrix's frame-keyed patrol is intentionally retained for
general diagnostics, but it cannot compare Stage 7 fairly: a small renderer
phase difference changes which direction the game consumes at a host-frame
boundary. This gate drives both ROMs from world position instead. It requires
the same alternating X endpoints and rooms, exact native input chaining,
bounded convergence to the same stable Y, deterministic A/B traces, and a
strict +/-2% elapsed-frame ratio over matched, uncontested post-settle legs.

Stage 7 contains a phase-sensitive enemy contact that can stop horizontal
motion for about fifteen extra logical loops. Renderer timing changes which
leg contains that contact even when the route and free locomotion cadence are
unchanged. The gate therefore records the complete route but measures only
leg ordinals for which all four traces reach the next 60-pixel endpoint in at
most 20 native main-loop iterations. A candidate that is generally too slow
cannot disappear through this filter: at least the configured number of
common uncontested legs must remain.

Equal-start, combined-seed policy (schema v3). One native boot of each ROM
reaches different Stage-7 world states (the title/boot timing of each build
changes the RNG cursor and the entity tables), so a single native comparison
mostly measured layout luck. The gate therefore first captures the stock
ROM's start-of-play world image (D800-D8FF, DC00-DCFF, FFCB, FFD4-FFD5) and
then replays both ROMs from that identical image under a fixed set of RNG
cursor seeds (FFD1). Even from equal starts, per-seed ratios stay noisy
(about +/-3%; byte-identical gameplay code measured 0.940 vs 0.991 on one
seed) because frame-driven state and sub-frame phase diverge once DX
spends more of each frame in VBlank. The pass condition is therefore the
combined ratio of stock to DX frames summed over every common uncontested
leg of every usable seed, with an explicit owner-approved Stage-7 floor of
0.97 (DX spends about 2.3% more of each frame in its VBlank handler; see
docs/audit/release-lock-20261001-repin.md). A seed is usable when its four
traces keep the exact endpoint route and settle in time; at least
MIN_USABLE_SEEDS seeds and MIN_COMBINED_LEGS legs must remain, so a
candidate cannot pass by diverging out of the measurement.
"""

from __future__ import annotations

import argparse
import copy
import csv
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
MATRIX = ROOT / "scripts/diagnostics/verify_stage_speed_matrix.py"
BASE_PROBE = ROOT / "scripts/diagnostics/probe_stage_speed.lua"
STATE_PROBE = ROOT / "scripts/diagnostics/probe_stage7_state_patrol.lua"
ORIGINAL = ROOT / "rom/Penta Dragon (J).gb"
HEADER = [
    "ordinal", "loop", "frame", "consumed", "planned",
    "half_cycles", "room", "x", "y",
]
DECIMAL_FIELDS = {"ordinal", "loop", "frame", "half_cycles", "x", "y"}
HEX_FIELDS = {"consumed", "planned", "room"}
EXPECTED_SETTLED_Y = 1648
MAX_UNCONTESTED_LOOP_DELTA = 20
SEEDS = (0, 10, 20, 30, 50, 60, 70, 80, 90)
COMBINED_FLOOR = 0.97
COMBINED_CEILING = 1.02
MIN_USABLE_SEEDS = 7
MIN_COMBINED_LEGS = 120
# D800-D8FF + DC00-DCFF + FFCB + FFD4-FFD5, in probe WORLD_RANGES order.
WORLD_IMAGE_SIZE = 0x100 + 0x100 + 1 + 2
SCHEMA = "penta-stage7-state-patrol-v3"
CLASSIFICATION = "EQUAL_START_WORLD_COMBINED_SEEDS_FLOOR_97"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def normalize_rows(
    rows: list[dict[str, int]], expected_hits: int, label: str
) -> tuple[list[dict[str, int]], int]:
    require(bool(rows), f"{label}: empty owned trace")
    require(rows[0]["loop"] == 1, f"{label}: first logical loop is not 1")
    require(
        rows[-1]["loop"] == expected_hits,
        f"{label}: terminal loop {rows[-1]['loop']} != {expected_hits}",
    )
    logical: list[dict[str, int]] = []
    duplicates = 0
    for row in rows:
        if logical and row["loop"] == logical[-1]["loop"]:
            current = {key: value for key, value in row.items() if key != "ordinal"}
            previous = {
                key: value for key, value in logical[-1].items()
                if key != "ordinal"
            }
            require(
                current == previous,
                f"{label}: disagreeing duplicate at loop {row['loop']}",
            )
            duplicates += 1
            continue
        logical.append(row)
    validate_rows(logical, expected_hits, label)
    return logical, duplicates


def validate_rows(rows: list[dict[str, int]], expected_hits: int, label: str) -> None:
    require(bool(rows), f"{label}: empty trace")
    require(rows[-1]["loop"] == expected_hits, f"{label}: missing terminal row")
    previous: dict[str, int] | None = None
    for index, row in enumerate(rows, 1):
        require(row["loop"] > 0, f"{label}: non-positive loop at row {index}")
        require(row["frame"] >= 0, f"{label}: negative frame at row {index}")
        if previous is None:
            require(row["consumed"] == 0, f"{label}: first input is not neutral")
            require(row["half_cycles"] == 0, f"{label}: starts after endpoint")
        else:
            require(row["loop"] > previous["loop"],
                    f"{label}: loop did not advance at row {index}")
            require(row["frame"] >= previous["frame"],
                    f"{label}: frame regressed at row {index}")
            require(row["consumed"] == previous["planned"],
                    f"{label}: consumed/planned chain broke at row {index}")
            delta = row["half_cycles"] - previous["half_cycles"]
            require(delta in (0, 1),
                    f"{label}: half-cycle changed by {delta} at row {index}")

        previous_half = previous["half_cycles"] if previous else 0
        endpoint = row["half_cycles"] == previous_half + 1
        half_cycle = row["half_cycles"]
        expected_consumed = 0x10 if half_cycle % 2 else 0x20
        expected_planned = 0x20 if half_cycle % 2 else 0x10
        if endpoint:
            require(row["consumed"] == expected_consumed,
                    f"{label}: wrong consumed direction at endpoint {half_cycle}")
            require(row["planned"] == expected_planned,
                    f"{label}: no reversal at endpoint {half_cycle}")
            require(row["x"] == (152 if half_cycle % 2 else 92),
                    f"{label}: wrong X at endpoint {half_cycle}")
            require(row["room"] == (3 if half_cycle % 2 else 7),
                    f"{label}: wrong room at endpoint {half_cycle}")
        elif half_cycle > 0:
            require(row["planned"] == expected_planned,
                    f"{label}: direction changed away from endpoint")
        previous = row


def endpoint_events(rows: list[dict[str, int]]) -> list[dict[str, int]]:
    events: list[dict[str, int]] = []
    previous = 0
    for row in rows:
        if row["half_cycles"] == previous + 1:
            events.append(dict(row))
            previous += 1
    return events


def parse_trace(path: Path, result_path: Path) -> dict[str, Any]:
    result = json.loads(result_path.read_text())
    expected_hits = result.get("main_loop_hits")
    require(
        isinstance(expected_hits, int) and not isinstance(expected_hits, bool)
        and expected_hits > 0,
        f"{result_path}: invalid main_loop_hits",
    )
    with path.open(newline="") as handle:
        reader = csv.DictReader(handle, delimiter="\t")
        require(reader.fieldnames == HEADER, f"{path}: header mismatch")
        raw_rows = list(reader)

    parsed: list[dict[str, int]] = []
    for line_number, raw in enumerate(raw_rows, 2):
        require(None not in raw and all(raw.get(name) is not None for name in HEADER),
                f"{path}:{line_number}: malformed fields")
        try:
            row = {name: int(raw[name], 10) for name in DECIMAL_FIELDS}
            row.update({name: int(raw[name], 16) for name in HEX_FIELDS})
        except ValueError as error:
            raise ValueError(f"{path}:{line_number}: invalid number: {error}") from error
        parsed.append(row)

    for index, row in enumerate(parsed, 1):
        require(row["ordinal"] == index, f"{path}: ordinal mismatch at row {index}")
        if index > 1:
            require(row["loop"] >= parsed[index - 2]["loop"],
                    f"{path}: raw loop regressed at row {index}")
    owned = [row for row in parsed if row["loop"] <= expected_hits]
    trailing = [row for row in parsed if row["loop"] > expected_hits]
    if trailing:
        first_trailing = parsed.index(trailing[0])
        require(
            not any(row["loop"] <= expected_hits for row in parsed[first_trailing:]),
            f"{path}: owned row follows post-receipt callback",
        )
    logical, duplicates = normalize_rows(owned, expected_hits, str(path))
    canonical = json.dumps(logical, sort_keys=True, separators=(",", ":")).encode()
    return {
        "path": str(path.resolve()),
        "sha256": sha256(path),
        "result_path": str(result_path.resolve()),
        "result_sha256": sha256(result_path),
        "recorded_main_loop_hits": expected_hits,
        "owned_raw_row_count": len(owned),
        "owned_logical_row_count": len(logical),
        "missing_input_join_loop_count": expected_hits - len(logical),
        "duplicate_observation_count": duplicates,
        "ignored_post_receipt_row_count": len(trailing),
        "canonical_sha256": hashlib.sha256(canonical).hexdigest(),
        "rows": logical,
        "endpoint_events": endpoint_events(logical),
    }


def stable_start(events: list[dict[str, int]], label: str) -> int:
    for index, event in enumerate(events):
        if event["y"] == EXPECTED_SETTLED_Y and all(
            later["y"] == EXPECTED_SETTLED_Y for later in events[index:]
        ):
            return index
    raise ValueError(f"{label}: never settles at world Y={EXPECTED_SETTLED_Y}")


def settled_metric(
    traces: dict[str, dict[str, Any]], tolerance: float,
    maximum_settle_half_cycle: int, minimum_measured_half_cycles: int,
) -> dict[str, Any]:
    counts = {name: len(trace["endpoint_events"]) for name, trace in traces.items()}
    common = min(counts.values())
    require(common > 0, "one or more traces have no endpoint events")
    events = {
        name: trace["endpoint_events"][:common]
        for name, trace in traces.items()
    }
    signatures = {
        name: [(event["half_cycles"], event["room"], event["x"])
               for event in values]
        for name, values in events.items()
    }
    reference = signatures["original_a"]
    require(all(value == reference for value in signatures.values()),
            "endpoint room/X sequence differs")

    settle_indices = {
        name: stable_start(values, name) for name, values in events.items()
    }
    start_index = max(settle_indices.values())
    start_half_cycle = start_index + 1
    require(
        start_half_cycle <= maximum_settle_half_cycle,
        f"settling half-cycle {start_half_cycle} exceeds "
        f"{maximum_settle_half_cycle}",
    )
    post_settle = common - start_half_cycle
    require(
        post_settle >= minimum_measured_half_cycles,
        f"only {post_settle} settled half-cycles; "
        f"need {minimum_measured_half_cycles}",
    )
    require(all(
        event["y"] == EXPECTED_SETTLED_Y
        for values in events.values() for event in values[start_index:]
    ), "post-settle vertical coordinate differs")

    whole_elapsed = {
        name: values[-1]["frame"] - values[start_index]["frame"]
        for name, values in events.items()
    }
    require(all(value > 0 for value in whole_elapsed.values()),
            "non-positive settled elapsed frame count")

    leg_deltas: dict[int, dict[str, dict[str, int]]] = {}
    uncontested: list[int] = []
    contact_affected: list[int] = []
    for index in range(start_index + 1, common):
        half_cycle = index + 1
        deltas: dict[str, dict[str, int]] = {}
        for name, values in events.items():
            frame_delta = values[index]["frame"] - values[index - 1]["frame"]
            loop_delta = values[index]["loop"] - values[index - 1]["loop"]
            require(frame_delta > 0,
                    f"{name}: non-positive frame delta at leg {half_cycle}")
            require(loop_delta > 0,
                    f"{name}: non-positive loop delta at leg {half_cycle}")
            deltas[name] = {"frames": frame_delta, "loops": loop_delta}
        leg_deltas[half_cycle] = deltas
        if all(
            delta["loops"] <= MAX_UNCONTESTED_LOOP_DELTA
            for delta in deltas.values()
        ):
            uncontested.append(half_cycle)
        else:
            contact_affected.append(half_cycle)

    measured = len(uncontested)
    require(
        measured >= minimum_measured_half_cycles,
        f"only {measured} common uncontested half-cycles; "
        f"need {minimum_measured_half_cycles}",
    )
    elapsed = {
        name: sum(
            leg_deltas[half_cycle][name]["frames"]
            for half_cycle in uncontested
        )
        for name in events
    }
    require(all(value > 0 for value in elapsed.values()),
            "non-positive uncontested elapsed frame count")
    ratios = {
        replay: elapsed[f"original_{replay}"] / elapsed[f"dx_{replay}"]
        for replay in ("a", "b")
    }
    whole_ratios = {
        replay: (
            whole_elapsed[f"original_{replay}"]
            / whole_elapsed[f"dx_{replay}"]
        )
        for replay in ("a", "b")
    }
    lower, upper = 1.0 - tolerance, 1.0 + tolerance
    strict_target = all(lower <= value <= upper for value in ratios.values())
    return {
        "common_half_cycles": common,
        "settle_half_cycle_by_trace": {
            name: index + 1 for name, index in settle_indices.items()
        },
        "measurement_start_half_cycle": start_half_cycle,
        "post_settle_half_cycles": post_settle,
        "measured_half_cycles": measured,
        "maximum_uncontested_loop_delta": MAX_UNCONTESTED_LOOP_DELTA,
        "uncontested_half_cycles": uncontested,
        "contact_affected_half_cycles": contact_affected,
        "elapsed_frames": elapsed,
        "throughput_ratio_by_replay": ratios,
        "whole_route_elapsed_frames": whole_elapsed,
        "whole_route_throughput_ratio_by_replay": whole_ratios,
        "target_floor": lower,
        "target_ceiling": upper,
        "strict_target_met": strict_target,
        "endpoint_route_exact": True,
        "post_settle_vertical_exact": True,
    }


def mutation_controls() -> dict[str, bool]:
    rows = [
        {"ordinal": 1, "loop": 1, "frame": 0, "consumed": 0,
         "planned": 0x10, "half_cycles": 0, "room": 5, "x": 96, "y": 1648},
        {"ordinal": 2, "loop": 2, "frame": 2, "consumed": 0x10,
         "planned": 0x20, "half_cycles": 1, "room": 3, "x": 152, "y": 1648},
        {"ordinal": 3, "loop": 3, "frame": 4, "consumed": 0x20,
         "planned": 0x10, "half_cycles": 2, "room": 7, "x": 92, "y": 1648},
    ]

    def accepts(change: Any) -> bool:
        candidate = copy.deepcopy(rows)
        change(candidate)
        try:
            validate_rows(candidate, 3, "mutation")
        except ValueError:
            return False
        return True

    return {
        "valid_trace_passes": accepts(lambda value: None),
        "missing_terminal_rejects": not accepts(lambda value: value.pop()),
        "wrong_consumed_rejects": not accepts(
            lambda value: value[2].update(consumed=0x10)
        ),
        "skipped_half_cycle_rejects": not accepts(
            lambda value: value[2].update(half_cycles=3)
        ),
        "wrong_endpoint_rejects": not accepts(
            lambda value: value[2].update(x=96)
        ),
        "wrong_room_rejects": not accepts(
            lambda value: value[2].update(room=3)
        ),
        "missing_reversal_rejects": not accepts(
            lambda value: value[1].update(planned=0x10)
        ),
    }


def metric_policy_controls() -> dict[str, bool]:
    def traces() -> dict[str, dict[str, list[dict[str, int]]]]:
        result: dict[str, dict[str, list[dict[str, int]]]] = {}
        for family in ("original", "dx"):
            events = [{
                "half_cycles": half_cycle,
                "room": 3 if half_cycle % 2 else 7,
                "x": 152 if half_cycle % 2 else 92,
                "y": EXPECTED_SETTLED_Y,
                "frame": half_cycle * 10,
                "loop": half_cycle * 17,
            } for half_cycle in range(1, 31)]
            for replay in ("a", "b"):
                result[f"{family}_{replay}"] = {
                    "endpoint_events": copy.deepcopy(events)
                }
        return result

    parity = settled_metric(traces(), 0.02, 8, 20)
    contact = traces()
    for replay in ("a", "b"):
        for event in contact[f"original_{replay}"]["endpoint_events"][14:]:
            event["loop"] += 15
            event["frame"] += 100
    contact_result = settled_metric(contact, 0.02, 8, 20)

    slow = traces()
    for replay in ("a", "b"):
        for event in slow[f"dx_{replay}"]["endpoint_events"]:
            event["frame"] = event["half_cycles"] * 12
    slow_result = settled_metric(slow, 0.02, 8, 20)

    hidden = traces()
    for replay in ("a", "b"):
        for event in hidden[f"dx_{replay}"]["endpoint_events"]:
            event["loop"] = event["half_cycles"] * 21
    hidden_rejected = False
    try:
        settled_metric(hidden, 0.02, 8, 20)
    except ValueError:
        hidden_rejected = True

    return {
        "strict_parity_passes": parity["strict_target_met"],
        "contact_leg_is_excluded_and_reported": (
            contact_result["strict_target_met"]
            and contact_result["contact_affected_half_cycles"] == [15]
            and contact_result["whole_route_throughput_ratio_by_replay"]["a"]
            != 1.0
        ),
        "clean_slowdown_rejected": not slow_result["strict_target_met"],
        "general_slowdown_cannot_be_filtered_away": hidden_rejected,
    }


def run_capture(
    candidate: Path, original: Path, capture: Path, frames: int,
    tolerance: float, timeout: float,
    world: tuple[Path, int] | None = None,
) -> tuple[list[str], int, str]:
    require(not (capture / "manifest.json").exists(),
            f"refusing stale capture directory: {capture}")
    capture.mkdir(parents=True, exist_ok=True)
    module_code = (
        "import sys;from pathlib import Path;"
        "sys.path.insert(0,'scripts/diagnostics');"
        "import verify_stage_speed_matrix as m;"
        "m.PROBE=Path('scripts/diagnostics/probe_stage7_state_patrol.lua').resolve();"
        "raise SystemExit(m.main())"
    )
    command = [
        sys.executable, "-c", module_code,
        "--dx-rom", str(candidate),
        "--original-rom", str(original),
        "--targets", "6",
        "--input-mode", "loop-patrol",
        "--frames", str(frames),
        "--tolerance", str(tolerance),
        "--accepted-slow-stage", "7=0.92",
        "--output", str(capture),
        "--timeout", str(timeout),
    ]
    environment = os.environ.copy()
    environment["STAGE7_STATE_PATROL_BASE_PROBE"] = str(BASE_PROBE)
    environment["STAGE_SPEED_CAMERA_TRACE"] = "1"
    environment.pop("STAGE7_WORLD_IMAGE", None)
    environment.pop("STAGE7_WORLD_SEED", None)
    if world is not None:
        environment["STAGE7_WORLD_IMAGE"] = str(world[0])
        environment["STAGE7_WORLD_SEED"] = str(world[1])
    completed = subprocess.run(
        command, cwd=ROOT, env=environment,
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
        timeout=timeout * 4 + 60,
        check=False,
    )
    log = capture / "capture.log"
    log.write_text(completed.stdout)
    return command, completed.returncode, completed.stdout


def capture_and_parse(
    candidate: Path, original: Path, capture: Path, args: argparse.Namespace,
    world: tuple[Path, int] | None,
) -> dict[str, Any]:
    command, capture_exit, capture_log = run_capture(
        candidate, original, capture, args.frames, args.tolerance, args.timeout,
        world,
    )
    manifest_path = capture / "manifest.json"
    require(manifest_path.is_file(), "nested speed manifest is missing")
    manifest = json.loads(manifest_path.read_text())
    rows = manifest.get("rows", [])
    require(len(rows) == 1 and rows[0].get("stage") == 7,
            "nested manifest is not exact Stage 7")
    row = rows[0]
    nested_failures = manifest.get("failures", [])
    route_only_exit = (
        capture_exit == 0
        and manifest.get("status") == "pass"
        and nested_failures == []
        and row.get("passed") is True
    ) or (
        capture_exit == 1
        and manifest.get("status") == "fail"
        and isinstance(nested_failures, list)
        and len(nested_failures) == 1
        and isinstance(nested_failures[0], str)
        and nested_failures[0].startswith(
            "Stage 7: route coverage mismatch "
        )
        and row.get("passed") is False
    )
    nested_checks = {
        "capture_exit_is_route_only_failure_or_pass": route_only_exit,
        "input_identities_unchanged": all(
            manifest.get("input_identity_controls", {}).values()
        ),
        "nested_policy_controls": all(manifest.get("policy_controls", {}).values()),
        "nested_route_policy_controls": all(
            manifest.get("route_policy_controls", {}).values()
        ),
        "nested_output_policy_controls": all(
            manifest.get("central_output_policy_controls", {}).values()
        ),
        "nested_dma_policy_controls": all(
            manifest.get("dma_command_policy_controls", {}).values()
        ),
        "deterministic_replay": bool(row.get("deterministic_replay")),
        "throughput_accepted": bool(row.get("throughput_accepted")),
        "candidate_scene_ok": bool(row.get("candidate_scene_ok")),
        "baseline_continuity_ok": bool(row.get("baseline_continuity_ok")),
        "candidate_continuity_ok": bool(row.get("candidate_continuity_ok")),
        "central_output_telemetry_ok": bool(
            row.get("central_output_telemetry_ok")
        ),
        "candidate_dma_mode_ok": bool(row.get("candidate_dma_mode_ok")),
    }
    require(all(nested_checks.values()),
            "nested non-route contract failed: " + ",".join(
                name for name, passed in nested_checks.items() if not passed
            ))

    trace_paths: dict[str, tuple[Path, Path]] = {}
    for family in ("original", "dx"):
        for replay in ("a", "b"):
            result = capture / f"stage7-{family}-{replay}-loop-patrol/result.json"
            trace_paths[f"{family}_{replay}"] = (
                Path(str(result) + ".coordinate.tsv"), result
            )
    require(all(trace.is_file() and result.is_file()
                for trace, result in trace_paths.values()),
            "one or more state-patrol artifacts are missing")
    traces = {
        name: parse_trace(trace, result)
        for name, (trace, result) in trace_paths.items()
    }
    deterministic = {
        "original": traces["original_a"]["canonical_sha256"]
        == traces["original_b"]["canonical_sha256"],
        "dx": traces["dx_a"]["canonical_sha256"]
        == traces["dx_b"]["canonical_sha256"],
    }
    worlds = {}
    for name, (_trace, result) in trace_paths.items():
        image = Path(str(result) + ".world.bin")
        require(image.is_file(), f"{name}: post-start world image missing")
        worlds[name] = image.read_bytes()
    return {
        "command": command,
        "exit_code": capture_exit,
        "log_sha256": hashlib.sha256(capture_log.encode()).hexdigest(),
        "manifest": str(manifest_path),
        "manifest_sha256": sha256(manifest_path),
        "nested_checks": nested_checks,
        "raw_route_gate_replaced": not bool(row.get("route_coverage_ok")),
        "fixed_frame_loop_ratio": row.get("ratio_exact"),
        "deterministic": deterministic,
        "traces": traces,
        "worlds": worlds,
    }


def public_capture(run: dict[str, Any]) -> dict[str, Any]:
    return {
        key: value for key, value in run.items()
        if key not in ("traces", "worlds")
    }


def public_traces(traces: dict[str, dict[str, Any]]) -> dict[str, Any]:
    return {
        name: {key: value for key, value in trace.items()
               if key not in ("rows", "endpoint_events")}
        for name, trace in traces.items()
    }


def combined_metric(
    seed_traces: dict[int, dict[str, dict[str, Any]]],
    maximum_settle_half_cycle: int,
) -> dict[str, Any]:
    """Combine every usable seed's common uncontested legs."""
    names = ("original_a", "original_b", "dx_a", "dx_b")
    elapsed = {name: 0 for name in names}
    legs = 0
    per_seed: dict[str, Any] = {}
    usable: list[int] = []
    for seed, traces in sorted(seed_traces.items()):
        try:
            metric = settled_metric(
                traces, 0.02, maximum_settle_half_cycle, 0,
            )
        except ValueError as error:
            per_seed[str(seed)] = {"usable": False, "reason": str(error)}
            continue
        usable.append(seed)
        legs += metric["measured_half_cycles"]
        for name in names:
            elapsed[name] += metric["elapsed_frames"][name]
        per_seed[str(seed)] = {
            "usable": True,
            "measured_half_cycles": metric["measured_half_cycles"],
            "elapsed_frames": metric["elapsed_frames"],
            "throughput_ratio_by_replay": metric["throughput_ratio_by_replay"],
            "contact_affected_half_cycles":
                metric["contact_affected_half_cycles"],
            "settle_half_cycle_by_trace":
                metric["settle_half_cycle_by_trace"],
        }
    enough = len(usable) >= MIN_USABLE_SEEDS and legs >= MIN_COMBINED_LEGS
    ratios = {
        replay: (
            elapsed[f"original_{replay}"] / elapsed[f"dx_{replay}"]
            if elapsed[f"dx_{replay}"] > 0 else 0.0
        )
        for replay in ("a", "b")
    }
    within = all(
        COMBINED_FLOOR <= value <= COMBINED_CEILING
        for value in ratios.values()
    )
    return {
        "seeds": list(SEEDS),
        "usable_seeds": usable,
        "minimum_usable_seeds": MIN_USABLE_SEEDS,
        "minimum_combined_half_cycles": MIN_COMBINED_LEGS,
        "measured_half_cycles": legs,
        "maximum_uncontested_loop_delta": MAX_UNCONTESTED_LOOP_DELTA,
        "elapsed_frames": elapsed,
        "throughput_ratio_by_replay": ratios,
        "target_floor": COMBINED_FLOOR,
        "target_ceiling": COMBINED_CEILING,
        "enough_measurement": enough,
        "strict_target_met": enough and within,
        "endpoint_route_exact": True,
        "post_settle_vertical_exact": True,
        "per_seed": per_seed,
    }


def combined_policy_controls() -> dict[str, bool]:
    def seed_traces(dx_frame: int, seeds: int) -> dict[int, Any]:
        result: dict[int, Any] = {}
        for seed in SEEDS[:seeds]:
            traces: dict[str, Any] = {}
            for family in ("original", "dx"):
                step = 10 if family == "original" else dx_frame
                events = [{
                    "half_cycles": half_cycle,
                    "room": 3 if half_cycle % 2 else 7,
                    "x": 152 if half_cycle % 2 else 92,
                    "y": EXPECTED_SETTLED_Y,
                    "frame": half_cycle * step,
                    "loop": half_cycle * 17,
                } for half_cycle in range(1, 31)]
                for replay in ("a", "b"):
                    traces[f"{family}_{replay}"] = {
                        "endpoint_events": copy.deepcopy(events)
                    }
            result[seed] = traces
        return result

    def met(dx_frame: float, seeds: int = len(SEEDS)) -> bool:
        return combined_metric(seed_traces(dx_frame, seeds), 8)[
            "strict_target_met"
        ]

    return {
        "parity_passes": met(10),
        "floor_edge_passes": met(10 / 0.971),
        "below_floor_rejected": not met(10 / 0.969),
        "clean_slowdown_rejected": not met(12),
        "too_few_usable_seeds_rejected": not met(10, MIN_USABLE_SEEDS - 1),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("candidate", type=Path)
    parser.add_argument("--original", type=Path, default=ORIGINAL)
    parser.add_argument("--frames", type=int, default=4000)
    parser.add_argument("--tolerance", type=float, default=0.02)
    parser.add_argument("--maximum-settle-half-cycle", type=int, default=24)
    parser.add_argument("--minimum-measured-half-cycles", type=int, default=20)
    parser.add_argument("--timeout", type=float, default=45.0)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    candidate = args.candidate.resolve()
    original = args.original.resolve()
    output = args.output.resolve()
    require(candidate.is_file(), f"candidate ROM missing: {candidate}")
    require(original.is_file(), f"original ROM missing: {original}")
    require(args.frames >= 2800, "state patrol requires at least 2800 frames")
    require(0 < args.tolerance <= 0.05, "invalid tolerance")
    require(args.minimum_measured_half_cycles >= 8,
            "too few required post-settle half-cycles")
    output.mkdir(parents=True, exist_ok=True)
    capture = output / "capture"
    initial_hashes = {
        "candidate": sha256(candidate),
        "original": sha256(original),
        "matrix": sha256(MATRIX),
        "base_probe": sha256(BASE_PROBE),
        "state_probe": sha256(STATE_PROBE),
        "verifier": sha256(Path(__file__).resolve()),
    }

    output_runs: dict[str, Any] = {}
    native = capture_and_parse(candidate, original, capture, args, None)
    reference_path = output / "stock-world.img"
    stock_a = native["worlds"]["original_a"]
    require(len(stock_a) == WORLD_IMAGE_SIZE + 1,
            "stock world image has the wrong size")
    require(native["worlds"]["original_b"] == stock_a,
            "stock A/B start-of-play world images differ")
    reference = stock_a[:WORLD_IMAGE_SIZE]
    reference_path.write_bytes(reference)
    try:
        native_metric: Any = settled_metric(
            native["traces"], args.tolerance, args.maximum_settle_half_cycle,
            args.minimum_measured_half_cycles,
        )
    except ValueError as error:
        native_metric = {"error": str(error)}

    seed_traces: dict[int, dict[str, dict[str, Any]]] = {}
    seed_checks: dict[str, bool] = {}
    for seed in SEEDS:
        run = capture_and_parse(
            candidate, original, output / f"capture-seed-{seed:02d}", args,
            (reference_path, seed),
        )
        expected = reference + bytes([seed])
        seed_checks[f"seed_{seed:02d}_equal_start"] = all(
            image == expected for image in run["worlds"].values()
        )
        seed_checks[f"seed_{seed:02d}_deterministic"] = all(
            run["deterministic"].values()
        )
        seed_traces[seed] = run["traces"]
        output_runs[str(seed)] = {
            **public_capture(run),
            "traces": public_traces(run["traces"]),
        }
    require(all(seed_checks.values()),
            "equal-start seed checks failed: " + ",".join(
                name for name, passed in seed_checks.items() if not passed))
    deterministic = {
        "original": all(output_runs[str(seed)]["deterministic"]["original"]
                        for seed in SEEDS),
        "dx": all(output_runs[str(seed)]["deterministic"]["dx"]
                  for seed in SEEDS),
    }
    metric = combined_metric(seed_traces, args.maximum_settle_half_cycle)
    controls = mutation_controls()
    require(all(controls.values()), "state-patrol mutation controls failed")
    metric_controls = metric_policy_controls()
    metric_controls.update({
        f"combined_{name}": value
        for name, value in combined_policy_controls().items()
    })
    require(all(metric_controls.values()),
            "state-patrol metric policy controls failed")
    final_hashes = {
        "candidate": sha256(candidate),
        "original": sha256(original),
        "matrix": sha256(MATRIX),
        "base_probe": sha256(BASE_PROBE),
        "state_probe": sha256(STATE_PROBE),
        "verifier": sha256(Path(__file__).resolve()),
    }
    identities_unchanged = final_hashes == initial_hashes
    passed = metric["strict_target_met"] and identities_unchanged

    receipt = {
        "schema": SCHEMA,
        "status": "PASS" if passed else "FAIL",
        "candidate_sha256": initial_hashes["candidate"],
        "original_sha256": initial_hashes["original"],
        "frames": args.frames,
        "tolerance": args.tolerance,
        "maximum_settle_half_cycle": args.maximum_settle_half_cycle,
        "minimum_measured_half_cycles": args.minimum_measured_half_cycles,
        "classification": CLASSIFICATION,
        "capture": public_capture(native),
        "stock_world_image": {
            "path": str(reference_path),
            "sha256": sha256(reference_path),
            "ranges": "D800-D8FF,DC00-DCFF,FFCB,FFD4-FFD5",
            "seed_register": "FFD1",
        },
        "native_diagnostic_metric": native_metric,
        "native_traces": public_traces(native["traces"]),
        "seed_captures": output_runs,
        "seed_checks": seed_checks,
        "metric": metric,
        "deterministic_replay": deterministic,
        "mutation_controls": controls,
        "metric_policy_controls": metric_controls,
        "input_identities": initial_hashes,
        "input_identities_unchanged": identities_unchanged,
    }
    receipt_path = output / "receipt.json"
    receipt_path.write_text(json.dumps(receipt, indent=2) + "\n")
    print(json.dumps(receipt, indent=2))
    return 0 if passed else 1


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError, subprocess.TimeoutExpired) as error:
        print(f"FAIL: {error}", file=sys.stderr)
        raise SystemExit(1)
