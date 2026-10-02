#!/usr/bin/env python3
"""Fail closed before reporting a Stage-1 candidate as ready.

This is the reporting interceptor for the repeatedly reported Stage-1 visual
regressions.  It runs only checked-in Python verifiers, in a fixed serial
order.  It never invokes an emulator executable itself and exposes no
``--mgba`` override.

READY requires all of the following evidence for the exact candidate SHA:

* exact cold and attract-returned Nightfall title palettes, attributes, and
  rendered rasters, with readable white/grayscale menus explicitly rejected;
* exhaustive live-LCDC menu-selector and Stage-1 sentinel machine-code proofs;
* an untouched blank-SRAM route through Stage 1, SELECT open/close, and the
  natural bank-1 art-loader completion;
* an independent native SELECT Window open/hold/close route whose visible
  C4E0 tiles and candidate-derived VBK1 attributes are exact every frame;
* the exact archived scene-$0B wall incident, the compatible operator state,
  its SELECT-only candidate-native closed derivative, and duplicate live
  native-menu roundtrips (static savestate inspection alone is not accepted);
* a consecutive-frame blank-SRAM Stage-card handoff with no cyan/partial
  third presentation state;
* the independent reviewed room-$01 north-wall oracle, replayed exactly;
* three deep Stage-1 fixtures whose completed tile and ordinary-attribute
  publications match an immutable entry-owned oracle on both physical maps;
* a candidate-generated Stage-1 pickup state plus all 19 pickup forms replayed
  at the current visible host with exact attributes, graphics, and CRAM;
* a cold-boot, natural 3,600-frame box route with temporal tile/attribute and
  rendered-raster pickup-color coverage;
* a naturally generated, ROM-owned hazard-room state;
* a stationary menu replay which preserves that ROM-owned state and performs
  no normalization writes;
* an independent rendered-pixel continuity receipt which rejects clear cells,
  yellow trails, gray spikes, and wall-edge artifacts; and
* the operator-declared 95 percent release floors on named Stages 1/2/3/4/5,
  strict 99--101 percent qualification on Stage 6, and the current strict
  equal-world-position Stage-7 speed oracle.

Any missing input, failed subprocess, stale SHA, malformed receipt, timeout,
or changed candidate produces NOT_READY.  Outputs must live below repository
``tmp/`` or ``/mnt/data/tmp/`` and a run never reuses a non-empty output path.
"""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
DIAGNOSTICS = ROOT / "scripts" / "diagnostics"
NATURAL_VERIFIER = DIAGNOSTICS / "verify_stage1_natural_menu_bg.py"
MENU_WINDOW_VERIFIER = DIAGNOSTICS / "verify_menu_window_order.py"
MENU_WINDOW_PROBE = DIAGNOSTICS / "probe_menu_window_order.lua"
MENU_COMMIT_PROTOCOL = DIAGNOSTICS / "menu_commit_protocol.py"
TITLE_NIGHTFALL_VERIFIER = DIAGNOSTICS / "verify_title_nightfall_mgba.py"
TITLE_NIGHTFALL_PROBE = DIAGNOSTICS / "probe_title_nightfall_mgba.lua"
MENU_RACE_VERIFIER = DIAGNOSTICS / "verify_stage1_menu_race_static.py"
STAGE_CARD_VERIFIER = DIAGNOSTICS / "verify_stage_card_stability.py"
STATE_GENERATOR = DIAGNOSTICS / "generate_stage1_hazard_state.py"
HAZARD_MENU_VERIFIER = DIAGNOSTICS / "verify_stage1_current_hazard_menu.py"
CONTINUITY_VERIFIER = DIAGNOSTICS / "verify_stage1_rendered_continuity.py"
CONTINUITY_OPERATOR_CAPTURE_FIXTURE = (
    DIAGNOSTICS / "fixtures/stage1_rendered_operator_captures.json"
)
SPEED_QUALIFIER = DIAGNOSTICS / "verify_split_stage_speed_qualification.py"
PICKUP_STATE_GENERATOR = DIAGNOSTICS / "generate_stage1_pickup_state.py"
PICKUP_HOST_VERIFIER = (
    DIAGNOSTICS / "verify_pickup_current_host_palettes.py"
)
STAGE1_NO_BLEED_VERIFIER = DIAGNOSTICS / "verify_stage1_no_bleed.py"
STAGE1_NO_BLEED_PROBE = DIAGNOSTICS / "probe_stage1_no_bleed.lua"
PROCESS_CHECK = ROOT / "scripts" / "check_emulator_processes.sh"
NORTH_VERIFIER = DIAGNOSTICS / "verify_stage1_north_integrity.py"
SCENE0B_BINDER = (
    DIAGNOSTICS / "verify_stage1_scene0b_captured_menu_receipt.py"
)
SCENE0B_LIVE_VERIFIER = (
    DIAGNOSTICS / "verify_stage1_scene0b_live_menu_roundtrip.py"
)
SCENE0B_LIVE_PROBE = (
    DIAGNOSTICS / "probe_stage1_scene0b_live_menu_roundtrip.lua"
)
TILEMAP_VERIFIER = DIAGNOSTICS / "verify_stage1_tilemap_copy.py"
TILEMAP_PROBE = DIAGNOSTICS / "probe_stage1_tilemap_copy.lua"
TILEMAP_STATES_ROOT = ROOT / "save_states_for_claude"
ROOM01_WALL_ORACLE = DIAGNOSTICS / "stage1_room01_wall_oracle.py"
ROOM01_WALL_FIXTURE = (
    DIAGNOSTICS / "fixtures" / "stage1_room01_wall_oracle.json"
)
SCENE0B_CAPTURE_FIXTURE = (
    DIAGNOSTICS / "fixtures" / "stage1_scene0b_capture_contract.json"
)

if str(DIAGNOSTICS) not in sys.path:
    sys.path.insert(0, str(DIAGNOSTICS))
from verify_stage1_scene0b_captured_menu_receipt import (  # noqa: E402
    BOUND_SCHEMA as SCENE0B_BOUND_SCHEMA,
    validate_bound_receipt as validate_scene0b_bound_receipt,
)
import verify_pocket_visual_receipts as pickup_receipts  # noqa: E402
import verify_stage1_natural_menu_bg as natural_menu_oracle  # noqa: E402
import verify_stage1_tilemap_copy as tilemap_oracle  # noqa: E402
import verify_menu_window_order as menu_window_oracle  # noqa: E402
import verify_stage1_no_bleed as no_bleed_oracle  # noqa: E402
import verify_stage1_north_integrity as north_oracle  # noqa: E402
import verify_title_nightfall_mgba as title_nightfall_oracle  # noqa: E402
import verify_split_stage_speed_qualification as speed_qualifier  # noqa: E402

SCHEMA = "penta-stage1-reported-regressions-ready-v10"
TITLE_NIGHTFALL_SCHEMA = title_nightfall_oracle.SCHEMA
NORTH_SCHEMA = "penta-stage1-north-integrity-v3"
CONTINUITY_SCHEMA = "penta-stage1-rendered-continuity-v1"
SPEED_SCHEMA = "penta-split-stage-speed-qualification-v4"
SPEED_STATUS = "PASS_RELEASE_95_NAMED_STAGE6_STRICT99_STAGE7_EQUAL_START97"
STATE_SCHEMA = "penta-stage1-hazard-state-v1"
HAZARD_MENU_SCHEMA = "penta-stage1-current-hazard-menu-v1"
MENU_RACE_SCHEMA = "penta-stage1-menu-race-static-v2"
STAGE_CARD_SCHEMA = "penta-stage-card-stability-v1"
PICKUP_STATE_SCHEMA = "penta-stage1-current-pickup-state-v1"
PICKUP_HOST_SCHEMA = "penta-dragon-dx-pickup-current-host-palettes-v1"
NO_BLEED_SCHEMA = "penta-dragon-dx-stage1-no-bleed-v6"
TILEMAP_RECEIPT_SCHEMA = tilemap_oracle.RECEIPT_SCHEMA
TILEMAP_RELEASE_STATES = (
    "level1_sara_w_alone.ss0",
    "level1_sara_w_spike_hazard.ss0",
    "level1_sara_w_healpotion1_poison_cure_slow_cure.ss0",
)
TILEMAP_RELEASE_FRAMES = 8000
TILEMAP_RELEASE_TIMEOUT_SECONDS = 60.0
TILEMAP_MINIMUM_PUBLICATIONS = 3000

MENU_WINDOW_FRAMES = 1500
MENU_WINDOW_OPEN_FRAME = 1200
MENU_WINDOW_CLOSE_FRAME = 1380
TITLE_NIGHTFALL_CHECKS = frozenset({
    "exact candidate SHA is authenticated",
    "cold title uses all six exact Nightfall attribute roles",
    "returned title uses all six exact Nightfall attribute roles",
    "cold title BG1..BG6 CRAM matches palette YAML",
    "returned title BG1..BG6 CRAM matches palette YAML",
    "cold title renders a dark indigo chromatic field",
    "returned title renders a dark indigo chromatic field",
    "cold and returned title rasters are byte-identical",
    "white or grayscale title menus are rejected",
})
MENU_WINDOW_REPORT_KEYS = frozenset({
    "frames", "window_frames", "bad_frames",
    "window_frames_after_close", "stale_injected", "stale_scene",
    "stale_window_frames_after_grace", "worst_mismatches",
    "map_alias_frames", "forced_commit", "forced_commit_protocol",
    "forced_commit_consumed",
    "post_close_selector_checked_frames",
    "post_close_selector_alias_frames", "post_close_hud_leak_frames",
    "route_frame_limit", "route_open_frame", "route_close_frame",
    "route_force_alias_frame", "route_force_commit_frame",
    "route_stale_frame",
    "rom", "rom_sha256", "attr_mode", "attr_lut_sha256",
    "attr_checked_frames", "attr_bad_frames", "attr_mismatch_cells",
    "attr_unsafe_cells", "attr_entry_frames", "attr_settled_frames",
    "attr_exit_frames", "window_hidden_at_close_frames",
    "worst_attr_mismatches", "final_state", "transitions", "first_bad",
    "first_visible", "first_alias", "first_post_close_alias",
    "first_attr_bad", "content_mode", "content_fixture_sha256",
    "content_checked_frames", "content_bad_frames",
    "content_source_mismatch_cells", "content_window_mismatch_cells",
    "worst_content_source_mismatches",
    "worst_content_window_mismatches", "content_raster_trace",
    "first_content_bad", "content_raster_checked_frames",
    "content_raster_bad_frames", "content_raster_invariant_sha256",
    "first_content_raster_bad",
})

NO_BLEED_FRAMES = 3600
NO_BLEED_MODE = "box"
NO_BLEED_ROUTE_SOURCE = (
    "cold boot; native Stage 1 selection; continuous input"
)
NO_BLEED_RECEIPT_KEYS = frozenset({
    "schema", "status", "rom", "rom_md5", "rom_sha256", "route",
    "diagnostic_state", "raster_alignment_radius_frames",
    "stage1_table_histogram", "probe", "checks", "contact_sheet",
    "contact_sheet_sha256", "raster_contact_sheet",
    "raster_contact_sheet_sha256", "failures",
})
NO_BLEED_ROUTE_KEYS = frozenset({
    "source", "mode", "play_frames_requested", "emulated_seconds",
})
NO_BLEED_PROBE_KEYS = frozenset({
    "captures", "raster_captures", "helper_events", "frames",
    "sampled_frames", "checked_cells", "pal1_cells", "pickup_state_saved",
    "unexpected_cells",
    "unexpected_semantic_pickup_cells", "unexpected_floor_cells",
    "contextual_mismatch_pairs", "unsafe_cells",
    "runtime_lut_mismatch_frames", "runtime_lut_mismatch_cells",
    "runtime_lut_mismatch_max", "runtime_lut_mismatch_pairs",
    "runtime_lut_dma_unreadable_frames",
    "first_runtime_lut_dma_unreadable", "first_runtime_lut_mismatch_frame",
    "first_runtime_lut_mismatch_details", "first_pal1_frame",
    "first_unexpected_frame", "first_unexpected_floor_frame",
    "first_unexpected_floor_details", "scene_frames", "scene_histogram",
    "first_non_stage_scene_frame", "first_non_stage_scene",
    "compiler_unreadable_scene_frames", "active_frames", "scroll_changes",
    "scx_changes", "scy_changes", "source_signature_changes",
    "final_scene", "final_ffc1", "final_pc", "final_sp", "final_svbk",
    "final_compiler_unreadable", "debug_copy_hits", "debug_atomic_hits",
    "debug_pure_hits", "debug_main_hits", "debug_last_address",
    "capture_count", "raster_capture_count", "helper_event_count",
    "layout_record_count", "first_unexpected_screenshot",
    "first_unexpected_details", "pal1_tiles", "pal1_captures",
})
NO_BLEED_CAPTURE_KEYS = frozenset({
    "play_frame", "elapsed_seconds", "screenshot", "attribute_histogram",
    "palette_1_cells", "unexpected_palette_cells",
    "unsafe_attribute_cells", "screenshot_sha256", "native_size",
})
NO_BLEED_RASTER_CAPTURE_KEYS = frozenset({
    "play_frame", "elapsed_seconds", "screenshot", "lcdc", "scx", "scy",
    "source_signature", "dc00", "dc01", "dc02", "dc03", "cache_9800",
    "cache_9c00", "c1a4", "raw_hash", "attr_hash", "layout_id",
    "source_prefix", "pickup_rectangles", "oam_rectangles",
    "screenshot_sha256", "native_size", "raster_alignment_frames",
    "raster_audit",
})
NO_BLEED_RASTER_AUDIT_KEYS = frozenset({
    "background_pickup_accent_pixels", "stray_pickup_accent_pixels",
    "first_stray_coordinates",
})
NO_BLEED_CHECKS = frozenset({
    "1200+ continuous actual gameplay frames",
    "private-WRAM compiler scene samples are exactly bounded",
    "every actual-play frame sampled",
    "route visibly scrolled",
    "route exercised horizontal scrolling",
    "route exercised vertical scrolling",
    "intentional health-red pickup cells observed",
    "all interval receipts contain no unsafe attribute bits",
    "every contextual non-pickup palette role is explicitly reviewed",
    "runtime Stage 1 LUT changes are exact reviewed wall roles",
    "OAM-DMA LUT samples are exact and separately classified",
    "scroll/source transition raster windows captured",
    "intentional semantic pickup accents are present in raster audit",
    "no detached pickup colors or floor-pattern bleed in rendered raster",
    "no tile-bank/flip/priority leakage",
    "at least six native screenshots",
    "final state remains Stage 1 gameplay",
})

TILEMAP_RECEIPT_KEYS = frozenset({
    "schema", "status", "candidate", "candidate_sha256", "configuration",
    "oracle", "tool_identity", "reports", "totals", "checks", "failures",
})
TILEMAP_CONFIGURATION_KEYS = frozenset({
    "states_root", "state_names", "frames", "timeout_seconds",
    "warm_reset", "force_pure", "trace_hash", "mgba",
})
TILEMAP_ORACLE_KEYS = frozenset({
    "schema", "canonical_lut_sha256", "copier_sha256",
    "ordinary_attribute_scope", "semantic_overlay_owner",
})
TILEMAP_REPORT_KEYS = frozenset({
    "state_name", "state_path", "state_sha256", "report_path",
    "retargeted_state_path", "retargeted_state_sha256", "retarget_mode",
    "report_sha256", "atomic_completions", "pure_completions",
    "exact_copies", "destinations",
})
TILEMAP_TOTAL_KEYS = frozenset({
    "requested_states", "completed_reports", "completions",
    "atomic_completions", "destinations",
})
TILEMAP_CHECKS = frozenset({
    "candidate ROM unchanged",
    "all requested fixtures completed",
    "every report passed the immutable publication oracle",
    "every fixture exercised dirty two-plane publication",
})

STRICT_SPEED_FLOOR = 0.99
STRICT_SPEED_CEILING = 1.01
NAMED_RELEASE_FLOOR = 0.95
NAMED_RELEASE_STAGES = frozenset({1, 2, 3, 4, 5})
MAIN_RELEASE_STAGES = NAMED_RELEASE_STAGES - {2}
STAGE2_RELEASE_STAGES = frozenset({2})
STRICT_SPEED_CLASSIFICATION = "STRICT_99_TO_101"
NAMED_RELEASE_CLASSIFICATION = "NAMED_STAGE_RELEASE_FLOOR_95"
STAGE7_SPEED_FLOOR = 0.97
STAGE7_SPEED_CEILING = 1.02
STAGE7_SPEED_CLASSIFICATION = "EQUAL_START_COMBINED_SEEDS_97_TO_102"

SPEED_MUTATION_CONTROLS = frozenset({
    "rejects_candidate",
    "rejects_missing_stage1_waiver",
    "rejects_wrong_stage1_waiver",
    "rejects_global_waiver",
    "rejects_other_stage_waiver",
    "rejects_classification",
    "rejects_missing_stage",
    "rejects_duplicate_stage",
    "rejects_ratio",
    "rejects_stage2_profile",
    "rejects_stage2_dma",
    "rejects_stage7_candidate",
    "rejects_stage7_status",
    "rejects_stage7_ratio",
    "rejects_stage7_tool",
})

SPEED_RECEIPT_KEYS = frozenset({
    "schema", "status", "candidate", "candidate_sha256",
    "original_rom_sha256", "measurement", "profiles", "tool_identity",
    "rows", "mutation_controls",
})

SPEED_MEASUREMENT_KEYS = frozenset({
    "input_mode", "frames", "strict_ratio_floor", "strict_ratio_ceiling",
    "named_stage_operator_release_floor", "named_floor_stages",
    "named_floors_are_per_stage_only",
    "strict_target_misses_remain_explicit", "strict_fixed_input_stages",
    "stage7_world_position_ratio_floor",
    "stage7_world_position_ratio_ceiling",
    "stage7_fixed_frame_route_is_diagnostic_only",
    "global_slowdown_waivers", "other_stage_slowdown_waivers",
    "stages_covered_exactly_once", "scroll_change_count_policy",
})

SPEED_ROW_KEYS = frozenset({
    "stage", "original_main_loop_hits", "candidate_main_loop_hits",
    "ratio_exact", "ratio_percent", "accepted_slowdown_floor",
    "target_met", "accepted_slowdown_deviation", "throughput_accepted",
    "qualification_class", "deterministic_replay", "route_coverage_ok",
    "scene_ok",
})

SPEED_STAGE7_PROFILE_KEYS = frozenset({
    "receipt", "receipt_sha256", "stage", "ratio_exact", "ratio_percent",
    "target_floor", "target_ceiling", "qualification_class",
    "deterministic_replay", "endpoint_route_exact",
    "post_settle_vertical_exact", "measured_half_cycles", "elapsed_frames",
    "fixed_frame_loop_ratio_diagnostic", "input_identities",
})

NATURAL_REPORT_KEYS = frozenset({
    "rom", "rom_sha256", "lut_sha256", "art_sha256", "expected_room", "frames",
    "open_frame", "close_frame", "menu_key", "close_key", "no_menu_control",
    "raster_baseline_frames", "baseline_frames",
    "baseline_bad_frames", "menu_frames", "menu_bad_frames",
    "menu_mismatch_cells", "post_close_frames",
    "post_close_bad_frames", "post_close_mismatch_cells",
    "last_preopen", "first_window", "first_closed", "first_menu_bad",
    "first_baseline_bad", "first_post_close_bad", "final_state",
    "first_gameplay", "settled_art_mismatch_bytes", "settled_art_examples",
    "settled_df5b", "settled_art_state", "art_writer_trace", "transitions",
    "menu_selector_trace",
    "first_selector_frame", "first_selector_lcdc", "first_selector_dc0b",
    "timer_isr_hits", "timer_baseline_hits", "timer_menu_hits",
    "timer_post_close_hits", "timer_max_frame_gap", "timer_max_cycle_gap", "timer_gap_trace",
    "publication_latch_trace", "publication_latch_fault",
    "semantic_visible_writes", "semantic_write_trace",
    "hardware_register_trace", "publication_boundary_trace",
    "temporal_raster_trace", "obj_contract_trace",
})

