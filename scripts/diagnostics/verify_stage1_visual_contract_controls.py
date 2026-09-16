#!/usr/bin/env python3
"""Offline negative controls for the Stage-1 visual regression harness."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import tempfile

from verify_low_health_flicker import hazard_attributes_clean
from verify_low_health_hazard_determinism import corpus_digest
from verify_pocket_visual_receipts import (
    COMMIT_PROTOCOL_NAME,
    menu_window_report_failures,
)
from verify_release_candidate import build_gates
from verify_stage1_hazard_menu import (
    CURRENT_HAZARD_REQUIRED_CHECKS,
    replay_is_clean,
)
from verify_stage1_north_integrity import (
    OWNER_STATUS_CGB_OWNED,
    OWNER_STATUS_DMG,
    TRAJECTORY_HEADER_SIZE,
    compare_trajectories,
    expected_stage1_attr,
    settled_candidate_state,
)
from verify_stage_card_stability import (
    first_gameplay_map_is_atomic,
    handoff_is_coherent,
    pregame_frames_are_consecutive,
    stage1_entry_transition_integrity,
)


ROOT = Path(__file__).resolve().parents[2]
TILE_COUNT = 21 * 19


def trajectory_record(
    *,
    selector: int,
    corrupt: bool = False,
    corrupt_attr: bool = False,
    unsafe_attr: bool = False,
    camera_y: int = 0x003C,
    scy: int = 0,
    svbk: int = 1,
    gameplay_frame: int = 1,
    owner_status: int = OWNER_STATUS_CGB_OWNED,
) -> bytes:
    header = bytearray(TRAJECTORY_HEADER_SIZE)
    header[0:2] = gameplay_frame.to_bytes(2, "little")
    header[2] = 1                    # room
    header[3:5] = (0x456).to_bytes(2, "little")
    header[5] = 0x8B                # LCDC
    header[7] = scy
    header[8:10] = camera_y.to_bytes(2, "little")
    header[10] = selector
    header[12:14] = (0xC413).to_bytes(2, "little")
    header[19] = 2                  # gameplay scene
    header[20] = 1                  # gameplay active
    header[26] = svbk               # CGB WRAM ownership at capture
    header[27] = owner_status
    if owner_status == OWNER_STATUS_CGB_OWNED:
        header[28] = 1              # physical page belongs to room 1
        header[29:31] = (1).to_bytes(2, "little")
    else:
        header[28] = 0xFF
        header[29:31] = (0xFFFF).to_bytes(2, "little")
    # This generic viewport control intentionally has no room-$01 structural
    # wall companions.  Those four IDs are geometry-dependent and are owned
    # by the reviewed 64-cell room-$01 oracle; scattering them at arbitrary
    # synthetic floor coordinates makes an otherwise clean route internally
    # inconsistent with that oracle.
    room01_wall_ids = {0x24, 0x27, 0x30, 0x33}
    tiles = bytearray(
        0x22 if (value := (index * 17 + 3) & 0xFF) in room01_wall_ids else value
        for index in range(TILE_COUNT)
    )
    if corrupt:
        tiles[173] ^= 0xFF
    attrs = bytearray()
    for index, tile in enumerate(tiles):
        screen_row, screen_column = divmod(index, 21)
        map_y = ((scy + screen_row * 8) >> 3) & 0x1F
        map_x = (screen_column * 8 >> 3) & 0x1F
        attrs.append(expected_stage1_attr(tile, map_y * 32 + map_x))
    if corrupt_attr:
        attrs[173] ^= 0x01
    if unsafe_attr:
        attrs[173] = 0xFF
    return bytes(header + tiles + attrs)


def clean_menu_replay() -> dict[str, int]:
    return {
        "passed": True,
        "menu_open_frames": 150,
        "menu_closed_frame": 321,
        "post_menu_closed_frames": 180,
        # The production repair must be reached through the native menu-close
        # tail exactly once.  Zero permits the old stale attribute cache;
        # multiple hits would hide an accidental per-frame workaround.
        "menu_close_repair_hits": 1,
        "menu_close_native_tail_hits": 1,
        "map_flip_events": 1,
        "unsafe_map_flip_events": 0,
        "menu_map_alias_frames": 0,
        "menu_use_input_frames": 0,
        "menu_a_handler_hits": 0,
        "menu_item_dispatch_hits": 0,
        "menu_selected_item_trace": "",
        "low_health_forced_frames": 0,
        "low_health_scene_frames": 0,
        "floor_mismatch_frames": 0,
        "transient_mismatch_frames": 0,
        "palette_mismatch_frames": 0,
        "endpoint_mismatch_frames": 0,
        "visible_attr_mismatch_frames": 0,
        "post_menu_transient_mismatch_frames": 0,
        "post_menu_palette_mismatch_frames": 0,
        "post_menu_floor_mismatch_frames": 0,
        "post_menu_endpoint_mismatch_frames": 0,
        "post_menu_visible_attr_mismatch_frames": 0,
        "active_hazard_attr_write_hits": 0,
        "post_menu_active_hazard_attr_write_hits": 0,
        "rendered_wrong_palette0_tooth_cells": 0,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    scratch_root = ROOT / "tmp"
    scratch_root.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(
        prefix="stage1-visual-controls-", dir=scratch_root
    ) as temporary:
        temporary_path = Path(temporary)
        baseline = temporary_path / "baseline.bin"
        candidate = temporary_path / "candidate.bin"
        baseline.write_bytes(trajectory_record(
            selector=1, owner_status=OWNER_STATUS_DMG,
        ))
        candidate.write_bytes(trajectory_record(selector=2))
        clean_trajectory = compare_trajectories(candidate, baseline)
        candidate.write_bytes(trajectory_record(selector=2, corrupt=True))
        corrupt_trajectory = compare_trajectories(candidate, baseline)
        candidate.write_bytes(trajectory_record(
            selector=2, corrupt_attr=True,
        ))
        corrupt_attr_trajectory = compare_trajectories(candidate, baseline)
        candidate.write_bytes(trajectory_record(
            selector=2, unsafe_attr=True,
        ))
        unsafe_attr_trajectory = compare_trajectories(candidate, baseline)
        candidate.write_bytes(b"".join((
            trajectory_record(selector=2, gameplay_frame=1),
            trajectory_record(
                selector=2, corrupt=True, svbk=2, gameplay_frame=2,
            ),
            trajectory_record(selector=2, gameplay_frame=3),
        )))
        parked_corrupt_trajectory = compare_trajectories(candidate, baseline)
        candidate.write_bytes(trajectory_record(selector=2, scy=1))
        unmatched_display_trajectory = compare_trajectories(candidate, baseline)
        candidate.write_bytes(trajectory_record(selector=2, camera_y=0x003D))
        unexpected_logical_trajectory = compare_trajectories(candidate, baseline)

        corpus_a = temporary_path / "corpus-a"
        corpus_b = temporary_path / "corpus-b"
        for corpus in (corpus_a, corpus_b):
            corpus.mkdir()
            (corpus / "low-health.frames.tsv").write_bytes(b"frame\tok\n1\t1\n")
            (corpus / "low-health.frame0001.png").write_bytes(b"frame-one")
        same_corpus = corpus_digest(corpus_a) == corpus_digest(corpus_b)
        (corpus_b / "low-health.frame0001.png").write_bytes(b"gray-endpoint")
        changed_corpus = corpus_digest(corpus_a) != corpus_digest(corpus_b)

    settled_report = {
        "final_state": "scene:02 room:01 ffc1:01 lcdc:83",
        "final_hardware": "hdma5:FF vbk:00 svbk:01 lcdc:83",
    }
    settled_control = settled_candidate_state(settled_report)
    unsettled_controls = {}
    for field, replacement in {
        "scene": "03", "ffc1": "00", "hdma5": "00",
        "svbk": "02", "lcdc": "03",
    }.items():
        mutant = dict(settled_report)
        source = "final_hardware" if field in {"hdma5", "svbk"} else "final_state"
        mutant[source] = re.sub(
            rf"{field}:[0-9A-F]{{2}}", f"{field}:{replacement}", mutant[source]
        )
        if field == "lcdc":
            mutant["final_hardware"] = re.sub(
                r"lcdc:[0-9A-F]{2}", "lcdc:03", mutant["final_hardware"]
            )
        unsettled_controls[field] = not bool(
            settled_candidate_state(mutant)["passed"]
        )

    menu_clean = clean_menu_replay()
    menu_mutations = {}
    for field in (
        "menu_close_repair_hits",
        "menu_close_native_tail_hits",
        "menu_map_alias_frames",
        "floor_mismatch_frames",
        "transient_mismatch_frames",
        "palette_mismatch_frames",
        "endpoint_mismatch_frames",
        "visible_attr_mismatch_frames",
        "post_menu_transient_mismatch_frames",
        "post_menu_palette_mismatch_frames",
        "post_menu_floor_mismatch_frames",
        "post_menu_endpoint_mismatch_frames",
        "post_menu_visible_attr_mismatch_frames",
        "active_hazard_attr_write_hits",
        "post_menu_active_hazard_attr_write_hits",
        "rendered_wrong_palette0_tooth_cells",
    ):
        mutant = dict(menu_clean)
        mutant[field] = (
            1
            if field in {
                "active_hazard_attr_write_hits",
                "post_menu_active_hazard_attr_write_hits",
            }
            else 0 if field.endswith("_hits") else 1
        )
        menu_mutations[field] = not replay_is_clean(mutant, 320)

    menu_window_rom = (ROOT / "tmp/window-contract-candidate.gb").resolve()
    clean_menu_window = {
        "rom": str(menu_window_rom),
        "rom_sha256": "ROM-SHA256",
        "attr_mode": "canonical",
        "attr_lut_sha256": "LUT-SHA256",
        "window_frames": "70",
        "bad_frames": "0",
        "map_alias_frames": "1",
        "forced_commit": "1",
        "forced_commit_consumed": "1",
        "forced_commit_protocol": COMMIT_PROTOCOL_NAME,
        "post_close_selector_checked_frames": "60",
        "post_close_selector_alias_frames": "0",
        "post_close_hud_leak_frames": "0",
        "route_frame_limit": "1320",
        "route_open_frame": "1200",
        "route_close_frame": "1260",
        "route_force_alias_frame": "1250",
        "route_force_commit_frame": "1260",
        "route_stale_frame": "-1",
        "attr_checked_frames": "70",
        "attr_bad_frames": "0",
        "attr_mismatch_cells": "0",
        "attr_unsafe_cells": "0",
        "attr_entry_frames": "8",
        "attr_settled_frames": "52",
        "attr_exit_frames": "10",
        "window_hidden_at_close_frames": "0",
        "window_frames_after_close": "0",
        "first_post_close_alias": "none",
    }

    def window_failures(report: dict[str, str]) -> list[str]:
        return menu_window_report_failures(
            report,
            rom=menu_window_rom,
            rom_sha256="ROM-SHA256",
            attr_mode="canonical",
            attr_lut_sha256="LUT-SHA256",
        )

    menu_window_mutations = {}
    for field, value in {
        "rom": str(ROOT / "tmp/wrong-candidate.gb"),
        "rom_sha256": "WRONG-ROM",
        "attr_lut_sha256": "WRONG-LUT",
        "attr_checked_frames": "69",
        "bad_frames": "1",
        "attr_bad_frames": "1",
        "attr_mismatch_cells": "1",
        "attr_unsafe_cells": "1",
        "attr_entry_frames": "0",
        "attr_settled_frames": "0",
        "route_stale_frame": "800",
        "window_frames_after_close": "1",
        "map_alias_frames": "2",
        "forced_commit_protocol": "wrong-protocol",
    }.items():
        mutant = dict(clean_menu_window)
        mutant[field] = value
        menu_window_mutations[field] = bool(window_failures(mutant))
    missing_exit = dict(clean_menu_window)
    missing_exit["attr_exit_frames"] = "0"
    missing_exit["window_hidden_at_close_frames"] = "0"
    menu_window_mutations["missing_exit_boundary"] = bool(
        window_failures(missing_exit)
    )
    legacy_window = {
        key: value for key, value in clean_menu_window.items()
        if not key.startswith("attr_") and not key.startswith("route_")
    }

    clean_rows = [{"unexpected_mismatches": "0"} for _ in range(4)]
    bad_rows = [*clean_rows, {"unexpected_mismatches": "1"}]

    compound_clean = dict(menu_clean)
    compound_clean.update({
        "menu_use_input_frames": 6,
        "menu_a_handler_hits": 1,
        "menu_item_dispatch_hits": 1,
        "menu_selected_item_trace": "f240:g00:i01",
        "low_health_forced_frames": 180,
    })
    compound_low_health_mutant = dict(compound_clean)
    compound_low_health_mutant["low_health_forced_frames"] = 0
    missing_menu_anchor_mutant = dict(compound_clean)
    missing_menu_anchor_mutant["menu_anchor_frame"] = -1
    stationary_hazard_clean = dict(compound_clean)
    stationary_hazard_clean.update({
        "room": "01",
        "post_menu_input_mask": 0,
        "post_menu_input_frames": 0,
        "map_flip_bases": ["9800", "9C00"],
        "checks": {name: True for name in CURRENT_HAZARD_REQUIRED_CHECKS},
    })
    missing_hazard_phase = dict(stationary_hazard_clean)
    missing_hazard_phase["checks"] = dict(stationary_hazard_clean["checks"])
    missing_hazard_phase["checks"][
        "post-menu rendered frames contain no gray tooth pixels"
    ] = False
    moved_out_of_hazard_room = dict(stationary_hazard_clean)
    moved_out_of_hazard_room["room"] = "05"
    moved_out_of_hazard_room["post_menu_input_mask"] = 0x80
    moved_out_of_hazard_room["post_menu_input_frames"] = 169

    final_card = {
        "tile_hash": "CARD",
        "attr_hash": "NEUTRAL",
        "bg0": "PALETTE",
        "bg_cram": "CRAM",
        "tiles": "TILES",
        "attrs": "ATTRS",
        "visual": {"sha256": "COMPLETE-CARD"},
    }
    coherent_handoff = dict(final_card)
    partial_handoff = dict(final_card)
    partial_handoff["attr_hash"] = "PARTIAL-DUNGEON-ATTRS"
    partial_handoff["visual"] = {"sha256": "CYAN-FRAGMENTS"}
    atomic_gameplay = [
        {"frame": "502", "d880": "02", "tile_hash": "CARD",
         "attr_hash": "NEUTRAL"},
        {"frame": "503", "d880": "02", "tile_hash": "DUNGEON",
         "attr_hash": "READY"},
        {"frame": "504", "d880": "02", "tile_hash": "DUNGEON",
         "attr_hash": "READY"},
    ]
    partial_gameplay = [
        *atomic_gameplay[:1],
        {"frame": "503", "d880": "02", "tile_hash": "PARTIAL-A",
         "attr_hash": "PARTIAL"},
        {"frame": "504", "d880": "02", "tile_hash": "PARTIAL-B",
         "attr_hash": "PARTIAL"},
        atomic_gameplay[-1],
    ]

    def transition_frame(
        frame: int, d880: str, ffc1: str, presentation: dict,
    ) -> dict:
        return {
            "frame": str(frame), "d880": d880, "ffc1": ffc1,
            "lcdc": "8B",
            **presentation,
        }

    dungeon = {
        **final_card,
        "tile_hash": "DUNGEON",
        "attr_hash": "READY",
        "bg0": "STAGE1-BG0",
        "bg_cram": "STAGE1-CRAM",
        "tiles": "DUNGEON-TILES",
        "attrs": "DUNGEON-ATTRS",
        "visual": {"sha256": "COMPLETE-DUNGEON"},
    }
    cyan_dungeon = {
        **dungeon,
        "bg0": "CYAN-FLASH",
        "bg_cram": "CYAN-FLASH-CRAM",
        "visual": {"sha256": "CYAN-DUNGEON"},
    }
    clean_entry_transition = [
        *(transition_frame(frame, "18", "01", final_card)
          for frame in range(496, 500)),
        transition_frame(500, "02", "01", final_card),
        transition_frame(501, "00", "01", final_card),
        # The completed map may first become visible during a native service
        # state; the visual classifier must not key acceptance to D880 alone.
        transition_frame(502, "00", "01", dungeon),
        *(transition_frame(frame, "02", "01", dungeon)
          for frame in range(503, 508)),
    ]
    cyan_entry_transition = [dict(row) for row in clean_entry_transition]
    cyan_entry_transition[5] = transition_frame(
        501, "00", "01", cyan_dungeon
    )
    unstable_splash_transition = [
        dict(row) for row in clean_entry_transition
    ]
    unstable_splash_transition[3] = transition_frame(
        499, "18", "01", partial_handoff
    )
    cyan_settle_transition = [dict(row) for row in clean_entry_transition]
    cyan_settle_transition[8] = transition_frame(
        504, "00", "01", cyan_dungeon
    )
    clean_entry_audit = stage1_entry_transition_integrity(
        clean_entry_transition, 500
    )
    cyan_entry_audit = stage1_entry_transition_integrity(
        cyan_entry_transition, 500
    )
    unstable_splash_audit = stage1_entry_transition_integrity(
        unstable_splash_transition, 500
    )
    cyan_settle_audit = stage1_entry_transition_integrity(
        cyan_settle_transition, 500
    )
    consecutive_pregame = [
        {"frame": str(frame)} for frame in range(170, 516)
    ]

    gates = {
        gate.name: gate
        for gate in build_gates(
            ROOT / "tmp/nonexistent-contract-candidate.gb",
            ROOT / "tmp/nonexistent-contract-output",
            expanded_candidate_override=False,
            menu_icon_candidate_override=False,
        )
    }
    low_command = gates["low_health_flicker"].command
    flicker_command = gates["frame_flicker"].command
    hazard_command = gates["stage1_current_hazard_menu"].command
    hazard_source = (
        ROOT / "scripts/diagnostics/verify_stage1_hazard_menu.py"
    ).read_text()
    current_hazard_source = (
        ROOT / "scripts/diagnostics/verify_stage1_current_hazard_menu.py"
    ).read_text()
    north_source = (
        ROOT / "scripts/diagnostics/verify_stage1_north_integrity.py"
    ).read_text()
    north_probe = (
        ROOT / "scripts/diagnostics/probe_stage1_north_integrity.lua"
    ).read_text()
    stage_card_source = (
        ROOT / "scripts/diagnostics/verify_stage_card_stability.py"
    ).read_text()
    stage_card_probe = (
        ROOT / "scripts/diagnostics/probe_stage_card_stability.lua"
    ).read_text()
    menu_window_source = (
        ROOT / "scripts/diagnostics/verify_menu_window_order.py"
    ).read_text()
    menu_window_probe = (
        ROOT / "scripts/diagnostics/probe_menu_window_order.lua"
    ).read_text()
    gallery_source = (
        ROOT / "scripts/diagnostics/build_visual_audit.py"
    ).read_text()
    stage1_builder_source = (
        ROOT / "scripts/build_v302_title_fix.py"
    ).read_text()
    release_builder_source = (
        ROOT / "scripts/build_ted_expanded_candidate.py"
    ).read_text()
    rejected_scanner_source = (
        ROOT / "scripts/stage1_semantic_scanner_cache.py"
    ).read_text()
    rejected_scanner_verifier_source = (
        ROOT / "scripts/diagnostics/verify_stage1_semantic_scanner_cache.py"
    ).read_text()
    checks = {
        "clean stationary menu-close receipt is accepted": replay_is_clean(
            menu_clean, 320
        ),
        "every menu/floor/spike mismatch class has a rejecting control": all(
            menu_mutations.values()
        ),
        "compound item/menu/low-health sequence is mandatory and fail-closed": (
            replay_is_clean(compound_clean, 320, 240, 430)
            and not replay_is_clean(
                compound_low_health_mutant, 320, 240, 430
            )
            and "use-item-low-health" in hazard_source
            and "low_health_frame=low_health_frame" in hazard_source
        ),
        "menu actions are event-anchored and a missing anchor is rejected": (
            not replay_is_clean(missing_menu_anchor_mutant, 320, 240, 430)
            and "menu_anchor_room=anchor_room" in hazard_source
            and '"menu_anchor_frame"' in hazard_source
            and "effective_menu_close_frame" in hazard_source
        ),
        "stationary hardware hazard coverage cannot pass by walking away": (
            replay_is_clean(
                stationary_hazard_clean, 320, 240, 430,
                require_hazard_coverage=True,
            )
            and not replay_is_clean(
                missing_hazard_phase, 320, 240, 430,
                require_hazard_coverage=True,
            )
            and not replay_is_clean(
                moved_out_of_hazard_room, 320, 240, 430,
                require_hazard_coverage=True,
            )
        ),
        "one wrong low-health hazard frame is rejected": (
            hazard_attributes_clean(clean_rows)
            and not hazard_attributes_clean(bad_rows)
        ),
        "world-coordinate route comparison tolerates private selector cadence": (
            clean_trajectory["maximum_progress_viewport_tile_differences"] == 0
            and clean_trajectory["unexpected_logical_state_records"] == 0
            and clean_trajectory["unmatched_display_state_records"] == 0
            and clean_trajectory["candidate_attribute_integrity"]["exact"]
        ),
        "one wrong intermediate wall tile is rejected": (
            corrupt_trajectory["maximum_progress_viewport_tile_differences"] == 1
            and corrupt_trajectory["progress_differing_records"] == 1
        ),
        "one wrong north-route VBK1 cell is rejected": (
            corrupt_attr_trajectory["candidate_attribute_integrity"]
            ["mismatch_cells"] == 1
            and not corrupt_attr_trajectory["candidate_attribute_integrity"]
            ["exact"]
        ),
        "uninitialized FF north-route attribute is rejected": (
            unsafe_attr_trajectory["candidate_attribute_integrity"]
            ["unsafe_high_bit_cells"] == 1
            and not unsafe_attr_trajectory["candidate_attribute_integrity"]
            ["exact"]
        ),
        "parked service frame cannot hide one wrong wall tile": (
            parked_corrupt_trajectory[
                "maximum_service_viewport_tile_differences"
            ] == 1
            and parked_corrupt_trajectory[
                "service_presentation_differing_records"
            ] == 1
        ),
        "unexpected logical and display states remain distinct failures": (
            unmatched_display_trajectory[
                "unmatched_display_state_records"
            ] == 1
            and unexpected_logical_trajectory[
                "unexpected_logical_state_records"
            ] == 1
        ),
        "north endpoint requires every settled hardware predicate": (
            bool(settled_control["passed"])
            and all(unsettled_controls.values())
        ),
        "partial colored STAGE-card handoff is rejected": (
            handoff_is_coherent([final_card], [coherent_handoff])
            and not handoff_is_coherent([final_card], [partial_handoff])
        ),
        "partial first dungeon map is rejected": (
            first_gameplay_map_is_atomic(atomic_gameplay, 502, "CARD")
            and not first_gameplay_map_is_atomic(
                partial_gameplay, 502, "CARD"
            )
        ),
        "blank-SRAM transition accepts only complete card or dungeon frames": (
            bool(clean_entry_audit["passed"])
            and not bool(cyan_entry_audit["passed"])
            and cyan_entry_audit["reason"] == "third-presentation-state"
            and not bool(unstable_splash_audit["passed"])
            and unstable_splash_audit["reason"]
            == "unstable-final-splash"
            and not bool(cyan_settle_audit["passed"])
            and cyan_settle_audit["reason"] == "unstable-dungeon-tail"
        ),
        "blank-SRAM pregame capture rejects one missing frame": (
            pregame_frames_are_consecutive(consecutive_pregame, 500)
            and not pregame_frames_are_consecutive(
                consecutive_pregame[1:], 500
            )
            and not pregame_frames_are_consecutive(
                consecutive_pregame[:-1], 500
            )
            and not pregame_frames_are_consecutive(
                consecutive_pregame[:120] + consecutive_pregame[121:], 500
            )
            and not pregame_frames_are_consecutive(
                consecutive_pregame[:-3] + consecutive_pregame[-2:], 500
            )
        ),
        "stage-card gate runs two exact natural blank-SRAM routes": (
            'output / "blank-sram-run-1"' in stage_card_source
            and 'output / "blank-sram-run-2"' in stage_card_source
            and "force_save=False" in stage_card_source
            and 'STAGE_CARD_FORCE_SAVE="1" if force_save else "0"'
            in stage_card_source
            and "Stage-card A at title-confirm +107" in stage_card_probe
            and "keys = keys | pulse(300, 306, KEY_A)" in stage_card_probe
        ),
        "low-health replay digest detects one changed rendered frame": (
            same_corpus and changed_corpus
        ),
        "release matrix requires deterministic low-health hazard attributes": (
            any(
                argument.endswith("verify_low_health_hazard_determinism.py")
                for argument in low_command
            )
            and "--require-hazard-attributes" in low_command
            and "--require-music-transition" in low_command
            and "--samples" in low_command
            and low_command[low_command.index("--samples") + 1] == "417"
            and "--post-trigger-keys" in low_command
            and low_command[
                low_command.index("--post-trigger-keys") + 1
            ] == "0x41"
        ),
        "release matrix meets the Pocket aggregate flicker sample bound": (
            "--frames" in flicker_command
            and flicker_command[flicker_command.index("--frames") + 1]
            == "2400"
        ),
        "hazard scanner retains all rows and both translated endpoints": (
            "front.db(0x06, 0x18)" in stage1_builder_source
            and "0x0E, 0x0F" in stage1_builder_source
            and "0x0E, 0x0B" in stage1_builder_source
            and "(STAGE1_HAZARD_START4_EDGE_ADDR + 9)" in stage1_builder_source
        ),
        "rejected room-3 scanner bypass cannot enter a release build": (
            "stage1_semantic_scanner_cache" not in release_builder_source
            and "rejected, non-promotable" in rejected_scanner_source
            and "must never be promoted or deployed" in rejected_scanner_source
            and "historical diagnostic coverage, not a production qualifier"
            in rejected_scanner_verifier_source
            and "forced-nonempty-room03" in rejected_scanner_verifier_source
            and "direct_exit_rejected" in rejected_scanner_verifier_source
        ),
        "release matrix requires current-ROM menu/item/low-health replay matrix": (
            any(
                argument.endswith("verify_stage1_current_hazard_menu.py")
                for argument in hazard_command
            )
            and '"--menu-hold-frames", type=int, default=240' in current_hazard_source
            and '"--menu-use-delay", type=int, default=80' in current_hazard_source
            and '"--low-health-delay", type=int, default=270' in current_hazard_source
            and "menu_close_frame=close_frame" in current_hazard_source
            and "menu_use_frame=use_frame" in current_hazard_source
            and "low_health_frame=low_health_frame" in current_hazard_source
            and "post_menu_input_mask=0" in current_hazard_source
            and "require_hazard_coverage=True" in current_hazard_source
            and "replay_indexes = (1,) if args.single_replay else (1, 2)"
            in current_hazard_source
            and "DEFAULT_MGBA.resolve()" in current_hazard_source
            and "--mgba" not in current_hazard_source
        ),
        "target-only north gate binds tiles attrs states and service frames": (
            "else progress_trajectory_ok and lag_ok and trajectory_ok"
            in north_source
            and '"progress_route_viewports_exact"' in north_source
            and '"unexpected_logical_state_records"]) == 0' in north_source
            and '"unmatched_display_state_records"]) == 0' in north_source
            and '"candidate_attribute_integrity"' in north_source
            and '"maximum_service_viewport_tile_differences"' in north_source
            and "local trajectory_vbk = emu:read8(0xFF4F) & 0x01"
            in north_probe
            and "emu:write8(0xFF4F, 0)" in north_probe
            and "emu:write8(0xFF4F, 1)" in north_probe
            and "0x8000 + trajectory_base" in north_probe
            and "emu:write8(0xFF4F, trajectory_vbk)" in north_probe
            and "gameplay_presentation_settled()" in north_probe
        ),
        "menu Window gate binds candidate and checks every visible VBK1 frame": (
            'report.get("rom_sha256") != rom_sha256' in menu_window_source
            and "attr_checked_frames != window_frames" in menu_window_source
            and 'report.get("attr_lut_sha256")' in menu_window_source
            and "attribute_mismatch_count(base)" in menu_window_probe
            and "attr_bad_frames = attr_bad_frames + 1" in menu_window_probe
            and "attr_entry_frames" in menu_window_probe
            and "attr_settled_frames" in menu_window_probe
            and "attr_exit_frames" in menu_window_probe
        ),
        "release menu route exercises entry, settled state, and close": (
            "--close-frame" in gates["menu_window_publish_order"].command
            and gates["menu_window_publish_order"].command[
                gates["menu_window_publish_order"].command.index(
                    "--close-frame"
                ) + 1
            ] == "1400"
            and "--frames" in gates["menu_window_publish_order"].command
            and int(gates["menu_window_publish_order"].command[
                gates["menu_window_publish_order"].command.index(
                    "--frames"
                ) + 1
            ]) > 1400
        ),
        "Pocket aggregate rejects missing or mutated Window VBK1 evidence": (
            not window_failures(clean_menu_window)
            and all(menu_window_mutations.values())
            and bool(window_failures(legacy_window))
        ),
        "human audit consumes deterministic low-health and menu receipts": (
            "penta-low-health-hazard-determinism-v1" in gallery_source
            and 'root / "stage1-hazard-menu"' in gallery_source
            and "no movement is permitted" in gallery_source
        ),
    }
    receipt = {
        "schema": "penta-stage1-visual-contract-controls-v1",
        "menu_negative_controls": menu_mutations,
        "menu_window_negative_controls": menu_window_mutations,
        "clean_menu_window_failures": window_failures(clean_menu_window),
        "legacy_menu_window_failures": window_failures(legacy_window),
        "clean_trajectory": clean_trajectory,
        "corrupt_trajectory": corrupt_trajectory,
        "corrupt_attr_trajectory": corrupt_attr_trajectory,
        "unsafe_attr_trajectory": unsafe_attr_trajectory,
        "parked_corrupt_trajectory": parked_corrupt_trajectory,
        "unmatched_display_trajectory": unmatched_display_trajectory,
        "unexpected_logical_trajectory": unexpected_logical_trajectory,
        "settled_endpoint_control": settled_control,
        "unsettled_endpoint_controls": unsettled_controls,
        "clean_stage1_entry_transition": clean_entry_audit,
        "cyan_stage1_entry_mutation": cyan_entry_audit,
        "cyan_stage1_settle_mutation": cyan_settle_audit,
        "unstable_final_splash_mutation": unstable_splash_audit,
        "checks": checks,
        "passed": all(checks.values()),
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(receipt, indent=2) + "\n")
    if not receipt["passed"]:
        failed = [name for name, passed in checks.items() if not passed]
        print("FAIL: " + "; ".join(failed))
        return 1
    print(
        "PASS: Stage-1 visual harness rejects menu residue, gray endpoints, "
        "low-health drift, one wrong wall tile, and replay nondeterminism"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
