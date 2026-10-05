#!/usr/bin/env python3
"""Compare vanilla/DX main-loop throughput across selected dungeon stages."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import signal
import shutil
import subprocess
import sys
import time


ROOT = Path(__file__).resolve().parents[2]
PROBE = ROOT / "scripts/diagnostics/probe_stage_speed.lua"
DEFAULT_ORIGINAL = ROOT / "rom/Penta Dragon (J).gb"
DEFAULT_DX = ROOT / "rom/working/penta_dragon_dx_FIXED.gb"


def md5(path: Path) -> str:
    digest = hashlib.md5()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def file_matches_sha256(path: Path, expected: str) -> bool:
    """Return false, rather than crash, if an input changes during a run."""

    try:
        return sha256(path) == expected
    except OSError:
        return False


def modular_nibble_distance(before: int, after: int) -> int:
    """Return the shortest camera-phase distance on stock's 16-pixel ring."""

    forward = ((after & 0x0F) - (before & 0x0F)) & 0x0F
    return min(forward, (-forward) & 0x0F)


def summarize_route_samples(samples: list[tuple[int, int, int]]) -> dict:
    """Summarize cadence-independent viewport coverage from attr events.

    The stock map copier exposes SCX/SCY at publication cadence. Camera phase
    wraps every 16 pixels, and a room transition can reset that phase without
    player movement, so only same-room modular deltas contribute to coverage.
    Full-byte first/final viewports and the ordered room-transition sequence
    independently prove the endpoints and traversal order.
    """

    horizontal = 0
    vertical = 0
    room_transitions: list[dict[str, dict[str, int]]] = []
    observed_rooms: list[int] = []
    camera_states: set[tuple[int, int, int]] = set()
    previous: tuple[int, int, int] | None = None
    for room, scx, scy in samples:
        if room not in observed_rooms:
            observed_rooms.append(room)
        camera_states.add((room, scx, scy))
        if previous is not None:
            previous_room, previous_scx, previous_scy = previous
            if room == previous_room:
                horizontal += modular_nibble_distance(previous_scx, scx)
                vertical += modular_nibble_distance(previous_scy, scy)
            else:
                room_transitions.append(
                    {
                        "from": {
                            "room": previous_room,
                            "scx": previous_scx,
                            "scy": previous_scy,
                        },
                        "to": {"room": room, "scx": scx, "scy": scy},
                    }
                )
        previous = (room, scx, scy)

    first = samples[0] if samples else None
    final = samples[-1] if samples else None

    def coordinates(value: tuple[int, int, int] | None) -> dict | None:
        if value is None:
            return None
        room, scx, scy = value
        return {"room": room, "scx": scx, "scy": scy}

    return {
        "available": bool(samples),
        "sample_count": len(samples),
        "horizontal_mod16_distance": horizontal,
        "vertical_mod16_distance": vertical,
        "first": coordinates(first),
        "final": coordinates(final),
        "room_transition_count": len(room_transitions),
        "room_transition_sequence": [
            {
                "from_room": transition["from"]["room"],
                "to_room": transition["to"]["room"],
            }
            for transition in room_transitions
        ],
        # Exact cameras around a transition are retained as evidence, but are
        # cadence-sensitive across OG/DX in Stages 1, 4, and 5. Ordered room
        # IDs are the semantic gate below.
        "room_transitions": room_transitions,
        "observed_rooms": observed_rooms,
        "unique_camera_state_count": len(camera_states),
    }


def route_coverage_from_attr_events(path: Path) -> dict:
    """Parse room/SCX/SCY from the probe's checked-in attr-event format."""

    if not path.is_file():
        raise RuntimeError(f"route coverage trace is missing: {path}")
    samples: list[tuple[int, int, int]] = []
    with path.open() as handle:
        for line_number, raw in enumerate(handle, 1):
            if not raw.strip():
                continue
            fields = raw.rstrip("\n").split("\t")
            if len(fields) < 6:
                raise RuntimeError(
                    f"route coverage trace {path}:{line_number} has "
                    f"{len(fields)} fields; expected at least 6"
                )
            try:
                room = int(fields[3], 16)
                scx = int(fields[4], 16)
                scy = int(fields[5], 16)
            except ValueError as error:
                raise RuntimeError(
                    f"route coverage trace {path}:{line_number} has invalid "
                    "room/SCX/SCY hex fields"
                ) from error
            samples.append((room, scx, scy))
    coverage = summarize_route_samples(samples)
    if not coverage["available"]:
        raise RuntimeError(f"route coverage trace has no samples: {path}")
    return coverage


def compare_route_coverage(original: dict, candidate: dict) -> dict:
    """Compare distance, endpoints, and ordered room traversal fail-closed."""

    original_first = original.get("first") or {}
    candidate_first = candidate.get("first") or {}
    original_final = original.get("final") or {}
    candidate_final = candidate.get("final") or {}
    component_values = {
        "horizontal_mod16_distance": (
            original.get("horizontal_mod16_distance"),
            candidate.get("horizontal_mod16_distance"),
        ),
        "vertical_mod16_distance": (
            original.get("vertical_mod16_distance"),
            candidate.get("vertical_mod16_distance"),
        ),
        "first_room": (
            original_first.get("room"), candidate_first.get("room")
        ),
        "first_scx": (
            original_first.get("scx"), candidate_first.get("scx")
        ),
        "first_scy": (
            original_first.get("scy"), candidate_first.get("scy")
        ),
        "room_transition_sequence": (
            original.get("room_transition_sequence"),
            candidate.get("room_transition_sequence"),
        ),
        "final_room": (
            original_final.get("room"), candidate_final.get("room")
        ),
        "final_scx": (
            original_final.get("scx"), candidate_final.get("scx")
        ),
        "final_scy": (
            original_final.get("scy"), candidate_final.get("scy")
        ),
    }
    components = {
        name: {
            "original": values[0],
            "dx": values[1],
            "matches": values[0] is not None and values[0] == values[1],
        }
        for name, values in component_values.items()
    }
    available = bool(original.get("available")) and bool(
        candidate.get("available")
    )
    return {
        "passed": available
        and all(component["matches"] for component in components.values()),
        "original_available": bool(original.get("available")),
        "dx_available": bool(candidate.get("available")),
        "components": components,
    }


