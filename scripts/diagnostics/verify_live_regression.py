#!/usr/bin/env python3
"""Run the deterministic emulator-backed DX live regression profile.

This is the one-command pre-stream gate. It keeps the historically fragile
paths together: cold/warm GAME START, post-attract start, gameplay speed and
Stage-1 traversal/copy integrity, visible Stage-1 color bleed, prerecorded and
live pickup palettes, rotating-spike palettes, the Stage-1 bonus room,
title/spotlight/demo timing, ordinary and low-health flicker, every opening and
pre/post-final illustration, and the complete credits/END/epilogue trajectory.
The release verifier still owns process isolation, per-gate receipts, hashes,
timeouts, and the final manifest.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess
import sys

from suite_contract import source_snapshot


ROOT = Path(__file__).resolve().parents[2]
RELEASE_VERIFIER = Path(__file__).with_name("verify_release_candidate.py")
DEFAULT_ROM = ROOT / "rom/working/penta_dragon_dx_FIXED.gb"

LIVE_GATES = (
    "emulator_singleflight_guard",
    "release_matrix_resume_contract",
    "title_footer_integration",
    "title_animation_frames",
    "flash_attribution",
    "title_color",
    "title_showcase",
    "title_visual_receipts",
    "title_cursor",
    "stage_intro_timing",
    "menu_hud_and_combo",
    "menu_icon_palettes",
    "menu_window_publish_order",
    "stale_gameplay_window",
    "levelselect_screen",
    "game_start_routes",
    "game_start_after_attract",
    "opening_to_stage1_integrity",
    "gameplay_speed_parity",
    "gameplay_bg_palettes",
    "pickup_class_palettes",
    "attract_pickup_palettes",
    "stage1_spike_palettes",
    "stage1_spike_miniboss_transition",
    "pickup_live_retry_contract",
    "pickup_live_palettes",
    "stage1_pickup_art",
    "bonus_stage_live",
    "stage1_north_route_integrity",
    "stage1_no_color_bleed",
    "stage1_tilemap_integrity",
    "gameplay_obj_palettes",
    "frame_flicker",
    "low_health_flicker",
    "miniboss_color",
    "later_stage_integrity",
    "later_stage_soak",
    "stage2_stream_soak",
    "stage_side_by_side_all7",
    "boss_atomic_attr_contract",
    "ted_expanded_integration",
    "boss_arenas",
    "boss_geometry_all9",
    "ted_contract_controls",
    "ted_materializer",
    "ted_classifier",
    "ted_entry",
    "ted_og_entry",
    "ted_cadence",
    "ted_two_plane_cache_contract",
    "ted_cache_plane_reservation",
    "ted_determinism",
    "ted_source_publication",
    "ted_publication_sequence",
    "ted_incremental_mask_corpus",
    "ted_release_readiness_receipt",
    "ted_candidate_delta",
    "ted_release_readiness",
    "boss_semantic_cadence",
    "boss_og_states",
    "boss_og_material_gallery_all9",
    "boss_og_silhouette_gallery",
    "boss_speed_parity",
    "boss_trajectory_pairing_null",
    "boss_trajectory_pairing",
    "boss_publication_cadence",
    "crystal_dragon_ghost",
    "boss_material_gallery_all9",
    "boss_silhouette_gallery",
    "boss_material_side_by_side",
    "death_gameover",
    "title_idle_reel",
    "spotlight_full_roster",
    "opening_cutscene",
    "final_cutscene_mgba",
    "pre_final_inventory",
    "ending_inventory_a",
    "ending_inventory_b",
    "ending_discriminators",
    "scroll_stability",
    "phantom_sound",
    "live_palette_deck",
    "story_attr_production",
    "palette_build_roundtrip",
    "candidate_ips_roundtrip",
    "mister_reservation_guard",
)


def registered_gate_names(rom: Path) -> set[str]:
    """Return the profile-aware release inventory without running it."""

    from verify_release_candidate import build_gates

    placeholder_output = ROOT / "tmp" / "penta-live-contract"
    return {
        gate.name for gate in build_gates(rom, placeholder_output)
    }


def profile_gates(rom: Path) -> tuple[tuple[str, ...], list[str]]:
    """Select exactly the gates applicable to *rom* from the profile superset."""

    failures: list[str] = []
    if len(LIVE_GATES) != len(set(LIVE_GATES)):
        failures.append("LIVE_GATES contains duplicate names")
    registered = registered_gate_names(rom)
    selected = tuple(name for name in LIVE_GATES if name in registered)
    omitted = sorted(registered - set(selected))
    if omitted:
        failures.append(
            "release gate(s) omitted from pre-stream profile: "
            + ", ".join(omitted)
        )

    from boss_geometry_contract import BOSSES
    from verify_boss_publication_cadence import (
        CRYSTAL_DRAGON_TARGET,
        DEFAULT_CRYSTAL_MAX_SLOWDOWN,
        DEFAULT_MAX_SLOWDOWN,
        allowed_slowdown,
    )

    limits = [allowed_slowdown(target) for target in range(len(BOSSES))]
    exceptions = [
        target
        for target, limit in enumerate(limits)
        if limit != DEFAULT_MAX_SLOWDOWN
    ]
    if DEFAULT_MAX_SLOWDOWN != 0.01:
        failures.append("ordinary boss cadence limit is not 1%")
    if DEFAULT_CRYSTAL_MAX_SLOWDOWN != 0.05:
        failures.append("Crystal Dragon cadence limit is not 5%")
    if exceptions != [CRYSTAL_DRAGON_TARGET]:
        failures.append(
            "boss cadence exception is not Crystal Dragon alone: "
            + ", ".join(map(str, exceptions))
        )
    return selected, failures


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run the Penta Dragon DX live regression profile"
    )
    parser.add_argument("rom", nargs="?", type=Path, default=DEFAULT_ROM)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--timeout-scale", type=float, default=1.0)
    parser.add_argument(
        "--check-contract",
        action="store_true",
        help="validate the live gate inventory without launching an emulator",
    )
    parser.add_argument(
        "--list",
        action="store_true",
        help="print the dedicated live gate inventory and exit",
    )
    parser.add_argument(
        "--resume",
        action="store_true",
        help="resume passed gates from the output manifest",
    )
    args = parser.parse_args()

    live_gates, failures = profile_gates(args.rom.resolve())
    if failures:
        for failure in failures:
            print(f"FAIL: {failure}")
        return 1
    if args.list:
        print("\n".join(live_gates))
        return 0
    if args.check_contract:
        print(
            f"PASS: dedicated live profile registers all "
            f"{len(live_gates)} required gates."
        )
        return 0
    if args.output is None:
        parser.error("--output is required when running the live profile")

    command = [
        sys.executable,
        str(RELEASE_VERIFIER),
        str(args.rom.resolve()),
        "--output",
        str(args.output.resolve()),
        "--timeout-scale",
        str(args.timeout_scale),
    ]
    if args.resume:
        command.append("--resume")
    for gate in live_gates:
        command.extend(("--only", gate))

    print("Live regression gates: " + ", ".join(live_gates), flush=True)
    result = subprocess.run(command, cwd=ROOT, check=False)
    if result.returncode:
        return result.returncode

    manifest_path = args.output.resolve() / "manifest.json"
    try:
        manifest = json.loads(manifest_path.read_text())
    except (OSError, json.JSONDecodeError) as exc:
        print(f"FAIL: live profile did not produce a readable manifest: {exc}")
        return 1
    expected = set(live_gates)
    source_fingerprint, source_inputs = source_snapshot()
    selected = set(manifest.get("selected_gates", []))
    results = manifest.get("results", [])
    passed = {
        item.get("name")
        for item in results
        if isinstance(item, dict)
        and item.get("status") == "passed"
        and item.get("returncode") == 0
    }
    if (
        manifest.get("status") != "selected-pass"
        or manifest.get("scope") != "selected"
        or manifest.get("failures") != 0
        or manifest.get("source_fingerprint") != source_fingerprint
        or manifest.get("source_fingerprint_after") != source_fingerprint
        or manifest.get("source_input_count") != len(source_inputs)
        or manifest.get("source_inputs_intact") is not True
        or selected != expected
        or passed != expected
        or len(results) != len(live_gates)
    ):
        print(
            "FAIL: release verifier returned success without an exact "
            f"{len(live_gates)}/{len(live_gates)} live manifest"
        )
        return 1
    print(
        f"PASS: dedicated live regression is green "
        f"({len(passed)}/{len(live_gates)}); receipt: {manifest_path}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
