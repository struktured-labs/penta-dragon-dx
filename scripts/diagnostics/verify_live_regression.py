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
    "title_footer_integration",
    "title_animation_frames",
    "flash_attribution",
    "title_color",
    "title_showcase",
    "title_visual_receipts",
    "title_cursor",
    "stage_intro_timing",
    "menu_hud_and_combo",
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
    "boss_arenas",
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


def registered_gate_names() -> set[str]:
    """Return the authoritative release-matrix inventory without running it."""

    from verify_release_candidate import build_gates

    placeholder_rom = Path("/tmp/penta-live-contract.gb")
    placeholder_output = Path("/tmp/penta-live-contract")
    return {
        gate.name for gate in build_gates(placeholder_rom, placeholder_output)
    }


def verify_contract() -> list[str]:
    failures: list[str] = []
    if len(LIVE_GATES) != len(set(LIVE_GATES)):
        failures.append("LIVE_GATES contains duplicate names")
    missing = sorted(set(LIVE_GATES) - registered_gate_names())
    if missing:
        failures.append(
            "live gate(s) absent from release matrix: " + ", ".join(missing)
        )
    omitted = sorted(registered_gate_names() - set(LIVE_GATES))
    if omitted:
        failures.append(
            "release gate(s) omitted from pre-stream profile: "
            + ", ".join(omitted)
        )
    return failures


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

    failures = verify_contract()
    if failures:
        for failure in failures:
            print(f"FAIL: {failure}")
        return 1
    if args.list:
        print("\n".join(LIVE_GATES))
        return 0
    if args.check_contract:
        print(
            f"PASS: dedicated live profile registers all "
            f"{len(LIVE_GATES)} required gates."
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
    for gate in LIVE_GATES:
        command.extend(("--only", gate))

    print("Live regression gates: " + ", ".join(LIVE_GATES), flush=True)
    result = subprocess.run(command, cwd=ROOT, check=False)
    if result.returncode:
        return result.returncode

    manifest_path = args.output.resolve() / "manifest.json"
    try:
        manifest = json.loads(manifest_path.read_text())
    except (OSError, json.JSONDecodeError) as exc:
        print(f"FAIL: live profile did not produce a readable manifest: {exc}")
        return 1
    expected = set(LIVE_GATES)
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
        or len(results) != len(LIVE_GATES)
    ):
        print(
            "FAIL: release verifier returned success without an exact "
            f"{len(LIVE_GATES)}/{len(LIVE_GATES)} live manifest"
        )
        return 1
    print(
        f"PASS: dedicated live regression is green "
        f"({len(passed)}/{len(LIVE_GATES)}); receipt: {manifest_path}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