MENU_RACE_CHECKS = frozenset({
    "relevant_machine_code_exact",
    "rom_checksums_valid",
    "selector_all_lcdc_dc0b_bytes",
    "selector_live_bg_never_changes",
    "selector_window_always_opposite_live_bg",
    "stage1_sentinel_all_ffe4_scene_bytes",
    "stage1_ff_always_forces_repaint",
})

STAGE_CARD_CHECKS = frozenset({
    "rendered STAGE card retires without exposing overwritten glyph graphics",
    "outgoing title never becomes a nonuniform monochrome image",
    "exact map-flip palette handoff is installed",
    "first route completed",
    "replay route completed",
    "selector observed",
    "splash observed",
    "frame-state replay exact",
    "rendered-frame replay exact",
    "stock saved-game route completed",
    "saved-game route stays within stock timing bound",
    "selector attributes remain palette 0",
    "splash attributes remain palette 0",
    "selector BG0 is temporally stable",
    "splash keeps the reviewed colored card or a raster-verified terminal black fade",
    "selector never becomes monochrome",
    "gameplay handoff preserves only the complete final STAGE card",
    "first dungeon handoff has no partial map frames",
    "Stage-1 BG0 is resident before the first dungeon tile appears",
    "blank-SRAM routes start without save artifacts or fixture writes",
    "blank-SRAM natural routes reach the Stage splash and gameplay",
    "blank-SRAM pregame captures every consecutive rendered frame",
    "blank-SRAM pregame frame-state and raster replay are exact",
    "blank-SRAM STAGE splash attrs remain stable through retirement",
    "blank-SRAM splash keeps the reviewed card or raster-verified terminal black",
    "blank-SRAM Stage-1 entry exposes no third purple/cyan/partial state",
    "blank-SRAM first dungeon map and attributes are atomic",
    "blank-SRAM Stage-1 BG0 precedes the first dungeon tile",
})

PICKUP_STATE_RECEIPT_KEYS = frozenset({
    "schema", "status", "passed", "rom", "rom_sha256", "state",
    "state_sha256", "screenshot", "screenshot_sha256", "probe",
    "hardware", "checks",
})
PICKUP_HOST_RECEIPT_KEYS = frozenset({
    "schema", "status", "passed", "rom", "rom_md5", "rom_sha256",
    "state", "candidate_payloads", "host", "checks", "forms",
    "contact_sheet", "contact_sheet_sha256", "failures",
})
PICKUP_HOST_FORM_KEYS = frozenset({
    "name", "palette", "tiles", "status", "screenshot",
    "screenshot_sha256", "gates", "report", "failures",
})
PICKUP_HOST_FORM_GATE_KEYS = frozenset({
    *pickup_receipts.PICKUP_FORM_GATES,
    "displayed_map",
    "physical_host_occurrences",
})

HAZARD_MENU_TOP_CHECKS = frozenset({
    "cold state is hash-bound to the candidate ROM",
    "both replays preserve the current-ROM machine phase",
    "both replays remain in live Stage-1 gameplay",
    "both menu/item/close/low-health replays are clean",
    "both replays retain full stationary hazard coverage",
    "replays are byte-deterministic",
})

HAZARD_MENU_REPLAY_CHECKS = frozenset({
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
    "every recurring semantic spike phase renders identical hazard pixels",
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
    "post-menu raster has at least twenty rendered samples",
    "post-menu rendered frames contain no gray tooth pixels",
    "semantic hazard attributes never write the visible BG map",
    "menu close never repaints hazards into the visible BG map",
    "warning health is held after the menu/item sequence",
    "post-menu warning mode leaves floors, endpoints and hazards exact",
    "broad visible/map-flip oracle uses pinned room-local wall context",
})

CONTINUITY_CHECKS = frozenset({
    "source state and menu replay bind the exact candidate",
    "source state is ROM-owned and settled",
    "two rendered replays are byte-identical",
    "at least 120 rendered samples are independently inspected",
    "at least 60 rendered samples contain visible hazards",
    "four rendered hazard phases are observed",
    "rendered hazard rows contain no clear cells",
    "rendered hazards leave no unsupported yellow trails",
    "rendered spike teeth never use neutral gray",
    "menu and post-menu wall edges never gain persistent red or green",
    "independent synthetic and hash-pinned operator controls pass",
})

CONTINUITY_MUTATION_CONTROLS = frozenset({
    "known_good_has_zero_reported_defects",
    "known_bad_clear_is_rejected",
    "known_bad_yellow_is_rejected",
    "known_bad_gray_is_rejected",
    "known_bad_wall_is_rejected",
    "supplemental_operator_pngs_are_file_and_rgb_hash_pinned",
    "real_busted_room_clear_hazard_cells_match_reviewed_fixture",
    "real_busted_room_is_rejected_by_generic_clear_classifier",
    "real_official_wall_masks_match_reviewed_fixture",
    "real_official_mixed_room01_wall_ramp_is_rejected",
})

CONTINUITY_DEFECT_FIELDS = frozenset({
    "clear_cell_frames",
    "yellow_trail_frames",
    "gray_spike_frames",
    "wall_edge_artifact_frames",
})

# This is the operator-facing inventory.  Every repeatedly reported symptom
# must remain bound to one or more independently revalidated gates; adding a
# gate elsewhere without naming the symptom here is not accepted as coverage.
REPORTED_ISSUE_CONTRACT = {
    "blank_white_game_start_title_menu": {
        "gates": ("cold_and_returned_title_nightfall",),
        "assertions": (
            "cold and attract-returned title use all six exact Nightfall roles",
            "BG1 through BG6 match the palette YAML in live CGB CRAM",
            "renderer pixels have a dark indigo field and reject grayscale",
        ),
    },
    "menu_exit_red_green_artifacts": {
        "gates": (
            "natural_blank_sram_menu_and_art_loader",
            "native_select_menu_window_exact",
            "captured_scene0b_transition_menu",
        ),
        "assertions": (
            "full 160x144 post-close raster matches a pre-menu BG/OAM phase",
            "displayed gameplay BG attributes remain canonical",
            "Window ownership and both map selectors are clean at close",
        ),
    },
    "menu_exit_repeating_bottom_stage_tiles": {
        "gates": (
            "natural_blank_sram_menu_and_art_loader",
            "native_select_menu_window_exact",
        ),
        "assertions": (
            "all 144 scanlines are compared after close",
            "Window stays hidden and former Window map never aliases BG",
        ),
    },
    "sarah_adjacent_transient_object_or_room_tile": {
        "gates": ("natural_blank_sram_menu_and_art_loader",),
        "assertions": (
            "the captured block is classified from hardware OAM rather than masked silently",
            "slot-34 tile-$0F predates SELECT, survives it, and moves across distinct coordinates",
            "the full background beneath and around the projectile remains exact",
            "Sara slots 0-3 never set OBJ priority bit 7 and expose floor pixels through her body",
        ),
    },
    "rotating_spike_flicker": {
        "gates": (
            "rom_owned_stationary_hazard_menu_replay",
            "independent_rendered_continuity",
        ),
        "assertions": (
            "every recurring semantic phase renders identical pixels",
            "BG5/BG7 CRAM and tile/attribute publication remain atomic",
            "four rendered hazard phases are inspected frame-by-frame",
        ),
    },
    "music_cadence_slowdown": {
        "gates": (
            "natural_blank_sram_menu_and_art_loader",
            "release_speed_named_stages_95_stage6_strict99",
        ),
        "assertions": (
            "Timer ISR has no inter-frame skip and stays within 99% of baseline",
            "all seven Stage throughput routes remain inside release floors",
        ),
    },
    "first_room_transition_wall_edges_and_entrances": {
        "gates": (
            "natural_room03_active_scroll_menu",
            "independent_room01_wall_north_replay",
            "independent_rendered_continuity",
        ),
        "assertions": (
            "active-scroll room transition and SELECT roundtrip are replayed",
            "room-01 wall tiles and attributes match an independent oracle",
            "real operator wall-edge capture remains a negative control",
        ),
    },
    "flashing_walls": {
        "gates": (
            "stage1_tilemap_publication_oracle",
            "independent_room01_wall_north_replay",
        ),
        "assertions": (
            "both physical maps publish complete tile/attribute pairs",
            "consecutive service frames preserve the reviewed wall viewport",
        ),
    },
    "hazard_clear_tiles_or_nubs": {
        "gates": (
            "rom_owned_stationary_hazard_menu_replay",
            "independent_rendered_continuity",
        ),
        "assertions": (
            "visible hazard rows contain no clear cells",
            "the real busted-room capture remains a negative control",
        ),
    },
    "hazard_yellow_extension_retraction_trails": {
        "gates": (
            "rom_owned_stationary_hazard_menu_replay",
            "independent_rendered_continuity",
        ),
        "assertions": (
            "phase-aligned raster has no unsupported yellow trail",
            "left/right endpoint semantics are checked every frame",
        ),
    },
    "hazard_gray_tip_and_wall_contact": {
        "gates": (
            "rom_owned_stationary_hazard_menu_replay",
            "independent_rendered_continuity",
        ),
        "assertions": (
            "gold teeth and fire terminal caps are required in every phase",
            "neutral-gray tooth pixels are rejected",
        ),
    },
    "pickup_color_alignment": {
        "gates": (
            "stage1_current_pickup_host_palettes",
            "natural_stage1_pickup_temporal_raster",
        ),
        "assertions": (
            "all 19 pickup forms use exact tile/attribute/CRAM hosts",
            "natural scrolling raster rejects detached pickup accents",
        ),
    },
    "pre_stage_cyan_or_purple_flash": {
        "gates": ("blank_sram_stage1_handoff_no_cyan_partial_flash",),
        "assertions": (
            "every consecutive blank-SRAM handoff frame is captured twice",
            "only the reviewed complete card or complete Stage-1 map may render",
        ),
    },
}

ROOM01_WALL_SELECTOR = {
    "room": 1, "camera": 0x03DC, "lcdc": 0x8B,
    "scx": 0x0C, "scy": 0, "camera_y": 0x3C,
    "scene": 2, "active": 1, "svbk": 1,
}
ROOM05_FLOOR_SELECTOR = {
    "room": 5, "camera": 0x0720, "lcdc": 0x83,
    "scx": 0, "scy": 0, "camera_y": 0x3C,
    "scene": 2, "active": 1, "svbk": 1,
}
ROOM05_PATTERNED_IDS = [
    0x2A, 0x2B, 0x2C, 0x2D, 0x2E, 0x3A, 0x3B, 0x3C, 0x3D,
]
ROOM01_RUNTIME_WALL_TILE_ATTRS = {
    "01:24": 0x06, "01:25": 0x06, "01:26": 0x06, "01:27": 0x06,
    "01:30": 0x06, "01:33": 0x06, "01:35": 0x06, "01:36": 0x06,
}

KEY_PATTERN = re.compile(r"[a-z][a-z0-9_]*\Z")
DECIMAL_PATTERN = re.compile(r"(?:0|[1-9][0-9]*)\Z")
SIGNED_DECIMAL_PATTERN = re.compile(r"(?:0|-?[1-9][0-9]*)\Z")
HEX_BYTE_PATTERN = re.compile(r"[0-9A-F]{2}\Z")
MD5_PATTERN = re.compile(r"[0-9a-f]{32}\Z")
SHA256_PATTERN = re.compile(r"[0-9a-f]{64}\Z")


class NotReady(RuntimeError):
    """A release gate was not satisfied."""


def sha256(path: Path) -> str:
    if not path.is_file():
        raise NotReady(f"required file is missing: {path}")
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def load_json(path: Path, label: str) -> dict[str, Any]:
    if not path.is_file():
        raise NotReady(f"{label} is missing: {path}")
    try:
        value = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError) as error:
        raise NotReady(f"{label} is not valid JSON: {path}: {error}") from error
    if not isinstance(value, dict):
        raise NotReady(f"{label} is not a JSON object: {path}")
    return value


def require(condition: bool, message: str) -> None:
    if not condition:
        raise NotReady(message)


def require_exact_true_checks(
    value: Any, expected: frozenset[str], label: str
) -> dict[str, bool]:
    require(isinstance(value, dict), f"{label} checks are missing")
    actual = set(value)
    missing = sorted(expected - actual)
    unexpected = sorted(actual - expected)
    require(
        not missing and not unexpected,
        f"{label} checks schema changed; missing={missing}, "
        f"unexpected={unexpected}",
    )
    failed = sorted(key for key in expected if value[key] is not True)
    require(not failed, f"{label} checks failed: {failed}")
    return value


def require_exact_keys(
    value: Any, expected: frozenset[str], label: str
) -> dict[str, Any]:
    require(isinstance(value, dict), f"{label} is missing")
    actual = set(value)
    missing = sorted(expected - actual)
    unexpected = sorted(actual - expected)
    require(
        not missing and not unexpected,
        f"{label} schema changed; missing={missing}, unexpected={unexpected}",
    )
    return value


def decimal_field(report: dict[str, str], field: str) -> int:
    value = report[field]
    require(
        DECIMAL_PATTERN.fullmatch(value) is not None,
        f"natural-route {field} is not a canonical unsigned decimal",
    )
    return int(value)


def hex_byte_field(report: dict[str, str], field: str) -> int:
    value = report[field]
    require(
        HEX_BYTE_PATTERN.fullmatch(value) is not None,
        f"natural-route {field} is not a two-digit uppercase hex byte",
    )
    return int(value, 16)


def require_integer(value: Any, label: str, *, minimum: int | None = None) -> int:
    require(
        isinstance(value, int) and not isinstance(value, bool),
        f"{label} is not an integer",
    )
    if minimum is not None:
        require(value >= minimum, f"{label} is below {minimum}")
    return value


def require_number(value: Any, label: str) -> float:
    require(
        isinstance(value, (int, float)) and not isinstance(value, bool),
        f"{label} is not numeric",
    )
    return float(value)


def parse_exact_key_values(
    path: Path, expected_keys: frozenset[str], label: str
) -> dict[str, str]:
    require(path.is_file(), f"{label} is missing: {path}")
    report: dict[str, str] = {}
    lines = path.read_text().splitlines()
    require(bool(lines), f"{label} is empty: {path}")
    for line_number, line in enumerate(lines, start=1):
        require(
            line != "" and "=" in line,
            f"{label} line {line_number} is malformed",
        )
        key, value = line.split("=", 1)
        require(
            KEY_PATTERN.fullmatch(key) is not None,
            f"{label} line {line_number} has an invalid key",
        )
        require(
            key not in report,
            f"{label} repeats key {key!r} on line {line_number}",
        )
        require(
            "\x00" not in value and "\r" not in value,
            f"{label} value {key!r} is malformed",
        )
        report[key] = value
    require_exact_keys(report, expected_keys, label)
    return report


def parse_key_values(path: Path) -> dict[str, str]:
    return parse_exact_key_values(
        path, NATURAL_REPORT_KEYS, "natural-route report"
    )


def signed_decimal_field(
    report: dict[str, str], field: str, label: str
) -> int:
    value = report[field]
    require(
        SIGNED_DECIMAL_PATTERN.fullmatch(value) is not None,
        f"{label} {field} is not a canonical signed decimal",
    )
    return int(value)


def scratch_output(path: Path) -> Path:
    resolved = path.resolve()
    allowed_roots = ((ROOT / "tmp").resolve(), Path("/mnt/data/tmp").resolve())
    require(
        any(
            root.exists()
            and resolved != root
            and resolved.is_relative_to(root)
            for root in allowed_roots
        ),
        "output must be a child of repository tmp/ or /mnt/data/tmp/",
    )
    if resolved.exists():
        require(resolved.is_dir(), f"output is not a directory: {resolved}")
        require(not any(resolved.iterdir()),
                f"refusing to reuse non-empty output: {resolved}")
    else:
        resolved.mkdir(parents=True)
    return resolved


def tool_identity() -> dict[str, dict[str, str]]:
    paths = {
        "reporting_interceptor": Path(__file__).resolve(),
        "natural_menu_verifier": NATURAL_VERIFIER,
        "natural_menu_probe": DIAGNOSTICS / "probe_stage1_natural_menu_bg.lua",
        "natural_obj_verifier": DIAGNOSTICS / "verify_natural_stage1_obj.py",
        "obj_visual_contract": DIAGNOSTICS / "verify_stage1_obj_visual_contract.py",
        "native_menu_window_verifier": MENU_WINDOW_VERIFIER,
        "native_menu_window_probe": MENU_WINDOW_PROBE,
        "native_menu_commit_protocol": MENU_COMMIT_PROTOCOL,
        "title_nightfall_verifier": TITLE_NIGHTFALL_VERIFIER,
        "title_nightfall_probe": TITLE_NIGHTFALL_PROBE,
        "menu_window_attribute_builder": (
            ROOT / "scripts" / "menu_icon_colorization.py"
        ),
        "stage1_hazard_art_contract": ROOT / "scripts/stage1_hazard_art.py",
        "stage1_hazard_art_yaml": ROOT / "palettes/bg_tile_categories.yaml",
        "stage1_hazard_palette_yaml": (
            ROOT / "palettes/penta_palettes_v097.yaml"
        ),
        "production_rom_builder": ROOT / "scripts/build_v302_title_fix.py",
        "menu_race_static_verifier": MENU_RACE_VERIFIER,
        "stage_card_verifier": STAGE_CARD_VERIFIER,
        "stage_card_probe": DIAGNOSTICS / "probe_stage_card_stability.lua",
        "stage_card_static_contract": ROOT / "scripts/stage_card_palette_handoff.py",
        "stage1_north_verifier": NORTH_VERIFIER,
        "stage1_north_probe": DIAGNOSTICS / "probe_stage1_north_integrity.lua",
        "room01_wall_oracle": ROOM01_WALL_ORACLE,
        "room01_wall_fixture": ROOM01_WALL_FIXTURE,
        "scene0b_receipt_binder": SCENE0B_BINDER,
        "scene0b_live_verifier": SCENE0B_LIVE_VERIFIER,
        "scene0b_live_probe": SCENE0B_LIVE_PROBE,
        "scene0b_capture_fixture": SCENE0B_CAPTURE_FIXTURE,
        "stage1_tilemap_publication_verifier": TILEMAP_VERIFIER,
        "stage1_tilemap_publication_probe": TILEMAP_PROBE,
        "scene0b_state_retargeter": (
            DIAGNOSTICS / "normalize_mgba_state_pc.py"
        ),
        "pickup_state_generator": PICKUP_STATE_GENERATOR,
        "pickup_state_probe": DIAGNOSTICS / "probe_stage1_no_bleed.lua",
        "pickup_host_verifier": PICKUP_HOST_VERIFIER,
        "pickup_host_runner": (
            DIAGNOSTICS / "verify_pickup_live_palettes.py"
        ),
        "pickup_host_probe": DIAGNOSTICS / "probe_pickup_live_palettes.lua",
        "natural_pickup_raster_verifier": STAGE1_NO_BLEED_VERIFIER,
        "natural_pickup_raster_probe": STAGE1_NO_BLEED_PROBE,
        "pickup_class_inventory": (
            DIAGNOSTICS / "verify_pickup_class_palettes.py"
        ),
        "pickup_art_verifier": DIAGNOSTICS / "verify_stage1_pickup_art.py",
        "pickup_art_analyzer": DIAGNOSTICS / "analyze_stage1_pickup_art.py",
        "pickup_table_builder": ROOT / "scripts" / "build_v301_gdma.py",
        "pickup_receipt_validator": (
            DIAGNOSTICS / "verify_pocket_visual_receipts.py"
        ),
        "hazard_state_generator": STATE_GENERATOR,
        "hazard_state_probe": DIAGNOSTICS / "probe_stage1_north_integrity.lua",
        "hazard_menu_verifier": HAZARD_MENU_VERIFIER,
        "hazard_menu_contract": DIAGNOSTICS / "verify_stage1_hazard_menu.py",
        "hazard_live_verifier": DIAGNOSTICS / "verify_stage1_spike_palettes.py",
        "hazard_menu_probe": DIAGNOSTICS / "probe_stage1_spike_palettes.lua",
        "rendered_continuity_verifier": CONTINUITY_VERIFIER,
        "rendered_continuity_operator_capture_fixture": (
            CONTINUITY_OPERATOR_CAPTURE_FIXTURE
        ),
        "speed_qualifier": SPEED_QUALIFIER,
        "singleflight_launcher": ROOT / "scripts" / "mgba-qt-singleflight",
        "read_only_process_check": PROCESS_CHECK,
    }
    return {
        name: {"path": str(path), "sha256": sha256(path)}
        for name, path in paths.items()
    }


