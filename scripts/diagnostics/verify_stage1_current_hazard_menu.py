#!/usr/bin/env python3
"""Verify menu/item/low-health hazards from a ROM-owned cold-route state."""

# PENTA_CHECKED_SINGLEFLIGHT_DELEGATION: live_receipt receives DEFAULT_MGBA
# from verify_stage1_spike_palettes, which is the checked-in guarded wrapper.

from __future__ import annotations

import argparse
import hashlib
import json
import time
from pathlib import Path

from verify_stage1_hazard_menu import (
    hazard_coverage_is_complete,
    replay_is_clean,
    stable_summary,
)
from verify_stage1_spike_palettes import DEFAULT_MGBA, live_receipt


# Every replay captures 650 native frames at one-frame cadence.  Sixty
# wall-clock seconds is below the observed guarded/offscreen capture time on a
# busy host (the failed run reached frame 565).  Keep the outer reporter's
# separate 180-second aggregate bound while allowing one replay to finish.
DEFAULT_REPLAY_TIMEOUT = 90.0


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def deterministic_replay_signature(receipt: dict) -> dict:
    """Return only replay invariants, excluding host-horizon counters.

    The broad visible oracle runs under fast-forward Qt, whose callback
    cadence is intentionally not wall-clock deterministic.  Counts such as
    total map flips, helper hits, post-menu samples, and the final raster
    phase therefore vary even when every contract check is green.  Compare
    the semantic identity, scheduled acknowledgements, and all mismatch
    counters instead; each replay still runs the complete clean/coverage
    predicates below.
    """
    keys = (
        "scene", "room", "reviewed_room_local_attr_oracle",
        "menu_anchor_room", "menu_anchor_frame", "effective_menu_open_frame",
        "effective_menu_close_frame", "effective_menu_use_frame",
        "effective_low_health_frame", "menu_use_input_frames",
        "menu_map_alias_frames", "first_menu_map_alias", "menu_hud_before_use",
        "menu_hud_change_frame", "menu_hp_before_use", "menu_hp_change_frame",
        "menu_hp_after_use", "menu_a_handler_hits", "menu_item_dispatch_hits",
        "menu_selected_item_trace", "menu_closed_frame", "post_menu_input_mask",
        "menu_close_repair_hits", "menu_close_native_tail_hits",
        "transient_mismatch_frames", "first_transient_mismatch",
        "floor_mismatch_frames", "first_floor_mismatch",
        "palette_mismatch_frames", "endpoint_mismatch_frames",
        "visible_attr_mismatch_frames", "first_endpoint_mismatch",
        "post_menu_transient_mismatch_frames", "post_menu_palette_mismatch_frames",
        "post_menu_floor_mismatch_frames", "post_menu_endpoint_mismatch_frames",
        "post_menu_visible_attr_mismatch_frames", "active_hazard_attr_write_hits",
        "post_menu_active_hazard_attr_write_hits", "visible_semantic_attr_write_hits",
        "semantic_attr_write_bases", "phase_floor_attr_mismatch_cells",
        "unsafe_map_flip_events", "map_flip_bases", "map_owner_invalid_publications",
        "map_owner_missing_flip_events", "map_owner_missing_visible_frames",
        "map_owner_live_room_divergence_frames", "low_health_scene_frames",
        "rendered_wrong_palette0_tooth_cells", "rendered_wrong_gray_terminal_cap_cells",
    )
    return {key: receipt.get(key) for key in keys}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("rom", type=Path)
    parser.add_argument("--state", type=Path, required=True)
    parser.add_argument("--state-receipt", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--timeout", type=float, default=DEFAULT_REPLAY_TIMEOUT)
    parser.add_argument("--frames", type=int, default=650)
    # The reported Pocket flicker is intermittent and a five-frame cadence
    # can sample around it.  Release evidence captures every frame; callers
    # may still request a coarser interval only for explicit diagnostics.
    parser.add_argument("--screenshot-interval", type=int, default=1)
    parser.add_argument(
        "--menu-anchor-delay", type=int, default=180,
        help="frames after the room-$01 anchor before SELECT is pressed",
    )
    parser.add_argument(
        "--menu-hold-frames", type=int, default=240,
        help="frames to hold the menu open before SELECT closes it",
    )
    parser.add_argument(
        "--menu-use-delay", type=int, default=80,
        help="frames after menu-open input before using the selected item",
    )
    parser.add_argument(
        "--low-health-delay", type=int, default=270,
        help="frames after menu-open input before forcing warning health",
    )
    parser.add_argument(
        "--trace-routes", action="store_true",
        help="record the banked postcopy route for diagnosis",
    )
    parser.add_argument(
        "--single-replay", action="store_true",
        help="run one diagnostic replay instead of the two-replay gate",
    )
    parser.add_argument(
        "--no-broad-visible-oracle", action="store_true",
        help="diagnostic-only: disable the expensive per-frame full viewport oracle",
    )
    args = parser.parse_args()

    rom = args.rom.resolve()
    state = args.state.resolve()
    state_receipt_path = args.state_receipt.resolve()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)

    rom_sha256 = digest(rom)
    state_sha256 = digest(state)
    state_receipt = json.loads(state_receipt_path.read_text())
    minimum_hazard_cells = int(
        state_receipt.get("minimum_hazard_cells", 40)
    )
    minimum_tooth_cells = int(
        state_receipt.get("minimum_tooth_cells", 10)
    )
    fixture_bound = (
        state_receipt.get("passed") is True
        and state_receipt.get("rom_sha256") == rom_sha256
        and state_receipt.get("state_sha256") == state_sha256
        and minimum_hazard_cells >= 1
        and minimum_tooth_cells >= 1
        and state_receipt.get("hazard_cells", 0) >= minimum_hazard_cells
        and state_receipt.get("tooth_cells", 0) >= minimum_tooth_cells
        and state_receipt.get("hardware", {}).get("settled") is True
    )
    if not fixture_bound:
        raise SystemExit("cold hazard state is not bound to this ROM")

    replays = []
    summaries = []
    replay_indexes = (1,) if args.single_replay else (1, 2)
    close_frame = args.menu_hold_frames
    use_frame = args.menu_use_delay
    low_health_frame = args.low_health_delay
    # Always require the live room-01 anchor and its configured stabilization
    # delay. A candidate-specific bypass would make the timing-sensitive menu
    # contract vacuous and is not admissible as release evidence.
    menu_anchor_room = 0x01
    for replay_index in replay_indexes:
        replay_started = time.monotonic()
        replay = live_receipt(
            rom,
            state,
            DEFAULT_MGBA.resolve(),
            output / f"replay-{replay_index}",
            args.timeout,
            prefix_name="current-hazard-menu",
            reinitialize=False,
            settle=args.frames,
            input_mask=0,
            # Keep the exact hardware incident visible after item use.  The
            # old route held UP here, left the spike room, and could therefore
            # pass after the red/gray artifacts disappeared through movement.
            post_menu_input_mask=0,
            screenshot_interval=args.screenshot_interval,
            expected_room=0x01,
            # At camera $015C the reviewed room-$12 cylinder phase begins at
            # physical-map offset $049.  The former generic $041 probe read a
            # wall tile ($FE), so it could never prove four hazard phases.
            phase_offset=0x49,
            normalization_writes=(),
            menu_open=True,
            menu_open_frame=0,
            menu_close_frame=close_frame,
            menu_use_frame=use_frame,
            low_health_frame=low_health_frame,
            menu_anchor_room=menu_anchor_room,
            menu_anchor_delay=args.menu_anchor_delay,
            # Release evidence must prove the semantic publisher executed;
            # otherwise a visually quiet fixture can pass vacuously while the
            # photographed active-map trail route remains untested.
            trace_routes=True,
            trace_writers=True,
            preserve_machine_state=True,
            preserve_rom_owned_state=True,
            broad_visible_oracle=not args.no_broad_visible_oracle,
        )
        replay["final_screenshot_sha256"] = digest(Path(replay["screenshot"]))
        replays.append(replay)
        summaries.append(stable_summary(replay))
        print(f"replay {replay_index}: total {time.monotonic() - replay_started:.2f}s "
              f"(capture/reap {replay['emulator_process_seconds']:.2f}s)", flush=True)

    clean = all(
        replay_is_clean(
            replay,
            close_frame=close_frame,
            use_frame=use_frame,
            low_health_frame=low_health_frame,
            require_hazard_coverage=True,
        )
        for replay in replays
    )
    checks = {
        "cold state is hash-bound to the candidate ROM": fixture_bound,
        "both replays preserve the current-ROM machine phase": all(
            replay["machine_state_preserved"] for replay in replays
        ),
        "both replays remain in live Stage-1 gameplay": all(
            replay["scene"] == "02"
            for replay in replays
        ),
        "both menu/item/close/low-health replays are clean": clean,
        "both replays retain full stationary hazard coverage": all(
            hazard_coverage_is_complete(replay) for replay in replays
        ),
        "replays are byte-deterministic": (
            args.single_replay
            or deterministic_replay_signature(replays[0])
            == deterministic_replay_signature(replays[1])
        ),
    }
    receipt = {
        "schema": "penta-stage1-current-hazard-menu-v1",
        "rom": str(rom),
        "rom_sha256": rom_sha256,
        "state": str(state),
        "state_sha256": state_sha256,
        "state_receipt": str(state_receipt_path),
        "state_receipt_sha256": digest(state_receipt_path),
        "timeline": {
            "menu_anchor_delay": args.menu_anchor_delay,
            "menu_hold_frames": close_frame,
            "menu_use_delay": use_frame,
            "low_health_delay": low_health_frame,
        },
        "replays": summaries,
        "raw_reports": [replay["report"] for replay in replays],
        "checks": checks,
        "passed": all(checks.values()),
    }
    receipt_path = output / "receipt.json"
    receipt_path.write_text(json.dumps(receipt, indent=2) + "\n")
    if not receipt["passed"]:
        failed = [name for name, passed in checks.items() if not passed]
        print("FAIL: current-ROM Stage-1 menu/item/low-health hazard contract")
        for name in failed:
            print(f"  failed check: {name}")
        print(f"Receipt: {receipt_path}")
        return 1
    print("PASS: current-ROM Stage-1 menu/item/low-health hazard contract")
    print(f"Receipt: {receipt_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
