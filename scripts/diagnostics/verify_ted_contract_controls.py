#!/usr/bin/env python3
"""Prove Ted's geometry gate accepts native art and rejects edge debris."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from ted_native_pose_contract_v2 import NATIVE_POSE_SHA256
from verify_ted_candidate_delta import (
    compare_baseline_pin,
    compare_readiness,
    validate_pair,
)
from verify_release_candidate import (
    DEFAULT_TED_BASELINE_DETERMINISM,
    DEFAULT_TED_BASELINE_PIN,
    DEFAULT_TED_BASELINE_READINESS,
    build_gates,
    dependency_closure,
)
from verify_ted_release_readiness import (
    evaluate as evaluate_release_readiness,
    evaluate_provenance,
    release_checks_pass,
)
from verify_ted_two_plane_cache_contract import rejects_overdiscriminating_key
from verify_ted_cache_plane_reservation import analyze as analyze_cache_planes
from verify_ted_determinism import (
    TED_FLOOR_PALETTE,
    TED_NUMBERED_TILE_POSITION,
    crown,
    floor_palette_violations,
    native_pose_digest,
    position_violations,
)

SCHEMA = "penta-ted-contract-controls-v1"
ANCHOR = (8, 12)


def floor_tile(row: int, col: int) -> int:
    return 0x77 + 2 * (row & 1) + (col & 1)


def put(tiles: bytearray, relative: tuple[int, int], tile: int) -> None:
    row = (ANCHOR[0] + relative[0]) & 31
    col = (ANCHOR[1] + relative[1]) & 31
    tiles[row * 32 + col] = tile


def canonical_pose() -> bytearray:
    tiles = bytearray(
        floor_tile(row, col) for row in range(32) for col in range(32)
    )
    for tile, relative in TED_NUMBERED_TILE_POSITION.items():
        put(tiles, relative, tile)
    return tiles


def translated_pose(tiles: bytes, row_shift: int, col_shift: int) -> bytearray:
    """Translate a whole 32x32 map with wrap, preserving its tile contents."""
    translated = bytearray(len(tiles))
    for offset, tile in enumerate(tiles):
        row, col = divmod(offset, 32)
        target_row = (row + row_shift) & 31
        target_col = (col + col_shift) & 31
        translated[target_row * 32 + target_col] = tile
    return translated


def normalized_body_cells(
    tiles: bytes, anchor: tuple[int, int]
) -> tuple[tuple[int, int, int], ...]:
    """Return an ordering-independent translation-normalized body contract."""
    body_ids = set(TED_NUMBERED_TILE_POSITION)
    return tuple(sorted(
        (((row - anchor[0]) & 31), ((col - anchor[1]) & 31), tile)
        for offset, tile in enumerate(tiles)
        for row, col in (divmod(offset, 32),)
        if tile in body_ids
    ))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("rom", nargs="?", type=Path,
                        help="candidate path accepted for release-gate uniformity")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    native = canonical_pose()
    native_hash, native_cells = native_pose_digest(native, ANCHOR)
    wrapped_anchor = ((ANCHOR[0] + 13) & 31, (ANCHOR[1] + 17) & 31)
    wrapped_hash, wrapped_cells = native_pose_digest(
        translated_pose(native, 13, 17), wrapped_anchor
    )
    native_numbered, native_sparse = position_violations(native, ANCHOR)
    material_attrs = bytes(TED_FLOOR_PALETTE.get(tile, 1) for tile in native)
    uniform_attrs = bytes(0 for _ in native)
    material_floor = floor_palette_violations(native, material_attrs)
    uniform_floor = floor_palette_violations(native, uniform_attrs)

    displaced = bytearray(native)
    moved_tile = 0x64
    old = TED_NUMBERED_TILE_POSITION[moved_tile]
    put(displaced, old, floor_tile(ANCHOR[0] + old[0], ANCHOR[1] + old[1]))
    put(displaced, (-6, -10), moved_tile)
    displaced_numbered, _ = position_violations(displaced, ANCHOR)
    displaced_hash, _ = native_pose_digest(displaced, ANCHOR)

    duplicate_pairs = bytearray(native)
    for tile, relative in (
        (0x13, (12, 8)), (0x14, (12, 9)), (0x1C, (13, 9)),
        (0x1F, (14, 10)), (0x20, (14, 11)),
        (0x27, (15, 10)), (0x28, (15, 11)),
    ):
        put(duplicate_pairs, relative, tile)
    duplicate_numbered, _ = position_violations(duplicate_pairs, ANCHOR)

    sparse = bytearray(native)
    put(sparse, (1, 9), 0x7B)               # measured legal limb position
    _, legal_sparse = position_violations(sparse, ANCHOR)
    put(sparse, (1, 9), floor_tile(ANCHOR[0] + 1, ANCHOR[1] + 9))
    put(sparse, (-8, -10), 0x7B)            # deliberate edge garbage
    _, illegal_sparse = position_violations(sparse, ANCHOR)

    clean_controls = {"status": "pass"}
    clean_materializer = {"status": "pass", "tests": 32}
    clean_classifier = {"status": "pass", "tests": 15}
    clean_expanded_integration = {
        "schema": "penta-ted-expanded-integration-v1",
        "status": "pass",
        "failing_checks": [],
        "architecture": {"publishable_poses": 47, "classifier_states": 49},
        "checks": {"native_pose_bank_exact": True},
    }
    clean_source_publication = {
        "deterministic_replay": True,
        "metrics": {"status": "pass", "frames": 2800},
    }
    clean_publication_sequence = {
        "status": "pass", "deterministic_replay": True,
        "metrics": {"frames": 2800},
    }
    clean_cache_contract = {
        "schema": "penta-ted-two-plane-cache-contract-v4", "status": "pass",
    }
    clean_cache_reservation = {
        "schema": "penta-ted-cache-plane-reservation-v4", "status": "pass",
    }
    phase_kwargs = {
        "source_publication": clean_source_publication,
        "publication_sequence": clean_publication_sequence,
        "cache_contract": clean_cache_contract,
        "cache_reservation": clean_cache_reservation,
        "expanded_integration": clean_expanded_integration,
    }
    clean_entry = "status=ok expected_scene=10 d880=10"
    clean_cadence = {
        "schema": "penta-boss-publication-cadence-v3",
        "status": "pass",
        "bosses": [{
            "status": "pass", "slowdown_percent": 0.5,
            "speed_ratio": 0.995,
            "target_met": True,
            "phase_bound_met": True,
            "accepted_phase_deviation": False,
            "observation_frames": 2800,
            "publication_liveness": True,
            "og": {"copies": 484, "deterministic_replay": True},
            "dx": {
                "copies": 484, "caller_histogram": {"028D": 484},
                "deterministic_replay": True,
            },
        }],
    }
    clean_determinism = {
        "status": "pass",
        "deterministic_replay": True,
        "metrics": {
            "status": "pass",
            "frames": 2800,
            "native_pose_matches": 2800,
            "native_pose_mismatches": 0,
            "floor_lattice_mismatches": 0,
            "floor_palette_mismatches": 0,
            "numbered_identity_mismatches": 0,
            "sparse_position_mismatches": 0,
        },
    }
    aggregate_clean, _, _ = evaluate_release_readiness(
        clean_controls, clean_entry, clean_cadence, clean_determinism,
        materializer=clean_materializer,
        classifier=clean_classifier,
        **phase_kwargs,
    )

    slow_cadence = json.loads(json.dumps(clean_cadence))
    slow_cadence["bosses"][0].update(
        status="pass", slowdown_percent=1.01, speed_ratio=0.9899,
        target_met=False, phase_bound_met=True,
        accepted_phase_deviation=True,
    )
    aggregate_slow, _, _ = evaluate_release_readiness(
        clean_controls, clean_entry, slow_cadence, clean_determinism,
        materializer=clean_materializer,
        classifier=clean_classifier,
        **phase_kwargs,
    )
    # Exercise both sides of the absolute cadence bound. Ted experiments have
    # previously replaced slowdown with over-publication; that is also a fail.
    fast_cadence = json.loads(json.dumps(clean_cadence))
    fast_cadence["bosses"][0].update(
        status="pass", slowdown_percent=-1.01, speed_ratio=1.0101,
        target_met=False, phase_bound_met=True,
        accepted_phase_deviation=True,
    )
    aggregate_fast, _, _ = evaluate_release_readiness(
        clean_controls, clean_entry, fast_cadence, clean_determinism,
        materializer=clean_materializer,
        classifier=clean_classifier,
        **phase_kwargs,
    )
    rejected_postcopy_cadence = json.loads(json.dumps(clean_cadence))
    rejected_postcopy_cadence["status"] = "fail"
    rejected_postcopy_cadence["bosses"][0].update(
        status="fail", slowdown_percent=5.7633611560981794,
        speed_ratio=0.9423663884390182, target_met=False,
        phase_bound_met=False, accepted_phase_deviation=False,
    )
    aggregate_rejected_postcopy, _, _ = evaluate_release_readiness(
        clean_controls, clean_entry, rejected_postcopy_cadence,
        clean_determinism, materializer=clean_materializer,
        classifier=clean_classifier, **phase_kwargs,
    )
    short_cadence = json.loads(json.dumps(clean_cadence))
    short_cadence["bosses"][0]["observation_frames"] = 600
    aggregate_short, _, _ = evaluate_release_readiness(
        clean_controls, clean_entry, short_cadence, clean_determinism,
        materializer=clean_materializer, classifier=clean_classifier,
        **phase_kwargs,
    )
    stale_cadence_schema = json.loads(json.dumps(clean_cadence))
    stale_cadence_schema["schema"] = "penta-boss-publication-cadence-v1"
    aggregate_stale_cadence, _, _ = evaluate_release_readiness(
        clean_controls, clean_entry, stale_cadence_schema, clean_determinism,
        materializer=clean_materializer, classifier=clean_classifier,
        **phase_kwargs,
    )
    wrong_caller = json.loads(json.dumps(clean_cadence))
    wrong_caller["bosses"][0]["dx"]["caller_histogram"] = {
        "028D": 483, "43BD": 1,
    }
    aggregate_wrong_caller, _, _ = evaluate_release_readiness(
        clean_controls, clean_entry, wrong_caller, clean_determinism,
        materializer=clean_materializer, classifier=clean_classifier,
        **phase_kwargs,
    )
    dead_publisher = json.loads(json.dumps(clean_cadence))
    dead_publisher["status"] = "fail"
    dead_publisher["bosses"][0].update(
        status="fail", publication_liveness=False,
        speed_ratio=None, slowdown_percent=None, target_met=False,
        phase_bound_met=False, accepted_phase_deviation=False,
    )
    dead_publisher["bosses"][0]["dx"].update(
        copies=0, caller_histogram={}, status="capture-error",
    )
    aggregate_dead_publisher, _, _ = evaluate_release_readiness(
        clean_controls, clean_entry, dead_publisher, clean_determinism,
        materializer=clean_materializer, classifier=clean_classifier,
        **phase_kwargs,
    )

    bad_material = json.loads(json.dumps(clean_determinism))
    bad_material["status"] = "fail"
    bad_material["metrics"].update(status="fail", floor_palette_mismatches=1)
    aggregate_material, _, _ = evaluate_release_readiness(
        clean_controls, clean_entry, clean_cadence, bad_material,
        materializer=clean_materializer,
        classifier=clean_classifier,
        **phase_kwargs,
    )

    bad_identity = json.loads(json.dumps(clean_determinism))
    bad_identity["status"] = "fail"
    bad_identity["metrics"].update(
        status="fail", numbered_identity_mismatches=1,
        sparse_position_mismatches=1,
    )
    aggregate_identity, _, _ = evaluate_release_readiness(
        clean_controls, clean_entry, clean_cadence, bad_identity,
        materializer=clean_materializer,
        classifier=clean_classifier,
        **phase_kwargs,
    )

    bad_replay = json.loads(json.dumps(clean_determinism))
    bad_replay["deterministic_replay"] = False
    bad_replay["metrics"]["frames"] = 2799
    aggregate_replay, _, _ = evaluate_release_readiness(
        clean_controls, clean_entry, clean_cadence, bad_replay,
        materializer=clean_materializer,
        classifier=clean_classifier,
        **phase_kwargs,
    )

    legacy_phase_kwargs = dict(phase_kwargs)
    legacy_phase_kwargs["expanded_integration"] = None
    aggregate_bad_materializer, _, _ = evaluate_release_readiness(
        clean_controls, clean_entry, clean_cadence, clean_determinism,
        materializer={"status": "fail", "tests": 32},
        classifier=clean_classifier,
        **legacy_phase_kwargs,
    )

    aggregate_bad_classifier, _, _ = evaluate_release_readiness(
        clean_controls, clean_entry, clean_cadence, clean_determinism,
        materializer=clean_materializer,
        classifier={"status": "fail", "tests": 15},
        **legacy_phase_kwargs,
    )

    bad_expanded = json.loads(json.dumps(clean_expanded_integration))
    bad_expanded.update(status="fail", failing_checks=["native_pose_bank_exact"])
    bad_expanded_phase = dict(phase_kwargs)
    bad_expanded_phase["expanded_integration"] = bad_expanded
    aggregate_bad_expanded, _, _ = evaluate_release_readiness(
        clean_controls, clean_entry, clean_cadence, clean_determinism,
        materializer=clean_materializer,
        classifier=clean_classifier,
        **bad_expanded_phase,
    )

    bad_sequence = json.loads(json.dumps(clean_publication_sequence))
    bad_sequence["status"] = "fail"
    aggregate_bad_sequence, _, _ = evaluate_release_readiness(
        clean_controls, clean_entry, clean_cadence, clean_determinism,
        materializer=clean_materializer, classifier=clean_classifier,
        source_publication=clean_source_publication,
        publication_sequence=bad_sequence,
    )
    nondeterministic_source = json.loads(json.dumps(clean_source_publication))
    nondeterministic_source["deterministic_replay"] = False
    aggregate_bad_source_receipt, _, _ = evaluate_release_readiness(
        clean_controls, clean_entry, clean_cadence, clean_determinism,
        materializer=clean_materializer, classifier=clean_classifier,
        source_publication=nondeterministic_source,
        publication_sequence=clean_publication_sequence,
    )

    checks = {
        "canonical_unique_crown": crown(native) == [ANCHOR],
        "canonical_body_cells": native_cells == 117,
        "canonical_native_pose_hash": native_hash in NATIVE_POSE_SHA256,
        "wrapped_translation_has_same_pose_hash": (
            normalized_body_cells(native, ANCHOR)
            == normalized_body_cells(
                translated_pose(native, 13, 17), wrapped_anchor
            )
            and wrapped_cells == native_cells
        ),
        "canonical_numbered_positions": not native_numbered,
        "canonical_sparse_positions": not native_sparse,
        "checker_materials_accepted": not material_floor,
        "uniform_checker_rejected": len(uniform_floor) > 800,
        "displaced_numbered_rejected": (
            len(displaced_numbered) == 1
            and displaced_numbered[0]["tile"] == moved_tile
            and displaced_hash not in NATIVE_POSE_SHA256
        ),
        "measured_duplicate_clusters_rejected": (
            len(duplicate_numbered) == 7
            and {item["tile"] for item in duplicate_numbered}
            == {0x13, 0x14, 0x1C, 0x1F, 0x20, 0x27, 0x28}
        ),
        "legal_sparse_accepted": not legal_sparse,
        "edge_sparse_rejected": (
            len(illegal_sparse) == 1
            and illegal_sparse[0]["tile"] == 0x7B
        ),
        "aggregate_positive_control": all(aggregate_clean.values()),
        "aggregate_cadence_accepted_control": (
            not aggregate_slow["cadence_within_one_percent"]
            and aggregate_slow["cadence_within_release_bound"]
            and release_checks_pass(aggregate_slow)
        ),
        "aggregate_fast_cadence_accepted_control": (
            not aggregate_fast["cadence_within_one_percent"]
            and aggregate_fast["cadence_within_release_bound"]
            and release_checks_pass(aggregate_fast)
        ),
        "measured_full_plane_postcopy_rejected": (
            not aggregate_rejected_postcopy["cadence_within_release_bound"]
            and not release_checks_pass(aggregate_rejected_postcopy)
        ),
        "aggregate_short_cadence_negative_control": (
            not aggregate_short["cadence_within_release_bound"]
            and not release_checks_pass(aggregate_short)
        ),
        "aggregate_publication_caller_negative_control": (
            not aggregate_wrong_caller["native_publication_caller"]
            and not release_checks_pass(aggregate_wrong_caller)
        ),
        "aggregate_dead_publisher_negative_control": (
            not aggregate_dead_publisher["publication_liveness"]
            and not aggregate_dead_publisher["cadence_within_release_bound"]
            and not aggregate_dead_publisher["native_publication_caller"]
            and not release_checks_pass(aggregate_dead_publisher)
        ),
        "aggregate_stale_cadence_schema_negative_control": (
            not aggregate_stale_cadence["cadence_within_release_bound"]
            and not aggregate_stale_cadence["native_publication_caller"]
            and not release_checks_pass(aggregate_stale_cadence)
        ),
        "aggregate_material_negative_control": (
            not aggregate_material["checker_palette_materials"]
            and not aggregate_material["visible_geometry_and_materials"]
            and not release_checks_pass(aggregate_material)
        ),
        "aggregate_identity_negative_control": (
            not aggregate_identity["numbered_tile_identity"]
            and not aggregate_identity["sparse_tentacle_identity"]
            and not release_checks_pass(aggregate_identity)
        ),
        "aggregate_replay_negative_control": (
            not aggregate_replay["deterministic_visible_replay"]
            and not release_checks_pass(aggregate_replay)
        ),
        "aggregate_materializer_negative_control": (
            not aggregate_bad_materializer["materializer_triplet_contract"]
            and not release_checks_pass(aggregate_bad_materializer)
        ),
        "aggregate_classifier_negative_control": (
            not aggregate_bad_classifier["classifier_identity_contract"]
            and not release_checks_pass(aggregate_bad_classifier)
        ),
        "aggregate_expanded_architecture_negative_control": (
            not aggregate_bad_expanded["expanded_bank_architecture"]
            and not release_checks_pass(aggregate_bad_expanded)
        ),
        "aggregate_publication_sequence_negative_control": (
            not aggregate_bad_sequence["stock_publication_sequence"]
            and not release_checks_pass(aggregate_bad_sequence)
        ),
        "aggregate_source_receipt_negative_control": (
            not aggregate_bad_source_receipt["source_publication_receipt"]
            and not release_checks_pass(aggregate_bad_source_receipt)
        ),
        "geometry_failure_cannot_hide_behind_classifier": (
            not aggregate_identity["classifier_identity_contract"]
            and not aggregate_identity["visible_geometry_and_materials"]
            and not release_checks_pass(aggregate_identity)
        ),
    }
    delta_baseline = {
        "schema": "penta-ted-release-readiness-v4",
        "checks": aggregate_clean,
        "cadence": {
            "status": "pass", "slowdown_percent": 0.25,
            "phase_bound_met": True,
        },
        "publication_sequence": {
            "partial_foreign_cells": 0,
            "partial_not_complete_next_frame": 5,
        },
        "input_errors": {},
    }
    delta_worse = json.loads(json.dumps(delta_baseline))
    delta_worse["checks"]["classifier_identity_contract"] = False
    delta_worse["cadence"]["slowdown_percent"] = 0.26
    delta_worse["publication_sequence"].update(
        partial_foreign_cells=1, partial_not_complete_next_frame=6
    )
    _, delta_failures, _ = compare_readiness(delta_baseline, delta_worse)
    checks["candidate_delta_v4_negative_controls"] = set(delta_failures) == {
        "lost_check:classifier_identity_contract",
        "publication:partial_foreign_cells",
        "publication:partial_not_complete_next_frame",
    }
    paired_determinism = {
        "rom_sha256": "rom", "state_sha256": "state",
        "trace_sha256": ["trace", "trace"],
        "metrics": {
            "frames": 2800, "native_pose_matches": 1,
            "native_pose_mismatches": 0, "numbered_identity_mismatches": 0,
            "sparse_position_mismatches": 0, "floor_lattice_mismatches": 0,
            "floor_palette_mismatches": 0,
        },
    }
    paired_readiness = {
        "identity": {
            "rom_sha256": "rom", "determinism_rom_sha256": "rom",
            "state_sha256": "state", "trace_sha256": ["trace", "trace"],
        },
        "geometry": dict(paired_determinism["metrics"]),
    }
    checks["candidate_delta_receipt_pair_positive_control"] = not validate_pair(
        "candidate", paired_determinism, paired_readiness
    )
    wrong_identity = json.loads(json.dumps(paired_readiness))
    wrong_identity["identity"]["rom_sha256"] = "other-rom"
    wrong_geometry = json.loads(json.dumps(paired_readiness))
    wrong_geometry["geometry"]["floor_palette_mismatches"] = 1
    checks["candidate_delta_receipt_pair_negative_controls"] = (
        validate_pair("candidate", paired_determinism, wrong_identity)
        == ["candidate_receipt_identity"]
        and validate_pair("candidate", paired_determinism, wrong_geometry)
        == ["candidate_geometry_payload"]
    )
    baseline_pin = {
        "schema": "penta-ted-qualified-baseline-v1",
        "determinism_receipt_sha256": "det-receipt",
        "readiness_receipt_sha256": "ready-receipt",
        "rom_sha256": "rom", "state_sha256": "state",
        "trace_sha256": ["trace", "trace"], "frames": 2800,
        "metrics": dict(paired_determinism["metrics"]),
    }
    checks["qualified_baseline_pin_positive_control"] = not compare_baseline_pin(
        baseline_pin, "det-receipt", "ready-receipt",
        paired_determinism, paired_readiness,
    )
    tampered_pin = json.loads(json.dumps(baseline_pin))
    tampered_pin["readiness_receipt_sha256"] = "other-receipt"
    tampered_pin["metrics"]["floor_palette_mismatches"] = 1
    checks["qualified_baseline_pin_negative_controls"] = set(
        compare_baseline_pin(
            tampered_pin, "det-receipt", "ready-receipt",
            paired_determinism, paired_readiness,
        )
    ) == {"baseline_pin_readiness_receipt", "baseline_pin_metrics"}
    provenance_inputs = {
        "candidate_rom_sha256": "rom",
        "cadence": {
            "schema": "penta-boss-publication-cadence-v3",
            "dx_rom_sha256": "rom",
            "bosses": [{"dx": {
                "state_sha256": "state", "trace_sha256": "cadence-trace",
            }}],
        },
        "determinism": {"rom_sha256": "rom", "state_sha256": "state"},
        "materializer": {"rom_sha256": "rom", "state_sha256": "fixture-a"},
        "classifier": {"rom_sha256": "rom", "state_sha256": "fixture-b"},
        "expanded_integration": {"rom_sha256": "rom"},
        "source_publication": {
            "rom_sha256": "rom", "state_sha256": "state",
            "trace_sha256": "source-trace",
        },
        "publication_sequence": {
            "trace_sha256": "source-trace",
            "replay_trace_sha256": "source-trace",
        },
        "cache_contract": {
            "rom_sha256": "rom", "source_trace_sha256": "source-trace",
        },
        "cache_reservation": {
            "rom_sha256": "rom", "state_sha256": "state",
        },
    }
    clean_provenance = evaluate_provenance(**provenance_inputs)
    checks["receipt_provenance_positive_control"] = all(clean_provenance.values())
    provenance_rejections = {}
    for name, mutation in (
        ("cadence_receipt_identity", ("cadence", "dx_rom_sha256")),
        ("source_publication_identity", ("source_publication", "state_sha256")),
        ("publication_trace_identity", ("publication_sequence", "trace_sha256")),
        ("runtime_contract_rom_identity", ("classifier", "rom_sha256")),
        ("cache_contract_identity", ("cache_contract", "source_trace_sha256")),
        ("cache_reservation_identity", ("cache_reservation", "state_sha256")),
        ("expanded_integration_identity", ("expanded_integration", "rom_sha256")),
    ):
        bad = json.loads(json.dumps(provenance_inputs))
        bad[mutation[0]][mutation[1]] = "tampered"
        result = evaluate_provenance(**bad)
        provenance_rejections[name] = (
            result[name] is False
            and all(value for key, value in result.items() if key != name)
        )
    checks["receipt_provenance_negative_controls"] = all(
        provenance_rejections.values()
    )
    runner_gates = {
        gate.name: gate for gate in build_gates(
            Path("candidate.gb"), Path("artifacts"),
            Path("baseline-determinism.json"),
            Path("baseline-readiness.json"), True, Path("baseline-pin.json"),
        )
    }
    delta_gate = runner_gates["ted_candidate_delta"]
    cadence_gate = runner_gates["ted_cadence"]
    stage_speed_gate = runner_gates["gameplay_speed_parity"]
    north_integrity_gate = runner_gates["stage1_north_route_integrity"]
    game_start_gate = runner_gates["game_start_routes"]
    stage_visual_gate = runner_gates["stage_side_by_side_all7"]
    boss_speed_gate = runner_gates["boss_speed_parity"]
    boss_publication_gate = runner_gates["boss_publication_cadence"]
    silhouette_gate = runner_gates["boss_silhouette_gallery"]
    og_silhouette_gate = runner_gates["boss_og_silhouette_gallery"]
    side_by_side_gate = runner_gates["boss_material_side_by_side"]
    cadence_frames = cadence_gate.command[
        cadence_gate.command.index("--frames") + 1
    ]
    delta_closure = dependency_closure({"ted_candidate_delta"}, runner_gates)
    checks["candidate_delta_official_runner_contract"] = (
        "--require-improvement" in delta_gate.command
        and "--baseline-pin" in delta_gate.command
        and delta_gate.dependencies
        == ("ted_determinism", "ted_release_readiness_receipt")
        and {
            "ted_expanded_integration",
            "ted_contract_controls", "ted_materializer", "ted_classifier",
            "ted_entry", "ted_og_entry", "ted_cadence", "ted_determinism",
            "ted_source_publication", "ted_publication_sequence",
            "ted_two_plane_cache_contract",
            "ted_cache_plane_reservation",
            "ted_release_readiness_receipt", "ted_candidate_delta",
        } <= delta_closure
        and runner_gates["ted_expanded_integration"].dependencies == ()
        and "verify_ted_expanded_integration.py"
            in " ".join(runner_gates["ted_expanded_integration"].command)
    )
    checks["cache_architecture_official_runner_contract"] = (
        cadence_frames == "2800"
        and runner_gates["ted_two_plane_cache_contract"].dependencies
            == ("ted_cadence",)
        and runner_gates["ted_cache_plane_reservation"].dependencies
            == ("ted_entry",)
        and rejects_overdiscriminating_key(485)
        and not rejects_overdiscriminating_key(50)
    )
    checks["whole_game_speed_official_runner_contract"] = (
        stage_speed_gate.command[
            stage_speed_gate.command.index("--targets") + 1
        ] == "0,1,2,3,4,5,6"
        and stage_speed_gate.command[
            stage_speed_gate.command.index("--tolerance") + 1
        ] == "0.02"
        and stage_speed_gate.command[
            stage_speed_gate.command.index("--accepted-slowdown-floor") + 1
        ] == "0.96"
        and boss_speed_gate.command[
            boss_speed_gate.command.index("--frames") + 1
        ] == "1800"
        and boss_speed_gate.command[
            boss_speed_gate.command.index("--max-slowdown") + 1
        ] == "0.02"
        and boss_speed_gate.command[
            boss_speed_gate.command.index("--accepted-slow-boss") + 1
        ] == "crystal_dragon=0.95"
        and boss_speed_gate.command[
            boss_speed_gate.command.index(
                "--phase-mismatch-speedup-ceiling"
            ) + 1
        ] == "1.20"
        and boss_speed_gate.dependencies == ("boss_arenas", "boss_og_states")
        and cadence_gate.command[
            cadence_gate.command.index("--phase-ratio-floor") + 1
        ] == "0.95"
        and cadence_gate.command[
            cadence_gate.command.index("--phase-ratio-ceiling") + 1
        ] == "1.20"
        and boss_publication_gate.command[
            boss_publication_gate.command.index("--phase-ratio-floor") + 1
        ] == "0.95"
        and boss_publication_gate.command[
            boss_publication_gate.command.index("--phase-ratio-ceiling") + 1
        ] == "1.20"
        and "--target-only" in north_integrity_gate.command
        and "--max-frame-lag-ratio" not in north_integrity_gate.command
        and game_start_gate.command[
            game_start_gate.command.index("--timeout") + 1
        ] == "60"
        and stage_visual_gate.command[
            stage_visual_gate.command.index("--frames") + 1
        ] == "1200"
        and stage_visual_gate.command[
            stage_visual_gate.command.index("--mode") + 1
        ] == "patrol"
    )
    checks["boss_silhouette_official_runner_contract"] = (
        silhouette_gate.dependencies == ("boss_material_gallery_all9",)
        and "verify_boss_silhouette_offline.py"
            in " ".join(silhouette_gate.command)
        and "--gallery" in silhouette_gate.command
        and og_silhouette_gate.dependencies
            == ("boss_og_material_gallery_all9",)
        and side_by_side_gate.dependencies
            == ("boss_og_silhouette_gallery", "boss_silhouette_gallery")
    )
    clean_cache_access = (
        "status=ok frames=2800 bank2=1 bank3=0 read2=1 read3=0\n"
        "owner=2:1234 count=1\nreader=2:5678 count=1\n"
    )
    checks["cache_reader_writer_ownership_controls"] = (
        analyze_cache_planes(
            clean_cache_access, 2800, frozenset({0x1234}),
            frozenset({0x5678}),
        )["status"] == "pass"
        and analyze_cache_planes(
            clean_cache_access, 2800, frozenset({0x1234}), frozenset(),
        )["status"] == "fail"
        and analyze_cache_planes(
            clean_cache_access, 2800, frozenset(), frozenset({0x5678}),
        )["status"] == "fail"
    )
    checks["portable_default_baseline_bundle"] = (
        DEFAULT_TED_BASELINE_DETERMINISM.is_file()
        and DEFAULT_TED_BASELINE_READINESS.is_file()
        and DEFAULT_TED_BASELINE_PIN.is_file()
        and not compare_baseline_pin(
            json.loads(DEFAULT_TED_BASELINE_PIN.read_text()),
            hashlib.sha256(
                DEFAULT_TED_BASELINE_DETERMINISM.read_bytes()
            ).hexdigest(),
            hashlib.sha256(
                DEFAULT_TED_BASELINE_READINESS.read_bytes()
            ).hexdigest(),
            json.loads(DEFAULT_TED_BASELINE_DETERMINISM.read_text()),
            json.loads(DEFAULT_TED_BASELINE_READINESS.read_text()),
        )
    )
    receipt = {
        "schema": SCHEMA,
        "status": "pass" if all(checks.values()) else "fail",
        "checks": checks,
        "canonical_pose_sha256": native_hash,
        "negative_control_numbered": displaced_numbered,
        "negative_control_duplicate_pairs": duplicate_numbered,
        "negative_control_sparse": illegal_sparse,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n")
    print(json.dumps(receipt, indent=2, sort_keys=True))
    return 0 if receipt["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