def write_rollup(path: Path, rollup: dict[str, Any]) -> None:
    path.write_text(json.dumps(rollup, indent=2, sort_keys=True) + "\n")


def reported_issue_coverage(gates: dict[str, Any]) -> dict[str, Any]:
    """Bind each operator-reported symptom to passing revalidated gates."""
    coverage: dict[str, Any] = {}
    for issue, contract in REPORTED_ISSUE_CONTRACT.items():
        gate_names = list(contract["gates"])
        require(gate_names, f"reported issue {issue} has no gate")
        for gate_name in gate_names:
            require(gate_name in gates,
                    f"reported issue {issue} lacks gate {gate_name}")
            require(
                str(gates[gate_name].get("status", "")).startswith("PASS"),
                f"reported issue {issue} gate did not pass: {gate_name}",
            )
        assertions = list(contract["assertions"])
        require(assertions, f"reported issue {issue} has no assertion inventory")
        coverage[issue] = {
            "status": "DETERMINISTIC_GATE",
            "gates": gate_names,
            "assertions": assertions,
        }
    return coverage


def assert_candidate_unchanged(candidate: Path, expected_sha256: str) -> None:
    require(
        sha256(candidate) == expected_sha256,
        "candidate ROM changed while the reporting interceptor was running",
    )


def run_read_only_process_check(log: Path) -> dict[str, Any]:
    """Record the mandatory post-interruption process census fail closed."""
    try:
        completed = subprocess.run(
            [str(PROCESS_CHECK)],
            cwd=ROOT,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            timeout=10.0,
            check=False,
        )
        output = completed.stdout
        exit_status: int | None = completed.returncode
        error: str | None = None
    except subprocess.TimeoutExpired as interrupted:
        output = interrupted.stdout or ""
        if isinstance(output, bytes):
            output = output.decode(errors="replace")
        exit_status = None
        error = "read-only process check timed out"
    except OSError as interrupted:
        output = f"read-only process check could not run: {interrupted}\n"
        exit_status = None
        error = str(interrupted)
    except KeyboardInterrupt:
        output = "read-only process check was itself interrupted\n"
        exit_status = None
        error = "read-only process check was itself interrupted"
    log.write_text(output)
    return {
        "command": [str(PROCESS_CHECK)],
        "log": str(log),
        "log_sha256": sha256(log),
        "exit_status": exit_status,
        "error": error,
    }


def literal_keyword(call: ast.Call, name: str) -> Any:
    matches = [keyword for keyword in call.keywords if keyword.arg == name]
    require(len(matches) == 1,
            f"hazard-menu verifier must set {name} exactly once")
    try:
        return ast.literal_eval(matches[0].value)
    except (ValueError, TypeError) as error:
        raise NotReady(
            f"hazard-menu verifier {name} is not a fixed literal"
        ) from error


def validate_hazard_menu_no_injection_contract() -> dict[str, Any]:
    """AST-bind the exact release call to the ROM-owned, guarded pathway."""
    source = HAZARD_MENU_VERIFIER.read_text()
    try:
        tree = ast.parse(source, filename=str(HAZARD_MENU_VERIFIER))
    except SyntaxError as error:
        raise NotReady(
            f"hazard-menu verifier is not valid Python: {error}"
        ) from error
    calls = [
        node for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "live_receipt"
    ]
    require(len(calls) == 1,
            "hazard-menu verifier must have exactly one live_receipt call site")
    call = calls[0]
    require(not any(keyword.arg is None for keyword in call.keywords),
            "hazard-menu verifier may not expand dynamic live_receipt keywords")
    require(len(call.args) == 5,
            "hazard-menu verifier live_receipt positional contract changed")
    for argument, expected_name in zip(
        call.args[:2], ("rom", "state"), strict=True
    ):
        require(
            isinstance(argument, ast.Name) and argument.id == expected_name,
            f"hazard-menu verifier no longer passes the bound {expected_name}",
        )
    guarded = call.args[2]
    require(
        isinstance(guarded, ast.Call)
        and not guarded.args
        and not guarded.keywords
        and isinstance(guarded.func, ast.Attribute)
        and guarded.func.attr == "resolve"
        and isinstance(guarded.func.value, ast.Name)
        and guarded.func.value.id == "DEFAULT_MGBA",
        "hazard-menu verifier no longer uses the guarded default emulator",
    )
    required_literals = {
        "reinitialize": False,
        "input_mask": 0,
        "post_menu_input_mask": 0,
        "expected_room": 0x01,
        "normalization_writes": (),
        "menu_open": True,
        "trace_routes": True,
        "trace_writers": True,
        "preserve_machine_state": True,
        "preserve_rom_owned_state": True,
    }
    for name, expected in required_literals.items():
        require(
            literal_keyword(call, name) == expected,
            f"hazard-menu verifier changed fixed {name}={expected!r}",
        )
    keyword_names = {keyword.arg for keyword in call.keywords}
    require("normalization_bank" not in keyword_names,
            "hazard-menu verifier unexpectedly selects a normalization bank")
    return {
        "live_receipt_call_sites": 1,
        "guarded_default_emulator": True,
        "normalization_writes": 0,
        "reinitialize": False,
        "input_mask": 0,
        "post_menu_input_mask": 0,
        "preserve_machine_state": True,
        "preserve_rom_owned_state": True,
    }


def run_checked_verifier(
    *,
    label: str,
    command: list[str],
    log: Path,
    timeout: float,
    candidate: Path,
    candidate_sha256: str,
) -> dict[str, Any]:
    """Run one fixed checked-in verifier; never continue after interruption."""
    assert_candidate_unchanged(candidate, candidate_sha256)
    pycache_prefix = log.parent / "python-pycaches" / label
    require(not pycache_prefix.exists(),
            f"refusing to reuse Python bytecode cache: {pycache_prefix}")
    pycache_prefix.mkdir(parents=True)
    environment = os.environ.copy()
    environment["PYTHONPYCACHEPREFIX"] = str(pycache_prefix)
    try:
        completed = subprocess.run(
            command,
            cwd=ROOT,
            env=environment,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            timeout=timeout,
            check=False,
        )
    except subprocess.TimeoutExpired as error:
        output = error.stdout or ""
        if isinstance(output, bytes):
            output = output.decode(errors="replace")
        log.write_text(output)
        # Project policy requires this read-only check after any interrupted
        # emulator-backed verifier.  Do not launch another verifier afterward.
        process_log = log.with_name(log.stem + "-process-check.log")
        process_check = run_read_only_process_check(process_log)
        raise NotReady(
            f"{label} timed out after {timeout:.1f}s; "
            f"read-only process check: {process_log} "
            f"(exit {process_check['exit_status']})"
        ) from error
    log.write_text(completed.stdout)
    assert_candidate_unchanged(candidate, candidate_sha256)
    require(
        completed.returncode == 0,
        f"{label} failed with exit status {completed.returncode}; see {log}",
    )
    return {
        "command": [str(item) for item in command],
        "log": str(log),
        "log_sha256": sha256(log),
        "exit_status": completed.returncode,
        "python_pycache_prefix": str(pycache_prefix),
    }


def validate_natural_report(
    path: Path, candidate: Path, candidate_sha256: str,
    *, expected_room: int = 0x05,
) -> dict[str, Any]:
    report = parse_key_values(path)
    require(report.get("rom") == str(candidate),
            "natural-route report names another ROM")
    require(report.get("rom_sha256") == candidate_sha256,
            "natural-route report SHA does not bind the candidate")
    for field in ("rom_sha256", "lut_sha256", "art_sha256"):
        require(
            SHA256_PATTERN.fullmatch(report[field]) is not None,
            f"natural-route {field} is malformed",
        )
    require(report["expected_room"] == f"{expected_room:02X}",
            "natural route expected-room provenance changed")
    require(report["no_menu_control"] == "0",
            "natural route used the no-menu diagnostic control")
    require(report["settled_art_examples"] == "none",
            "natural route reports settled Stage-1 art mismatches")
    require(report["art_writer_trace"] == "",
            "natural release route unexpectedly enabled art-writer tracing")
    room_marker = f"scene02:room{expected_room:02X}"
    require(room_marker in report.get("last_preopen", ""),
            f"natural route did not reach Stage-1 room {expected_room:02X}")
    require(room_marker in report.get("final_state", ""),
            f"natural SELECT route did not finish in room {expected_room:02X}")
    require("scene02:room05" in report["first_gameplay"],
            "natural route has no Stage-1 gameplay entry")
    require(room_marker in report["settled_art_state"],
            "natural route has no settled Stage-1 art state")
    frames = decimal_field(report, "frames")
    open_frame = decimal_field(report, "open_frame")
    close_frame = decimal_field(report, "close_frame")
    require(0 < open_frame < close_frame < frames,
            "natural-route frame schedule is malformed")
    baseline_frames = decimal_field(report, "baseline_frames")
    menu_frames = decimal_field(report, "menu_frames")
    post_close_frames = decimal_field(report, "post_close_frames")
    require(baseline_frames >= 60,
            "natural route has insufficient pre-menu coverage")
    require(menu_frames >= 60,
            "natural route has insufficient visible-menu coverage")
    require(post_close_frames >= 60,
            "natural route has insufficient stationary post-menu coverage")
    for field in (
        "baseline_bad_frames", "menu_bad_frames", "post_close_bad_frames",
        "menu_mismatch_cells", "post_close_mismatch_cells",
        "settled_art_mismatch_bytes",
    ):
        require(decimal_field(report, field) == 0,
                f"natural-route {field} is not zero")
    for field in (
        "first_baseline_bad", "first_menu_bad", "first_post_close_bad",
    ):
        require(report[field] == "none",
                f"natural-route {field} records a mismatch")
    require(report["first_window"] != "none",
            "natural route never observed the menu Window")
    require(report["first_closed"] != "none",
            "natural route never observed menu close")
    first_selector_frame = decimal_field(report, "first_selector_frame")
    require(first_selector_frame > 0,
            "natural route never observed the live menu selector")
    hex_byte_field(report, "first_selector_lcdc")
    hex_byte_field(report, "first_selector_dc0b")
    df5b = hex_byte_field(report, "settled_df5b")
    require(df5b & 0x03 == 0x03,
            "natural Stage-1 bank-1 art loader did not finish")
    timer_hits = {
        "total": decimal_field(report, "timer_isr_hits"),
        "baseline": decimal_field(report, "timer_baseline_hits"),
        "menu": decimal_field(report, "timer_menu_hits"),
        "post_close": decimal_field(report, "timer_post_close_hits"),
        "max_frame_gap": decimal_field(report, "timer_max_frame_gap"),
    }
    require(
        timer_hits["total"]
        == timer_hits["baseline"] + timer_hits["menu"]
        + timer_hits["post_close"],
        "natural-route music Timer ISR accounting is inconsistent",
    )
    timer_cadence = natural_menu_oracle.timer_cadence_receipt(
        report, frames, open_frame, close_frame,
    )
    require(
        timer_cadence["passed"] is True,
        "natural-route music Timer ISR cadence slowed, skipped a frame, "
        "or fell below 99 percent of its pre-menu rate",
    )
    require(report["publication_latch_fault"] == "none",
            "natural-route publication latch fault was injected or observed")
    require(decimal_field(report, "semantic_visible_writes") == 0,
            "natural-route semantic attributes wrote the visible BG map")
    for field in (
        "publication_latch_trace", "hardware_register_trace",
        "publication_boundary_trace",
    ):
        require(bool(report[field]),
                f"natural-route {field} lacks boundary coverage")
    from verify_natural_stage1_obj import bind as bind_natural_obj
    natural_obj = bind_natural_obj(
        candidate, path, open_frame, close_frame,
        expected_room=expected_room,
    )
    authenticated_enemy_oam = {
        int(snapshot["frame"]): {
            int(entry.split("/", 1)[0]): tuple(entry.split("/")[1:])
            for entry in snapshot.get("native_enemy_oam", [])
        }
        for snapshot in natural_obj["snapshots"]
    }
    temporal_raster = natural_menu_oracle.temporal_raster_receipt(
        report, open_frame, close_frame,
        obj_atlas_authenticated=True,
        native_animation_quads=(
            natural_menu_oracle.native_stage1_enemy_quads(
                candidate.read_bytes()
            )
        ),
        authenticated_enemy_oam=authenticated_enemy_oam,
    )
    projectile = temporal_raster["operator_projectile_classification"]
    sarah_priority = temporal_raster["sarah_priority_contract"]
    require(
        temporal_raster["enabled"]
        and temporal_raster["raster_height"]
        == natural_menu_oracle.NATIVE_HEIGHT
        and temporal_raster["baseline_frames_requested"]
        == natural_menu_oracle.RASTER_BASELINE_FRAMES
        and temporal_raster["unmatched_phase_frames"] == 0
        and temporal_raster["full_frame_mismatch_frames"] == 0
        and temporal_raster["mismatch_frames"] == 0,
        "natural-route full post-menu raster contains transient tiles, "
        "palette garbage, an unseen OAM phase, or bottom-band repetition",
    )
    if expected_room == 0x05:
        require(
            natural_menu_oracle.projectile_observation_is_safe(temporal_raster),
            "natural room-$05 route has an unclassified Sarah-adjacent "
            "projectile or lacks clean full-frame/OAM absence evidence",
        )
    require(
        sarah_priority["passed"] is True
        and sarah_priority["priority_entries"] == 0
        and sarah_priority["priority_frames"] == 0,
        "natural route exposed Stage-1 floor pixels through Sara via OAM "
        "priority bit 7",
    )
    return {
        "receipt": str(path),
        "receipt_sha256": sha256(path),
        "rom_sha256": candidate_sha256,
        "expected_room": f"{expected_room:02X}",
        "settled_df5b": f"{df5b:02X}",
        "coverage": {
            "baseline_frames": baseline_frames,
            "menu_frames": menu_frames,
            "post_close_frames": post_close_frames,
        },
        "music_timer_isr": timer_hits,
        "music_timer_cadence": timer_cadence,
        "temporal_raster": temporal_raster,
        "natural_obj": natural_obj,
        "semantic_visible_writes": 0,
        "mismatches": {
            "baseline_bad_frames": 0,
            "menu_bad_frames": 0,
            "menu_mismatch_cells": 0,
            "post_close_bad_frames": 0,
            "post_close_mismatch_cells": 0,
            "settled_art_mismatch_bytes": 0,
        },
        "first_bad": {
            "baseline": "none",
            "menu": "none",
            "post_close": "none",
        },
    }