def qualify_named_stage_route_skew(
    comparison: dict,
    *,
    stage: int,
    accepted_floor: float | None,
) -> dict[str, object]:
    """Admit the reviewed Stage-7 two-pixel cadence boundary only."""

    components = comparison.get("components", {})
    horizontal = components.get("horizontal_mod16_distance", {})
    original_horizontal = horizontal.get("original")
    candidate_horizontal = horizontal.get("dx")
    exact_components = (
        "vertical_mod16_distance",
        "first_room", "first_scx", "first_scy",
        "room_transition_sequence",
        "final_room", "final_scx", "final_scy",
    )
    exact_context = all(
        components.get(name, {}).get("matches") is True
        for name in exact_components
    )
    horizontal_delta = (
        abs(candidate_horizontal - original_horizontal)
        if isinstance(original_horizontal, int)
        and isinstance(candidate_horizontal, int)
        else None
    )
    policy_eligible = stage == 7 and accepted_floor == 0.95
    passed = bool(
        not comparison.get("passed")
        and comparison.get("original_available")
        and comparison.get("dx_available")
        and policy_eligible
        and exact_context
        and horizontal_delta is not None
        and 0 < horizontal_delta <= 2
    )
    return {
        "passed": passed,
        "classification": (
            "NAMED_STAGE7_RELEASE95_TWO_PIXEL_CADENCE"
            if passed else "NONE"
        ),
        "policy_eligible": policy_eligible,
        "accepted_floor": accepted_floor,
        "horizontal_delta": horizontal_delta,
        "maximum_horizontal_delta": 2,
        "exact_context": exact_context,
        "vertical_distance_exact": components.get(
            "vertical_mod16_distance", {}
        ).get("matches") is True,
        "first_viewport_exact": all(
            components.get(name, {}).get("matches") is True
            for name in ("first_room", "first_scx", "first_scy")
        ),
        "transition_sequence_exact": components.get(
            "room_transition_sequence", {}
        ).get("matches") is True,
        "final_viewport_exact": all(
            components.get(name, {}).get("matches") is True
            for name in ("final_room", "final_scx", "final_scy")
        ),
    }


def route_policy_controls() -> dict[str, bool]:
    """Deterministic positive/negative controls for route summarization."""

    same_room_wrap = summarize_route_samples(
        [(3, 0x0E, 0x0C), (3, 0x00, 0x00)]
    )
    room_reset = summarize_route_samples(
        [(5, 0x00, 0x00), (5, 0x04, 0x00), (3, 0x08, 0x0C)]
    )
    ordered_route = summarize_route_samples(
        [
            (5, 0x00, 0x00),
            (3, 0x04, 0x00),
            (1, 0x08, 0x00),
            (3, 0x0C, 0x00),
        ]
    )
    matching_route = compare_route_coverage(
        ordered_route, dict(ordered_route)
    )
    wrong_distance = dict(ordered_route)
    wrong_distance["horizontal_mod16_distance"] += 1
    two_pixel_distance = dict(ordered_route)
    two_pixel_distance["horizontal_mod16_distance"] += 2
    three_pixel_distance = dict(ordered_route)
    three_pixel_distance["horizontal_mod16_distance"] += 3
    wrong_vertical = dict(ordered_route)
    wrong_vertical["vertical_mod16_distance"] += 1
    wrong_endpoint = dict(ordered_route)
    wrong_endpoint["final"] = {"room": 3, "scx": 13, "scy": 0}
    wrong_first = dict(ordered_route)
    wrong_first["first"] = {"room": 5, "scx": 1, "scy": 0}
    wrong_order = dict(ordered_route)
    wrong_order["room_transition_sequence"] = list(
        reversed(ordered_route["room_transition_sequence"])
    )
    shifted_transition_cameras = dict(ordered_route)
    shifted_transition_cameras["room_transitions"] = [
        {
            "from": {
                **transition["from"],
                "scx": (transition["from"]["scx"] + 4) & 0xFF,
            },
            "to": dict(transition["to"]),
        }
        for transition in ordered_route["room_transitions"]
    ]
    unavailable = dict(ordered_route)
    unavailable["available"] = False
    return {
        "horizontal_wrap_is_two_pixels": (
            same_room_wrap["horizontal_mod16_distance"] == 2
        ),
        "vertical_wrap_is_four_pixels": (
            same_room_wrap["vertical_mod16_distance"] == 4
        ),
        "room_reset_is_not_camera_travel": (
            room_reset["horizontal_mod16_distance"] == 4
            and room_reset["vertical_mod16_distance"] == 0
        ),
        "final_coordinates_are_full_byte_exact": (
            room_reset["final"] == {"room": 3, "scx": 8, "scy": 12}
        ),
        "ordered_room_transitions_are_recorded": (
            ordered_route["room_transition_sequence"]
            == [
                {"from_room": 5, "to_room": 3},
                {"from_room": 3, "to_room": 1},
                {"from_room": 1, "to_room": 3},
            ]
        ),
        "matching_route_passes": matching_route["passed"],
        "distance_mismatch_rejects": not compare_route_coverage(
            ordered_route, wrong_distance
        )["passed"],
        "named_stage7_release95_accepts_only_two_pixel_cadence": (
            qualify_named_stage_route_skew(
                compare_route_coverage(ordered_route, two_pixel_distance),
                stage=7,
                accepted_floor=0.95,
            )["passed"]
        ),
        "named_stage7_cadence_rejects_three_pixels": not (
            qualify_named_stage_route_skew(
                compare_route_coverage(ordered_route, three_pixel_distance),
                stage=7,
                accepted_floor=0.95,
            )["passed"]
        ),
        "named_stage7_cadence_rejects_vertical_skew": not (
            qualify_named_stage_route_skew(
                compare_route_coverage(ordered_route, wrong_vertical),
                stage=7,
                accepted_floor=0.95,
            )["passed"]
        ),
        "named_stage7_cadence_requires_release_floor": not (
            qualify_named_stage_route_skew(
                compare_route_coverage(ordered_route, two_pixel_distance),
                stage=7,
                accepted_floor=None,
            )["passed"]
        ),
        "named_stage7_cadence_rejects_other_stages": not (
            qualify_named_stage_route_skew(
                compare_route_coverage(ordered_route, two_pixel_distance),
                stage=5,
                accepted_floor=0.95,
            )["passed"]
        ),
        "named_stage7_cadence_still_rejects_endpoint_mismatch": not (
            qualify_named_stage_route_skew(
                compare_route_coverage(ordered_route, wrong_endpoint),
                stage=7,
                accepted_floor=0.95,
            )["passed"]
        ),
        "endpoint_mismatch_rejects": not compare_route_coverage(
            ordered_route, wrong_endpoint
        )["passed"],
        "first_viewport_mismatch_rejects": not compare_route_coverage(
            ordered_route, wrong_first
        )["passed"],
        "transition_order_mismatch_rejects": not compare_route_coverage(
            ordered_route, wrong_order
        )["passed"],
        "transition_camera_cadence_is_diagnostic": compare_route_coverage(
            ordered_route, shifted_transition_cameras
        )["passed"],
        "missing_route_rejects": not compare_route_coverage(
            ordered_route, unavailable
        )["passed"],
    }


def deterministic_payload(result: dict) -> dict:
    """Strip invocation paths while retaining every measured value.

    The Lua probe opens its fixed-frame window on the first stock main-loop
    anchor after scene stabilization, so equality here is CPU-boundary-
    aligned replay evidence rather than host-callback luck.
    """
    return {
        key: value for key, value in result.items()
        if key not in {"rom", "log"}
    }


def payload_sha256(result: dict) -> str:
    encoded = json.dumps(
        deterministic_payload(result), sort_keys=True, separators=(",", ":")
    ).encode()
    return hashlib.sha256(encoded).hexdigest()


