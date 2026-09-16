#!/usr/bin/env python3
"""Reproduce and reject Stage-1 hazard/floor bleed under the frozen menu."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from verify_stage1_spike_palettes import (
    CEILING_LIVE_STATE,
    DEFAULT_MGBA,
    DEFAULT_ROM,
    LIVE_STATE,
    STATE_DIR,
    live_receipt,
)


CURRENT_HAZARD_REQUIRED_CHECKS = (
    "visible patterned floors never inherit a hazard palette",
    "every atomic floor compile reads Dungeon BG0",
    "historical spike room remains a live Stage-1 phase",
    "active map contains the rotating spike family",
    "every active-map spike tile uses its YAML material split",
    "visible map contains complete BG7 teeth",
    "every visible tooth phase uses the gold hazard palette",
    "both physical maps are observed active with exact tooth colors",
    "all bank-1 neutral/tooth art finished and matches bank 0",
    "visible map contains BG5 rings and fire body",
    "all four right-wall pole terminal cells use fire BG5",
    "visible support and shadow cells remain metallic BG6",
    "left/right endpoints match tooth/retracted semantics every frame",
    "every visible animation frame keeps tile and palette atomic",
    "hidden-map preparation never leaks through a physical-map flip",
    "live BG5 CRAM matches the candidate",
    "live Stage-1 BG7 CRAM matches the YAML hazard row",
    "Stage-1 hazard BG5/BG7 never flicker during the sampled interval",
    "a semantic hazard publication path is exercised",
    "selective row publisher is statically bounded and dynamically exact",
    "all four live cylinder phases have rendered-frame receipts",
    "normalized fixtures render current candidate hazard art",
    "rendered candidate pixels never expose gray palette-0 teeth",
    "every rendered phase visibly contains candidate BG7 gold teeth",
    "every rendered phase shows all four terminal caps in fire BG5",
    "rendered cylinder phases visibly contain red and gold material",
    "rendered lower field has no legacy red/gold palette wash",
    "every native map flip is transfer-idle and complete",
    "primary map publications never require retired FF97 SCX skip",
    "SELECT opens and holds the native item menu",
    "frozen item menu never recolors visible Stage-1 floor cells",
    "broad visible/map-flip oracle uses pinned room-local wall context",
    "frozen item menu keeps every visible BG attribute exact",
    "phase-aligned rendered raster has no yellow spike trails",
    "frozen item menu never exposes gray spike teeth",
    "item Window never aliases the visible gameplay BG map",
    "item use input is accepted for six visible-menu frames",
    "seeded item crosses the real native item dispatcher",
    "item-use redraw keeps Window and gameplay maps isolated",
    "SELECT closes the native item menu on schedule",
    "menu-close recovery uses the requested movement policy",
    "menu close executes exactly one native hidden-map handoff",
    "stationary post-menu gameplay has no stale red floor attrs",
    "stationary post-menu gameplay keeps every visible BG attribute exact",
    "stationary post-menu gameplay keeps BG5/BG7 CRAM stable",
    "stationary post-menu hazard tiles and attrs stay atomic",
    "left/right spike endpoints stay gold after menu close",
    "post-menu rendered frames contain no gray tooth pixels",
    "semantic hazard attributes never write the visible BG map",
    "menu close never repaints hazards into the visible BG map",
    "warning health is held after the menu/item sequence",
    "post-menu warning mode leaves floors, endpoints and hazards exact",
)


def hazard_coverage_is_complete(receipt: dict) -> bool:
    checks = receipt.get("checks")
    return (
        isinstance(checks, dict)
        and all(checks.get(name) is True for name in CURRENT_HAZARD_REQUIRED_CHECKS)
        and receipt.get("room") == "01"
        and receipt.get("post_menu_input_mask") == 0
        and receipt.get("map_flip_bases") == ["9800", "9C00"]
    )


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def stable_summary(receipt: dict) -> dict:
    temporal_raster = dict(receipt["temporal_raster"])
    if isinstance(temporal_raster.get("first_mismatch"), dict):
        first_mismatch = dict(temporal_raster["first_mismatch"])
        # Replay output directories differ by design; the frame/pixel receipt
        # is deterministic, while its absolute screenshot path is not.
        first_mismatch.pop("path", None)
        temporal_raster["first_mismatch"] = first_mismatch
    terminal_phase_receipts = []
    for phase in receipt["phase_pixel_receipts"]:
        terminal_phase_receipts.append({
            "screenshot_sha256": hashlib.sha256(
                Path(phase["path"]).read_bytes()
            ).hexdigest(),
            "wrong_gray_terminal_caps": len(
                phase["wrong_gray_terminal_caps"]
            ),
            "fire_terminal_caps": len(phase["fire_terminal_caps"]),
            "occluded_terminal_caps": len(
                phase.get("occluded_terminal_caps", [])
            ),
            "unexplained_missing_terminal_caps": len(
                phase.get("unexplained_missing_terminal_caps", [])
            ),
        })
    return {
        "scene": receipt["scene"],
        "room": receipt["room"],
        "reviewed_room_local_attr_oracle": receipt[
            "reviewed_room_local_attr_oracle"
        ],
        "menu_open_frames": receipt["menu_open_frames"],
        "menu_anchor_room": receipt["menu_anchor_room"],
        "menu_anchor_frame": receipt["menu_anchor_frame"],
        "effective_menu_open_frame": receipt["effective_menu_open_frame"],
        "effective_menu_close_frame": receipt["effective_menu_close_frame"],
        "effective_menu_use_frame": receipt["effective_menu_use_frame"],
        "effective_low_health_frame": receipt["effective_low_health_frame"],
        "menu_use_input_frames": receipt["menu_use_input_frames"],
        "menu_map_alias_frames": receipt["menu_map_alias_frames"],
        "first_menu_map_alias": receipt["first_menu_map_alias"],
        "menu_hud_before_use": receipt["menu_hud_before_use"],
        "menu_hud_change_frame": receipt["menu_hud_change_frame"],
        "menu_hp_before_use": receipt["menu_hp_before_use"],
        "menu_hp_change_frame": receipt["menu_hp_change_frame"],
        "menu_hp_after_use": receipt["menu_hp_after_use"],
        "menu_a_handler_hits": receipt["menu_a_handler_hits"],
        "menu_item_dispatch_hits": receipt["menu_item_dispatch_hits"],
        "menu_selected_item_trace": receipt["menu_selected_item_trace"],
        "menu_closed_frame": receipt["menu_closed_frame"],
        "post_menu_closed_frames": receipt["post_menu_closed_frames"],
        "post_menu_input_mask": receipt["post_menu_input_mask"],
        "post_menu_input_frames": receipt["post_menu_input_frames"],
        "menu_close_repair_hits": receipt["menu_close_repair_hits"],
        "menu_close_native_tail_hits": receipt[
            "menu_close_native_tail_hits"
        ],
        "menu_close_trace_sha256": hashlib.sha256(
            receipt["menu_close_trace"].encode()
        ).hexdigest(),
        "menu_state_trace_sha256": hashlib.sha256(
            receipt["menu_state_trace"].encode()
        ).hexdigest(),
        "transient_mismatch_frames": receipt["transient_mismatch_frames"],
        "inactive_preparation_mismatch_frames": receipt[
            "inactive_preparation_mismatch_frames"
        ],
        "map_flip_events": receipt["map_flip_events"],
        "unsafe_map_flip_events": receipt["unsafe_map_flip_events"],
        "map_flip_bases": receipt["map_flip_bases"],
        "exact_readable_map_flip_receipts": receipt[
            "exact_readable_map_flip_receipts"
        ],
        "map_flip_trace_sha256": hashlib.sha256(
            receipt["map_flip_trace"].encode()
        ).hexdigest(),
        "first_transient_mismatch": receipt["first_transient_mismatch"],
        "floor_mismatch_frames": receipt["floor_mismatch_frames"],
        "first_floor_mismatch": receipt["first_floor_mismatch"],
        "palette_mismatch_frames": receipt["palette_mismatch_frames"],
        "endpoint_mismatch_frames": receipt["endpoint_mismatch_frames"],
        "visible_attr_mismatch_frames": receipt[
            "visible_attr_mismatch_frames"
        ],
        "first_endpoint_mismatch": receipt["first_endpoint_mismatch"],
        "post_menu_transient_mismatch_frames": receipt[
            "post_menu_transient_mismatch_frames"
        ],
        "post_menu_palette_mismatch_frames": receipt[
            "post_menu_palette_mismatch_frames"
        ],
        "post_menu_floor_mismatch_frames": receipt[
            "post_menu_floor_mismatch_frames"
        ],
        "post_menu_endpoint_mismatch_frames": receipt[
            "post_menu_endpoint_mismatch_frames"
        ],
        "post_menu_visible_attr_mismatch_frames": receipt[
            "post_menu_visible_attr_mismatch_frames"
        ],
        "active_hazard_attr_write_hits": receipt[
            "active_hazard_attr_write_hits"
        ],
        "post_menu_active_hazard_attr_write_hits": receipt[
            "post_menu_active_hazard_attr_write_hits"
        ],
        "visible_hazard_attr_write_trace": receipt[
            "visible_hazard_attr_write_trace"
        ],
        "hazard_trampoline_hits": receipt["hazard_trampoline_hits"],
        "hazard_helper_hits": receipt["hazard_helper_hits"],
        "semantic_attr_write_hits": receipt["semantic_attr_write_hits"],
        "hidden_semantic_attr_write_hits": receipt[
            "hidden_semantic_attr_write_hits"
        ],
        "visible_semantic_attr_write_hits": receipt[
            "visible_semantic_attr_write_hits"
        ],
        "semantic_attr_write_bases": receipt[
            "semantic_attr_write_bases"
        ],
        "phase_floor_cells_reviewed": receipt[
            "phase_floor_cells_reviewed"
        ],
        "phase_floor_attr_mismatch_cells": receipt[
            "phase_floor_attr_mismatch_cells"
        ],
        "temporal_raster": temporal_raster,
        "low_health_forced_frames": receipt["low_health_forced_frames"],
        "low_health_scene_frames": receipt["low_health_scene_frames"],
        "rendered_wrong_palette0_tooth_cells": receipt[
            "rendered_wrong_palette0_tooth_cells"
        ],
        # Keep the operator-reported pole endpoints inside the byte-stable
        # replay contract.  Merely requiring the underlying live check to be
        # true would allow two different endpoint renderings to compare equal
        # at this wrapper layer.
        "terminal": receipt["terminal"],
        "rendered_wrong_gray_terminal_cap_cells": receipt[
            "rendered_wrong_gray_terminal_cap_cells"
        ],
        "terminal_phase_receipts": terminal_phase_receipts,
        "final_screenshot_sha256": receipt["final_screenshot_sha256"],
        "checks": receipt["checks"],
    }


def replay_is_clean(
    receipt: dict, close_frame: int, use_frame: int = -1,
    low_health_frame: int = -1, *, require_hazard_coverage: bool = False,
) -> bool:
    """Pure fail-closed contract used by live runs and negative controls."""
    anchor_frame = receipt.get("menu_anchor_frame", 0)
    effective_close_frame = receipt.get(
        "effective_menu_close_frame", close_frame
    )
    base_clean = (
        receipt.get("passed") is True
        and receipt["menu_open_frames"] >= 120
        and anchor_frame >= 0
        and receipt["menu_closed_frame"] >= effective_close_frame
        and receipt["post_menu_closed_frames"] >= 120
        and receipt["menu_close_repair_hits"] == 1
        and receipt["menu_close_native_tail_hits"] == 1
        and receipt["floor_mismatch_frames"] == 0
        and receipt["transient_mismatch_frames"] == 0
        and receipt["map_flip_events"] > 0
        and receipt["unsafe_map_flip_events"] == 0
        and receipt["palette_mismatch_frames"] == 0
        and receipt["endpoint_mismatch_frames"] == 0
        and receipt["visible_attr_mismatch_frames"] == 0
        and receipt["post_menu_transient_mismatch_frames"] == 0
        and receipt["post_menu_palette_mismatch_frames"] == 0
        and receipt["post_menu_floor_mismatch_frames"] == 0
        and receipt["post_menu_endpoint_mismatch_frames"] == 0
        and receipt["post_menu_visible_attr_mismatch_frames"] == 0
        and receipt["active_hazard_attr_write_hits"] == 0
        and receipt["post_menu_active_hazard_attr_write_hits"] == 0
        and receipt["rendered_wrong_palette0_tooth_cells"] == 0
        and receipt["menu_map_alias_frames"] == 0
        and (
            use_frame < 0
            or (
                receipt["menu_use_input_frames"] == 6
                and receipt["menu_a_handler_hits"] == 1
                and receipt["menu_item_dispatch_hits"] == 1
                and receipt["menu_selected_item_trace"]
                and ":g00:i00" not in receipt["menu_selected_item_trace"]
            )
        )
        and (
            low_health_frame < 0
            or receipt["low_health_forced_frames"] >= 120
        )
    )
    if not base_clean:
        return False
    if not require_hazard_coverage:
        return True

    # A menu-close receipt is not evidence for the reported hardware bug if
    # the route has already walked away from the rotating hazard.  The live
    # probe owns detailed rendered/tile/attribute checks; require every one of
    # them for the current-ROM stationary fixture instead of silently
    # accepting a receipt whose coverage predicates are false.
    return hazard_coverage_is_complete(receipt)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("rom", nargs="?", type=Path, default=DEFAULT_ROM)
    parser.add_argument("--states", type=Path, default=STATE_DIR)
    # This compound gate deliberately owns no emulator override: live_receipt
    # always receives the checked-in mGBA singleflight launcher.
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--frames", type=int, default=650)
    parser.add_argument("--timeout", type=float, default=45.0)
    parser.add_argument(
        "--item-use-only",
        action="store_true",
        help="run only the real A-button menu redraw regression cases",
    )
    parser.add_argument(
        "--case",
        help="run one exact named interaction case (two deterministic replays)",
    )
    args = parser.parse_args()

    rom = args.rom.resolve()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)

    cases = [
        ("floor-room12-open160", LIVE_STATE, 0x12, 0x03, 1, 160, -1, -1),
        *[
            (
                f"ceiling-room02-open{open_frame}",
                CEILING_LIVE_STATE,
                0x02,
                0x02,
                1,
                open_frame,
                -1,
                -1,
            )
            for open_frame in range(158, 166)
        ],
        ("floor-room12-use-item", LIVE_STATE, 0x12, 0x03, 1, 160, 240, -1),
        ("ceiling-room02-use-item", CEILING_LIVE_STATE, 0x02, 0x02, 1, 160, 240, -1),
        (
            "floor-room12-use-item-low-health", LIVE_STATE,
            0x12, 0x03, 1, 160, 240, 430,
        ),
        (
            "ceiling-room02-use-item-low-health", CEILING_LIVE_STATE,
            0x02, 0x02, 1, 160, 240, 430,
        ),
    ]
    if args.item_use_only:
        cases = [case for case in cases if case[6] >= 0]
    if args.case:
        cases = [case for case in cases if case[0] == args.case]
        if not cases:
            raise SystemExit(f"unknown Stage-1 hazard/menu case: {args.case}")
    case_receipts = {}
    for (
        case_name, state_name, room, anchor_room, bank, open_frame, use_frame,
        low_health_frame,
    ) in cases:
        state = (args.states / state_name).resolve()
        close_frame = open_frame + (240 if use_frame >= 0 else 160)
        replays = []
        for index in (1, 2):
            replay = live_receipt(
                rom,
                state,
                DEFAULT_MGBA.resolve(),
                output / case_name / f"replay-{index}",
                args.timeout,
                prefix_name="hazard-menu",
                # live_receipt injects the candidate's exact DA13 helper into
                # the serialized state. Preserve the fixture's already-settled
                # tile/attribute planes here: clearing its caches while the
                # menu is frozen would manufacture an impossible dirty-map
                # request that cannot publish until gameplay resumes.
                reinitialize=False,
                settle=args.frames,
                input_mask=0,
                screenshot_interval=5,
                expected_room=room,
                normalization_writes=((0xD880, 0x02),),
                normalization_bank=bank,
                menu_open=True,
                menu_open_frame=open_frame,
                menu_close_frame=close_frame,
                menu_use_frame=use_frame,
                low_health_frame=low_health_frame,
                menu_anchor_room=anchor_room,
                trace_routes=False,
            )
            replay["final_screenshot_sha256"] = digest(
                Path(replay["screenshot"])
            )
            replays.append(replay)
        summaries = [stable_summary(replay) for replay in replays]
        relevant_clean = all(
            replay_is_clean(replay, close_frame, use_frame, low_health_frame)
            for replay in replays
        )
        deterministic = summaries[0] == summaries[1]
        case_receipts[case_name] = {
            "state": str(state),
            "state_sha256": digest(state),
            "replays": summaries,
            "raw_reports": [replay["report"] for replay in replays],
            "open_frame": open_frame,
            "close_frame": close_frame,
            "use_frame": use_frame,
            "low_health_frame": low_health_frame,
            "clean": relevant_clean,
            "deterministic": deterministic,
            "passed": relevant_clean and deterministic,
        }

    checks = {
        "candidate hash is bound": len(rom.read_bytes()) == 0x80000,
        "all floor/ceiling menu round trips are byte-deterministic": (
            all(case["deterministic"] for case in case_receipts.values())
        ),
        "all stationary menu round trips are visually clean": (
            all(case["clean"] for case in case_receipts.values())
        ),
    }
    receipt = {
        "schema": "penta-stage1-hazard-menu-v1",
        "rom": str(rom),
        "rom_sha256": digest(rom),
        "frames": args.frames,
        "cases": case_receipts,
        "checks": checks,
        "passed": all(checks.values()),
    }
    (output / "receipt.json").write_text(json.dumps(receipt, indent=2) + "\n")
    if not receipt["passed"]:
        failed = [name for name, passed in checks.items() if not passed]
        print("FAIL: " + "; ".join(failed))
        return 1
    print(
        "PASS: deterministic floor/ceiling hazard menu round trips close "
        "cleanly without movement"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