def validate_menu_window_report(
    path: Path, candidate: Path, candidate_sha256: str
) -> dict[str, Any]:
    """Revalidate the exact native SELECT Window entry/hold/exit report."""
    report = parse_exact_key_values(
        path, MENU_WINDOW_REPORT_KEYS, "native menu-Window report"
    )
    require(report["rom"] == str(candidate.resolve()),
            "menu-Window report names another candidate")
    require(report["rom_sha256"] == candidate_sha256,
            "menu-Window report hash does not bind the candidate")
    require(SHA256_PATTERN.fullmatch(report["rom_sha256"]) is not None,
            "menu-Window candidate hash is malformed")

    expected_lut, expected_mode = menu_window_oracle.expected_window_lut(
        candidate.read_bytes()
    )
    close_atomicity = menu_window_oracle.menu_close_atomicity(
        candidate.read_bytes()
    )
    require(
        close_atomicity == "atomic-owner-clear-window-hide-before-ei",
        "menu-Window candidate does not clear ownership and hide Window "
        "before enabling interrupts",
    )
    expected_lut_sha256 = hashlib.sha256(expected_lut).hexdigest()
    require(report["attr_mode"] == expected_mode,
            "menu-Window report used another attribute-oracle mode")
    require(report["attr_lut_sha256"] == expected_lut_sha256,
            "menu-Window report used another candidate attribute LUT")
    try:
        content_fixture, _, _ = menu_window_oracle.load_content_fixture()
    except ValueError as error:
        raise NotReady(str(error)) from error
    require(
        report["content_mode"] == "native-fixture"
        and report["content_fixture_sha256"]
        == menu_window_oracle.CONTENT_FIXTURE_SHA256,
        "menu-Window report did not use the reviewed native HUD fixture",
    )

    route = {
        "frames": signed_decimal_field(
            report, "route_frame_limit", "menu-Window report"
        ),
        "open_frame": signed_decimal_field(
            report, "route_open_frame", "menu-Window report"
        ),
        "close_frame": signed_decimal_field(
            report, "route_close_frame", "menu-Window report"
        ),
        "force_alias_frame": signed_decimal_field(
            report, "route_force_alias_frame", "menu-Window report"
        ),
        "force_commit_frame": signed_decimal_field(
            report, "route_force_commit_frame", "menu-Window report"
        ),
        "stale_frame": signed_decimal_field(
            report, "route_stale_frame", "menu-Window report"
        ),
        "key": "select",
        "move": "none",
        "fire_every": 0,
    }
    require(route == {
        "frames": MENU_WINDOW_FRAMES,
        "open_frame": MENU_WINDOW_OPEN_FRAME,
        "close_frame": MENU_WINDOW_CLOSE_FRAME,
        "force_alias_frame": -1,
        "force_commit_frame": MENU_WINDOW_CLOSE_FRAME,
        "stale_frame": -1,
        "key": "select",
        "move": "none",
        "fire_every": 0,
    }, "menu-Window route is not the exact native SELECT release route")
    require(signed_decimal_field(
        report, "frames", "menu-Window report"
    ) == MENU_WINDOW_FRAMES, "menu-Window report ended at another frame")

    counts = {
        field: signed_decimal_field(report, field, "menu-Window report")
        for field in (
            "window_frames", "bad_frames", "window_frames_after_close",
            "stale_injected", "stale_window_frames_after_grace",
            "worst_mismatches", "map_alias_frames", "attr_checked_frames",
            "attr_bad_frames", "attr_mismatch_cells", "attr_unsafe_cells",
            "attr_entry_frames", "attr_settled_frames", "attr_exit_frames",
            "window_hidden_at_close_frames", "worst_attr_mismatches",
            "forced_commit", "forced_commit_consumed",
            "post_close_selector_checked_frames",
            "post_close_selector_alias_frames", "post_close_hud_leak_frames",
            "content_checked_frames", "content_bad_frames",
            "content_source_mismatch_cells",
            "content_window_mismatch_cells",
            "worst_content_source_mismatches",
            "worst_content_window_mismatches",
            "content_raster_checked_frames", "content_raster_bad_frames",
        )
    }
    require(counts["window_frames"] > 0,
            "menu-Window route never exposed the hardware Window")
    require(counts["attr_checked_frames"] == counts["window_frames"],
            "menu-Window VBK1 coverage is not every visible frame")
    require(
        counts["content_checked_frames"] == counts["window_frames"],
        "native HUD fixture coverage is not every visible Window frame",
    )
    require(
        counts["attr_entry_frames"] + counts["attr_settled_frames"]
        + counts["attr_exit_frames"] == counts["window_frames"],
        "menu-Window entry/hold/exit coverage does not partition visibility",
    )
    require(counts["attr_entry_frames"] == 8,
            "menu-Window entry boundary lacks its exact eight-frame audit")
    require(counts["attr_settled_frames"] >= 60,
            "menu-Window hold coverage is shorter than 60 frames")
    require(counts["attr_exit_frames"] > 0,
            "menu-Window close edge was not audited while visible")
    require(counts["window_hidden_at_close_frames"] >= 60,
            "menu-Window close lacks 60 hidden post-close frames")
    require(
        counts["forced_commit"] == 1
        and counts["forced_commit_consumed"] == 1,
        "menu-Window gate did not execute the completed-map close-edge race",
    )
    try:
        commit_protocol = menu_window_oracle.authenticate_commit_protocol(
            candidate.read_bytes()
        )
    except (AssertionError, ValueError) as error:
        raise NotReady(str(error)) from error
    require(
        report["forced_commit_protocol"] == commit_protocol["name"],
        "menu-Window gate used another completed-map transaction protocol",
    )
    require(counts["post_close_selector_checked_frames"] >= 60,
            "menu-Window gate lacks 60 stationary post-close selector frames")
    zero_fields = (
        "bad_frames", "window_frames_after_close", "stale_injected",
        "stale_window_frames_after_grace", "worst_mismatches",
        "map_alias_frames", "attr_bad_frames", "attr_mismatch_cells",
        "attr_unsafe_cells", "worst_attr_mismatches",
        "post_close_selector_alias_frames", "post_close_hud_leak_frames",
        "content_bad_frames", "content_source_mismatch_cells",
        "content_window_mismatch_cells",
        "worst_content_source_mismatches",
        "worst_content_window_mismatches", "content_raster_bad_frames",
    )
    require(all(counts[field] == 0 for field in zero_fields),
            "menu-Window geometry, tiles, attributes, or close checks failed")
    require(report["stale_scene"] == "native",
            "menu-Window report used a stale-scene injection")
    for field in (
        "first_bad", "first_alias", "first_post_close_alias",
        "first_attr_bad", "first_content_bad", "first_content_raster_bad",
    ):
        require(report[field] == "none",
                f"menu-Window report records {field}")
    require(
        re.search(r"(?:^| )scene:02(?: |$)", report["first_visible"])
        is not None
        and re.search(r"(?:^| )room:05(?: |$)", report["first_visible"])
        is not None
        and re.search(r"(?:^| )mismatches:0(?: |$)",
                      report["first_visible"]) is not None,
        "menu-Window first visible frame is not clean Stage-1 room 05",
    )
    final_lcdc = re.search(
        r"(?:^| )lcdc:([0-9A-F]{2})(?: |$)", report["final_state"]
    )
    require(
        re.search(r"(?:^| )scene:02(?: |$)", report["final_state"])
        is not None
        and re.search(r"(?:^| )room:05(?: |$)", report["final_state"])
        is not None
        and final_lcdc is not None
        and int(final_lcdc.group(1), 16) & 0x20 == 0,
        "menu-Window route did not finish in gameplay with Window hidden",
    )
    final_lcdc_value = int(final_lcdc.group(1), 16)
    require(
        bool(final_lcdc_value & 0x08) != bool(final_lcdc_value & 0x40),
        "menu-Window route finished with BG and Window selectors aliased",
    )
    require(bool(report["transitions"]),
            "menu-Window report has no presentation transitions")
    raster = menu_window_oracle.content_raster_receipt(
        report["content_raster_trace"], content_fixture
    )
    require(
        raster["passed"] is True
        and raster["checked_frames"]
        == len(content_fixture["raster"]["sample_visible_ages"])
        and counts["content_raster_checked_frames"]
        == raster["checked_frames"]
        and counts["content_raster_bad_frames"] == raster["bad_frames"]
        and report["content_raster_invariant_sha256"]
        == raster["expected_rgb_sha256"],
        "menu-Window rendered fixture is blank, white, incomplete, or stale",
    )
    return {
        "receipt": str(path.resolve()),
        "receipt_sha256": sha256(path),
        "rom_sha256": candidate_sha256,
        "route": route,
        "attribute_oracle": {
            "mode": expected_mode,
            "sha256": expected_lut_sha256,
        },
        "menu_close_atomicity": close_atomicity,
        "completed_map_commit_protocol": commit_protocol,
        "content_oracle": {
            "fixture_sha256": menu_window_oracle.CONTENT_FIXTURE_SHA256,
            "raster_invariant_sha256": raster["expected_rgb_sha256"],
            "sampled_frames": raster["checked_frames"],
        },
        "coverage": {
            "window_frames": counts["window_frames"],
            "entry_frames": counts["attr_entry_frames"],
            "settled_frames": counts["attr_settled_frames"],
            "exit_frames": counts["attr_exit_frames"],
            "hidden_post_close_frames": counts[
                "window_hidden_at_close_frames"
            ],
        },
        "geometry_tile_attribute_content_failures": 0,
    }


def validate_title_nightfall_receipt(
    path: Path, candidate: Path, candidate_sha256: str
) -> dict[str, Any]:
    """Re-open both mGBA title captures and independently re-run the oracle."""
    receipt = load_json(path, "Nightfall title receipt")
    require_exact_keys(receipt, frozenset({
        "schema", "status", "candidate", "candidate_sha256",
        "palette_yaml", "palette_yaml_sha256", "active_scheme", "probe",
        "snapshots", "checks", "tool_identity", "failures",
    }), "Nightfall title receipt")
    require(receipt["schema"] == TITLE_NIGHTFALL_SCHEMA,
            "Nightfall title receipt schema changed")
    require(receipt["status"] == "pass" and receipt["failures"] == [],
            "Nightfall title receipt is not passing")
    require(receipt["candidate"] == str(candidate.resolve())
            and receipt["candidate_sha256"] == candidate_sha256,
            "Nightfall title receipt names another candidate")
    require(
        Path(receipt["palette_yaml"]).resolve()
        == title_nightfall_oracle.title.PALETTE_YAML.resolve()
        and receipt["palette_yaml_sha256"]
        == sha256(title_nightfall_oracle.title.PALETTE_YAML.resolve())
        and receipt["active_scheme"] == "Nightfall",
        "Nightfall title palette provenance changed",
    )
    checks = require_exact_true_checks(
        receipt["checks"], TITLE_NIGHTFALL_CHECKS, "Nightfall title"
    )
    probe = require_exact_keys(receipt["probe"], frozenset({
        "status", "message", "frames", "deferred_wram_frames",
        "transitions", "cold_captured", "left_title", "returned_captured",
    }), "Nightfall title probe")
    require(
        probe["status"] == "ok"
        and probe["message"] == "cold-and-returned-title-captured"
        and probe["cold_captured"] == "true"
        and probe["left_title"] == "true"
        and probe["returned_captured"] == "true"
        and probe["transitions"],
        "Nightfall title probe did not complete both title epochs",
    )
    require(
        isinstance(probe["frames"], str)
        and DECIMAL_PATTERN.fullmatch(probe["frames"]) is not None
        and 600 <= int(probe["frames"]) <= 12000,
        "Nightfall title probe frame count is invalid",
    )
    require(
        isinstance(probe["deferred_wram_frames"], str)
        and DECIMAL_PATTERN.fullmatch(probe["deferred_wram_frames"])
        is not None,
        "Nightfall title deferred-WRAM count is invalid",
    )

    tools = require_exact_keys(receipt["tool_identity"], frozenset({
        "verifier_sha256", "probe_sha256", "singleflight_sha256",
    }), "Nightfall title tool identity")
    require(
        tools == {
            "verifier_sha256": sha256(TITLE_NIGHTFALL_VERIFIER),
            "probe_sha256": sha256(TITLE_NIGHTFALL_PROBE),
            "singleflight_sha256": sha256(
                ROOT / "scripts" / "mgba-qt-singleflight"
            ),
        },
        "Nightfall title tool identity differs",
    )

    snapshots = require_exact_keys(
        receipt["snapshots"], frozenset({"cold", "returned"}),
        "Nightfall title snapshots",
    )
    snapshot_keys = frozenset({
        "frame", "scene", "base", "attribute_histogram",
        "unsafe_attributes", "rendered_colours", "dominant_field",
        "dominant_field_pixels", "chromatic_pixels", "png", "png_sha256",
        "report", "report_sha256", "rgb_sha256",
    })
    expected_attributes, expected_palettes = (
        title_nightfall_oracle.expected_title_payload(candidate.read_bytes())
    )
    revalidated: dict[str, dict[str, Any]] = {}
    receipt_parent = path.resolve().parent
    for label in ("cold", "returned"):
        saved = require_exact_keys(
            snapshots[label], snapshot_keys,
            f"Nightfall {label} snapshot",
        )
        png = Path(saved["png"]).resolve()
        text = Path(saved["report"]).resolve()
        require(
            png == receipt_parent / f"title.{label}.png"
            and text == receipt_parent / f"title.{label}.txt",
            f"Nightfall {label} artifact path changed",
        )
        try:
            actual = title_nightfall_oracle.analyze_snapshot(
                label=label,
                text_path=text,
                png_path=png,
                expected_attributes=expected_attributes,
                expected_palettes=expected_palettes,
            )
        except title_nightfall_oracle.GateFailure as error:
            raise NotReady(str(error)) from error
        require(saved == actual,
                f"Nightfall {label} snapshot receipt is stale")
        revalidated[label] = actual
    require(
        revalidated["cold"]["rgb_sha256"]
        == revalidated["returned"]["rgb_sha256"],
        "cold and returned Nightfall title rasters differ",
    )
    return {
        "receipt": str(path.resolve()),
        "receipt_sha256": sha256(path),
        "rom_sha256": candidate_sha256,
        "active_scheme": "Nightfall",
        "checks": checks,
        "snapshots": revalidated,
    }


def validate_no_bleed_receipt(
    path: Path, candidate: Path, candidate_sha256: str
) -> dict[str, Any]:
    """Revalidate the cold 3,600-frame natural pickup temporal/raster gate."""
    resolved = path.resolve()
    receipt = require_exact_keys(
        load_json(resolved, "natural pickup temporal/raster receipt"),
        NO_BLEED_RECEIPT_KEYS,
        "natural pickup temporal/raster receipt",
    )
    require(receipt["schema"] == NO_BLEED_SCHEMA,
            "wrong natural pickup temporal/raster receipt schema")
    require(receipt["status"] == "pass" and receipt["failures"] == [],
            "natural pickup temporal/raster receipt did not pass")
    require(receipt["rom"] == str(candidate.resolve()),
            "natural pickup temporal/raster receipt names another ROM")
    require(receipt["rom_sha256"] == candidate_sha256,
            "natural pickup temporal/raster receipt targets another ROM")
    expected_md5 = hashlib.md5(candidate.read_bytes()).hexdigest()
    require(
        MD5_PATTERN.fullmatch(receipt["rom_md5"]) is not None
        and receipt["rom_md5"] == expected_md5,
        "natural pickup temporal/raster MD5 does not bind the candidate",
    )

    route = require_exact_keys(
        receipt["route"], NO_BLEED_ROUTE_KEYS,
        "natural pickup temporal/raster route",
    )
    require(route == {
        "source": NO_BLEED_ROUTE_SOURCE,
        "mode": NO_BLEED_MODE,
        "play_frames_requested": NO_BLEED_FRAMES,
        "emulated_seconds": round(NO_BLEED_FRAMES / no_bleed_oracle.FPS, 3),
    }, "natural pickup temporal/raster route is not exact")
    require(receipt["diagnostic_state"] is None,
            "natural pickup temporal/raster route used an injected state")
    require(
        receipt["raster_alignment_radius_frames"]
        == no_bleed_oracle.RASTER_ALIGNMENT_RADIUS,
        "natural pickup raster alignment policy changed",
    )
    expected_table = no_bleed_oracle.expected_stage1_table(
        candidate.read_bytes()
    )
    expected_histogram = {
        str(palette): expected_table.count(palette)
        for palette in sorted(set(expected_table))
    }
    require(receipt["stage1_table_histogram"] == expected_histogram,
            "natural pickup receipt has another Stage-1 semantic table")
    checks = require_exact_true_checks(
        receipt["checks"], NO_BLEED_CHECKS,
        "natural pickup temporal/raster",
    )
    probe = require_exact_keys(
        receipt["probe"], NO_BLEED_PROBE_KEYS,
        "natural pickup temporal/raster probe",
    )

    def probe_integer(name: str, minimum: int | None = None) -> int:
        return require_integer(
            probe[name], f"natural pickup probe {name}", minimum=minimum
        )

    frames = probe_integer("frames", NO_BLEED_FRAMES)
    sampled_frames = probe_integer("sampled_frames", NO_BLEED_FRAMES)
    probe_integer("checked_cells", 1)
    scene_frames = probe_integer("scene_frames", 1200)
    active_frames = probe_integer("active_frames", 1200)
    scroll_changes = probe_integer("scroll_changes", 1)
    scx_changes = probe_integer("scx_changes", 1)
    scy_changes = probe_integer("scy_changes", 1)
    require(probe_integer("pal1_cells", 1) > 0,
            "natural pickup route observed no health-red pickup cells")
    require(probe_integer("pickup_state_saved") == 0,
            "natural pickup route unexpectedly exported a diagnostic state")
    for field in ("unexpected_semantic_pickup_cells", "unsafe_cells"):
        require(probe_integer(field) == 0,
                f"natural pickup probe {field} is not zero")
    unexpected_cells = probe_integer("unexpected_cells")
    unexpected_floor_cells = probe_integer("unexpected_floor_cells")
    require(unexpected_cells == unexpected_floor_cells,
            "natural pickup mismatch accounting is inconsistent")

    scene_histogram = probe["scene_histogram"]
    require(
        isinstance(scene_histogram, dict)
        and bool(scene_histogram)
        and all(
            HEX_BYTE_PATTERN.fullmatch(scene) is not None
            and isinstance(count, int)
            and not isinstance(count, bool)
            and count > 0
            for scene, count in scene_histogram.items()
        ),
        "natural pickup scene histogram is malformed",
    )
    require(
        set(scene_histogram) <= {"00", "02", "0A", "0B"},
        "natural pickup route sampled a non-Stage-1 scene",
    )
    require(
        sum(scene_histogram.values()) == sampled_frames == frames
        and scene_frames == frames,
        "natural pickup scene accounting is inconsistent",
    )
    first_non_stage_frame = require_integer(
        probe["first_non_stage_scene_frame"],
        "natural pickup first non-Stage-1 scene frame",
    )
    first_non_stage_scene = require_integer(
        probe["first_non_stage_scene"],
        "natural pickup first non-Stage-1 scene",
    )
    if "00" in scene_histogram:
        require(
            1 <= first_non_stage_frame <= frames
            and first_non_stage_scene == 0,
            "natural pickup transitional scene witness is inconsistent",
        )
    else:
        require(
            first_non_stage_frame == -1 and first_non_stage_scene == -1,
            "natural pickup non-Stage-1 witness is spurious",
        )

    compiler_unreadable = probe_integer("compiler_unreadable_scene_frames")
    require(compiler_unreadable <= scene_frames,
            "natural pickup private-WRAM samples exceed scene coverage")
    final_private_unreadable = probe_integer("final_compiler_unreadable")
    require(
        final_private_unreadable in {0, 1}
        and (
            final_private_unreadable == 0
            or no_bleed_oracle.private_scene_unreadable(
                probe_integer("final_pc"), probe_integer("final_svbk")
            )
        ),
        "natural pickup final private-WRAM scene sample is not bounded",
    )
    dma_unreadable = probe_integer("runtime_lut_dma_unreadable_frames")
    dma_first = probe["first_runtime_lut_dma_unreadable"]
    require(isinstance(dma_first, str)
            and ((dma_unreadable == 0 and dma_first == "")
                 or (dma_unreadable > 0 and bool(dma_first))),
            "natural pickup OAM-DMA LUT classification is inconsistent")
    contextual = probe["contextual_mismatch_pairs"]
    require(isinstance(contextual, dict)
            and all(isinstance(value, int) and not isinstance(value, bool)
                    and value > 0 for value in contextual.values()),
            "natural pickup contextual signatures are malformed")
    contextual_signatures = set(contextual)
    require(
        no_bleed_oracle.contextual_signatures_reviewed(
            contextual_signatures
        ),
        "natural pickup route contains unreviewed contextual signatures",
    )
    require(sum(contextual.values()) == unexpected_floor_cells,
            "natural pickup floor mismatches are not fully context-reviewed")
    runtime_contextual = probe["runtime_lut_mismatch_pairs"]
    require(
        isinstance(runtime_contextual, dict)
        and all(
            isinstance(value, int) and not isinstance(value, bool) and value > 0
            for value in runtime_contextual.values()
        )
        and set(runtime_contextual)
        == no_bleed_oracle.EXPECTED_RUNTIME_CONTEXTUAL_SIGNATURES,
        "natural pickup runtime LUT changes are not exact reviewed wall roles",
    )
    require(
        probe_integer("runtime_lut_mismatch_frames", 1) > 0
        and probe_integer("runtime_lut_mismatch_cells", 1)
        == sum(runtime_contextual.values())
        and 0 < probe_integer("runtime_lut_mismatch_max")
        <= len(no_bleed_oracle.EXPECTED_RUNTIME_CONTEXTUAL_SIGNATURES),
        "natural pickup runtime LUT mismatch accounting is inconsistent",
    )
    require(
        isinstance(probe["helper_events"], list)
        and probe_integer("helper_event_count") == len(probe["helper_events"]),
        "natural pickup helper-event coverage is inconsistent",
    )
    probe_integer("layout_record_count")
    require(isinstance(probe["pal1_captures"], list)
            and bool(probe["pal1_captures"]),
            "natural pickup route lacks palette-1 temporal captures")

    captures = probe["captures"]
    require(isinstance(captures, list)
            and probe_integer("capture_count") == len(captures)
            and len(captures) >= 6,
            "natural pickup interval screenshot coverage is incomplete")
    for index, capture in enumerate(captures):
        require_exact_keys(
            capture, NO_BLEED_CAPTURE_KEYS,
            f"natural pickup interval capture {index}",
        )
        require(capture["native_size"] == [160, 144],
                f"natural pickup interval capture {index} is not native")
        require_integer(
            capture["play_frame"],
            f"natural pickup interval capture {index} frame", minimum=1,
        )
        histogram = require_exact_keys(
            capture["attribute_histogram"],
            frozenset(str(palette) for palette in range(8)),
            f"natural pickup interval capture {index} histogram",
        )
        require(
            all(isinstance(value, int) and not isinstance(value, bool)
                and value >= 0 for value in histogram.values())
            and 360 <= sum(histogram.values()) <= 399,
            f"natural pickup interval capture {index} histogram is malformed",
        )
        require(
            capture["palette_1_cells"] == histogram["1"],
            f"natural pickup interval capture {index} palette-1 count differs",
        )
        require(require_integer(
            capture["unsafe_attribute_cells"],
            f"natural pickup interval capture {index} unsafe cells",
        ) == 0, f"natural pickup interval capture {index} has unsafe attrs")
        interval_unexpected = require_integer(
            capture["unexpected_palette_cells"],
            f"natural pickup interval capture {index} unexpected cells",
            minimum=0,
        )
        require(
            interval_unexpected <= unexpected_cells
            and interval_unexpected <= sum(histogram.values())
            and (interval_unexpected == 0 or bool(contextual_signatures)),
            f"natural pickup interval capture {index} mismatch accounting "
            "is invalid",
        )
        require(
            isinstance(capture["screenshot"], str)
            and Path(capture["screenshot"]).name == capture["screenshot"]
            and SHA256_PATTERN.fullmatch(capture["screenshot_sha256"])
            is not None,
            f"natural pickup interval capture {index} is not hash-bound",
        )

    raster_captures = probe["raster_captures"]
    require(
        isinstance(raster_captures, list)
        and probe_integer("raster_capture_count") == len(raster_captures)
        and len(raster_captures) >= 1000,
        "natural pickup route has fewer than 1,000 raster transition samples",
    )
    raster_frames: list[int] = []
    background_accents = 0
    stray_accents = 0
    for index, capture in enumerate(raster_captures):
        require_exact_keys(
            capture, NO_BLEED_RASTER_CAPTURE_KEYS,
            f"natural pickup raster capture {index}",
        )
        frame = require_integer(
            capture["play_frame"],
            f"natural pickup raster capture {index} frame", minimum=1,
        )
        raster_frames.append(frame)
        require(capture["native_size"] == [160, 144],
                f"natural pickup raster capture {index} is not native")
        require(
            isinstance(capture["screenshot"], str)
            and Path(capture["screenshot"]).name == capture["screenshot"]
            and SHA256_PATTERN.fullmatch(capture["screenshot_sha256"])
            is not None,
            f"natural pickup raster capture {index} is not hash-bound",
        )
        alignment = capture["raster_alignment_frames"]
        require(
            isinstance(alignment, list) and len(alignment) == 2
            and all(isinstance(value, int) and not isinstance(value, bool)
                    for value in alignment)
            and alignment[0] <= frame <= alignment[1]
            and alignment[1] - alignment[0]
            <= 2 * no_bleed_oracle.RASTER_ALIGNMENT_RADIUS,
            f"natural pickup raster capture {index} alignment is malformed",
        )
        audit = require_exact_keys(
            capture["raster_audit"], NO_BLEED_RASTER_AUDIT_KEYS,
            f"natural pickup raster audit {index}",
        )
        background_accents += require_integer(
            audit["background_pickup_accent_pixels"],
            f"natural pickup raster audit {index} accent pixels",
        )
        stray_accents += require_integer(
            audit["stray_pickup_accent_pixels"],
            f"natural pickup raster audit {index} stray pixels",
        )
        require(isinstance(audit["first_stray_coordinates"], list),
                f"natural pickup raster audit {index} coordinates malformed")
    require(raster_frames == sorted(set(raster_frames)),
            "natural pickup raster frames are duplicate or unordered")
    source_changes = probe_integer("source_signature_changes")
    require(len(raster_captures) >= max(scroll_changes, source_changes),
            "natural pickup route missed a scroll/source raster window")
    require(background_accents > 0,
            "natural pickup raster contains no intentional pickup accents")
    require(not (stray_accents > 0 and unexpected_cells > 0),
            "natural pickup raster contains semantically detached colors")
    require(
        (probe["final_scene"] in {2, 10}
         or final_private_unreadable == 1)
        and probe_integer("final_ffc1") == 1,
        "natural pickup route did not finish in Stage-1 gameplay",
    )
    for field in (
        "contact_sheet_sha256", "raster_contact_sheet_sha256",
    ):
        require(isinstance(receipt[field], str)
                and SHA256_PATTERN.fullmatch(receipt[field]) is not None,
                f"natural pickup {field} is malformed")
    for field in ("contact_sheet", "raster_contact_sheet"):
        require(isinstance(receipt[field], str)
                and Path(receipt[field]).name == receipt[field],
                f"natural pickup {field} is not portable")

    return {
        "receipt": str(resolved),
        "receipt_sha256": sha256(resolved),
        "rom_sha256": candidate_sha256,
        "route": dict(route),
        "coverage": {
            "frames": frames,
            "sampled_frames": sampled_frames,
            "scene_frames": scene_frames,
            "active_frames": active_frames,
            "scroll_changes": scroll_changes,
            "horizontal_scroll_changes": scx_changes,
            "vertical_scroll_changes": scy_changes,
            "interval_captures": len(captures),
            "raster_captures": len(raster_captures),
            "background_pickup_accent_pixels": background_accents,
        },
        "semantic_pickup_attribute_mismatches": 0,
        "reviewed_contextual_floor_observations": unexpected_floor_cells,
        "rendered_stray_accent_pixels": stray_accents,
        "checks": checks,
    }