def classify_throughput(
    ratio: float,
    target_tolerance: float,
    accepted_slowdown_floor: float | None,
) -> dict:
    """Classify measured throughput without hiding an accepted compromise.

    The symmetric target remains aspirational.  An operator-approved floor
    may accept only a bounded slowdown below that target; it never excuses a
    speed-up beyond the target envelope.
    """

    target_met = abs(1.0 - ratio) <= target_tolerance + 1e-9
    accepted_slowdown = (
        not target_met
        and accepted_slowdown_floor is not None
        and accepted_slowdown_floor - 1e-9 <= ratio < 1.0
    )
    return {
        "target_met": target_met,
        "accepted_slowdown_deviation": accepted_slowdown,
        "throughput_accepted": target_met or accepted_slowdown,
    }


def throughput_policy_controls(
    target_tolerance: float = 0.02,
    accepted_floors: dict[str, float] | None = None,
) -> dict[str, bool]:
    """Exercise the exact target envelope and every requested slow floor."""

    lower_edge = 1.0 - target_tolerance
    upper_edge = 1.0 + target_tolerance
    outside_step = max(1e-6, lower_edge * 1e-6)
    strict = lambda ratio: classify_throughput(
        ratio, target_tolerance, None
    )
    controls = {
        "target_center_passes": strict(1.0)["throughput_accepted"],
        "target_lower_edge_passes": strict(lower_edge)[
            "throughput_accepted"
        ],
        "target_upper_edge_passes": strict(upper_edge)[
            "throughput_accepted"
        ],
        "strict_rejects_just_below_target": not strict(
            lower_edge - outside_step
        )["throughput_accepted"],
        "strict_rejects_just_above_target": not strict(
            upper_edge + outside_step
        )["throughput_accepted"],
    }

    floors = dict(accepted_floors or {})
    if not floors:
        # Keep the accepted-compromise path mutation-tested even for a strict
        # invocation. This synthetic floor cannot affect measured acceptance.
        floors["synthetic"] = max(lower_edge / 2.0, lower_edge - 0.02)
    for name, floor in sorted(floors.items()):
        at_floor = classify_throughput(
            floor, target_tolerance, floor
        )
        below_floor = classify_throughput(
            floor - max(1e-6, floor * 1e-6), target_tolerance, floor
        )
        beyond_upper = classify_throughput(
            upper_edge + outside_step, target_tolerance, floor
        )
        floor_is_outside_target = floor < lower_edge - 1e-9
        prefix = f"accepted_floor_{name}"
        controls[f"{prefix}_passes_at_equality"] = at_floor[
            "throughput_accepted"
        ]
        controls[f"{prefix}_classification_is_explicit"] = (
            at_floor["accepted_slowdown_deviation"]
            and not at_floor["target_met"]
            if floor_is_outside_target
            else at_floor["target_met"]
            and not at_floor["accepted_slowdown_deviation"]
        )
        controls[f"{prefix}_rejects_below_floor"] = not below_floor[
            "throughput_accepted"
        ]
        controls[f"{prefix}_never_excuses_speedup"] = not beyond_upper[
            "throughput_accepted"
        ]
    return controls


