#!/usr/bin/env python3
"""Run the authoritative emulator release matrix on an isolated ROM copy.

The older ``full_verification_loop*.sh`` scripts rebuild and test the retired
teleport ROM. This harness never builds or patches a ROM. It copies the chosen
candidate to /tmp, runs every current release gate sequentially, retains each
gate's log/artifacts, and fails if either the source ROM or tested copy changes.

Passing this matrix proves the emulator-visible release requirements only.
Reservation-backed MiSTer FPGA verification remains a separate hardware gate.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from suite_contract import source_snapshot


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_ROM = ROOT / "rom/working/penta_dragon_dx_FIXED.gb"


@dataclass(frozen=True)
class Gate:
    name: str
    command: tuple[str, ...]
    timeout: float
    dependencies: tuple[str, ...] = ()


def md5(path: Path) -> str:
    digest = hashlib.md5()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def build_gates(rom: Path, output: Path) -> list[Gate]:
    py = sys.executable
    r = str(rom)
    artifacts = output / "artifacts"
    ending_a = artifacts / "ending-inventory-a"
    ending_b = artifacts / "ending-inventory-b"
    story_states = artifacts / "story-states"

    def script(path: str, *arguments: str) -> tuple[str, ...]:
        return (py, str(ROOT / path), *arguments)

    return [
        Gate(
            "emulator_singleflight_guard",
            script(
                "scripts/diagnostics/verify_mgba_singleflight_guard.py"
            ),
            15,
        ),
        Gate(
            "title_footer_integration",
            script("scripts/probes/verify_title_screen_integration.py", r),
            120,
        ),
        Gate(
            "title_animation_frames",
            script("scripts/probes/verify_title_animation_frames.py", r),
            180,
        ),
        Gate(
            "flash_attribution",
            script("scripts/probes/verify_flash_attribution.py", r),
            240,
        ),
        Gate(
            "title_color",
            script("scripts/probes/verify_title_color.py", r),
            120,
        ),
        Gate(
            "title_showcase",
            script(
                "scripts/diagnostics/verify_title_showcase_mgba.py",
                r,
                "--output",
                str(artifacts / "title-showcase/title"),
            ),
            180,
        ),
        Gate(
            "title_visual_receipts",
            script(
                "scripts/diagnostics/verify_title_visual_receipts.py",
                r,
                "--output",
                str(artifacts / "title-visual"),
            ),
            180,
        ),
        Gate(
            "title_cursor",
            script(
                "scripts/diagnostics/verify_title_cursor_pixels.py",
                r,
                "--output",
                str(artifacts / "title-cursor"),
            ),
            120,
        ),
        Gate(
            "stage_intro_timing",
            script("scripts/probes/verify_stage_intro_timing.py", r),
            180,
        ),
        Gate(
            "menu_hud_and_combo",
            script("scripts/probes/verify_menu_hud_and_combo.py", r),
            300,
        ),
        Gate(
            "menu_window_publish_order",
            script(
                "scripts/diagnostics/verify_menu_window_order.py",
                r,
                "--output",
                str(artifacts / "menu-window-order/report.txt"),
            ),
            120,
        ),
        Gate(
            "stale_gameplay_window",
            script(
                "scripts/diagnostics/verify_menu_window_order.py",
                r,
                "--inject-stale-frame",
                "800",
                "--frames",
                "805",
                "--output",
                str(artifacts / "stale-gameplay-window/report.txt"),
            ),
            120,
        ),
        Gate(
            "levelselect_screen",
            script(
                "scripts/diagnostics/verify_levelselect_screen.py",
                r,
                "--timeout",
                "60",
            ),
            120,
        ),
        Gate(
            "game_start_routes",
            script(
                "scripts/diagnostics/verify_game_start_routes.py",
                r,
                "--stage-confirm-offset",
                "207",
                "--max-gameplay-frame",
                "650",
                "--include-warm-reset",
                "--output",
                str(artifacts / "game-start-routes"),
            ),
            300,
        ),
        Gate(
            "game_start_after_attract",
            script(
                "scripts/diagnostics/verify_game_start_routes.py",
                r,
                "--save-mode",
                "blank",
                "--confirm",
                "a",
                "--timing",
                "delayed",
                "--stage-confirm-offset",
                "207",
                "--after-attract",
                "--probe-max-frames",
                "10000",
                "--max-gameplay-frame",
                "10000",
                "--timeout",
                "30",
                "--output",
                str(artifacts / "game-start-after-attract"),
            ),
            120,
        ),
        Gate(
            "opening_to_stage1_integrity",
            script(
                "scripts/diagnostics/verify_opening_to_stage1.py",
                r,
                "--output",
                str(artifacts / "opening-to-stage1"),
            ),
            300,
        ),
        Gate(
            "gameplay_speed_parity",
            script(
                "scripts/diagnostics/verify_stage_speed_matrix.py",
                "--dx-rom",
                r,
                "--original-rom",
                str(ROOT / "rom/Penta Dragon (J).gb"),
                "--targets",
                "0,4,6",
                "--input-mode",
                "right",
                "--frames",
                "600",
                "--tolerance",
                "0.10",
                "--output",
                str(artifacts / "gameplay-speed"),
            ),
            180,
        ),
        Gate(
            "gameplay_bg_palettes",
            script("scripts/probes/verify_gameplay_palette.py", r),
            180,
        ),
        Gate(
            "pickup_class_palettes",
            script(
                "scripts/diagnostics/verify_pickup_class_palettes.py",
                r,
                "--output",
                str(artifacts / "pickup-class-palettes"),
            ),
            30,
        ),
        Gate(
            "attract_pickup_palettes",
            script(
                "scripts/diagnostics/verify_attract_pickup_palettes.py",
                r,
                "--output",
                str(artifacts / "attract-pickup-palettes"),
            ),
            120,
        ),
        Gate(
            "stage1_spike_palettes",
            script(
                "scripts/diagnostics/verify_stage1_spike_palettes.py",
                r,
                "--scroll-settle",
                "800",
                "--screenshot-interval",
                "15",
                "--output",
                str(artifacts / "stage1-spike-palettes.json"),
            ),
            # Floor/ceiling animation plus the 600-frame north-scroll receipt
            # run serially under the emulator lock. Keep real headroom so
            # scheduler jitter cannot turn a green atomicity receipt into
            # rc=124.
            60,
        ),
        Gate(
            "stage1_spike_miniboss_transition",
            script(
                "scripts/diagnostics/verify_stage1_spike_palettes.py",
                r,
                "--keys",
                "0x01",
                "--live-settle",
                "3000",
                "--natural-settle",
                "3000",
                "--scroll-settle",
                "800",
                "--screenshot-interval",
                "15",
                "--output",
                str(artifacts / "stage1-spike-miniboss-transition.json"),
            ),
            120,
        ),
        Gate(
            "pickup_live_retry_contract",
            script("scripts/diagnostics/verify_pickup_live_retry.py"),
            15,
        ),
        Gate(
            "pickup_live_palettes",
            script(
                "scripts/diagnostics/verify_pickup_live_palettes.py",
                r,
                "--output",
                str(artifacts / "pickup-live-palettes"),
            ),
            180,
        ),
        Gate(
            "stage1_pickup_art",
            script(
                "scripts/diagnostics/verify_stage1_pickup_art.py",
                r,
                "--output",
                str(artifacts / "stage1-pickup-art"),
            ),
            120,
        ),
        Gate(
            "bonus_stage_live",
            script(
                "scripts/diagnostics/verify_bonus_stage_live.py",
                r,
                "--output",
                str(artifacts / "bonus-stage-live"),
            ),
            120,
        ),
        Gate(
            "stage1_no_color_bleed",
            script(
                "scripts/diagnostics/verify_stage1_no_bleed.py",
                r,
                "--frames",
                "1200",
                "--output",
                str(artifacts / "stage1-no-color-bleed"),
            ),
            180,
        ),
        Gate(
            "stage1_tilemap_integrity",
            script(
                "scripts/diagnostics/verify_stage1_tilemap_copy.py",
                r,
                "--frames",
                # The DE/ISR race first reproduced deterministically after
                # frame 15,000, well beyond the former smoke-sized gate.
                "20000",
                "--timeout",
                "60",
                "--output",
                str(artifacts / "stage1-tilemap-integrity"),
            ),
            180,
        ),
        Gate(
            "stage1_north_route_integrity",
            script(
                "scripts/diagnostics/verify_stage1_north_integrity.py",
                r,
                "--target-camera",
                # Reproduce the reported failure directly: cold GAME START,
                # then walk straight north into the first-room void area.
                # The former long expert trace crossed dozens of rooms and
                # menus, so a tiny timing delta could make it wander away
                # without ever producing terrain bytes to compare.
                "0x03A4",
                "--target-room",
                "1",
                "--target-settle",
                # Let both circular map publishers settle, then compare the
                # exact mutually visible terrain at their bounded X phases.
                "60",
                "--frames",
                "3000",
                "--play-frames",
                "240",
                "--dynamic-prefix",
                "0",
                # Use the same explicit OG-speed policy as the three-stage
                # matrix. The route still independently requires every one
                # of the 576 packed terrain bytes to match stock.
                "--max-frame-lag-ratio",
                # Enemy contact can deflect the UP-only route while the
                # dedicated speed matrix independently enforces <=10% CPU
                # throughput loss across Stages 1/5/7.
                "0.15",
                "--output",
                str(artifacts / "stage1-north-route-integrity"),
            ),
            180,
        ),
        Gate(
            "gameplay_obj_palettes",
            script(
                "scripts/diagnostics/verify_gameplay_obj_palettes.py",
                r,
                "--output",
                str(artifacts / "gameplay-obj-palettes"),
            ),
            180,
        ),
        Gate(
            "frame_flicker",
            script(
                "scripts/diagnostics/verify_frame_flicker.py",
                r,
                "--mode",
                "both",
                "--frames",
                "240",
                "--output",
                str(artifacts / "frame-flicker"),
            ),
            180,
        ),
        Gate(
            "low_health_flicker",
            script(
                "scripts/diagnostics/verify_low_health_flicker.py",
                r,
                "--samples",
                "1600",
                "--post-trigger-keys",
                "0x01",
                "--require-music-transition",
                "--output",
                str(artifacts / "low-health-flicker"),
            ),
            90,
        ),
        Gate(
            "miniboss_color",
            script("scripts/probes/verify_miniboss_color.py", r),
            240,
        ),
        Gate(
            "later_stage_integrity",
            script(
                "scripts/diagnostics/verify_later_stage_integrity.py",
                r,
                "--timeout",
                "45",
                "--require-semantic-pickups",
            ),
            180,
        ),
        Gate(
            "later_stage_soak",
            script(
                "scripts/diagnostics/verify_later_stage_soak.py",
                r,
                "--frames",
                "8000",
                "--timeout",
                "60",
                "--mgba",
                str(ROOT / "scripts/mgba-qt-singleflight"),
                "--screenshots",
                "--capture-stable",
                "0",
                "--require-semantic-pickups",
            ),
            360,
        ),
        Gate(
            "stage2_stream_soak",
            script(
                "scripts/diagnostics/verify_later_stage_soak.py",
                r,
                "--stages",
                "2",
                "--frames",
                "8000",
                "--timeout",
                "60",
                # Room $01 can be a one-frame route during the deterministic
                # Stage-2 cycle. Capture its already-live CRAM on entry so the
                # stage-identity gate covers every visited room instead of
                # failing on a deliberately delayed, never-created receipt.
                "--capture-stable",
                "0",
                "--require-stage-bg0",
                "--keep-dir",
                str(artifacts / "stage2-stream-soak"),
            ),
            180,
        ),
        Gate(
            "boss_arenas",
            script(
                "scripts/probes/verify_boss_arena_palettes.py",
                r,
                "--output",
                str(artifacts / "boss-arenas"),
            ),
            600,
        ),
        Gate(
            "death_gameover",
            script(
                "scripts/diagnostics/verify_death_gameover.py",
                r,
                "--output",
                str(artifacts / "death-gameover"),
            ),
            600,
        ),
        Gate(
            "title_idle_reel",
            script(
                "scripts/diagnostics/inventory_attract_reel.py",
                r,
                "--frames",
                "14000",
                "--timeout",
                "60",
                "--keep",
                str(artifacts / "title-idle-reel"),
            ),
            240,
        ),
        Gate(
            "spotlight_full_roster",
            script(
                "scripts/diagnostics/capture_attract_reel.py",
                r,
                "--output",
                str(artifacts / "spotlight-full-roster"),
                "--frames-per-identity",
                "4500",
            ),
            240,
        ),
        Gate(
            "opening_cutscene",
            script(
                "scripts/diagnostics/inventory_opening_cutscene.py",
                r,
                "--expect-production",
                "--output",
                str(artifacts / "opening-cutscene"),
            ),
            240,
        ),
        Gate(
            "final_cutscene_mgba",
            script(
                "scripts/diagnostics/verify_final_cutscene_mgba.py",
                r,
                "--output",
                str(artifacts / "final-cutscene-mgba"),
            ),
            180,
        ),
        Gate(
            "pre_final_inventory",
            script(
                "scripts/diagnostics/inventory_final_cutscene.py",
                r,
                "--entry",
                "pre-final",
                "--frames",
                "32000",
                "--expect-production",
                "--output",
                str(artifacts / "pre-final-inventory"),
            ),
            180,
        ),
        Gate(
            "ending_inventory_a",
            script(
                "scripts/diagnostics/inventory_final_cutscene.py",
                r,
                "--entry",
                "post-final",
                "--frames",
                "32000",
                "--expect-production",
                "--output",
                str(ending_a),
            ),
            300,
        ),
        Gate(
            "ending_inventory_b",
            script(
                "scripts/diagnostics/inventory_final_cutscene.py",
                r,
                "--entry",
                "post-final",
                "--frames",
                "32000",
                "--expect-production",
                "--output",
                str(ending_b),
            ),
            300,
        ),
        Gate(
            "ending_discriminators",
            script(
                "scripts/diagnostics/analyze_ending_page_discriminators.py",
                str(ending_a / "manifest.json"),
                str(ending_b / "manifest.json"),
                "--output",
                str(artifacts / "ending-discriminators.json"),
            ),
            30,
            ("ending_inventory_a", "ending_inventory_b"),
        ),
        Gate(
            "scroll_stability",
            script("scripts/probes/verify_scroll_tearing.py", r),
            300,
        ),
        Gate(
            "phantom_sound",
            script("scripts/probes/verify_phantom_d887.py", r),
            300,
        ),
        Gate(
            "live_palette_deck",
            script(
                "scripts/diagnostics/verify_live_palette_session.py",
                r,
                "--timeout",
                "60",
                "--keep-story-states",
                str(story_states),
            ),
            600,
        ),
        Gate(
            "story_attr_production",
            script(
                "scripts/diagnostics/verify_story_attr_production.py",
                r,
                "--states",
                str(story_states),
                "--output",
                str(artifacts / "story-attr-production"),
                "--timeout",
                "12",
            ),
            240,
            ("live_palette_deck",),
        ),
        Gate(
            "palette_build_roundtrip",
            script(
                "scripts/diagnostics/verify_palette_build_roundtrip.py",
                "--candidate",
                r,
                "--timeout",
                "60",
            ),
            180,
        ),
        Gate(
            "candidate_ips_roundtrip",
            script(
                "scripts/diagnostics/verify_release_patch.py",
                r,
                "--candidate-only",
            ),
            30,
        ),
        Gate(
            "mister_reservation_guard",
            script("scripts/diagnostics/verify_mister_reservation_guard.py"),
            30,
        ),
    ]


def tail(path: Path, lines: int = 24) -> str:
    try:
        content = path.read_text(errors="replace").splitlines()
    except OSError:
        return "(log unavailable)"
    return "\n".join(content[-lines:])


def write_manifest(path: Path, manifest: dict) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(manifest, indent=2) + "\n")
    temporary.replace(path)


def dependency_closure(
    selected: set[str], gates: dict[str, Gate]
) -> set[str]:
    result = set(selected)
    pending = list(selected)
    while pending:
        name = pending.pop()
        for dependency in gates[name].dependencies:
            if dependency not in result:
                result.add(dependency)
                pending.append(dependency)
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("rom", nargs="?", type=Path, default=DEFAULT_ROM)
    parser.add_argument(
        "--output",
        type=Path,
        help="artifact directory (default: timestamped directory under /tmp)",
    )
    parser.add_argument(
        "--only",
        action="append",
        help="run one named gate; repeat for multiple gates",
    )
    parser.add_argument(
        "--timeout-scale",
        type=float,
        default=1.0,
        help="multiply every outer timeout (default: 1.0)",
    )
    parser.add_argument(
        "--list",
        action="store_true",
        help="list gate names without running them",
    )
    parser.add_argument(
        "--resume",
        action="store_true",
        help="resume passed gates from an interrupted --output manifest",
    )
    args = parser.parse_args()

    if args.timeout_scale <= 0:
        parser.error("--timeout-scale must be positive")
    if args.resume and not args.output:
        parser.error("--resume requires --output")
    source_rom = args.rom.resolve()
    if not source_rom.is_file():
        parser.error(f"ROM not found: {source_rom}")

    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    output = (
        args.output.resolve()
        if args.output
        else Path(f"/tmp/penta-release-candidate-{stamp}")
    )
    output.mkdir(parents=True, exist_ok=True)
    (output / "logs").mkdir(exist_ok=True)
    (output / "artifacts").mkdir(exist_ok=True)
    tested_dir = output / "tested-rom"
    tested_dir.mkdir(exist_ok=True)
    tested_rom = tested_dir / "penta_dragon_dx_FIXED.gb"

    source_hash = md5(source_rom)
    source_size = source_rom.stat().st_size
    suite_source_fingerprint, suite_source_inputs = source_snapshot()
    if args.resume:
        if not tested_rom.is_file():
            parser.error(f"resume tested ROM not found: {tested_rom}")
    else:
        shutil.copy2(source_rom, tested_rom)
    tested_hash = md5(tested_rom)
    if tested_hash != source_hash:
        print("FAIL: isolated ROM copy does not match the source candidate")
        return 1

    gate_list = build_gates(tested_rom, output)
    gates = {gate.name: gate for gate in gate_list}
    if args.list:
        for gate in gate_list:
            print(gate.name)
        return 0

    unknown = set(args.only or ()) - gates.keys()
    if unknown:
        parser.error(f"unknown gate(s): {', '.join(sorted(unknown))}")
    selected = (
        dependency_closure(set(args.only), gates)
        if args.only
        else set(gates)
    )
    full_matrix = selected == set(gates)

    manifest_path = output / "manifest.json"
    results_by_name: dict[str, dict]
    if args.resume:
        if not manifest_path.is_file():
            parser.error(f"resume manifest not found: {manifest_path}")
        manifest = json.loads(manifest_path.read_text())
        if manifest.get("rom_md5") != source_hash:
            parser.error(
                "resume manifest ROM hash does not match the source candidate"
            )
        if manifest.get("source_fingerprint") != suite_source_fingerprint:
            parser.error(
                "resume manifest suite-source fingerprint does not match; "
                "rerun the selected gates instead of retaining stale results"
            )
        prior_results = {
            result.get("name"): result
            for result in manifest.get("results", [])
            if result.get("status") == "passed"
            and result.get("name") in selected
        }
        manifest["results"] = [
            prior_results[gate.name]
            for gate in gate_list
            if gate.name in prior_results
        ]
        results_by_name = dict(prior_results)
        manifest.update(
            status="running",
            scope="full" if full_matrix else "selected",
            finished_at=None,
            resumed_at=utc_now(),
            selected_gates=[
                gate.name for gate in gate_list if gate.name in selected
            ],
            failures=0,
        )
        print(f"Resuming {len(results_by_name)} passed gate(s).")
    else:
        manifest = {
            "status": "running",
            "scope": "full" if full_matrix else "selected",
            "started_at": utc_now(),
            "finished_at": None,
            "source_rom": str(source_rom),
            "tested_rom": str(tested_rom),
            "rom_md5": source_hash,
            "rom_size": source_size,
            "source_fingerprint": suite_source_fingerprint,
            "source_input_count": len(suite_source_inputs),
            "python": sys.version,
            "platform": platform.platform(),
            "mgba_qt": str(ROOT / "scripts/mgba-qt-singleflight"),
            "hardware_gate": "pending-reservation-backed-mister",
            "selected_gates": [
                gate.name for gate in gate_list if gate.name in selected
            ],
            "results": [],
        }
        results_by_name = {}
    write_manifest(manifest_path, manifest)

    failures = 0
    print(
        f"Candidate MD5: {source_hash}\n"
        f"Isolated ROM: {tested_rom}\n"
        f"Artifacts:    {output}\n"
        f"Gates:        {len(selected)}"
    )

    for index, gate in enumerate(gate_list, 1):
        if gate.name not in selected:
            continue
        if gate.name in results_by_name:
            print(f"[{index:02d}/{len(gate_list):02d}] KEEP  {gate.name}")
            continue
        blocked_by = [
            dependency
            for dependency in gate.dependencies
            if results_by_name.get(dependency, {}).get("status") != "passed"
        ]
        log_path = output / "logs" / f"{gate.name}.log"
        started = time.monotonic()
        result = {
            "name": gate.name,
            "status": "running",
            "command": list(gate.command),
            "timeout_seconds": gate.timeout * args.timeout_scale,
            "started_at": utc_now(),
            "finished_at": None,
            "duration_seconds": None,
            "returncode": None,
            "log": str(log_path),
            "blocked_by": blocked_by,
        }
        manifest["results"].append(result)
        write_manifest(manifest_path, manifest)

        if blocked_by:
            result["status"] = "blocked"
            result["finished_at"] = utc_now()
            result["duration_seconds"] = 0
            log_path.write_text(
                "Blocked by failed dependency: "
                + ", ".join(blocked_by)
                + "\n"
            )
            failures += 1
            print(
                f"[{index:02d}/{len(gate_list):02d}] BLOCK "
                f"{gate.name} <- {', '.join(blocked_by)}"
            )
            results_by_name[gate.name] = result
            write_manifest(manifest_path, manifest)
            continue

        try:
            with log_path.open("w") as log:
                completed = subprocess.run(
                    gate.command,
                    cwd=ROOT,
                    env=os.environ.copy(),
                    stdout=log,
                    stderr=subprocess.STDOUT,
                    timeout=gate.timeout * args.timeout_scale,
                    check=False,
                )
            returncode = completed.returncode
            status = "passed" if returncode == 0 else "failed"
        except subprocess.TimeoutExpired:
            returncode = 124
            status = "timeout"
            with log_path.open("a") as log:
                log.write(
                    f"\nTIMEOUT after "
                    f"{gate.timeout * args.timeout_scale:.1f}s\n"
                )

        duration = time.monotonic() - started
        result.update(
            status=status,
            returncode=returncode,
            duration_seconds=round(duration, 3),
            finished_at=utc_now(),
        )
        results_by_name[gate.name] = result

        source_after = md5(source_rom)
        tested_after = md5(tested_rom)
        if source_after != source_hash or tested_after != tested_hash:
            result["status"] = "rom-mutated"
            result["source_md5_after"] = source_after
            result["tested_md5_after"] = tested_after
            status = "rom-mutated"
        if result["status"] != "passed":
            failures += 1
            print(
                f"[{index:02d}/{len(gate_list):02d}] FAIL  "
                f"{gate.name} ({duration:.1f}s, rc={returncode})"
            )
            print(tail(log_path))
        else:
            print(
                f"[{index:02d}/{len(gate_list):02d}] PASS  "
                f"{gate.name} ({duration:.1f}s)"
            )
        write_manifest(manifest_path, manifest)

    source_final = md5(source_rom)
    tested_final = md5(tested_rom)
    hashes_intact = source_final == source_hash and tested_final == tested_hash
    if not hashes_intact:
        failures += 1
    suite_source_fingerprint_after, suite_source_inputs_after = source_snapshot()
    source_inputs_intact = (
        suite_source_fingerprint_after == suite_source_fingerprint
        and suite_source_inputs_after == suite_source_inputs
    )
    if not source_inputs_intact:
        failures += 1

    # Resume can complete a dependency after later independent gates already
    # passed. Serialize the finished manifest in canonical gate order so
    # release packaging can compare it directly with selected_gates.
    manifest["results"] = [
        results_by_name[gate.name]
        for gate in gate_list
        if gate.name in selected and gate.name in results_by_name
    ]
    manifest.update(
        status=(
            "failed"
            if failures
            else "emulator-pass" if full_matrix else "selected-pass"
        ),
        finished_at=utc_now(),
        source_rom_md5_after=source_final,
        tested_rom_md5_after=tested_final,
        rom_hashes_intact=hashes_intact,
        source_fingerprint_after=suite_source_fingerprint_after,
        source_inputs_intact=source_inputs_intact,
        failures=failures,
    )
    write_manifest(manifest_path, manifest)

    if failures:
        print(
            f"FAIL: {failures} release gate(s) failed or were blocked. "
            f"See {manifest_path}."
        )
        return 1
    if full_matrix:
        print(
            f"PASS: all {len(selected)} emulator release gates passed; "
            f"ROM MD5 remained {source_hash}."
        )
        print(
            "HARDWARE PENDING: complete the reservation-backed MiSTer sweep "
            "before release."
        )
    else:
        print(
            f"PASS: all {len(selected)} selected emulator gates passed. "
            "This was not the full release matrix."
        )
    print(f"Manifest: {manifest_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