def validate_reviewed_wall_oracle(
    value: Any, label: str
) -> dict[str, Any]:
    oracle = require_exact_keys(
        value,
        frozenset({
            "schema", "room01", "room05_patterned_floor_control",
            "fingerprint_sha256", "exact",
        }),
        label,
    )
    require(oracle["schema"] == "penta-stage1-room01-wall-oracle-v1",
            f"{label} used the wrong independent oracle schema")
    require(oracle["exact"] is True,
            f"{label} is not exact")
    require(SHA256_PATTERN.fullmatch(
        oracle["fingerprint_sha256"] or ""
    ) is not None, f"{label} fingerprint is malformed")

    room01 = require_exact_keys(
        oracle["room01"],
        frozenset({
            "selector", "minimum_records", "records", "gameplay_frames",
            "reviewed_cells_per_record", "checked_cell_instances",
            "expected_attr", "tile_mismatches", "attr_mismatches",
            "first_mismatch", "exact",
        }),
        f"{label} room01",
    )
    require(room01["selector"] == ROOM01_WALL_SELECTOR,
            f"{label} selected another room01 checkpoint")
    records = require_integer(room01["records"], f"{label} room01 records")
    require(room01["minimum_records"] == 3 and records >= 3,
            f"{label} has fewer than three room01 checkpoint records")
    require(room01["reviewed_cells_per_record"] == 64,
            f"{label} no longer checks all 64 reviewed wall cells")
    require(room01["checked_cell_instances"] == records * 64,
            f"{label} room01 checked-cell count is incomplete")
    require(room01["expected_attr"] == 0x06,
            f"{label} no longer requires full attr byte $06")
    require(room01["tile_mismatches"] == 0
            and room01["attr_mismatches"] == 0
            and room01["first_mismatch"] is None
            and room01["exact"] is True,
            f"{label} room01 wall cells are not exact")
    require(isinstance(room01["gameplay_frames"], list)
            and len(room01["gameplay_frames"]) == records,
            f"{label} room01 frame evidence is incomplete")

    room05 = require_exact_keys(
        oracle["room05_patterned_floor_control"],
        frozenset({
            "selector", "minimum_records", "records", "gameplay_frames",
            "patterned_floor_tile_ids", "observed_patterned_tile_ids",
            "observed_patterned_cells", "expected_attr", "tile_mismatches",
            "control_attr_mismatches", "patterned_attr_mismatches",
            "first_mismatch", "exact",
        }),
        f"{label} room05 control",
    )
    require(room05["selector"] == ROOM05_FLOOR_SELECTOR,
            f"{label} selected another room05 control checkpoint")
    floor_records = require_integer(
        room05["records"], f"{label} room05 records"
    )
    require(room05["minimum_records"] == 2 and floor_records >= 2,
            f"{label} has fewer than two room05 control records")
    require(room05["patterned_floor_tile_ids"] == ROOM05_PATTERNED_IDS,
            f"{label} changed the room05 patterned-floor control class")
    observed_ids = room05["observed_patterned_tile_ids"]
    require(isinstance(observed_ids, list) and observed_ids
            and set(observed_ids).issubset(ROOM05_PATTERNED_IDS),
            f"{label} has no valid observed room05 patterned-floor IDs")
    require(require_integer(
        room05["observed_patterned_cells"],
        f"{label} room05 observed cells",
    ) > 0, f"{label} room05 control is vacuous")
    require(room05["expected_attr"] == 0
            and room05["tile_mismatches"] == 0
            and room05["control_attr_mismatches"] == 0
            and room05["patterned_attr_mismatches"] == 0
            and room05["first_mismatch"] is None
            and room05["exact"] is True,
            f"{label} room05 floor-to-BG0 control failed")
    require(isinstance(room05["gameplay_frames"], list)
            and len(room05["gameplay_frames"]) == floor_records,
            f"{label} room05 frame evidence is incomplete")
    return oracle


def validate_north_traversal_speed(receipt: dict[str, Any]) -> dict[str, Any]:
    """A visually exact target-only replay must not hide sustained slowdown."""
    timing_fields = (
        "frames",
        "first_gameplay",
        "native_gameplay_start",
        "gameplay_frames",
        "native_gameplay_frames",
    )
    timings: dict[str, dict[str, int]] = {}
    for label in ("baseline", "candidate", "candidate_replay"):
        report = receipt.get(label)
        require(isinstance(report, dict),
                f"north traversal timing missing or invalid: {label}")
        timing: dict[str, int] = {}
        for field in timing_fields:
            value = report.get(field)
            require(
                isinstance(value, str)
                and DECIMAL_PATTERN.fullmatch(value) is not None,
                f"north traversal timing missing or invalid: {label}.{field}",
            )
            timing[field] = int(value)
        require(60 < timing["frames"] <= 2400,
                f"north traversal timing outside measured route: {label}")
        require(0 <= timing["first_gameplay"] < timing["frames"],
                f"north traversal first gameplay boundary is invalid: {label}")
        require(
            timing["first_gameplay"]
            <= timing["native_gameplay_start"]
            < timing["frames"],
            f"north traversal native gameplay boundary is invalid: {label}",
        )
        require(
            timing["gameplay_frames"]
            == timing["frames"] - timing["first_gameplay"],
            f"north traversal gameplay timing arithmetic is invalid: {label}",
        )
        require(
            timing["native_gameplay_frames"]
            == timing["frames"] - timing["native_gameplay_start"],
            f"north traversal native gameplay timing arithmetic is invalid: "
            f"{label}",
        )
        require(60 < timing["native_gameplay_frames"] <= 2400,
                f"north traversal timing outside measured route: {label}")
        timings[label] = timing
    require(timings["candidate"] == timings["candidate_replay"],
            "north traversal timing is not repeatable")
    reported_lag = require_integer(
        receipt.get("gameplay_frame_lag"),
        "north traversal reported gameplay-frame lag",
    )
    native_frames = {
        label: timing["native_gameplay_frames"]
        for label, timing in timings.items()
    }
    require(reported_lag
            == native_frames["candidate"] - native_frames["baseline"],
            "north traversal timing disagrees with reported lag")
    # Equal target-settle intervals are included on both sides. This is a
    # conservative floor: counting idle settling cannot exaggerate slowdown.
    ratio = native_frames["baseline"] / native_frames["candidate"]
    require(ratio >= 0.95,
            f"north traversal speed {ratio:.6f} is below the 0.95 release floor")
    return {
        "timings": timings,
        "native_gameplay_frames": native_frames,
        "gameplay_frame_lag": reported_lag,
        "ratio": ratio,
        "minimum_ratio": 0.95,
        "passed": True,
    }


def validate_north_receipt(
    path: Path, candidate: Path, candidate_sha256: str
) -> dict[str, Any]:
    resolved = path.resolve()
    receipt = load_json(resolved, "independent room01 north receipt")
    require(receipt.get("schema") == NORTH_SCHEMA,
            "wrong independent room01 north receipt schema")
    require(receipt.get("status") == "pass",
            "independent room01 north verifier did not pass")
    require(Path(receipt.get("candidate_rom", "")).resolve()
            == candidate.resolve(),
            "independent room01 north receipt targets another candidate path")
    require(receipt.get("candidate_sha256") == candidate_sha256,
            "independent room01 north receipt targets another candidate hash")
    require(receipt.get("input_route")
            == "cold GAME START; hold UP; no gameplay memory writes",
            "independent room01 north route changed")
    require(receipt.get("gameplay_frames") == 2400
            and receipt.get("target_camera") == 0x03A4
            and receipt.get("target_room") == 1
            and receipt.get("target_settle_frames") == 60
            and receipt.get("dynamic_prefix_bytes") == 0
            and receipt.get("target_only_policy") is True,
            "independent room01 north route policy changed")
    for field in (
        "candidate_replay_exact", "candidate_replay_attributes_exact",
        "settled_final_state_ok", "reviewed_room01_wall_replay_exact",
        "reviewed_room01_wall_oracle_ok",
        "service_frame_presentations_exact",
        "candidate_attribute_trajectory_exact",
        "candidate_physical_page_ownership_exact",
        "physical_page_owner_reports_exact",
        "progress_route_geometry_exact", "progress_route_viewports_exact",
        "target_only_static_route_ok",
    ):
        require(receipt.get(field) is True,
                f"independent room01 north receipt failed {field}")
    require(receipt.get("terrain_differences") == 0,
            "independent room01 north terrain differs from stock")
    require(receipt.get("world_template", {}).get("exact_at_entry") is True,
            "independent room01 north world template differs at entry")
    require(receipt.get("metatile_table", {}).get("exact_at_entry") is True,
            "independent room01 north metatile table differs at entry")
    require(receipt.get("candidate_settled_final_state", {}).get("passed") is True
            and receipt.get("candidate_replay_settled_final_state", {}).get(
                "passed"
            ) is True,
            "independent room01 north final state is not settled in both runs")
    fixture_path = receipt.get("reviewed_wall_fixture")
    require(fixture_path == str(ROOM01_WALL_FIXTURE.relative_to(ROOT)),
            "independent room01 north receipt names another wall fixture")
    require(receipt.get("reviewed_wall_fixture_sha256")
            == sha256(ROOM01_WALL_FIXTURE),
            "independent room01 north wall fixture hash differs")
    require(receipt.get("reviewed_room01_runtime_tile_attrs")
            == ROOM01_RUNTIME_WALL_TILE_ATTRS,
            "room01 runtime wall expectations are not fixture-derived $06")
    oracle = validate_reviewed_wall_oracle(
        receipt.get("reviewed_room01_wall_oracle"),
        "independent room01 north oracle",
    )
    replay_oracle = validate_reviewed_wall_oracle(
        receipt.get("reviewed_room01_wall_replay_oracle"),
        "independent room01 north replay oracle",
    )
    require(replay_oracle == oracle,
            "independent room01 north oracle differs across replay")
    trajectory = receipt.get("full_route_viewport_integrity")
    require(isinstance(trajectory, dict)
            and trajectory.get("reviewed_room01_wall_oracle") == oracle,
            "north trajectory rollup differs from reviewed wall oracle")
    geometry_maxima = receipt.get("full_route_geometry_maxima")
    require(
        isinstance(geometry_maxima, dict)
        and set(geometry_maxima) == {
            "world_state", "world_progress", "service_presentation",
        }
        and all(
            isinstance(value, int) and value <= 0
            for value in geometry_maxima.values()
        )
        and receipt.get("full_route_geometry_differences_present") is False
        and receipt.get("full_route_geometry_worst_example") is None,
        "north receipt contains a nonzero full-route geometry difference",
    )
    require(
        trajectory.get("maximum_viewport_tile_differences", 1) <= 0
        and trajectory.get(
            "maximum_progress_viewport_tile_differences", 1
        ) <= 0
        and trajectory.get(
            "maximum_service_viewport_tile_differences", 1
        ) <= 0,
        "north trajectory contains a nonzero viewport geometry difference",
    )
    require(receipt.get("trajectory_schema")
            == "penta-stage1-north-trajectory-v3",
            "north trajectory record schema is stale")
    ownership = trajectory.get("candidate_attribute_integrity", {}).get(
        "physical_page_ownership", {}
    )
    require(
        ownership.get("policy")
        == "ffe5-at-bank1-42a7-promoted-at-exact-lcdc-store-v2"
        and ownership.get("exact") is True
        and ownership.get("evidence_errors") == [],
        "north trajectory lacks exact FFE5 physical-page ownership",
    )
    candidate_publication = north_oracle.detect_publication_boundary(
        candidate.read_bytes()
    )
    baseline_path = Path(receipt.get("baseline_rom", "")).resolve()
    require(baseline_path.is_file(),
            "north receipt baseline ROM is missing")
    require(receipt.get("baseline_sha256") == sha256(baseline_path),
            "north receipt baseline ROM hash is stale")
    baseline_publication = north_oracle.detect_publication_boundary(
        baseline_path.read_bytes()
    )
    for label, mode, publication in (
        (
            "baseline_physical_page_owner_report",
            "dmg",
            baseline_publication,
        ),
        (
            "candidate_physical_page_owner_report",
            "cgb",
            candidate_publication,
        ),
        (
            "candidate_replay_physical_page_owner_report",
            "cgb",
            candidate_publication,
        ),
    ):
        owner_report = receipt.get(label)
        require(isinstance(owner_report, dict)
                and owner_report.get("exact") is True
                and owner_report.get("errors") == []
                and owner_report.get("rom_mode") == mode
                and owner_report.get("room_source")
                == "FFE5-at-bank1:42A7"
                and owner_report.get("publication") == publication,
                f"north receipt failed {label}")
        counters = owner_report.get("counters")
        require(isinstance(counters, dict),
                f"north receipt {label} counters are missing")
        for counter in (
            "map_owner_invalid_arms",
            "map_owner_invalid_commits",
            "map_owner_missing_commits",
            "map_owner_missing_trajectory_frames",
            "map_owner_invalid_trajectory_frames",
        ):
            require(counters.get(counter) == 0,
                    f"north receipt {label} failed {counter}")
        if mode == "cgb":
            require(counters.get("map_owner_arm_events", 0) > 0
                    and counters.get("map_owner_publications", 0) > 0,
                    f"north receipt {label} lacks owner hook coverage")
    require(sha256(candidate.resolve()) == candidate_sha256,
            "candidate changed during independent north receipt validation")
    traversal_speed = validate_north_traversal_speed(receipt)
    return {
        "receipt": str(resolved),
        "receipt_sha256": sha256(resolved),
        "rom_sha256": candidate_sha256,
        "fixture": str(ROOM01_WALL_FIXTURE),
        "fixture_sha256": sha256(ROOM01_WALL_FIXTURE),
        "checkpoint_selector": ROOM01_WALL_SELECTOR,
        "traversal_speed": traversal_speed,
        "reviewed_cells_per_record": 64,
        "checkpoint_records": oracle["room01"]["records"],
        "expected_attr": "06",
        "runtime_tile_attrs": ROOM01_RUNTIME_WALL_TILE_ATTRS,
        "room05_patterned_floor_attr": "00",
        "fingerprint_sha256": oracle["fingerprint_sha256"],
        "candidate_replay_exact": True,
    }


def validate_scene0b_receipt(
    path: Path,
    candidate: Path,
    candidate_sha256: str,
    expected_live_receipt: Path,
) -> dict[str, Any]:
    bound = validate_scene0b_bound_receipt(
        path.resolve(), candidate.resolve(), candidate_sha256,
        expected_live_receipt.resolve(),
    )
    require(bound.get("schema") == SCENE0B_BOUND_SCHEMA,
            "wrong bound scene-$0B receipt schema")
    coverage = bound.get("coverage")
    require(coverage == {
        "archived_incompatible_capture_count": 1,
        "candidate_native_capture_count": 1,
        "capture_count": 2,
        "replay_count": 4,
        "scene0b_live": True,
        "menu_roundtrip": True,
        "deterministic": True,
    }, "bound scene-$0B live coverage is incomplete")
    return {
        "receipt": str(path.resolve()),
        "receipt_sha256": sha256(path.resolve()),
        "rom_sha256": candidate_sha256,
        "live_receipt": bound["live_receipt"],
        "live_receipt_sha256": bound["live_receipt_sha256"],
        "fixture": bound["fixture"],
        "fixture_sha256": bound["fixture_sha256"],
        "archived_incompatible_capture_count": 1,
        "candidate_native_capture_count": 1,
        "capture_count": 2,
        "replay_count": 4,
        "scene0b_live": True,
        "menu_roundtrip": True,
        "deterministic": True,
    }


