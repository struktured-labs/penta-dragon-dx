#!/usr/bin/env python3
"""Consolidate every official Ted release invariant into one receipt."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

SCHEMA = "penta-ted-release-readiness-v4"
CADENCE_SCHEMA = "penta-boss-publication-cadence-v3"


def load_json(path: Path) -> tuple[dict[str, object] | None, str | None]:
    if not path.is_file():
        return None, "missing"
    try:
        value = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError) as error:
        return None, f"invalid: {error}"
    if not isinstance(value, dict):
        return None, "invalid: root is not an object"
    return value, None


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def evaluate_provenance(
    candidate_rom_sha256: str | None,
    cadence: dict[str, object] | None,
    determinism: dict[str, object] | None,
    materializer: dict[str, object] | None,
    classifier: dict[str, object] | None,
    source_publication: dict[str, object] | None,
    publication_sequence: dict[str, object] | None,
    cache_contract: dict[str, object] | None,
    cache_reservation: dict[str, object] | None,
) -> dict[str, bool]:
    state_sha256 = determinism.get("state_sha256") if determinism else None
    bosses = cadence.get("bosses", []) if cadence else []
    ted = bosses[0] if len(bosses) == 1 else {}
    ted_dx = ted.get("dx", {}) if isinstance(ted, dict) else {}
    source_trace = (
        source_publication.get("trace_sha256") if source_publication else None
    )
    return {
        "candidate_rom_identity": candidate_rom_sha256 is not None
            and determinism is not None
            and determinism.get("rom_sha256") == candidate_rom_sha256,
        "cadence_receipt_identity": cadence is not None
            and cadence.get("schema") == CADENCE_SCHEMA
            and cadence.get("dx_rom_sha256") == candidate_rom_sha256
            and isinstance(ted_dx, dict)
            and ted_dx.get("state_sha256") == state_sha256
            and isinstance(ted_dx.get("trace_sha256"), str),
        "source_publication_identity": source_publication is not None
            and source_publication.get("rom_sha256") == candidate_rom_sha256
            and source_publication.get("state_sha256") == state_sha256
            and isinstance(source_publication.get("trace_sha256"), str),
        "publication_trace_identity": publication_sequence is not None
            and publication_sequence.get("trace_sha256") == source_trace
            and publication_sequence.get("replay_trace_sha256") == source_trace,
        "runtime_contract_rom_identity": materializer is not None
            and classifier is not None
            and materializer.get("rom_sha256") == candidate_rom_sha256
            and classifier.get("rom_sha256") == candidate_rom_sha256
            and isinstance(materializer.get("state_sha256"), str)
            and isinstance(classifier.get("state_sha256"), str),
        "cache_contract_identity": cache_contract is not None
            and cache_contract.get("rom_sha256") == candidate_rom_sha256
            and cache_contract.get("source_trace_sha256") == source_trace,
        "cache_reservation_identity": cache_reservation is not None
            and cache_reservation.get("rom_sha256") == candidate_rom_sha256
            and cache_reservation.get("state_sha256") == state_sha256,
    }


def evaluate(
    controls: dict[str, object] | None,
    entry_text: str,
    cadence: dict[str, object] | None,
    determinism: dict[str, object] | None,
    *,
    materializer: dict[str, object] | None = None,
    classifier: dict[str, object] | None = None,
    source_publication: dict[str, object] | None = None,
    publication_sequence: dict[str, object] | None = None,
    cache_contract: dict[str, object] | None = None,
    cache_reservation: dict[str, object] | None = None,
    controls_error: str | None = None,
    cadence_error: str | None = None,
    determinism_error: str | None = None,
    materializer_error: str | None = None,
    classifier_error: str | None = None,
    source_publication_error: str | None = None,
    publication_sequence_error: str | None = None,
    cache_contract_error: str | None = None,
    cache_reservation_error: str | None = None,
) -> tuple[dict[str, bool], dict[str, object], dict[str, object]]:
    """Return aggregate checks plus the selected cadence and geometry rows."""
    cadence_bosses = cadence.get("bosses", []) if cadence else []
    ted_cadence = cadence_bosses[0] if len(cadence_bosses) == 1 else {}
    metrics = determinism.get("metrics", {}) if determinism else {}
    checks = {
        "contract_controls": controls_error is None
            and controls is not None and controls.get("status") == "pass",
        "materializer_triplet_contract": materializer_error is None
            and materializer is not None and materializer.get("status") == "pass"
            and materializer.get("tests") == 32,
        "classifier_identity_contract": classifier_error is None
            and classifier is not None and classifier.get("status") == "pass"
            and classifier.get("tests") == 15,
        "source_publication_receipt": source_publication_error is None
            and source_publication is not None
            and source_publication.get("deterministic_replay") is True
            and source_publication.get("metrics", {}).get("frames") == 2800,
        "stock_publication_sequence": publication_sequence_error is None
            and publication_sequence is not None
            and publication_sequence.get("status") == "pass"
            and publication_sequence.get("deterministic_replay") is True
            and publication_sequence.get("metrics", {}).get("frames") == 2800,
        "two_plane_cache_contract": cache_contract_error is None
            and cache_contract is not None
            and cache_contract.get("status") == "pass"
            and cache_contract.get("schema")
                == "penta-ted-two-plane-cache-contract-v4",
        "cache_plane_ownership": cache_reservation_error is None
            and cache_reservation is not None
            and cache_reservation.get("status") == "pass"
            and cache_reservation.get("schema")
                == "penta-ted-cache-plane-reservation-v4",
        "entry_fixture": "status=ok" in entry_text
            and "expected_scene=10" in entry_text
            and "d880=10" in entry_text,
        "publication_liveness": cadence_error is None
            and cadence is not None
            and ted_cadence.get("publication_liveness") is True
            and int(ted_cadence.get("og", {}).get("copies", 0)) >= 8
            and int(ted_cadence.get("dx", {}).get("copies", 0)) >= 8,
        "cadence_within_one_percent": cadence_error is None
            and cadence is not None and cadence.get("status") == "pass"
            and cadence.get("schema") == CADENCE_SCHEMA
            and ted_cadence.get("status") == "pass"
            and ted_cadence.get("observation_frames") == 2800
            and abs(float(ted_cadence.get("slowdown_percent", 999.0))) <= 1.0,
        "native_publication_caller": cadence_error is None
            and cadence is not None and cadence.get("schema") == CADENCE_SCHEMA
            and ted_cadence.get("dx", {}).get("caller_histogram")
            == {"028D": ted_cadence.get("dx", {}).get("copies")},
        "deterministic_visible_replay": determinism_error is None
            and determinism is not None
            and determinism.get("deterministic_replay") is True
            and metrics.get("frames") == 2800,
        "visible_geometry_and_materials": determinism_error is None
            and determinism is not None and determinism.get("status") == "pass"
            and metrics.get("status") == "pass",
        "checker_tile_lattice": metrics.get("floor_lattice_mismatches") == 0,
        "checker_palette_materials": metrics.get("floor_palette_mismatches") == 0,
        "numbered_tile_identity": metrics.get("numbered_identity_mismatches") == 0,
        "sparse_tentacle_identity": metrics.get("sparse_position_mismatches") == 0,
    }
    return checks, ted_cadence, metrics


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("rom", nargs="?", type=Path,
                        help="candidate path accepted for release-runner uniformity")
    parser.add_argument("--controls", type=Path, required=True)
    parser.add_argument("--entry-report", type=Path, required=True)
    parser.add_argument("--cadence", type=Path, required=True)
    parser.add_argument("--determinism", type=Path, required=True)
    parser.add_argument("--materializer", type=Path, required=True)
    parser.add_argument("--classifier", type=Path, required=True)
    parser.add_argument("--source-publication", type=Path, required=True)
    parser.add_argument("--publication-sequence", type=Path, required=True)
    parser.add_argument("--cache-contract", type=Path, required=True)
    parser.add_argument("--cache-reservation", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--receipt-only", action="store_true",
        help="write consolidated evidence for delta comparison without enforcing it",
    )
    args = parser.parse_args()

    controls, controls_error = load_json(args.controls)
    cadence, cadence_error = load_json(args.cadence)
    determinism, determinism_error = load_json(args.determinism)
    materializer, materializer_error = load_json(args.materializer)
    classifier, classifier_error = load_json(args.classifier)
    source_publication, source_publication_error = load_json(
        args.source_publication
    )
    publication_sequence, publication_sequence_error = load_json(
        args.publication_sequence
    )
    cache_contract, cache_contract_error = load_json(args.cache_contract)
    cache_reservation, cache_reservation_error = load_json(
        args.cache_reservation
    )
    entry_text = args.entry_report.read_text() if args.entry_report.is_file() else ""

    checks, ted_cadence, metrics = evaluate(
        controls, entry_text, cadence, determinism,
        materializer=materializer,
        classifier=classifier,
        source_publication=source_publication,
        publication_sequence=publication_sequence,
        cache_contract=cache_contract,
        cache_reservation=cache_reservation,
        controls_error=controls_error,
        cadence_error=cadence_error,
        determinism_error=determinism_error,
        materializer_error=materializer_error,
        classifier_error=classifier_error,
        source_publication_error=source_publication_error,
        publication_sequence_error=publication_sequence_error,
        cache_contract_error=cache_contract_error,
        cache_reservation_error=cache_reservation_error,
    )
    candidate_rom_sha256 = (
        sha256(args.rom.resolve()) if args.rom is not None and args.rom.is_file()
        else None
    )
    checks.update(evaluate_provenance(
        candidate_rom_sha256, cadence, determinism, materializer, classifier,
        source_publication, publication_sequence, cache_contract,
        cache_reservation,
    ))
    receipt = {
        "schema": SCHEMA,
        "status": "pass" if all(checks.values()) else "fail",
        "checks": checks,
        "failing_checks": sorted(name for name, passed in checks.items()
                                 if not passed),
        "input_errors": {
            name: error for name, error in (
                ("controls", controls_error),
                ("cadence", cadence_error),
                ("determinism", determinism_error),
                ("materializer", materializer_error),
                ("classifier", classifier_error),
                ("source_publication", source_publication_error),
                ("publication_sequence", publication_sequence_error),
                ("cache_contract", cache_contract_error),
                ("cache_reservation", cache_reservation_error),
                ("entry", None if entry_text else "missing"),
            ) if error is not None
        },
        "cadence": {
            key: ted_cadence.get(key) for key in (
                "status", "speed_ratio", "slowdown_percent",
                "maximum_speed_deviation_percent",
                "observation_frames",
            )
        },
        "identity": {
            "rom_sha256": candidate_rom_sha256,
            "determinism_rom_sha256": (
                determinism.get("rom_sha256") if determinism else None
            ),
            "state_sha256": (
                determinism.get("state_sha256") if determinism else None
            ),
            "trace_sha256": (
                determinism.get("trace_sha256") if determinism else None
            ),
        },
        "geometry": {
            key: metrics.get(key) for key in (
                "frames", "native_pose_matches", "native_pose_mismatches",
                "numbered_identity_mismatches",
                "numbered_identity_mismatch_frames",
                "numbered_identity_delta_histogram",
                "numbered_identity_tile_histogram",
                "numbered_identity_tile_delta_histogram",
                "numbered_identity_group_slot_histogram",
                "runtime_anchor_samples", "runtime_anchor_matches",
                "runtime_anchor_delta_histogram",
                "sparse_position_mismatches",
                "floor_lattice_mismatches", "floor_palette_mismatches",
                "sparse_floor_frames", "tentacle_samples", "failures",
            )
        },
        "publication_sequence": {
            key: (publication_sequence or {}).get("metrics", {}).get(key)
            for key in (
                "frames", "map_change_events", "source_exact_events",
                "partial_events", "partial_foreign_cells",
                "partial_not_complete_next_frame", "failures",
            )
        },
        "sources": {
            "controls": str(args.controls.resolve()),
            "entry_report": str(args.entry_report.resolve()),
            "cadence": str(args.cadence.resolve()),
            "determinism": str(args.determinism.resolve()),
            "materializer": str(args.materializer.resolve()),
            "classifier": str(args.classifier.resolve()),
            "source_publication": str(args.source_publication.resolve()),
            "publication_sequence": str(args.publication_sequence.resolve()),
            "cache_contract": str(args.cache_contract.resolve()),
            "cache_reservation": str(args.cache_reservation.resolve()),
        },
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n")
    print(json.dumps(receipt, indent=2, sort_keys=True))
    return 0 if args.receipt_only or receipt["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