def central_output_telemetry_contract(
    emitter_entries: int,
    x_entries: int,
    completed_outputs: int,
) -> tuple[bool, int, int, int]:
    """Qualify the central OBJ pipeline without a fixed-duration false fail.

    The emitter entry precedes legitimate clipping/early-return decisions, so
    its count is slightly larger than the attribute pipeline count.  The old
    fixed allowance of 32 worked at 800 frames but rejected the same qualified
    path at 2,800 frames.  Require every observed X-helper entry to reach the
    final attribute output, then permit at most 0.2% (one in 500) or 32 early
    emitter exits.  This remains fail-closed for a relocated/missing helper.
    """

    pending_output_tail = x_entries - completed_outputs
    missing_outputs = emitter_entries - completed_outputs
    allowed_early_exits = max(32, (emitter_entries + 499) // 500)
    passed = (
        completed_outputs > 0
        # The DI-bounded pipeline can have at most one X-helper entry pending
        # when the final host-frame callback closes the measurement window.
        and 0 <= pending_output_tail <= 1
        and 0 <= missing_outputs <= allowed_early_exits
    )
    return passed, missing_outputs, allowed_early_exits, pending_output_tail


def central_output_policy_controls() -> dict[str, bool]:
    """Positive and mutation-style negative controls for OBJ telemetry."""

    exact = central_output_telemetry_contract(10_000, 10_000, 10_000)[0]
    qualified_long = central_output_telemetry_contract(
        21_581, 21_543, 21_543
    )[0]
    over_bound = central_output_telemetry_contract(
        22_000, 21_955, 21_955
    )[0]
    missing_helper = central_output_telemetry_contract(22_000, 0, 0)[0]
    one_pending_tail = central_output_telemetry_contract(
        22_000, 21_960, 21_959
    )[0]
    two_pending_tail = central_output_telemetry_contract(
        22_000, 21_960, 21_958
    )[0]
    return {
        "exact_pipeline_passes": exact,
        "qualified_long_run_passes": qualified_long,
        "over_bound_early_exits_reject": not over_bound,
        "missing_helper_rejects": not missing_helper,
        "one_pending_output_tail_passes": one_pending_tail,
        "two_pending_output_tail_rejects": not two_pending_tail,
    }


def normalize_dma_command_addrs(addresses: list[int]) -> list[int]:
    """Validate and de-duplicate command PCs while preserving CLI order."""

    normalized: list[int] = []
    for address in addresses:
        if isinstance(address, bool) or not isinstance(address, int):
            raise ValueError("DMA command addresses must be integers")
        if address <= 0 or address > 0xFFFF:
            raise ValueError(
                "DMA command addresses must be CPU addresses in $0001-$FFFF"
            )
        if address not in normalized:
            normalized.append(address)
    return normalized


def dma_command_environment(addresses: list[int]) -> dict[str, str]:
    """Return both probe inputs, explicitly clearing absent/stale sites."""

    normalized = normalize_dma_command_addrs(addresses)
    return {
        "STAGE_SPEED_DMA_COMMAND_ADDR": str(
            normalized[0] if normalized else 0
        ),
        "STAGE_SPEED_DMA_COMMAND_ADDRS": ",".join(
            str(address) for address in normalized[1:]
        ),
    }


def dma_command_contract(
    result: dict,
    requested_addresses: list[int],
    expected_mode: str,
) -> dict:
    """Bind every requested FF55 store PC to valid expected-mode telemetry.

    The Lua probe increments the aggregate command count and exactly one
    per-site count in the same callback.  Requiring the site-count sum to
    equal that aggregate therefore rejects a missing, stale, or unexpected
    breakpoint as well as a requested site which never executes.  The
    aggregate mode/scene checks then qualify every one of those site hits.
    """

    addresses = normalize_dma_command_addrs(requested_addresses)
    if not addresses:
        return {
            "enabled": False,
            "passed": True,
            "requested_addresses": [],
            "requested_site_keys": [],
            "observed_site_hits": {},
        }

    if expected_mode not in ("stage1-hblank", "hblank", "gdma"):
        raise ValueError(f"unsupported expected DMA mode: {expected_mode}")

    requested_keys = [f"0x{address:04X}" for address in addresses]
    raw_site_hits = result.get("attr_dma_site_hits", {})
    site_hits = raw_site_hits if isinstance(raw_site_hits, dict) else {}
    actual_keys = set(site_hits)
    expected_keys = set(requested_keys)
    positive_site_hits = {
        key: (
            isinstance(site_hits.get(key), int)
            and not isinstance(site_hits.get(key), bool)
            and site_hits[key] > 0
        )
        for key in requested_keys
    }
    numeric_site_hit_sum = sum(
        value
        for value in site_hits.values()
        if isinstance(value, int) and not isinstance(value, bool)
    )
    command_count = result.get("attr_dma_commands", 0)
    hblank_count = result.get("attr_hblank_commands", 0)
    gdma_count = result.get("attr_gdma_commands", 0)
    expected_count = (
        hblank_count
        if expected_mode in ("stage1-hblank", "hblank")
        else gdma_count
    )
    opposite_count = (
        gdma_count
        if expected_mode in ("stage1-hblank", "hblank")
        else hblank_count
    )
    checks = {
        "site_key_set_exact": actual_keys == expected_keys,
        "every_requested_site_positive": all(positive_site_hits.values()),
        "command_count_positive": (
            isinstance(command_count, int)
            and not isinstance(command_count, bool)
            and command_count > 0
        ),
        "site_sum_matches_command_count": (
            numeric_site_hit_sum == command_count
        ),
        "every_command_has_expected_mode": expected_count == command_count,
        "opposite_mode_absent": opposite_count == 0,
        "invalid_commands_absent": (
            result.get("attr_invalid_dma_commands", 0) == 0
        ),
        "scene_violations_absent": (
            result.get("attr_dma_scene_violations", 0) == 0
        ),
        "dma_idle_at_finish": result.get("final_hdma5") == 0xFF,
    }
    return {
        "enabled": True,
        "passed": all(checks.values()),
        "expected_mode": expected_mode,
        "requested_addresses": addresses,
        "requested_site_keys": requested_keys,
        "observed_site_hits": site_hits,
        "positive_site_hits": positive_site_hits,
        "site_hit_sum": numeric_site_hit_sum,
        "command_count": command_count,
        "expected_mode_command_count": expected_count,
        "opposite_mode_command_count": opposite_count,
        "checks": checks,
    }


def dma_command_policy_controls() -> dict[str, bool]:
    """Mutation-style controls for the multi-site DMA receipt contract."""

    addresses = [0x7149, 0x7193]
    valid = {
        "attr_dma_commands": 25,
        "attr_hblank_commands": 25,
        "attr_gdma_commands": 0,
        "attr_invalid_dma_commands": 0,
        "attr_dma_scene_violations": 0,
        "attr_dma_site_hits": {"0x7149": 1, "0x7193": 24},
        "final_hdma5": 0xFF,
    }

    def mutated(**changes: object) -> dict:
        result = dict(valid)
        result.update(changes)
        return result

    return {
        "two_hblank_sites_pass": dma_command_contract(
            valid, addresses, "hblank"
        )["passed"],
        "legacy_single_site_passes": dma_command_contract(
            mutated(
                attr_dma_commands=1,
                attr_hblank_commands=1,
                attr_dma_site_hits={"0x7149": 1},
            ),
            [0x7149],
            "hblank",
        )["passed"],
        "duplicate_cli_site_is_normalized": (
            normalize_dma_command_addrs([0x7149, 0x7149, 0x7193])
            == addresses
        ),
        "two_sites_propagate_without_outer_environment": (
            dma_command_environment(addresses)
            == {
                "STAGE_SPEED_DMA_COMMAND_ADDR": str(0x7149),
                "STAGE_SPEED_DMA_COMMAND_ADDRS": str(0x7193),
            }
        ),
        "legacy_single_site_uses_legacy_probe_input": (
            dma_command_environment([0x7149])
            == {
                "STAGE_SPEED_DMA_COMMAND_ADDR": str(0x7149),
                "STAGE_SPEED_DMA_COMMAND_ADDRS": "",
            }
        ),
        "unconfigured_run_clears_both_probe_inputs": (
            dma_command_environment([])
            == {
                "STAGE_SPEED_DMA_COMMAND_ADDR": "0",
                "STAGE_SPEED_DMA_COMMAND_ADDRS": "",
            }
        ),
        "missing_site_rejects": not dma_command_contract(
            mutated(attr_dma_site_hits={"0x7149": 25}),
            addresses,
            "hblank",
        )["passed"],
        "zero_hit_site_rejects": not dma_command_contract(
            mutated(attr_dma_site_hits={"0x7149": 25, "0x7193": 0}),
            addresses,
            "hblank",
        )["passed"],
        "unexpected_site_rejects": not dma_command_contract(
            mutated(
                attr_dma_site_hits={
                    "0x7149": 1, "0x7193": 23, "0x7000": 1,
                }
            ),
            addresses,
            "hblank",
        )["passed"],
        "site_sum_mismatch_rejects": not dma_command_contract(
            mutated(attr_dma_site_hits={"0x7149": 1, "0x7193": 23}),
            addresses,
            "hblank",
        )["passed"],
        "opposite_mode_rejects": not dma_command_contract(
            mutated(attr_hblank_commands=24, attr_gdma_commands=1),
            addresses,
            "hblank",
        )["passed"],
        "wrong_expected_mode_rejects": not dma_command_contract(
            valid, addresses, "gdma"
        )["passed"],
        "invalid_command_rejects": not dma_command_contract(
            mutated(attr_invalid_dma_commands=1), addresses, "hblank"
        )["passed"],
        "scene_violation_rejects": not dma_command_contract(
            mutated(attr_dma_scene_violations=1), addresses, "hblank"
        )["passed"],
        "active_dma_at_finish_rejects": not dma_command_contract(
            mutated(final_hdma5=0x80), addresses, "hblank"
        )["passed"],
        "unconfigured_dma_contract_is_disabled": dma_command_contract(
            {}, [], "gdma"
        )["passed"],
    }


def stop_owned_process_group(process: subprocess.Popen) -> None:
    """Stop only the xvfb/mGBA session created by this probe."""

    try:
        os.killpg(process.pid, signal.SIGTERM)
    except ProcessLookupError:
        pass
    try:
        process.wait(timeout=2)
    except subprocess.TimeoutExpired:
        pass
    # xvfb-run can exit before its emulator child. Finish any survivors in
    # this exact session without using a process-name pattern.
    try:
        os.killpg(process.pid, signal.SIGKILL)
    except ProcessLookupError:
        pass
    if process.poll() is None:
        process.wait(timeout=2)


def run_one(
    mgba: str,
    rom: Path,
    label: str,
    target: int,
    mode: str,
    frames: int,
    atomic_addr: int,
    dma_command_addrs: list[int],
    compiler_bank: int,
    compiler_start: int,
    compiler_end: int,
    trace_addrs: str,
    stage1_decider_mode: str,
    dump_metatile_state: bool,
    output: Path,
    timeout: float,
) -> dict:
    dma_command_addrs = normalize_dma_command_addrs(dma_command_addrs)
    run_dir = output / f"stage{target + 1}-{label}-{mode}"
    run_dir.mkdir(parents=True, exist_ok=True)
    receipt = run_dir / "result.json"
    marker = run_dir / "DONE"
    receipt.unlink(missing_ok=True)
    marker.unlink(missing_ok=True)
    # A reused receipt directory must never silently seed a replay from an
    # emulator battery save. Each run is expected to boot from ROM state.
    for stale_save in sorted(run_dir.glob("*.sav")):
        stale_save.unlink()
    for stale in (
        run_dir / "attr-events.tsv",
        run_dir / "lifecycle.tsv",
        run_dir / "metatile-state.bin",
        run_dir / "metatile-state.bin.grids",
    ):
        stale.unlink(missing_ok=True)
    environment = os.environ.copy()
    environment.update(
        {
            "QT_QPA_PLATFORM": "offscreen",
            "SDL_AUDIODRIVER": "dummy",
            "STAGE_SPEED_TARGET": str(target),
            "STAGE_SPEED_OUT": str(receipt),
            "STAGE_SPEED_DONE": str(marker),
            "STAGE_SPEED_TRACE": str(run_dir / "attr-events.tsv"),
            "STAGE_SPEED_LIFECYCLE": str(run_dir / "lifecycle.tsv"),
            "STAGE_SPEED_MODE": mode,
            "STAGE_SPEED_FRAMES": str(frames),
            "STAGE_SPEED_ATOMIC_ADDR": str(atomic_addr),
            # Preserve the probe's legacy single-site input for the first
            # address and put every additional requested site in its plural
            # input. The helper assigns both variables on every run so a
            # caller's stale environment cannot add an unrecorded breakpoint.
            **dma_command_environment(dma_command_addrs),
            "STAGE_SPEED_COMPILER_BANK": str(compiler_bank),
            "STAGE_SPEED_COMPILER_START": str(compiler_start),
            "STAGE_SPEED_COMPILER_END": str(compiler_end),
            "STAGE_SPEED_TRACE_ADDRS": trace_addrs,
            "STAGE_SPEED_STAGE1_DECIDER_MODE": stage1_decider_mode,
        }
    )
    if dump_metatile_state:
        environment["STAGE_SPEED_METATILE_DUMP"] = str(
            run_dir / "metatile-state.bin"
        )
    environment.pop("DISPLAY", None)
    environment.pop("WAYLAND_DISPLAY", None)
    log = run_dir / "mgba.log"
    with log.open("w") as stream:
        process = subprocess.Popen(
            [
                "xvfb-run",
                "-a",
                mgba,
                "--fastforward",
                "-C",
                f"savegamePath={run_dir}",
                "-C",
                f"savestatePath={run_dir}",
                str(rom),
                "--script",
                str(PROBE),
                "-l",
                "0",
            ],
            cwd=run_dir,
            env=environment,
            stdout=stream,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if receipt.is_file() and marker.is_file():
                break
            if process.poll() is not None:
                break
            time.sleep(0.05)
        stop_owned_process_group(process)
    if not receipt.is_file():
        raise RuntimeError(
            f"Stage {target + 1} {label}/{mode}: no receipt; see {log}"
        )
    result = json.loads(receipt.read_text())
    result["rom"] = str(rom)
    result["rom_md5"] = md5(rom)
    result["rom_sha256"] = sha256(rom)
    result["log"] = str(log)
    attr_trace = run_dir / "attr-events.tsv"
    result["route_coverage"] = route_coverage_from_attr_events(attr_trace)
    for name in ("attr-events.tsv", "lifecycle.tsv"):
        trace = run_dir / name
        result[f"{name.removesuffix('.tsv').replace('-', '_')}_sha256"] = (
            hashlib.sha256(trace.read_bytes()).hexdigest()
            if trace.is_file() else None
        )
    metatile_dump = run_dir / "metatile-state.bin"
    if dump_metatile_state and not metatile_dump.is_file():
        raise RuntimeError(
            f"Stage {target + 1} {label}/{mode}: metatile capture missing; "
            f"see {log}"
        )
    metatile_grids = run_dir / "metatile-state.bin.grids"
    if dump_metatile_state and not metatile_grids.is_file():
        raise RuntimeError(
            f"Stage {target + 1} {label}/{mode}: metatile grid trace missing; "
            f"see {log}"
        )
    result["metatile_state_sha256"] = (
        hashlib.sha256(metatile_dump.read_bytes()).hexdigest()
        if metatile_dump.is_file() else None
    )
    result["metatile_grids_sha256"] = (
        hashlib.sha256(metatile_grids.read_bytes()).hexdigest()
        if metatile_grids.is_file() else None
    )
    return result


def targets(raw: str) -> list[int]:
    values = [int(value.strip()) for value in raw.split(",") if value.strip()]
    if not values or any(value < 0 or value > 6 for value in values):
        raise argparse.ArgumentTypeError("targets must be comma-separated FFBA 0..6")
    return values


def accepted_slow_stage(raw: str) -> tuple[int, float]:
    """Parse a narrow, human-facing Stage-N accepted floor."""
    stage_text, separator, floor_text = raw.partition("=")
    if not separator:
        raise argparse.ArgumentTypeError(
            "accepted slow stage must use STAGE=FLOOR, for example 5=0.95"
        )
    try:
        stage, floor = int(stage_text), float(floor_text)
    except ValueError as error:
        raise argparse.ArgumentTypeError(
            "accepted slow stage must use numeric STAGE=FLOOR"
        ) from error
    if stage < 1 or stage > 7 or not 0 < floor <= 1:
        raise argparse.ArgumentTypeError(
            "accepted slow stage requires Stage 1..7 and floor (0, 1]"
        )
    return stage, floor


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dx-rom", type=Path, default=DEFAULT_DX)
    parser.add_argument("--original-rom", type=Path, default=DEFAULT_ORIGINAL)
    parser.add_argument(
        "--mgba", default=str(ROOT / "scripts/mgba-qt-singleflight")
    )
    parser.add_argument("--targets", type=targets, default=[0, 4, 6])
    parser.add_argument(
        "--input-mode",
        choices=("right", "left", "up", "down", "stationary", "patrol", "vertical-patrol",
                 "loop-patrol", "loop-vertical-patrol"),
        default="right",
    )
    parser.add_argument("--frames", type=int, default=600)
    parser.add_argument("--atomic-addr", type=lambda value: int(value, 0), default=0)
    parser.add_argument(
        "--dma-command-addr",
        action="append",
        type=lambda value: int(value, 0),
        default=[],
        metavar="ADDR",
        help=(
            "candidate-only breakpoint immediately before an HDMA5 write; "
            "repeat for every command site (a single use remains compatible)"
        ),
    )
    parser.add_argument(
        "--expected-dma-mode",
        choices=("stage1-hblank", "hblank", "gdma"),
        default=None,
        help="fail-closed expected candidate attribute DMA command mode",
    )
    parser.add_argument(
        "--compiler-bank", type=lambda value: int(value, 0), default=0,
        help="candidate expansion-bank number owning a banked WRAM compiler",
    )
    parser.add_argument(
        "--compiler-start", type=lambda value: int(value, 0), default=0,
        help="inclusive CPU start of the candidate banked compiler window",
    )
    parser.add_argument(
        "--compiler-end", type=lambda value: int(value, 0), default=0,
        help="inclusive CPU end of the candidate banked compiler window",
    )
    parser.add_argument(
        "--stage1-decider-mode", choices=("native", "pure", "dirty"),
        default="native",
        help="diagnostically force Stage 1's layout decider on DX runs only",
    )
    parser.add_argument(
        "--trace-addrs",
        default="",
        help="comma-separated breakpoint addresses counted during play",
    )
    parser.add_argument(
        "--dump-metatile-state", action="store_true",
        help="dump A000 definitions, C600 LUT, and the current 10x11 source",
    )
    parser.add_argument("--tolerance", type=float, default=0.05)
    parser.add_argument(
        "--accepted-slowdown-floor",
        type=float,
        default=None,
        help=(
            "explicit operator-approved minimum DX/OG ratio below the "
            "symmetric target; target misses remain visible in the receipt"
        ),
    )
    parser.add_argument(
        "--accepted-slow-stage",
        action="append",
        type=accepted_slow_stage,
        default=[],
        metavar="STAGE=FLOOR",
        help=(
            "operator-approved floor for one numbered stage; repeatable and "
            "never inherited by neighboring stages"
        ),
    )
    parser.add_argument("--timeout", type=float, default=45.0)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        dma_command_addrs = normalize_dma_command_addrs(
            args.dma_command_addr
        )
    except ValueError as error:
        parser.error(str(error))
    if not args.mgba:
        parser.error("mgba-qt was not found")
    if args.frames <= 0 or args.timeout <= 0:
        parser.error("frames and timeout must be positive")
    if args.tolerance < 0 or args.tolerance >= 1:
        parser.error("tolerance must be in [0, 1)")
    if args.accepted_slowdown_floor is not None and not (
        0 < args.accepted_slowdown_floor <= 1.0 - args.tolerance
    ):
        parser.error(
            "accepted slowdown floor must be positive and no greater than "
            "the target envelope's lower edge"
        )
    accepted_slow_stages: dict[int, float] = {}
    for stage, floor in args.accepted_slow_stage:
        if stage in accepted_slow_stages:
            parser.error(f"accepted slow Stage {stage} was specified twice")
        if floor > 1.0 - args.tolerance:
            parser.error(
                f"accepted slow Stage {stage} floor must be no greater than "
                "the target envelope's lower edge"
            )
        accepted_slow_stages[stage] = floor

    dx = args.dx_rom.resolve()
    original = args.original_rom.resolve()
    output = args.output.resolve()
    verifier = Path(__file__).resolve()
    for description, path in (
        ("DX ROM", dx),
        ("original ROM", original),
        ("Lua speed probe", PROBE),
    ):
        if not path.is_file():
            parser.error(f"{description} was not found: {path}")

    resolved_mgba_text = shutil.which(args.mgba)
    resolved_mgba = (
        Path(resolved_mgba_text).resolve() if resolved_mgba_text else None
    )
    initial_hashes = {
        "original_rom_md5": md5(original),
        "dx_rom_md5": md5(dx),
        "original_rom_sha256": sha256(original),
        "dx_rom_sha256": sha256(dx),
        "verifier_sha256": sha256(verifier),
        "probe_sha256": sha256(PROBE),
    }
    requested_policy_floors: dict[str, float] = {}
    if args.accepted_slowdown_floor is not None:
        requested_policy_floors["global"] = args.accepted_slowdown_floor
    requested_policy_floors.update(
        {
            f"stage_{stage}": floor
            for stage, floor in sorted(accepted_slow_stages.items())
        }
    )
    effective_dma_modes = {
        str(target + 1): (
            args.expected_dma_mode
            or ("stage1-hblank" if target == 0 else "gdma")
            if dma_command_addrs
            else None
        )
        for target in args.targets
    }
    normalized_config = {
        "dx_rom": str(dx),
        "original_rom": str(original),
        "mgba_argument": args.mgba,
        "mgba_resolved": str(resolved_mgba) if resolved_mgba else None,
        "targets_ffba": list(args.targets),
        "stages": [target + 1 for target in args.targets],
        "input_mode": args.input_mode,
        "frames": args.frames,
        "atomic_addr": args.atomic_addr,
        # Keep the legacy scalar for old receipt readers while making the
        # complete, ordered command-site contract explicit.
        "dma_command_addr": (
            dma_command_addrs[0] if dma_command_addrs else 0
        ),
        "dma_command_addrs": dma_command_addrs,
        "expected_dma_mode": args.expected_dma_mode,
        "effective_dma_mode_by_stage": effective_dma_modes,
        "compiler_bank": args.compiler_bank,
        "compiler_start": args.compiler_start,
        "compiler_end": args.compiler_end,
        "stage1_decider_mode": args.stage1_decider_mode,
        "trace_addrs": args.trace_addrs,
        "dump_metatile_state": args.dump_metatile_state,
        "tolerance": args.tolerance,
        "target_ratio_floor": 1.0 - args.tolerance,
        "target_ratio_ceiling": 1.0 + args.tolerance,
        "accepted_slowdown_floor": args.accepted_slowdown_floor,
        "accepted_slow_stages": {
            str(stage): floor
            for stage, floor in sorted(accepted_slow_stages.items())
        },
        "timeout_seconds": args.timeout,
        "output": str(output),
        "replays_per_rom_stage": 2,
        "save_state_policy": "remove-run-dir-dot-sav-before-each-launch",
        "display_environment": {
            "QT_QPA_PLATFORM": "offscreen",
            "SDL_AUDIODRIVER": "dummy",
            "DISPLAY": None,
            "WAYLAND_DISPLAY": None,
        },
    }
    invocation = {
        "command": [sys.executable, str(verifier), *sys.argv[1:]],
        "raw_argv": list(sys.argv),
        "cwd": str(Path.cwd().resolve()),
        "python_executable": sys.executable,
        "python_version": sys.version,
        "normalized_config": normalized_config,
    }
    tool_identity = {
        "verifier": {
            "path": str(verifier),
            "sha256": initial_hashes["verifier_sha256"],
        },
        "lua_probe": {
            "path": str(PROBE.resolve()),
            "sha256": initial_hashes["probe_sha256"],
        },
        "mgba_launcher": {
            "argument": args.mgba,
            "resolved_path": (
                str(resolved_mgba) if resolved_mgba is not None else None
            ),
            "sha256": (
                sha256(resolved_mgba)
                if resolved_mgba is not None and resolved_mgba.is_file()
                else None
            ),
        },
    }
    output.mkdir(parents=True, exist_ok=True)
    failures: list[str] = []
    rows: list[dict] = []
    policy_controls = throughput_policy_controls(
        args.tolerance, requested_policy_floors
    )
    route_controls = route_policy_controls()
    output_policy_controls = central_output_policy_controls()
    dma_policy_controls = dma_command_policy_controls()
    if not all(policy_controls.values()):
        failures.append("internal throughput policy controls failed")
    if not all(route_controls.values()):
        failures.append("internal route-coverage policy controls failed")
    if not all(output_policy_controls.values()):
        failures.append("internal central-output policy controls failed")
    if not all(dma_policy_controls.values()):
        failures.append("internal DMA command-site policy controls failed")

    for target in args.targets:
        try:
            baseline_runs = [
                run_one(
                    args.mgba, original, f"original-{replay}", target,
                    args.input_mode, args.frames, 0, [],
                    0, 0, 0,
                    args.trace_addrs,
                    "native",
                    args.dump_metatile_state,
                    output, args.timeout,
                )
                for replay in ("a", "b")
            ]
            candidate_runs = [
                run_one(
                    args.mgba, dx, f"dx-{replay}", target, args.input_mode,
                    args.frames, args.atomic_addr, dma_command_addrs,
                    args.compiler_bank, args.compiler_start, args.compiler_end,
                    args.trace_addrs,
                    args.stage1_decider_mode,
                    args.dump_metatile_state,
                    output, args.timeout,
                )
                for replay in ("a", "b")
            ]
        except (OSError, RuntimeError, TimeoutError) as error:
            row = {
                "target": target,
                "stage": target + 1,
                "passed": False,
                "status": "capture-error",
                "error": str(error),
            }
            rows.append(row)
            failures.append(f"Stage {target + 1}: {error}")
            print(f"Stage {target + 1}: CAPTURE ERROR: {error}")
            continue
        baseline, candidate = baseline_runs[0], candidate_runs[0]
        baseline_deterministic = (
            deterministic_payload(baseline_runs[0])
            == deterministic_payload(baseline_runs[1])
        )
        candidate_deterministic = (
            deterministic_payload(candidate_runs[0])
            == deterministic_payload(candidate_runs[1])
        )
        baseline_hits = baseline["main_loop_hits"]
        candidate_hits = candidate["main_loop_hits"]
        ratio = candidate_hits / baseline_hits if baseline_hits else 0.0
        accepted_floor = accepted_slow_stages.get(
            target + 1, args.accepted_slowdown_floor
        )
        throughput = classify_throughput(
            ratio, args.tolerance, accepted_floor
        )
        candidate_scene_mismatch_frames = (
            args.frames - candidate["expected_scene_frames"]
        )
        # A frame callback can land inside the stock HRAM OAM-DMA routine.
        # During that bounded interval CPU-bus reads of WRAM correctly return
        # $FF. The probe classifies every such sample from its PC and DMA
        # source, so tolerate all proven DMA-unreadable samples while keeping
        # every real scene mismatch fatal. This is cadence-independent and
        # therefore deterministic across otherwise equivalent builds.
        dma_unreadable_scene_samples = candidate.get(
            "dma_unreadable_scene_samples", 0
        )
        compiler_unreadable_scene_samples = candidate.get(
            "compiler_unreadable_scene_samples", 0
        )
        non_dma_scene_mismatch_frames = candidate.get(
            "non_dma_scene_mismatch_frames",
            candidate_scene_mismatch_frames,
        )
        candidate_scene_ok = (
            non_dma_scene_mismatch_frames == 0
            and candidate_scene_mismatch_frames
            == dma_unreadable_scene_samples
        )
        # FFC1 is a stage sub-mode flag and legitimately clears in some
        # layouts. Continuity is instead proven from the stock main-loop
        # breakpoint: reject a long internal stall or a run that stops making
        # progress before the final 30 rendered frames.
        max_continuity_gap = 30
        baseline_continuity_ok = (
            baseline.get("max_main_loop_gap", max_continuity_gap + 1)
            <= max_continuity_gap
            and baseline.get("last_main_loop_frame", -1)
            >= args.frames - max_continuity_gap
        )
        candidate_continuity_ok = (
            candidate.get("max_main_loop_gap", max_continuity_gap + 1)
            <= max_continuity_gap
            and candidate.get("last_main_loop_frame", -1)
            >= args.frames - max_continuity_gap
        )
        # Raw publication counts are cadence-sensitive: Stage 7's known-good
        # rightward route publishes 110 stock events versus 70 DX events while
        # both travel H=240/V=28 and finish at room 03, SCX=08, SCY=00. Gate
        # deterministic modular distance, exact first/final viewports, and the
        # ordered room sequence instead, while retaining the old scalar as a
        # diagnostic.
        scroll_change_count_parity = (
            candidate.get("scroll_changes") == baseline.get("scroll_changes")
        )
        route_comparison = compare_route_coverage(
            baseline.get("route_coverage", {}),
            candidate.get("route_coverage", {}),
        )
        route_coverage_strict_ok = route_comparison["passed"]
        route_coverage_qualification = qualify_named_stage_route_skew(
            route_comparison,
            stage=target + 1,
            accepted_floor=accepted_floor,
        )
        route_coverage_ok = bool(
            route_coverage_strict_ok
            or route_coverage_qualification["passed"]
        )
        # The DX central emitter must expose output-side flip telemetry.  A
        # relocated helper once escaped the profiler because only its former
        # entry address was watched; throughput without observed outputs is
        # not a qualified optimization.  A handful of entry/exit samples can
        # straddle the fixed host-frame boundary, so bound that difference
        # rather than requiring the emitter entry count to be identical.
        central_attr_samples = candidate.get("central_attr_samples", 0)
        central_x_entry_samples = (
            candidate.get("central_x_entry_11a2", 0)
            + candidate.get("central_x_entry_11a5", 0)
            + candidate.get("central_x_entry_db40", 0)
            + candidate.get("central_x_entry_11a0", 0)
        )
        (
            central_output_telemetry_ok,
            central_output_missing,
            central_output_missing_allowed,
            central_output_pending_tail,
        ) = central_output_telemetry_contract(
            candidate.get("central_emitter_hits", 0),
            central_x_entry_samples,
            central_attr_samples,
        )
        expected_dma_mode = args.expected_dma_mode or (
            "stage1-hblank" if target == 0 else "gdma"
        )
        candidate_dma_contract = dma_command_contract(
            candidate, dma_command_addrs, expected_dma_mode
        )
        dma_mode_ok = candidate_dma_contract["passed"]
        passed = (
            baseline_deterministic
            and candidate_deterministic
            and baseline["breakpoints_available"]
            and candidate["breakpoints_available"]
            and baseline["frames"] == args.frames
            and candidate["frames"] == args.frames
            and baseline["final_scene"] == target + 2
            and candidate["final_scene"] == target + 2
            and baseline["expected_scene_frames"] == args.frames
            and candidate_scene_ok
            and baseline_continuity_ok
            and candidate_continuity_ok
            and route_coverage_ok
            and central_output_telemetry_ok
            and dma_mode_ok
            and throughput["throughput_accepted"]
        )
        row = {
            "target": target,
            "stage": target + 1,
            "ratio": round(ratio, 4),
            "ratio_exact": ratio,
            "accepted_slowdown_floor": accepted_floor,
            **throughput,
            "candidate_scene_ok": candidate_scene_ok,
            "candidate_scene_mismatch_frames": candidate_scene_mismatch_frames,
            "candidate_dma_unreadable_scene_samples": (
                dma_unreadable_scene_samples
            ),
            "candidate_compiler_unreadable_scene_samples": (
                compiler_unreadable_scene_samples
            ),
            "candidate_non_dma_scene_mismatch_frames": (
                non_dma_scene_mismatch_frames
            ),
            "max_continuity_gap": max_continuity_gap,
            "baseline_continuity_ok": baseline_continuity_ok,
            "candidate_continuity_ok": candidate_continuity_ok,
            # Compatibility alias retained for old receipt consumers. It is a
            # diagnostic only; route_coverage_ok is the semantic gate.
            "scroll_parity_ok": scroll_change_count_parity,
            "scroll_change_count_parity": scroll_change_count_parity,
            "scroll_change_count_gate": False,
            "route_coverage_ok": route_coverage_ok,
            "route_coverage_strict_ok": route_coverage_strict_ok,
            "route_coverage_qualification": route_coverage_qualification,
            "route_coverage_comparison": route_comparison,
            "central_output_telemetry_ok": central_output_telemetry_ok,
            "central_x_entry_samples": central_x_entry_samples,
            "central_output_missing": central_output_missing,
            "central_output_missing_allowed": central_output_missing_allowed,
            "central_output_pending_tail": central_output_pending_tail,
            "candidate_dma_mode_ok": dma_mode_ok,
            "candidate_dma_command_contract": candidate_dma_contract,
            "deterministic_replay": (
                baseline_deterministic and candidate_deterministic
            ),
            "original_replay_receipt_sha256": [
                payload_sha256(result) for result in baseline_runs
            ],
            "dx_replay_receipt_sha256": [
                payload_sha256(result) for result in candidate_runs
            ],
            "passed": passed,
            "original": baseline,
            "dx": candidate,
        }
        rows.append(row)
        original_route = baseline["route_coverage"]
        dx_route = candidate["route_coverage"]
        route_policy = (
            "STRICT"
            if route_coverage_strict_ok
            else str(route_coverage_qualification["classification"])
        )
        print(
            f"Stage {target + 1}: original={baseline_hits} dx={candidate_hits} "
            f"ratio={ratio:.3f} scroll={baseline['scroll_changes']}/"
            f"{candidate['scroll_changes']} route="
            f"H{original_route['horizontal_mod16_distance']}/"
            f"{dx_route['horizontal_mod16_distance']} "
            f"V{original_route['vertical_mod16_distance']}/"
            f"{dx_route['vertical_mod16_distance']} "
            f"route-policy={route_policy} "
            f"target={'PASS' if throughput['target_met'] else 'MISS'} "
            f"{'PASS' if passed else 'FAIL'}"
        )
        if not passed:
            reasons = []
            if not throughput["throughput_accepted"]:
                reasons.append(f"throughput ratio {ratio:.3f}")
            if not baseline_deterministic:
                reasons.append("baseline replay mismatch")
            if not candidate_deterministic:
                reasons.append("candidate replay mismatch")
            if not candidate_scene_ok:
                reasons.append("scene mismatch")
            if not baseline_continuity_ok:
                reasons.append("baseline main-loop continuity missing")
            if not candidate_continuity_ok:
                reasons.append("candidate main-loop continuity missing")
            if not route_coverage_ok:
                original_final = original_route.get("final")
                dx_final = dx_route.get("final")
                reasons.append(
                    "route coverage mismatch "
                    f"H={original_route.get('horizontal_mod16_distance')}/"
                    f"{dx_route.get('horizontal_mod16_distance')} "
                    f"V={original_route.get('vertical_mod16_distance')}/"
                    f"{dx_route.get('vertical_mod16_distance')} "
                    f"first={original_route.get('first')}/"
                    f"{dx_route.get('first')} "
                    f"rooms={original_route.get('room_transition_sequence')}/"
                    f"{dx_route.get('room_transition_sequence')} "
                    f"final={original_final}/{dx_final}"
                )
            if not central_output_telemetry_ok:
                reasons.append(
                    "central OBJ output telemetry missing/incomplete "
                    f"entries={central_x_entry_samples} "
                    f"outputs={central_attr_samples}"
                )
            if not dma_mode_ok:
                failed_dma_checks = [
                    name for name, passed_check in
                    candidate_dma_contract.get("checks", {}).items()
                    if not passed_check
                ]
                reasons.append(
                    "candidate dungeon DMA command-site contract failed"
                    + (
                        ": " + ",".join(failed_dma_checks)
                        if failed_dma_checks else ""
                    )
                )
            failures.append(
                f"Stage {target + 1}: " + (", ".join(reasons) or "gate failed")
            )

    identity_controls = {
        "original_rom_unchanged": file_matches_sha256(
            original, initial_hashes["original_rom_sha256"]
        ),
        "dx_rom_unchanged": file_matches_sha256(
            dx, initial_hashes["dx_rom_sha256"]
        ),
        "verifier_unchanged": file_matches_sha256(
            verifier, initial_hashes["verifier_sha256"]
        ),
        "lua_probe_unchanged": file_matches_sha256(
            PROBE, initial_hashes["probe_sha256"]
        ),
        "mgba_launcher_unchanged": (
            True
            if tool_identity["mgba_launcher"]["sha256"] is None
            else resolved_mgba is not None
            and file_matches_sha256(
                resolved_mgba, tool_identity["mgba_launcher"]["sha256"]
            )
        ),
    }
    if not all(identity_controls.values()):
        failures.append("a ROM or verifier input changed during capture")

    manifest = {
        "schema": "penta-stage-speed-matrix-v2",
        "status": "pass" if not failures else "fail",
        "mode": args.input_mode,
        "frames": args.frames,
        "measurement_window": (
            "cpu-main-loop-anchor-synchronized-host-frames"
        ),
        "tolerance": args.tolerance,
        "target_ratio_floor": 1.0 - args.tolerance,
        "target_ratio_ceiling": 1.0 + args.tolerance,
        "accepted_slowdown_floor": args.accepted_slowdown_floor,
        "accepted_slow_stages": {
            str(stage): floor
            for stage, floor in sorted(accepted_slow_stages.items())
        },
        "dma_command_addr": (
            dma_command_addrs[0] if dma_command_addrs else 0
        ),
        "dma_command_addrs": dma_command_addrs,
        "expected_dma_mode": args.expected_dma_mode,
        "compiler_bank": args.compiler_bank,
        "compiler_start": args.compiler_start,
        "compiler_end": args.compiler_end,
        "invocation": invocation,
        "tool_identity": tool_identity,
        "input_identity_controls": identity_controls,
        "policy_controls": policy_controls,
        "route_policy_controls": route_controls,
        "central_output_policy_controls": output_policy_controls,
        "dma_command_policy_controls": dma_policy_controls,
        "scroll_change_count_policy": "diagnostic-only-cadence-sensitive",
        "route_coverage_policy": (
            "equal-mod16-distance-first-final-and-ordered-room-transitions"
        ),
        "room_transition_camera_policy": (
            "diagnostic-only-cadence-sensitive-across-og-dx"
        ),
        "original_rom_md5": initial_hashes["original_rom_md5"],
        "dx_rom_md5": initial_hashes["dx_rom_md5"],
        "original_rom_sha256": initial_hashes["original_rom_sha256"],
        "dx_rom_sha256": initial_hashes["dx_rom_sha256"],
        "verifier_sha256": initial_hashes["verifier_sha256"],
        "probe_sha256": initial_hashes["probe_sha256"],
        "rows": rows,
        "failures": failures,
    }
    manifest_path = output / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n")
    if failures:
        print("FAIL:")
        for failure in failures:
            print(f"  - {failure}")
        print(f"Receipt: {manifest_path}")
        return 1
    print(
        "PASS: selected stage-speed matrix meets the target or the explicit "
        "accepted slowdown floor."
    )
    print(f"Receipt: {manifest_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