def validate_tilemap_receipt(
    path: Path, candidate: Path, candidate_sha256: str
) -> dict[str, Any]:
    """Re-grade every in-run tilemap report against the immutable oracle."""

    resolved = path.resolve()
    receipt = load_json(resolved, "Stage-1 tilemap publication receipt")
    require_exact_keys(
        receipt, TILEMAP_RECEIPT_KEYS, "Stage-1 tilemap publication receipt",
    )
    require(receipt["schema"] == TILEMAP_RECEIPT_SCHEMA,
            "wrong Stage-1 tilemap publication receipt schema")
    require(receipt["status"] == "PASS" and receipt["failures"] == [],
            "Stage-1 tilemap publication verifier did not pass cleanly")
    require(receipt["candidate"] == str(candidate.resolve()),
            "Stage-1 tilemap receipt names another candidate")
    require(receipt["candidate_sha256"] == candidate_sha256,
            "Stage-1 tilemap receipt targets another candidate hash")
    require(sha256(candidate.resolve()) == candidate_sha256,
            "candidate changed during Stage-1 tilemap receipt validation")

    configuration = require_exact_keys(
        receipt["configuration"], TILEMAP_CONFIGURATION_KEYS,
        "Stage-1 tilemap configuration",
    )
    guarded_mgba = (ROOT / "scripts/mgba-qt-singleflight").resolve()
    require(
        configuration == {
            "states_root": str(TILEMAP_STATES_ROOT.resolve()),
            "state_names": list(TILEMAP_RELEASE_STATES),
            "frames": TILEMAP_RELEASE_FRAMES,
            "timeout_seconds": TILEMAP_RELEASE_TIMEOUT_SECONDS,
            "warm_reset": False,
            "force_pure": False,
            "trace_hash": "",
            "mgba": str(guarded_mgba),
        },
        "Stage-1 tilemap release configuration changed",
    )
    oracle = require_exact_keys(
        receipt["oracle"], TILEMAP_ORACLE_KEYS,
        "Stage-1 tilemap immutable oracle",
    )
    candidate_copier_sha256 = tilemap_oracle.sha256_bytes(
        tilemap_oracle.reviewed_postcomputed_copier(candidate.read_bytes())
    )
    candidate_lut_sha256 = tilemap_oracle.reviewed_lut_identity(
        tilemap_oracle.reviewed_stage1_lut(candidate.read_bytes())
    )
    require(oracle == {
        "schema": tilemap_oracle.PUBLICATION_ORACLE_SCHEMA,
        "canonical_lut_sha256": candidate_lut_sha256,
        "copier_sha256": candidate_copier_sha256,
        "ordinary_attribute_scope": tilemap_oracle.ORDINARY_ATTRIBUTE_SCOPE,
        "semantic_overlay_owner": tilemap_oracle.SEMANTIC_OVERLAY_OWNER,
    }, "Stage-1 tilemap immutable oracle identity changed")
    expected_tool_identity = tilemap_oracle.receipt_tool_identity(guarded_mgba)
    require(receipt["tool_identity"] == expected_tool_identity,
            "Stage-1 tilemap verifier tool identity changed")

    reports = receipt["reports"]
    require(isinstance(reports, list)
            and len(reports) == len(TILEMAP_RELEASE_STATES),
            "Stage-1 tilemap receipt lacks all three release fixtures")
    require([item.get("state_name") for item in reports]
            == list(TILEMAP_RELEASE_STATES),
            "Stage-1 tilemap fixture order or inventory changed")
    receipt_root = resolved.parent
    total_completions = 0
    total_atomic = 0
    all_destinations: set[str] = set()
    validated_reports: list[dict[str, Any]] = []
    for index, (item, state_name) in enumerate(
        zip(reports, TILEMAP_RELEASE_STATES, strict=True), start=1
    ):
        require_exact_keys(
            item, TILEMAP_REPORT_KEYS,
            f"Stage-1 tilemap report receipt {index}",
        )
        expected_state = (TILEMAP_STATES_ROOT / state_name).resolve()
        require(expected_state.is_file(),
                f"Stage-1 tilemap fixture is missing: {expected_state}")
        require(item["state_path"] == str(expected_state)
                and item["state_sha256"] == sha256(expected_state),
                f"Stage-1 tilemap fixture {state_name} is not hash-bound")
        expected_retargeted = (
            receipt_root / Path(state_name).stem / "retargeted-state.ss0"
        ).resolve()
        require(
            item["retargeted_state_path"] == str(expected_retargeted)
            and expected_retargeted.is_file()
            and item["retargeted_state_sha256"]
            == sha256(expected_retargeted)
            and item["retarget_mode"] == "ROM_IDENTITY_ONLY",
            f"Stage-1 tilemap fixture {state_name} lacks exact identity-only "
            "retarget provenance",
        )
        expected_report = receipt_root / f"{Path(state_name).stem}.report"
        require(item["report_path"] == str(expected_report.resolve()),
                f"Stage-1 tilemap report {state_name} escaped its run output")
        require(expected_report.is_file()
                and item["report_sha256"] == sha256(expected_report),
                f"Stage-1 tilemap report {state_name} hash differs")
        report = tilemap_oracle.parse_report(expected_report)
        report_failures = tilemap_oracle.publication_oracle_report_failures(
            report, expected_rom_sha256=candidate_sha256,
            expected_copier_sha256=candidate_copier_sha256,
            expected_lut_sha256=candidate_lut_sha256,
            require_atomic=True, label=state_name,
        )
        require(not report_failures,
                "Stage-1 tilemap report failed immutable oracle: "
                + "; ".join(report_failures))
        atomic = require_integer(
            int(report["atomic_completions"]),
            f"Stage-1 tilemap {state_name} atomic completions", minimum=1,
        )
        pure = require_integer(
            int(report["pure_completions"]),
            f"Stage-1 tilemap {state_name} pure completions", minimum=0,
        )
        exact = require_integer(
            int(report["exact_copies"]),
            f"Stage-1 tilemap {state_name} exact copies", minimum=1,
        )
        destinations = sorted({
            value for value in report["destinations"].split(",") if value
        })
        require(item["atomic_completions"] == atomic
                and item["pure_completions"] == pure
                and item["exact_copies"] == exact
                and item["destinations"] == destinations,
                f"Stage-1 tilemap report rollup differs for {state_name}")
        total_completions += atomic + pure
        total_atomic += atomic
        all_destinations.update(destinations)
        validated_reports.append({
            "state_name": state_name,
            "state_path": str(expected_state),
            "state_sha256": sha256(expected_state),
            "report_path": str(expected_report.resolve()),
            "report_sha256": sha256(expected_report),
            "exact_copies": exact,
            "atomic_completions": atomic,
        })

    totals = require_exact_keys(
        receipt["totals"], TILEMAP_TOTAL_KEYS,
        "Stage-1 tilemap publication totals",
    )
    require(totals == {
        "requested_states": len(TILEMAP_RELEASE_STATES),
        "completed_reports": len(TILEMAP_RELEASE_STATES),
        "completions": total_completions,
        "atomic_completions": total_atomic,
        "destinations": sorted(all_destinations),
    }, "Stage-1 tilemap aggregate totals are not recomputable")
    require(total_completions >= TILEMAP_MINIMUM_PUBLICATIONS,
            "Stage-1 tilemap publication coverage is below 3000 copies")
    require(all_destinations == {"9800", "9C00"},
            "Stage-1 tilemap gate did not exercise both physical maps")
    require_exact_true_checks(
        receipt["checks"], TILEMAP_CHECKS,
        "Stage-1 tilemap publication",
    )
    require(sha256(candidate.resolve()) == candidate_sha256,
            "candidate changed during Stage-1 tilemap report regrading")
    return {
        "receipt": str(resolved),
        "receipt_sha256": sha256(resolved),
        "rom_sha256": candidate_sha256,
        "oracle": oracle,
        "reports": validated_reports,
        "total_completions": total_completions,
        "total_atomic_completions": total_atomic,
        "destinations": sorted(all_destinations),
        "tool_identity": expected_tool_identity,
    }


def validate_state_receipt(
    path: Path, state: Path, candidate_sha256: str
) -> dict[str, Any]:
    receipt = load_json(path, "ROM-owned hazard-state receipt")
    state_sha256 = sha256(state)
    require(receipt.get("schema") == STATE_SCHEMA,
            "wrong hazard-state receipt schema")
    require(receipt.get("passed") is True,
            "hazard-state generation did not pass")
    require(receipt.get("rom_sha256") == candidate_sha256,
            "hazard-state receipt targets another ROM")
    require(receipt.get("state_sha256") == state_sha256,
            "hazard-state receipt does not bind its state")
    require(receipt.get("hardware", {}).get("settled") is True,
            "hazard state was not saved at settled hardware")
    require(receipt.get("hazard_cells", 0) >=
            receipt.get("minimum_hazard_cells", 1) >= 1,
            "hazard state has insufficient ROM-owned hazard cells")
    require(receipt.get("tooth_cells", 0) >=
            receipt.get("minimum_tooth_cells", 1) >= 1,
            "hazard state has insufficient ROM-owned tooth cells")
    return {
        "receipt": str(path),
        "receipt_sha256": sha256(path),
        "state": str(state),
        "state_sha256": state_sha256,
        "rom_sha256": candidate_sha256,
        "hazard_cells": receipt["hazard_cells"],
        "tooth_cells": receipt["tooth_cells"],
        "hardware_settled": True,
    }


def validate_hazard_menu_receipt(
    path: Path,
    state_evidence: dict[str, Any],
    candidate_sha256: str,
) -> dict[str, Any]:
    receipt = load_json(path, "ROM-owned hazard-menu receipt")
    require(receipt.get("schema") == HAZARD_MENU_SCHEMA,
            "wrong hazard-menu receipt schema")
    require(receipt.get("passed") is True,
            "ROM-owned hazard-menu replay did not pass")
    require(receipt.get("rom_sha256") == candidate_sha256,
            "hazard-menu receipt targets another ROM")
    require(receipt.get("state_sha256") == state_evidence["state_sha256"],
            "hazard-menu replay uses another state")
    require(
        receipt.get("state_receipt_sha256")
        == state_evidence["receipt_sha256"],
        "hazard-menu replay uses another state receipt",
    )
    require_exact_true_checks(
        receipt.get("checks"), HAZARD_MENU_TOP_CHECKS,
        "top-level ROM-owned hazard-menu",
    )
    replays = receipt.get("replays")
    require(isinstance(replays, list) and len(replays) == 2,
            "exactly two ROM-owned hazard-menu replays are required")
    require(replays[0] == replays[1],
            "ROM-owned hazard-menu replays are not deterministic")
    zero_fields = (
        "menu_map_alias_frames",
        "transient_mismatch_frames",
        "unsafe_map_flip_events",
        "floor_mismatch_frames",
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
        "visible_semantic_attr_write_hits",
        "phase_floor_attr_mismatch_cells",
        "rendered_wrong_palette0_tooth_cells",
    )
    first_bad_fields = (
        "first_menu_map_alias",
        "first_transient_mismatch",
        "first_floor_mismatch",
        "first_endpoint_mismatch",
    )
    for index, replay in enumerate(replays, start=1):
        require(isinstance(replay, dict),
                f"hazard-menu replay {index} is not an object")
        require_exact_true_checks(
            replay.get("checks"), HAZARD_MENU_REPLAY_CHECKS,
            f"ROM-owned hazard-menu replay {index}",
        )
        require(replay.get("post_menu_input_mask") == 0,
                "hazard-menu replay moved to hide stationary artifacts")
        require(replay.get("room") == "01",
                "hazard-menu replay did not remain in the hazard room")
        reviewed_wall = require_exact_keys(
            replay.get("reviewed_room_local_attr_oracle"),
            frozenset({
                "fixture", "fixture_sha256", "policy", "entries",
                "immutable_lut_divergences",
                "candidate_runtime_lut_used_as_oracle",
            }),
            f"hazard-menu replay {index} reviewed wall oracle",
        )
        expected_policy = ",".join(
            f"{key}:{value:02X}"
            for key, value in sorted(ROOM01_RUNTIME_WALL_TILE_ATTRS.items())
        )
        require(
            reviewed_wall == {
                "fixture": str(ROOM01_WALL_FIXTURE.resolve()),
                "fixture_sha256": sha256(ROOM01_WALL_FIXTURE),
                "policy": expected_policy,
                "entries": len(ROOM01_RUNTIME_WALL_TILE_ATTRS),
                "immutable_lut_divergences": [
                    "01:24:06", "01:27:06", "01:30:06", "01:33:06",
                ],
                "candidate_runtime_lut_used_as_oracle": False,
            },
            f"hazard-menu replay {index} wall oracle is not fixture-pinned",
        )
        require(
            require_integer(
                replay.get("post_menu_closed_frames"),
                f"hazard-menu replay {index} post-menu frames",
                minimum=20,
            ) >= 20,
            f"hazard-menu replay {index} lacks post-menu raster coverage",
        )
        for field in zero_fields:
            require(
                require_integer(
                    replay.get(field), f"hazard-menu replay {index} {field}"
                ) == 0,
                f"hazard-menu replay {index} {field} is not zero",
            )
        for field in first_bad_fields:
            require(replay.get(field) == "",
                    f"hazard-menu replay {index} {field} records a defect")
        temporal = require_exact_keys(
            replay.get("temporal_raster"),
            frozenset({
                "enabled", "baseline_frames", "checked_frames",
                "baseline_phase_signatures", "baseline_observable_pixels",
                "baseline_unobservable_pixels", "unmatched_phase_frames",
                "mismatch_frames", "first_mismatch",
            }),
            f"hazard-menu replay {index} temporal raster",
        )
        require(temporal["enabled"] is True,
                f"hazard-menu replay {index} temporal raster is disabled")
        require_integer(
            temporal["baseline_frames"],
            f"hazard-menu replay {index} temporal baseline",
            minimum=24,
        )
        require_integer(
            temporal["checked_frames"],
            f"hazard-menu replay {index} temporal coverage",
            minimum=60,
        )
        require_integer(
            temporal["baseline_phase_signatures"],
            f"hazard-menu replay {index} temporal phase coverage",
            minimum=4,
        )
        require_integer(
            temporal["baseline_observable_pixels"],
            f"hazard-menu replay {index} observable baseline pixels",
            minimum=1,
        )
        require_integer(
            temporal["baseline_unobservable_pixels"],
            f"hazard-menu replay {index} sprite-occluded baseline pixels",
            minimum=0,
        )
        require(
            require_integer(
                temporal["mismatch_frames"],
                f"hazard-menu replay {index} temporal mismatch frames",
            ) == 0
            and require_integer(
                temporal["unmatched_phase_frames"],
                f"hazard-menu replay {index} unmatched temporal phases",
            ) == 0
            and temporal["first_mismatch"] is None,
            f"hazard-menu replay {index} temporal raster records a mismatch",
        )

    raw_reports = receipt.get("raw_reports")
    require(isinstance(raw_reports, list) and len(raw_reports) == 2,
            "hazard-menu receipt does not bind exactly two raw reports")
    for index, raw_report in enumerate(raw_reports, start=1):
        require(isinstance(raw_report, str),
                f"hazard-menu raw report {index} path is malformed")
        resolved_report = Path(raw_report).resolve()
        require(resolved_report.is_file(),
                f"hazard-menu raw report {index} is missing")
        require(
            resolved_report.parent
            == (path.parent / f"replay-{index}").resolve(),
            f"hazard-menu raw report {index} is outside its replay directory",
        )

    no_injection_contract = validate_hazard_menu_no_injection_contract()
    return {
        "receipt": str(path),
        "receipt_sha256": sha256(path),
        "rom_sha256": candidate_sha256,
        "state_sha256": state_evidence["state_sha256"],
        "replay_count": 2,
        "byte_deterministic": True,
        "stationary_post_menu": True,
        "normalization_writes": 0,
        "df5b_injected": False,
        "vram_injection_bytes": 0,
        "no_injection_contract": no_injection_contract,
    }


def validate_menu_race_receipt(
    path: Path, candidate_sha256: str
) -> dict[str, Any]:
    receipt = load_json(path, "Stage-1 menu-race static receipt")
    require(receipt.get("schema") == MENU_RACE_SCHEMA,
            "wrong menu-race static receipt schema")
    require(receipt.get("status") == "PASS",
            "menu-race static proof did not pass")
    require(receipt.get("candidate_sha256") == candidate_sha256,
            "menu-race static receipt targets another candidate")
    require_exact_true_checks(
        receipt.get("checks"), MENU_RACE_CHECKS, "menu-race static"
    )
    require(receipt.get("coverage") == {
        "selector_byte_pairs": 65536,
        "selector_canonical_bit_pairs": 4,
        "sentinel_state_pairs": 65536,
        "ff_decider_signature_phase_pairs": 65536,
    }, "menu-race exhaustive coverage changed")
    require(receipt.get("negative_controls") == {
        "old_dc0b_selector_rejected_cases": 32768,
        "wrong_lcdc_bit_rejected_cases": 32768,
        "old_zero_sentinel_rejected_cases": 255,
        "zero_sentinel_false_hit_cases": 256,
        "mutated_decider_rejected": True,
    }, "menu-race negative controls changed")
    return {
        "receipt": str(path),
        "receipt_sha256": sha256(path),
        "rom_sha256": candidate_sha256,
        "coverage": receipt["coverage"],
        "negative_controls": receipt["negative_controls"],
    }


def validate_stage_card_receipt(
    path: Path, candidate_sha256: str
) -> dict[str, Any]:
    receipt = load_json(path, "fresh Stage-card stability receipt")
    require(receipt.get("schema") == STAGE_CARD_SCHEMA,
            "wrong Stage-card stability receipt schema")
    require(receipt.get("status") == "pass",
            "Stage-card stability verifier did not pass")
    require(receipt.get("observe_only") is False,
            "observe-only Stage-card receipt cannot qualify READY")
    require(receipt.get("rom_sha256") == candidate_sha256,
            "Stage-card receipt targets another candidate")
    require(
        isinstance(receipt.get("expected_title_bg0"), str)
        and re.fullmatch(r"[0-9A-F]{16}", receipt["expected_title_bg0"])
        is not None,
        "Stage-card receipt lacks its reviewed title/card BG0 oracle",
    )
    checks = require_exact_true_checks(
        receipt.get("checks"), STAGE_CARD_CHECKS, "Stage-card stability"
    )
    exact_check = (
        "blank-SRAM Stage-1 entry exposes no third purple/cyan/partial state"
    )
    require(checks.get(exact_check) is True,
            f"required Stage-card check did not pass: {exact_check}")
    return {
        "receipt": str(path),
        "receipt_sha256": sha256(path),
        "rom_sha256": candidate_sha256,
        "required_check": exact_check,
        "all_checks_passed": True,
    }


def validate_pickup_state_receipt(
    path: Path,
    state: Path,
    candidate: Path,
    candidate_sha256: str,
) -> dict[str, Any]:
    """Revalidate the candidate-owned pickup-state receipt and artifacts."""

    resolved = path.resolve()
    resolved_state = state.resolve()
    receipt = load_json(resolved, "candidate-owned pickup-state receipt")
    require_exact_keys(
        receipt, PICKUP_STATE_RECEIPT_KEYS,
        "candidate-owned pickup-state receipt",
    )
    require(receipt.get("schema") == PICKUP_STATE_SCHEMA,
            "wrong candidate-owned pickup-state receipt schema")
    require(receipt.get("rom") == str(candidate.resolve()),
            "candidate-owned pickup-state receipt names another ROM")
    checks = require_exact_true_checks(
        receipt.get("checks"),
        frozenset(pickup_receipts.PICKUP_GENERATOR_CHECKS),
        "candidate-owned pickup-state",
    )
    failures: list[str] = []
    evidence = pickup_receipts.validate_pickup_generator(
        receipt, resolved, candidate_sha256, failures,
    )
    require(not failures,
            "candidate-owned pickup-state validation failed: "
            + "; ".join(failures))
    require(evidence.get("state") == str(resolved_state),
            "candidate-owned pickup-state artifact path changed")
    require(evidence.get("state_sha256") == sha256(resolved_state),
            "candidate-owned pickup-state artifact hash changed")
    require(resolved_state.parent == resolved.parent,
            "candidate-owned pickup state is outside its receipt directory")
    return {
        "receipt": str(resolved),
        "receipt_sha256": sha256(resolved),
        "rom_sha256": candidate_sha256,
        "state": str(resolved_state),
        "state_sha256": evidence["state_sha256"],
        "screenshot": evidence["screenshot"],
        "screenshot_sha256": evidence["screenshot_sha256"],
        "passing_checks": len(checks),
        "validator": "verify_pocket_visual_receipts.validate_pickup_generator",
    }


def validate_pickup_host_receipt(
    path: Path,
    generator_receipt: Path,
    generator_evidence: dict[str, Any],
    candidate: Path,
    candidate_sha256: str,
) -> dict[str, Any]:
    """Revalidate all 19 live current-host pickup palette presentations."""

    resolved = path.resolve()
    resolved_generator = generator_receipt.resolve()
    receipt = load_json(resolved, "current-host pickup palette receipt")
    require_exact_keys(
        receipt, PICKUP_HOST_RECEIPT_KEYS,
        "current-host pickup palette receipt",
    )
    require(receipt.get("schema") == PICKUP_HOST_SCHEMA,
            "wrong current-host pickup palette receipt schema")
    require(receipt.get("rom") == str(candidate.resolve()),
            "current-host pickup receipt names another ROM")
    checks = require_exact_true_checks(
        receipt.get("checks"),
        frozenset(pickup_receipts.PICKUP_HOST_CHECKS),
        "current-host pickup palette",
    )
    forms = receipt.get("forms")
    require(isinstance(forms, list) and len(forms) == 19,
            "current-host pickup receipt does not contain 19 forms")
    for index, form in enumerate(forms, start=1):
        require_exact_keys(
            form, PICKUP_HOST_FORM_KEYS,
            f"current-host pickup form {index}",
        )
        require_exact_keys(
            form.get("gates"), PICKUP_HOST_FORM_GATE_KEYS,
            f"current-host pickup form {index} gates",
        )
    failures: list[str] = []
    pickup_evidence = pickup_receipts.validate_pickup_host(
        receipt,
        resolved,
        {
            "state_sha256": generator_evidence["state_sha256"],
        },
        resolved_generator,
        candidate_sha256,
        failures,
    )
    require(not failures,
            "current-host pickup palette validation failed: "
            + "; ".join(failures))
    require(pickup_evidence.get("forms") == 19
            and pickup_evidence.get("unique_forms") == 19,
            "current-host pickup form coverage is not exact")
    return {
        "receipt": str(resolved),
        "receipt_sha256": sha256(resolved),
        "rom_sha256": candidate_sha256,
        "generator_receipt": str(resolved_generator),
        "generator_receipt_sha256": sha256(resolved_generator),
        "state": generator_evidence["state"],
        "state_sha256": generator_evidence["state_sha256"],
        "forms": 19,
        "passing_checks": len(checks),
        "validator": "verify_pocket_visual_receipts.validate_pickup_host",
        "pickup_evidence": pickup_evidence,
    }


def validate_continuity_receipt(
    path: Path,
    candidate_sha256: str,
    state_evidence: dict[str, Any],
    replay_evidence: dict[str, Any],
) -> dict[str, Any]:
    resolved = path.resolve()
    receipt = load_json(resolved, "independent rendered-continuity receipt")
    require(receipt.get("schema") == CONTINUITY_SCHEMA,
            "wrong rendered-continuity receipt schema")
    require(receipt.get("passed") is True,
            "independent rendered-continuity analysis did not pass")
    require(receipt.get("rom_sha256") == candidate_sha256,
            "rendered-continuity receipt targets another ROM")
    require(receipt.get("oracle") == "independent-rendered-continuity",
            "rendered-continuity receipt used a candidate-owned oracle")
    require(receipt.get("rom_owned_state") is True,
            "rendered-continuity evidence did not use ROM-owned state")
    require(receipt.get("vram_injection_bytes") == 0,
            "rendered-continuity evidence injected VRAM")
    require(receipt.get("df5b_injected") is False,
            "rendered-continuity evidence injected DF5B")
    require(receipt.get("state_sha256") == state_evidence["state_sha256"],
            "rendered-continuity receipt uses another state")
    require(
        receipt.get("state_receipt_sha256") == state_evidence["receipt_sha256"],
        "rendered-continuity receipt uses another state receipt",
    )
    require(
        receipt.get("hazard_menu_receipt_sha256")
        == replay_evidence["receipt_sha256"],
        "rendered-continuity receipt uses another hazard-menu replay",
    )
    require_exact_true_checks(
        receipt.get("checks"), CONTINUITY_CHECKS,
        "independent rendered-continuity",
    )
    mutation_controls = require_exact_true_checks(
        receipt.get("mutation_controls"), CONTINUITY_MUTATION_CONTROLS,
        "rendered-continuity mutation controls",
    )
    oracle_contract = require_exact_keys(
        receipt.get("oracle_contract"),
        frozenset({
            "candidate_palette_bytes_used", "candidate_remap_output_used",
            "candidate_vram_used_as_expected_output", "fixed_render_semantics",
            "temporal_reference", "menu_window_top",
            "sprite_occlusion_source",
            "supplemental_operator_capture_fixture",
            "supplemental_operator_capture_fixture_sha256",
        }),
        "rendered-continuity oracle contract",
    )
    require(
        oracle_contract.get("candidate_palette_bytes_used") is False
        and oracle_contract.get("candidate_remap_output_used") is False
        and oracle_contract.get("candidate_vram_used_as_expected_output") is False,
        "rendered-continuity analysis used a candidate-owned oracle",
    )
    require(oracle_contract.get("menu_window_top") == 96,
            "rendered-continuity menu-window boundary changed")
    require(
        oracle_contract.get("sprite_occlusion_source")
        == "hash-bound per-frame hardware OAM footprints; exclusion-only",
        "rendered-continuity sprite-occlusion provenance changed",
    )
    require(
        oracle_contract.get("supplemental_operator_capture_fixture")
        == str(CONTINUITY_OPERATOR_CAPTURE_FIXTURE.relative_to(ROOT)),
        "rendered-continuity receipt names another operator PNG fixture",
    )
    require(
        oracle_contract.get("supplemental_operator_capture_fixture_sha256")
        == sha256(CONTINUITY_OPERATOR_CAPTURE_FIXTURE),
        "rendered-continuity operator PNG fixture hash changed",
    )
    metrics = require_exact_keys(
        receipt.get("metrics"),
        frozenset({
            "rendered_frames", "hazard_visible_frames", "hazard_phases",
            *CONTINUITY_DEFECT_FIELDS,
        }),
        "rendered-continuity metrics",
    )
    require(require_integer(metrics["rendered_frames"],
                            "rendered-continuity rendered_frames") >= 120,
            "rendered-continuity coverage is shorter than 120 frames")
    require(require_integer(metrics["hazard_visible_frames"],
                            "rendered-continuity hazard_visible_frames") >= 60,
            "rendered-continuity hazard coverage is shorter than 60 frames")
    require(require_integer(metrics["hazard_phases"],
                            "rendered-continuity hazard_phases") >= 4,
            "rendered-continuity evidence covers fewer than four phases")
    failures = require_exact_keys(
        receipt.get("failure_frames"), CONTINUITY_DEFECT_FIELDS,
        "rendered-continuity failure frames",
    )
    for field in CONTINUITY_DEFECT_FIELDS:
        require(require_integer(metrics[field],
                                f"rendered-continuity {field}") == 0,
                f"rendered-continuity {field} is not zero")
        require(failures[field] == [],
                f"rendered-continuity {field} has failure-frame evidence")
    return {
        "receipt": str(resolved),
        "receipt_sha256": sha256(resolved),
        "rom_sha256": candidate_sha256,
        "oracle": receipt["oracle"],
        "metrics": metrics,
        "state_sha256": receipt["state_sha256"],
        "state_receipt_sha256": receipt["state_receipt_sha256"],
        "hazard_menu_receipt_sha256": receipt[
            "hazard_menu_receipt_sha256"
        ],
        "mutation_controls": mutation_controls,
    }


def validate_speed_receipt(
    path: Path,
    candidate: Path,
    candidate_sha256: str,
    main_manifest: Path,
    stage2_manifest: Path,
    stage7_state_receipt: Path,
) -> dict[str, Any]:
    resolved = path.resolve()
    receipt = load_json(resolved, "release speed qualification receipt")
    require_exact_keys(receipt, SPEED_RECEIPT_KEYS,
                       "release speed qualification receipt")
    require(receipt.get("schema") == SPEED_SCHEMA,
            "wrong release-speed receipt schema")
    require(receipt.get("status") == SPEED_STATUS,
            "release-speed qualification did not pass the exact policy")
    require(receipt.get("candidate") == str(candidate.resolve()),
            "release-speed receipt names another candidate")
    require(receipt.get("candidate_sha256") == candidate_sha256,
            "release-speed receipt targets another candidate")
    require(
        isinstance(receipt.get("original_rom_sha256"), str)
        and SHA256_PATTERN.fullmatch(receipt["original_rom_sha256"]) is not None,
        "release-speed receipt has an invalid original-ROM identity",
    )

    measurement = require_exact_keys(
        receipt.get("measurement"), SPEED_MEASUREMENT_KEYS,
        "release-speed measurement policy",
    )
    require(measurement.get("input_mode") == "right"
            and measurement.get("frames") == 2800,
            "release-speed route or measurement length changed")
    require(measurement.get("strict_ratio_floor") == STRICT_SPEED_FLOOR
            and measurement.get("strict_ratio_ceiling") == STRICT_SPEED_CEILING,
            "release-speed strict target band changed")
    require(measurement.get("named_stage_operator_release_floor")
            == NAMED_RELEASE_FLOOR,
            "release-speed named-stage operator floor is not exactly 0.95")
    require(measurement.get("named_floor_stages")
            == sorted(NAMED_RELEASE_STAGES),
            "release-speed named-stage floor coverage changed")
    require(measurement.get("named_floors_are_per_stage_only") is True
            and measurement.get("strict_target_misses_remain_explicit") is True,
            "release-speed named-stage classification policy changed")
    require(measurement.get("strict_fixed_input_stages") == [6],
            "release-speed strict fixed-input stage coverage changed")
    require(
        measurement.get("stage7_world_position_ratio_floor")
        == STAGE7_SPEED_FLOOR
        and measurement.get("stage7_world_position_ratio_ceiling")
        == STAGE7_SPEED_CEILING
        and measurement.get("stage7_fixed_frame_route_is_diagnostic_only")
        is True,
        "release-speed Stage-7 matched-work policy changed",
    )
    require(measurement.get("global_slowdown_waivers") is False
            and measurement.get("other_stage_slowdown_waivers") is False,
            "release-speed receipt permits a broad slowdown waiver")
    require(measurement.get("stages_covered_exactly_once")
            == [1, 2, 3, 4, 5, 6, 7],
            "release-speed stage coverage policy changed")

    profiles = require_exact_keys(
        receipt.get("profiles"),
        frozenset({
            "stages_1_3_4_5_6", "stage_2", "stage_7_world_position",
        }),
        "release-speed profiles",
    )
    main_profile = require_exact_keys(
        profiles.get("stages_1_3_4_5_6"),
        frozenset({
            "manifest", "manifest_sha256", "compiler_bank",
            "compiler_range", "accepted_slowdown_floor",
            "accepted_slow_stages",
        }),
        "release-speed main profile",
    )
    stage2_profile = require_exact_keys(
        profiles.get("stage_2"),
        frozenset({
            "manifest", "manifest_sha256", "compiler_bank",
            "compiler_range", "dma_command_addr", "expected_dma_mode",
            "accepted_slowdown_floor", "accepted_slow_stages",
        }),
        "release-speed Stage-2 profile",
    )
    stage7_profile = require_exact_keys(
        profiles.get("stage_7_world_position"),
        SPEED_STAGE7_PROFILE_KEYS,
        "release-speed Stage-7 world-position profile",
    )
    require(main_profile.get("manifest") == str(main_manifest.resolve())
            and main_profile.get("manifest_sha256") == sha256(main_manifest),
            "release-speed receipt does not bind the exact main manifest")
    require(main_profile.get("compiler_bank") == 0x16
            and main_profile.get("compiler_range") == [0x6C80, 0x7232],
            "release-speed main compiler profile changed")
    require(main_profile.get("accepted_slowdown_floor") is None
            and main_profile.get("accepted_slow_stages")
            == {str(stage): NAMED_RELEASE_FLOOR
                for stage in sorted(MAIN_RELEASE_STAGES)},
            "release-speed main profile lacks exact named-stage floors")
    require(stage2_profile.get("manifest") == str(stage2_manifest.resolve())
            and stage2_profile.get("manifest_sha256") == sha256(stage2_manifest),
            "release-speed receipt does not bind the exact Stage-2 manifest")
    require(stage2_profile.get("compiler_bank") == 0x15
            and stage2_profile.get("compiler_range") == [0x4C00, 0x582D]
            and stage2_profile.get("dma_command_addr") == 0x5816
            and stage2_profile.get("expected_dma_mode") == "hblank",
            "release-speed Stage-2 compiler/DMA profile changed")
    require(stage2_profile.get("accepted_slowdown_floor") is None
            and stage2_profile.get("accepted_slow_stages")
            == {"2": NAMED_RELEASE_FLOOR},
            "release-speed Stage-2 profile lacks its named release floor")

    main_source = load_json(main_manifest, "main release-speed manifest")
    stage2_source = load_json(stage2_manifest, "Stage-2 strict-speed manifest")
    require(receipt.get("tool_identity") == main_source.get("tool_identity")
            == stage2_source.get("tool_identity"),
            "release-speed receipt tool identity differs from its manifests")

    stage7_source = load_json(
        stage7_state_receipt, "Stage-7 world-position speed receipt"
    )
    expected_stage7 = speed_qualifier.validate_stage7_payload(
        stage7_source, candidate_sha256
    )
    require(
        stage7_profile == {
            "receipt": str(stage7_state_receipt.resolve()),
            "receipt_sha256": sha256(stage7_state_receipt),
            **expected_stage7,
            "input_identities": stage7_source["input_identities"],
        },
        "release-speed Stage-7 profile differs from revalidated evidence",
    )

    rows = receipt.get("rows")
    require(isinstance(rows, list) and len(rows) == 6,
            "release-speed fixed-input receipt does not cover six stages")
    require({row.get("stage") for row in rows} == set(range(1, 7)),
            "release-speed fixed-input receipt has incomplete stage coverage")
    classifications: dict[str, str] = {}
    ratios: dict[str, float] = {}
    for row in rows:
        require_exact_keys(row, SPEED_ROW_KEYS,
                           f"release-speed Stage {row.get('stage')} row")
        stage = require_integer(row["stage"], "release-speed stage",
                                minimum=1)
        original_hits = require_integer(
            row["original_main_loop_hits"],
            f"release-speed Stage {stage} original hits", minimum=1,
        )
        candidate_hits = require_integer(
            row["candidate_main_loop_hits"],
            f"release-speed Stage {stage} candidate hits", minimum=1,
        )
        ratio = candidate_hits / original_hits
        recorded_ratio = require_number(
            row["ratio_exact"], f"release-speed Stage {stage} ratio"
        )
        require(abs(recorded_ratio - ratio) < 1e-15,
                f"release-speed Stage {stage} ratio is not recomputable")
        require(row["ratio_percent"] == round(100.0 * ratio, 6),
                f"release-speed Stage {stage} percentage is not recomputable")
        strict_target_met = (
            abs(1.0 - ratio) <= (1.0 - STRICT_SPEED_FLOOR) + 1e-9
        )
        has_release_floor = stage in NAMED_RELEASE_STAGES
        accepted_release_deviation = (
            has_release_floor
            and not strict_target_met
            and NAMED_RELEASE_FLOOR - 1e-9 <= ratio < 1.0
        )
        expected_floor = NAMED_RELEASE_FLOOR if has_release_floor else None
        require(row["accepted_slowdown_floor"]
                == expected_floor,
                f"release-speed Stage {stage} effective floor changed")
        require(row["target_met"] is strict_target_met,
                f"release-speed Stage {stage} strict target is misclassified")
        require(row["accepted_slowdown_deviation"]
                is accepted_release_deviation,
                f"release-speed Stage {stage} floor use is misclassified")
        require(row["throughput_accepted"] is True,
                f"release-speed Stage {stage} throughput was not accepted")
        expected_classification = (
            STRICT_SPEED_CLASSIFICATION if strict_target_met
            else NAMED_RELEASE_CLASSIFICATION
        )
        require(row["qualification_class"] == expected_classification,
                f"release-speed Stage {stage} class is not explicit")
        for key in ("deterministic_replay", "route_coverage_ok", "scene_ok"):
            require(row[key] is True,
                    f"release-speed Stage {stage} {key} did not pass")
        lower_bound = (
            NAMED_RELEASE_FLOOR if has_release_floor else STRICT_SPEED_FLOOR
        )
        require(lower_bound <= ratio <= STRICT_SPEED_CEILING,
                f"release-speed Stage {stage} is outside its exact band")
        ratios[str(stage)] = ratio
        classifications[str(stage)] = expected_classification

    ratios["7"] = expected_stage7["ratio_exact"]
    classifications["7"] = STAGE7_SPEED_CLASSIFICATION

    mutation_controls = require_exact_true_checks(
        receipt.get("mutation_controls"), SPEED_MUTATION_CONTROLS,
        "release-speed mutation controls",
    )
    return {
        "receipt": str(resolved),
        "receipt_sha256": sha256(resolved),
        "rom_sha256": candidate_sha256,
        "status": receipt["status"],
        "stage_ratios": ratios,
        "stage_classifications": classifications,
        "mutation_controls": mutation_controls,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("rom", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--main-speed-manifest", type=Path)
    parser.add_argument("--stage2-speed-manifest", type=Path)
    parser.add_argument("--stage7-state-receipt", type=Path)
    parser.add_argument("--scene0b-live-receipt", type=Path)
    parser.add_argument("--natural-timeout", type=float, default=90.0)
    parser.add_argument("--menu-window-timeout", type=float, default=120.0)
    parser.add_argument("--title-timeout", type=float, default=60.0)
    parser.add_argument("--stage-card-timeout", type=float, default=300.0)
    parser.add_argument("--north-timeout", type=float, default=240.0)
    parser.add_argument("--pickup-state-timeout", type=float, default=120.0)
    parser.add_argument("--pickup-host-timeout", type=float, default=480.0)
    parser.add_argument("--no-bleed-timeout", type=float, default=180.0)
    parser.add_argument("--state-timeout", type=float, default=120.0)
    parser.add_argument("--hazard-menu-timeout", type=float, default=180.0)
    args = parser.parse_args()

    candidate = args.rom.resolve()
    if not candidate.is_file():
        parser.error(f"ROM is missing: {candidate}")
    try:
        output = scratch_output(args.output)
    except NotReady as error:
        parser.error(str(error))

    candidate_sha256 = sha256(candidate)
    receipt_path = output / "receipt.json"
    rollup: dict[str, Any] = {
        "schema": SCHEMA,
        "status": "NOT_READY",
        "candidate": str(candidate),
        "candidate_sha256": candidate_sha256,
        "output": str(output),
        "gates": {},
        "reported_issue_coverage": {},
        "failures": [],
    }
    write_rollup(receipt_path, rollup)

    current_gate = "preflight"
    try:
        rollup["tool_identity"] = tool_identity()
        require(args.natural_timeout > 5.0,
                "--natural-timeout must be greater than 5 seconds")
        require(args.menu_window_timeout > 10.0,
                "--menu-window-timeout must be greater than 10 seconds")
        require(args.title_timeout > 10.0,
                "--title-timeout must be greater than 10 seconds")
        require(args.stage_card_timeout > 30.0,
                "--stage-card-timeout must be greater than 30 seconds")
        require(args.north_timeout > 30.0,
                "--north-timeout must be greater than 30 seconds")
        require(args.pickup_state_timeout > 10.0,
                "--pickup-state-timeout must be greater than 10 seconds")
        require(args.pickup_host_timeout > 30.0,
                "--pickup-host-timeout must be greater than 30 seconds")
        require(args.no_bleed_timeout > 90.0,
                "--no-bleed-timeout must be greater than 90 seconds")
        require(args.state_timeout > 10.0,
                "--state-timeout must be greater than 10 seconds")
        require(args.hazard_menu_timeout > 10.0,
                "--hazard-menu-timeout must be greater than 10 seconds")
        require(args.main_speed_manifest is not None,
                "--main-speed-manifest is required for READY")
        require(args.stage2_speed_manifest is not None,
                "--stage2-speed-manifest is required for READY")
        require(args.stage7_state_receipt is not None,
                "--stage7-state-receipt is required for READY")
        require(args.scene0b_live_receipt is not None,
                "--scene0b-live-receipt is required for READY")
        # Missing inputs are rejected before any emulator-backed verifier.
        for path, label in (
            (args.main_speed_manifest, "main release-speed manifest"),
            (args.stage2_speed_manifest, "Stage-2 strict-speed manifest"),
            (args.stage7_state_receipt,
             "Stage-7 world-position speed receipt"),
            (args.scene0b_live_receipt,
             "live scene-$0B captured-state/menu receipt"),
        ):
            require(path.resolve().is_file(), f"{label} is missing: {path}")
        for path, label, expected_slow_stages in (
            (args.main_speed_manifest.resolve(), "main release-speed manifest",
             {str(stage): NAMED_RELEASE_FLOOR
              for stage in sorted(MAIN_RELEASE_STAGES)}),
            (args.stage2_speed_manifest.resolve(),
             "Stage-2 strict-speed manifest",
             {"2": NAMED_RELEASE_FLOOR}),
        ):
            manifest = load_json(path, label)
            require(manifest.get("schema") == "penta-stage-speed-matrix-v2",
                    f"{label} has the wrong schema")
            require(manifest.get("status") == "pass"
                    and manifest.get("failures") == [],
                    f"{label} is not a passing speed matrix")
            require(manifest.get("dx_rom_sha256") == candidate_sha256,
                    f"{label} targets another candidate")
            require(manifest.get("mode") == "right"
                    and manifest.get("frames") == 2800
                    and manifest.get("tolerance") == 0.01
                    and manifest.get("target_ratio_floor")
                    == STRICT_SPEED_FLOOR
                    and manifest.get("target_ratio_ceiling")
                    == STRICT_SPEED_CEILING,
                    f"{label} has the wrong measurement policy")
            require(manifest.get("accepted_slowdown_floor") is None,
                    f"{label} carries a forbidden global slowdown waiver")
            require(manifest.get("accepted_slow_stages")
                    == expected_slow_stages,
                    f"{label} has the wrong per-stage slowdown policy")
        speed_qualifier.validate_stage7_payload(
            load_json(
                args.stage7_state_receipt.resolve(),
                "Stage-7 world-position speed receipt",
            ),
            candidate_sha256,
        )

        current_gate = "stage1_menu_race_static_exhaustive"
        menu_race_receipt = output / "menu-race-static.json"
        command_evidence = run_checked_verifier(
            label=current_gate,
            command=[
                sys.executable, str(MENU_RACE_VERIFIER), str(candidate),
                "--output", str(menu_race_receipt),
            ],
            log=output / "menu-race-static.log",
            timeout=30.0,
            candidate=candidate,
            candidate_sha256=candidate_sha256,
        )
        rollup["gates"][current_gate] = {
            "status": "PASS", **command_evidence,
            **validate_menu_race_receipt(menu_race_receipt, candidate_sha256),
        }
        write_rollup(receipt_path, rollup)

        current_gate = "cold_and_returned_title_nightfall"
        title_output = output / "title-nightfall-mgba"
        command_evidence = run_checked_verifier(
            label=current_gate,
            command=[
                sys.executable, str(TITLE_NIGHTFALL_VERIFIER), str(candidate),
                "--expected-sha256", candidate_sha256,
                "--output", str(title_output),
                "--timeout", str(args.title_timeout),
            ],
            log=output / "title-nightfall-mgba.log",
            timeout=args.title_timeout + 15.0,
            candidate=candidate,
            candidate_sha256=candidate_sha256,
        )
        title_receipt = title_output / "receipt.json"
        rollup["gates"][current_gate] = {
            "status": "PASS", **command_evidence,
            **validate_title_nightfall_receipt(
                title_receipt, candidate, candidate_sha256
            ),
        }
        write_rollup(receipt_path, rollup)

        current_gate = "captured_scene0b_transition_menu"
        scene0b_receipt = output / "scene0b-captured-menu.json"
        command_evidence = run_checked_verifier(
            label=current_gate,
            command=[
                sys.executable, str(SCENE0B_BINDER), str(candidate),
                "--live-receipt", str(args.scene0b_live_receipt.resolve()),
                "--output", str(scene0b_receipt),
            ],
            log=output / "scene0b-captured-menu.log",
            timeout=30.0,
            candidate=candidate,
            candidate_sha256=candidate_sha256,
        )
        rollup["gates"][current_gate] = {
            "status": "PASS", **command_evidence,
            **validate_scene0b_receipt(
                scene0b_receipt, candidate, candidate_sha256,
                args.scene0b_live_receipt.resolve(),
            ),
        }
        write_rollup(receipt_path, rollup)

        current_gate = "stage1_tilemap_publication_oracle"
        tilemap_output = output / "stage1-tilemap-publication"
        command_evidence = run_checked_verifier(
            label=current_gate,
            command=[
                sys.executable, str(TILEMAP_VERIFIER), str(candidate),
                "--state", TILEMAP_RELEASE_STATES[0],
                "--state", TILEMAP_RELEASE_STATES[1],
                "--state", TILEMAP_RELEASE_STATES[2],
                "--frames", str(TILEMAP_RELEASE_FRAMES),
                "--timeout", str(TILEMAP_RELEASE_TIMEOUT_SECONDS),
                "--output", str(tilemap_output),
            ],
            log=output / "stage1-tilemap-publication.log",
            timeout=210.0,
            candidate=candidate,
            candidate_sha256=candidate_sha256,
        )
        tilemap_receipt = tilemap_output / "receipt.json"
        rollup["gates"][current_gate] = {
            "status": "PASS", **command_evidence,
            **validate_tilemap_receipt(
                tilemap_receipt, candidate, candidate_sha256,
            ),
        }
        write_rollup(receipt_path, rollup)

        current_gate = "natural_blank_sram_menu_and_art_loader"
        natural_report = output / "natural-menu" / "report.txt"
        natural_report.parent.mkdir()
        command_evidence = run_checked_verifier(
            label=current_gate,
            command=[
                sys.executable, str(NATURAL_VERIFIER), str(candidate),
                "--blank-sram", "--output", str(natural_report),
            ],
            log=output / "natural-menu.log",
            timeout=args.natural_timeout,
            candidate=candidate,
            candidate_sha256=candidate_sha256,
        )
        rollup["gates"][current_gate] = {
            "status": "PASS", **command_evidence,
            **validate_natural_report(
                natural_report, candidate, candidate_sha256
            ),
        }
        write_rollup(receipt_path, rollup)

        current_gate = "natural_room03_active_scroll_menu"
        scrolled_report = output / "natural-menu-scrolled" / "report.txt"
        scrolled_report.parent.mkdir()
        command_evidence = run_checked_verifier(
            label=current_gate,
            command=[
                sys.executable, str(NATURAL_VERIFIER), str(candidate),
                "--blank-sram", "--output", str(scrolled_report),
                "--frames", "1600",
                "--open-frame", "1200",
                "--close-frame", "1380",
                "--move", "right",
                "--move-start", "700",
                "--move-end", "1250",
                "--expected-room", "03",
            ],
            log=output / "natural-menu-scrolled.log",
            timeout=args.natural_timeout,
            candidate=candidate,
            candidate_sha256=candidate_sha256,
        )
        rollup["gates"][current_gate] = {
            "status": "PASS", **command_evidence,
            **validate_natural_report(
                scrolled_report, candidate, candidate_sha256,
                expected_room=0x03,
            ),
            "route": {
                "movement": "right@700-1249",
                "menu": "SELECT@1200-1205 while movement remains active",
                "close": "SELECT@1380-1385",
            },
        }
        write_rollup(receipt_path, rollup)

        current_gate = "native_select_menu_window_exact"
        menu_window_report = output / "native-menu-window" / "report.txt"
        menu_window_report.parent.mkdir()
        command_evidence = run_checked_verifier(
            label=current_gate,
            command=[
                sys.executable, str(MENU_WINDOW_VERIFIER), str(candidate),
                "--output", str(menu_window_report),
                "--frames", str(MENU_WINDOW_FRAMES),
                "--key", "select",
                "--open-frame", str(MENU_WINDOW_OPEN_FRAME),
                "--close-frame", str(MENU_WINDOW_CLOSE_FRAME),
                "--move", "none",
                "--fire-every", "0",
                "--inject-stale-frame", "-1",
                "--force-map-alias-frame", "-1",
                "--force-map-commit-frame", str(MENU_WINDOW_CLOSE_FRAME),
            ],
            log=output / "native-menu-window.log",
            timeout=args.menu_window_timeout,
            candidate=candidate,
            candidate_sha256=candidate_sha256,
        )
        rollup["gates"][current_gate] = {
            "status": "PASS", **command_evidence,
            **validate_menu_window_report(
                menu_window_report, candidate, candidate_sha256
            ),
        }
        write_rollup(receipt_path, rollup)

        current_gate = "blank_sram_stage1_handoff_no_cyan_partial_flash"
        stage_card_output = output / "stage-card"
        command_evidence = run_checked_verifier(
            label=current_gate,
            command=[
                sys.executable, str(STAGE_CARD_VERIFIER), str(candidate),
                "--output", str(stage_card_output),
            ],
            log=output / "stage-card.log",
            timeout=args.stage_card_timeout,
            candidate=candidate,
            candidate_sha256=candidate_sha256,
        )
        stage_card_receipt = stage_card_output / "receipt.json"
        rollup["gates"][current_gate] = {
            "status": "PASS", **command_evidence,
            **validate_stage_card_receipt(
                stage_card_receipt, candidate_sha256
            ),
        }
        write_rollup(receipt_path, rollup)

        current_gate = "independent_room01_wall_north_replay"
        north_output = output / "room01-north"
        command_evidence = run_checked_verifier(
            label=current_gate,
            command=[
                sys.executable, str(NORTH_VERIFIER), str(candidate),
                "--target-camera", "0x03A4",
                "--target-room", "1",
                "--target-settle", "60",
                "--frames", "3000",
                "--play-frames", "2400",
                "--dynamic-prefix", "0",
                "--target-only",
                "--output", str(north_output),
            ],
            log=output / "room01-north.log",
            timeout=args.north_timeout,
            candidate=candidate,
            candidate_sha256=candidate_sha256,
        )
        north_receipt = north_output / "receipt.json"
        rollup["gates"][current_gate] = {
            "status": "PASS", **command_evidence,
            **validate_north_receipt(
                north_receipt, candidate, candidate_sha256
            ),
        }
        write_rollup(receipt_path, rollup)

        current_gate = "stage1_current_pickup_state"
        pickup_state_output = output / "stage1-current-pickup-state"
        command_evidence = run_checked_verifier(
            label=current_gate,
            command=[
                sys.executable, str(PICKUP_STATE_GENERATOR), str(candidate),
                "--output", str(pickup_state_output),
            ],
            log=output / "pickup-state.log",
            timeout=args.pickup_state_timeout,
            candidate=candidate,
            candidate_sha256=candidate_sha256,
        )
        pickup_state_receipt = pickup_state_output / "receipt.json"
        pickup_state = pickup_state_output / "current-pickup.ss0"
        pickup_state_evidence = validate_pickup_state_receipt(
            pickup_state_receipt, pickup_state, candidate, candidate_sha256,
        )
        rollup["gates"][current_gate] = {
            "status": "PASS", **command_evidence, **pickup_state_evidence,
        }
        write_rollup(receipt_path, rollup)

        current_gate = "stage1_current_pickup_host_palettes"
        pickup_host_output = output / "stage1-current-pickup-host-palettes"
        command_evidence = run_checked_verifier(
            label=current_gate,
            command=[
                sys.executable, str(PICKUP_HOST_VERIFIER), str(candidate),
                "--state", str(pickup_state),
                "--state-receipt", str(pickup_state_receipt),
                "--output", str(pickup_host_output),
            ],
            log=output / "pickup-host.log",
            timeout=args.pickup_host_timeout,
            candidate=candidate,
            candidate_sha256=candidate_sha256,
        )
        pickup_host_receipt = pickup_host_output / "receipt.json"
        rollup["gates"][current_gate] = {
            "status": "PASS", **command_evidence,
            **validate_pickup_host_receipt(
                pickup_host_receipt,
                pickup_state_receipt,
                pickup_state_evidence,
                candidate,
                candidate_sha256,
            ),
        }
        write_rollup(receipt_path, rollup)

        current_gate = "natural_stage1_pickup_temporal_raster"
        no_bleed_output = output / "natural-pickup-temporal-raster"
        command_evidence = run_checked_verifier(
            label=current_gate,
            command=[
                sys.executable, str(STAGE1_NO_BLEED_VERIFIER),
                str(candidate),
                "--frames", str(NO_BLEED_FRAMES),
                "--mode", NO_BLEED_MODE,
                "--output", str(no_bleed_output),
            ],
            log=output / "natural-pickup-temporal-raster.log",
            timeout=args.no_bleed_timeout,
            candidate=candidate,
            candidate_sha256=candidate_sha256,
        )
        no_bleed_receipt = no_bleed_output / "receipt.json"
        rollup["gates"][current_gate] = {
            "status": "PASS", **command_evidence,
            **validate_no_bleed_receipt(
                no_bleed_receipt, candidate, candidate_sha256
            ),
        }
        write_rollup(receipt_path, rollup)

        current_gate = "rom_owned_natural_hazard_state"
        state_output = output / "hazard-state"
        state_output.mkdir()
        command_evidence = run_checked_verifier(
            label=current_gate,
            command=[
                sys.executable, str(STATE_GENERATOR), str(candidate),
                "--output", str(state_output),
                "--min-hazard-cells", "40", "--min-tooth-cells", "10",
                "--timeout", str(min(args.state_timeout - 5.0, 90.0)),
            ],
            log=output / "hazard-state.log",
            timeout=args.state_timeout,
            candidate=candidate,
            candidate_sha256=candidate_sha256,
        )
        state_receipt = state_output / "receipt.json"
        state = state_output / "stage1-hazard.ss0"
        state_evidence = validate_state_receipt(
            state_receipt, state, candidate_sha256
        )
        rollup["gates"][current_gate] = {
            "status": "PASS", **command_evidence, **state_evidence,
        }
        write_rollup(receipt_path, rollup)

        current_gate = "rom_owned_stationary_hazard_menu_replay"
        replay_output = output / "hazard-menu"
        command_evidence = run_checked_verifier(
            label=current_gate,
            command=[
                sys.executable, str(HAZARD_MENU_VERIFIER), str(candidate),
                "--state", str(state),
                "--state-receipt", str(state_receipt),
                "--output", str(replay_output),
                "--screenshot-interval", "1",
            ],
            log=output / "hazard-menu.log",
            timeout=args.hazard_menu_timeout,
            candidate=candidate,
            candidate_sha256=candidate_sha256,
        )
        replay_receipt = replay_output / "receipt.json"
        replay_evidence = validate_hazard_menu_receipt(
            replay_receipt, state_evidence, candidate_sha256
        )
        rollup["gates"][current_gate] = {
            "status": "PASS", **command_evidence, **replay_evidence,
        }
        write_rollup(receipt_path, rollup)

        current_gate = "independent_rendered_continuity"
        continuity_receipt = output / "rendered-continuity.json"
        command_evidence = run_checked_verifier(
            label=current_gate,
            command=[
                sys.executable, str(CONTINUITY_VERIFIER), str(candidate),
                "--state-receipt", str(state_receipt),
                "--hazard-menu-receipt", str(replay_receipt),
                "--frames-dir", str(replay_output / "replay-1"),
                "--frames-dir", str(replay_output / "replay-2"),
                "--output", str(continuity_receipt),
            ],
            log=output / "rendered-continuity.log",
            timeout=90.0,
            candidate=candidate,
            candidate_sha256=candidate_sha256,
        )
        continuity_evidence = validate_continuity_receipt(
            continuity_receipt, candidate_sha256,
            state_evidence, replay_evidence,
        )
        rollup["gates"][current_gate] = {
            "status": "PASS", **command_evidence, **continuity_evidence,
        }
        write_rollup(receipt_path, rollup)

        current_gate = "release_speed_named_stages_95_stage6_strict99"
        speed_receipt = output / "release-speed.json"
        command_evidence = run_checked_verifier(
            label=current_gate,
            command=[
                sys.executable, str(SPEED_QUALIFIER),
                "--candidate", str(candidate),
                "--main-manifest", str(args.main_speed_manifest.resolve()),
                "--stage2-manifest", str(args.stage2_speed_manifest.resolve()),
                "--stage7-state-receipt",
                str(args.stage7_state_receipt.resolve()),
                "--output", str(speed_receipt),
            ],
            log=output / "release-speed.log",
            timeout=30.0,
            candidate=candidate,
            candidate_sha256=candidate_sha256,
        )
        rollup["gates"][current_gate] = {
            "status": "PASS", **command_evidence,
            **validate_speed_receipt(
                speed_receipt, candidate, candidate_sha256,
                args.main_speed_manifest.resolve(),
                args.stage2_speed_manifest.resolve(),
                args.stage7_state_receipt.resolve(),
            ),
        }

        current_gate = "tool_identity_reverification"
        assert_candidate_unchanged(candidate, candidate_sha256)
        reverified_tool_identity = tool_identity()
        require(
            reverified_tool_identity == rollup["tool_identity"],
            "reporting interceptor or a checked tool changed during the run",
        )
        rollup["gates"][current_gate] = {
            "status": "PASS",
            "all_tool_hashes_unchanged": True,
            "tool_identity": reverified_tool_identity,
        }
        assert_candidate_unchanged(candidate, candidate_sha256)
        rollup["reported_issue_coverage"] = reported_issue_coverage(
            rollup["gates"]
        )
        rollup["status"] = "READY"
        rollup["failures"] = []
        write_rollup(receipt_path, rollup)
        print(f"READY: exact Stage-1 reported-regression gates passed: {candidate}")
        print(f"Receipt: {receipt_path}")
        return 0
    except KeyboardInterrupt:
        process_log = output / (
            f"{current_gate}-keyboard-interrupt-process-check.log"
        )
        process_check = run_read_only_process_check(process_log)
        reason = (
            "reporting interceptor was interrupted; "
            f"read-only process check: {process_log} "
            f"(exit {process_check['exit_status']})"
        )
        rollup["status"] = "NOT_READY"
        rollup["interrupt_process_check"] = process_check
        rollup["failures"].append({
            "gate": current_gate,
            "reason": reason,
        })
        if current_gate not in rollup["gates"]:
            rollup["gates"][current_gate] = {
                "status": "FAIL", "reason": reason
            }
        write_rollup(receipt_path, rollup)
        print(f"NOT_READY: {current_gate}: {reason}")
        print(f"Receipt: {receipt_path}")
        return 1
    except (
        NotReady, OSError, KeyError, TypeError, ValueError,
        subprocess.SubprocessError,
    ) as error:
        rollup["status"] = "NOT_READY"
        rollup["failures"].append({"gate": current_gate, "reason": str(error)})
        if current_gate not in rollup["gates"]:
            rollup["gates"][current_gate] = {
                "status": "FAIL", "reason": str(error)
            }
        write_rollup(receipt_path, rollup)
        print(f"NOT_READY: {current_gate}: {error}")
        print(f"Receipt: {receipt_path}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
