from __future__ import annotations

import copy
import hashlib
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock
import zlib

from PIL import Image


ROOT = Path(__file__).resolve().parents[1]
DIAGNOSTICS = ROOT / "scripts" / "diagnostics"
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(DIAGNOSTICS))

import verify_stage1_reported_regressions_ready as ready  # noqa: E402
import deploy_pocket_rom as deploy  # noqa: E402
import verify_stage1_north_integrity as north  # noqa: E402
import verify_stage1_scene0b_captured_menu_receipt as scene0b  # noqa: E402
import verify_stage1_menu_race_static as menu_race  # noqa: E402
import build_stage1_selector_latch_cold_init_r317 as r317  # noqa: E402
from normalize_mgba_state_pc import retarget_rom_identity  # noqa: E402
from stage1_hazard_art import (  # noqa: E402
    compile_stage1_hazard_terminal_variants,
    load_stage1_hazard_config,
)


class ReadyOracleWiringTests(unittest.TestCase):
    def setUp(self) -> None:
        (ROOT / "tmp").mkdir(exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(
            prefix="stage1-ready-wiring-", dir=ROOT / "tmp"
        )
        self.root = Path(self.temp.name)
        self.candidate = self.root / "candidate.gb"
        candidate = r317.DEFAULT_OUTPUT.read_bytes()
        self.assertEqual(
            hashlib.sha256(candidate).hexdigest(),
            r317.EXPECTED_CANDIDATE_SHA256,
        )
        config = load_stage1_hazard_config()
        stock = (ROOT / "rom/Penta Dragon (J).gb").read_bytes()
        terminal_variants = compile_stage1_hazard_terminal_variants(
            stock, config
        )
        candidate = bytearray(candidate)
        for tile, variant in terminal_variants.items():
            start = config.source_offset + tile * 16
            candidate[start:start + 16] = variant
        # The native menu-Window validator now authenticates the exact r364
        # close boundary in addition to its receipt.  Install that reviewed
        # byte sequence in this synthetic all-oracle candidate.
        candidate[
            ready.menu_window_oracle.MENU_EXIT_OFFSET:
            ready.menu_window_oracle.MENU_EXIT_OFFSET
            + len(ready.menu_window_oracle.MENU_EXIT_ATOMIC_JUMP)
        ] = ready.menu_window_oracle.MENU_EXIT_ATOMIC_JUMP
        candidate[
            ready.menu_window_oracle.MENU_WRAPPER_TAIL_OFFSET:
            ready.menu_window_oracle.MENU_WRAPPER_TAIL_OFFSET
            + len(ready.menu_window_oracle.MENU_WRAPPER_TAIL_ATOMIC)
        ] = ready.menu_window_oracle.MENU_WRAPPER_TAIL_ATOMIC
        candidate[
            ready.menu_window_oracle.MENU_ATOMIC_EXIT_OFFSET:
            ready.menu_window_oracle.MENU_ATOMIC_EXIT_OFFSET
            + len(ready.menu_window_oracle.MENU_ATOMIC_EXIT)
        ] = ready.menu_window_oracle.MENU_ATOMIC_EXIT
        candidate = bytes(candidate)
        self.canonical_lut = candidate[
            scene0b.STAGE1_LUT_OFFSET:scene0b.STAGE1_LUT_OFFSET + 0x100
        ]
        self.assertEqual(
            hashlib.sha256(self.canonical_lut).hexdigest(),
            scene0b.STAGE1_LUT_SHA256,
        )
        self.candidate.write_bytes(candidate)
        self.candidate_sha = hashlib.sha256(
            self.candidate.read_bytes()
        ).hexdigest()

    def test_stop_hook_and_gate_are_retired(self) -> None:
        self.assertFalse((ROOT / ".codex" / "hooks.json").exists())
        self.assertFalse((ROOT / ".codex" / "hooks" / "stage1_ready_stop.py").exists())
        self.assertFalse((ROOT / ".codex" / "stage1-ready-gate.json").exists())

    def tearDown(self) -> None:
        self.temp.cleanup()

    @staticmethod
    def wall_oracle() -> dict:
        return {
            "schema": "penta-stage1-room01-wall-oracle-v1",
            "room01": {
                "selector": ready.ROOM01_WALL_SELECTOR,
                "minimum_records": 3,
                "records": 3,
                "gameplay_frames": [1065, 1066, 1067],
                "reviewed_cells_per_record": 64,
                "checked_cell_instances": 192,
                "expected_attr": 6,
                "tile_mismatches": 0,
                "attr_mismatches": 0,
                "first_mismatch": None,
                "exact": True,
            },
            "room05_patterned_floor_control": {
                "selector": ready.ROOM05_FLOOR_SELECTOR,
                "minimum_records": 2,
                "records": 2,
                "gameplay_frames": [1, 2],
                "patterned_floor_tile_ids": ready.ROOM05_PATTERNED_IDS,
                "observed_patterned_tile_ids": [0x2C, 0x2D, 0x3C],
                "observed_patterned_cells": 6,
                "expected_attr": 0,
                "tile_mismatches": 0,
                "control_attr_mismatches": 0,
                "patterned_attr_mismatches": 0,
                "first_mismatch": None,
                "exact": True,
            },
            "fingerprint_sha256": "a" * 64,
            "exact": True,
        }

    def north_receipt(self) -> dict:
        oracle = self.wall_oracle()
        baseline = ROOT / "rom/Penta Dragon (J).gb"
        candidate_publication = north.detect_publication_boundary(
            self.candidate.read_bytes()
        )
        baseline_publication = north.detect_publication_boundary(
            baseline.read_bytes()
        )

        def owner_report(
            mode: str, publication: dict[str, object]
        ) -> dict:
            cgb = mode == "cgb"
            return {
                "trajectory_schema": north.TRAJECTORY_SCHEMA,
                "rom_mode": mode,
                "room_source": "FFE5-at-bank1:42A7",
                "promotion_boundary": (
                    f"fixed-bank:{publication['publication_pc_hex']}"
                    "-LCDC-write"
                ),
                "publication": publication,
                "counters": {
                    "map_owner_arm_events": 3 if cgb else 0,
                    "map_owner_publications": 2 if cgb else 0,
                    "map_owner_reused_commits": 1 if cgb else 0,
                    "map_owner_superseded_arms": 0,
                    "map_owner_invalid_arms": 0,
                    "map_owner_invalid_commits": 0,
                    "map_owner_missing_commits": 0,
                    "map_owner_missing_trajectory_frames": 0,
                    "map_owner_invalid_trajectory_frames": 0,
                },
                "trace": "fixture",
                "errors": [],
                "exact": True,
            }

        return {
            "schema": ready.NORTH_SCHEMA,
            "status": "pass",
            "candidate_rom": str(self.candidate.resolve()),
            "candidate_sha256": self.candidate_sha,
            "baseline_rom": str(baseline.resolve()),
            "baseline_sha256": ready.sha256(baseline),
            "input_route": "cold GAME START; hold UP; no gameplay memory writes",
            "gameplay_frames": 2400,
            "target_camera": 0x03A4,
            "target_room": 1,
            "target_settle_frames": 60,
            "dynamic_prefix_bytes": 0,
            "target_only_policy": True,
            "baseline": {
                "frames": "1505",
                "first_gameplay": "489",
                "native_gameplay_start": "523",
                "gameplay_frames": "1016",
                "native_gameplay_frames": "982",
            },
            "candidate": {
                "frames": "1509",
                "first_gameplay": "489",
                "native_gameplay_start": "523",
                "gameplay_frames": "1020",
                "native_gameplay_frames": "986",
            },
            "candidate_replay": {
                "frames": "1509",
                "first_gameplay": "489",
                "native_gameplay_start": "523",
                "gameplay_frames": "1020",
                "native_gameplay_frames": "986",
            },
            "gameplay_frame_lag": 4,
            "candidate_replay_exact": True,
            "candidate_replay_attributes_exact": True,
            "settled_final_state_ok": True,
            "reviewed_room01_wall_replay_exact": True,
            "reviewed_room01_wall_oracle_ok": True,
            "service_frame_presentations_exact": True,
            "candidate_attribute_trajectory_exact": True,
            "candidate_physical_page_ownership_exact": True,
            "physical_page_owner_reports_exact": True,
            "progress_route_geometry_exact": True,
            "full_route_geometry_maxima": {
                "world_state": 0,
                "world_progress": 0,
                "service_presentation": 0,
            },
            "full_route_geometry_differences_present": False,
            "full_route_geometry_worst_example": None,
            "progress_route_viewports_exact": True,
            "target_only_static_route_ok": True,
            "terrain_differences": 0,
            "world_template": {"exact_at_entry": True},
            "metatile_table": {"exact_at_entry": True},
            "candidate_settled_final_state": {"passed": True},
            "candidate_replay_settled_final_state": {"passed": True},
            "reviewed_wall_fixture": str(
                ready.ROOM01_WALL_FIXTURE.relative_to(ROOT)
            ),
            "reviewed_wall_fixture_sha256": ready.sha256(
                ready.ROOM01_WALL_FIXTURE
            ),
            "reviewed_room01_runtime_tile_attrs": (
                ready.ROOM01_RUNTIME_WALL_TILE_ATTRS
            ),
            "reviewed_room01_wall_oracle": oracle,
            "reviewed_room01_wall_replay_oracle": copy.deepcopy(oracle),
            "trajectory_schema": north.TRAJECTORY_SCHEMA,
            "baseline_physical_page_owner_report": owner_report(
                "dmg", baseline_publication
            ),
            "candidate_physical_page_owner_report": owner_report(
                "cgb", candidate_publication
            ),
            "candidate_replay_physical_page_owner_report": owner_report(
                "cgb", candidate_publication
            ),
            "full_route_viewport_integrity": {
                "reviewed_room01_wall_oracle": copy.deepcopy(oracle),
                "maximum_viewport_tile_differences": 0,
                "maximum_progress_viewport_tile_differences": 0,
                "maximum_service_viewport_tile_differences": 0,
                "candidate_attribute_integrity": {
                    "physical_page_ownership": {
                        "policy": (
                            "ffe5-at-bank1-42a7-promoted-at-exact-lcdc-store-v2"
                        ),
                        "exact": True,
                        "evidence_errors": [],
                    },
                },
            },
        }

    @staticmethod
    def trajectory_record(
        room: int,
        tile: int,
        attr: int,
        **overrides: int,
    ) -> dict:
        tiles = bytearray(21 * 19)
        attrs = bytearray(21 * 19)
        tiles[0] = tile
        attrs[0] = attr
        record = {
            "gameplay_frame": 1,
            "room": room,
            "camera": 1,
            "lcdc": 0x8B,
            "scx": 0,
            "scy": 0,
            "selector_c": 0x70,
            "selector_d": 0x03,
            "source": 0xC403,
            "scene": 2,
            "active": 1,
            "svbk": 1,
            "page_owner_status": north.OWNER_STATUS_CGB_OWNED,
            "page_owner_status_name": north.OWNER_STATUS_NAMES[
                north.OWNER_STATUS_CGB_OWNED
            ],
            "page_owner_room": room,
            "page_owner_epoch": 1,
            "page_owner_base": 0x9C00,
            "tiles": bytes(tiles),
            "attrs": bytes(attrs),
        }
        record.update(overrides)
        if "page_owner_base" not in overrides:
            record["page_owner_base"] = (
                0x9C00 if int(record["lcdc"]) & 0x08 else 0x9800
            )
        return record

    def display_room_handoff(self, published_attr: int = 0x06) -> list[dict]:
        return [
            self.trajectory_record(
                5, 0x24, 0x00, gameplay_frame=1, lcdc=0x83,
                selector_c=0x71, source=0xC413,
                page_owner_room=5, page_owner_epoch=1,
            ),
            self.trajectory_record(
                1, 0x24, 0x00, gameplay_frame=2, lcdc=0x8B,
                selector_c=0x71, source=0xC413,
                page_owner_room=5, page_owner_epoch=2,
            ),
            self.trajectory_record(
                1, 0x24, 0x00, gameplay_frame=3, lcdc=0x8B,
                selector_c=0x70, source=0xC403,
                page_owner_room=5, page_owner_epoch=2,
            ),
            self.trajectory_record(
                1, 0x24, published_attr, gameplay_frame=4, lcdc=0x83,
                selector_c=0x70, source=0xC403,
                page_owner_room=1, page_owner_epoch=3,
            ),
        ]

    def test_display_room_comes_from_selected_physical_page_owner(self) -> None:
        result = north.trajectory_attribute_integrity(
            self.display_room_handoff(),
            north.REVIEWED_WALL_CONTEXT,
            north.REVIEWED_WALL_TILE_CONTEXT,
        )
        self.assertTrue(result["exact"])
        ownership = result["physical_page_ownership"]
        self.assertTrue(ownership["exact"])
        self.assertEqual(ownership["evidence_errors"], [])
        transitions = ownership["owner_transitions"]
        self.assertEqual(len(transitions), 3)
        self.assertEqual(
            (transitions[1]["base"], transitions[1]["room"]),
            (0x9C00, 5),
        )
        self.assertEqual(
            (transitions[-1]["base"], transitions[-1]["room"]),
            (0x9800, 1),
        )

    def test_display_room_rejects_attrs_from_the_wrong_side_of_handoff(
        self,
    ) -> None:
        premature = self.display_room_handoff()
        premature[1] = self.trajectory_record(
            1, 0x24, 0x06, gameplay_frame=2, lcdc=0x8B,
            selector_c=0x71, source=0xC413,
            page_owner_room=5, page_owner_epoch=2,
        )
        result = north.trajectory_attribute_integrity(
            premature,
            north.REVIEWED_WALL_CONTEXT,
            north.REVIEWED_WALL_TILE_CONTEXT,
        )
        self.assertFalse(result["exact"])
        self.assertEqual(result["first_mismatch"]["room"], 1)
        self.assertEqual(result["first_mismatch"]["display_room"], 5)

        stale = north.trajectory_attribute_integrity(
            self.display_room_handoff(published_attr=0x00),
            north.REVIEWED_WALL_CONTEXT,
            north.REVIEWED_WALL_TILE_CONTEXT,
        )
        self.assertFalse(stale["exact"])
        self.assertEqual(stale["first_mismatch"]["display_room"], 1)

    def test_physical_page_owner_evidence_is_fail_closed(self) -> None:
        missing = self.display_room_handoff()
        missing[1].update({
            "page_owner_status": north.OWNER_STATUS_CGB_MISSING,
            "page_owner_status_name": north.OWNER_STATUS_NAMES[
                north.OWNER_STATUS_CGB_MISSING
            ],
            "page_owner_room": 0xFF,
            "page_owner_epoch": 0xFFFF,
        })
        result = north.trajectory_attribute_integrity(
            missing,
            north.REVIEWED_WALL_CONTEXT,
            north.REVIEWED_WALL_TILE_CONTEXT,
        )
        self.assertFalse(result["exact"])
        ownership = result["physical_page_ownership"]
        self.assertFalse(ownership["exact"])
        self.assertEqual(
            ownership["first_error"]["reason"], "cgb-missing"
        )

        malformed = self.display_room_handoff()
        malformed[2].pop("page_owner_epoch")
        result = north.trajectory_attribute_integrity(
            malformed,
            north.REVIEWED_WALL_CONTEXT,
            north.REVIEWED_WALL_TILE_CONTEXT,
        )
        self.assertFalse(result["exact"])
        self.assertEqual(
            result["physical_page_ownership"]["first_error"]["reason"],
            "missing-owner-fields",
        )

    def test_broad_runtime_model_uses_room_local_reviewed_wall_class(self) -> None:
        # These are the four mutable C600 entries used by the runtime-only
        # room-$01 repair.  The immutable ROM table remains $00, so the broad
        # route model must select the reviewed room-local $06 policy here.
        for tile in (0x24, 0x27, 0x30, 0x33):
            with self.subTest(room=1, tile=tile, attr=0x06):
                good_room01 = north.trajectory_attribute_integrity(
                    [self.trajectory_record(1, tile, 0x06)],
                    north.REVIEWED_WALL_CONTEXT,
                    north.REVIEWED_WALL_TILE_CONTEXT,
                )
                self.assertTrue(good_room01["exact"])
            with self.subTest(room=1, tile=tile, attr=0x00):
                bad_room01 = north.trajectory_attribute_integrity(
                    [self.trajectory_record(1, tile, 0x00)],
                    north.REVIEWED_WALL_CONTEXT,
                    north.REVIEWED_WALL_TILE_CONTEXT,
                )
                self.assertFalse(bad_room01["exact"])

            # Room $05 contains the same four IDs, but the room-$01 policy
            # must not bleed into it.  Its unchanged table expectation is $00.
            with self.subTest(room=5, tile=tile, attr=0x00):
                good_room05_same_id = north.trajectory_attribute_integrity(
                    [self.trajectory_record(5, tile, 0x00)],
                    north.REVIEWED_WALL_CONTEXT,
                    north.REVIEWED_WALL_TILE_CONTEXT,
                )
                self.assertTrue(good_room05_same_id["exact"])
            with self.subTest(room=5, tile=tile, attr=0x06):
                bad_room05_same_id = north.trajectory_attribute_integrity(
                    [self.trajectory_record(5, tile, 0x06)],
                    north.REVIEWED_WALL_CONTEXT,
                    north.REVIEWED_WALL_TILE_CONTEXT,
                )
                self.assertFalse(bad_room05_same_id["exact"])

        # Keep the independent room-$05 2A-2E/3A-3D patterned-floor class
        # control too; it does not depend on any room-$01 wall ID.
        good_room05 = north.trajectory_attribute_integrity(
            [self.trajectory_record(5, 0x2A, 0x00)],
            north.REVIEWED_WALL_CONTEXT,
            north.REVIEWED_WALL_TILE_CONTEXT,
        )
        self.assertTrue(good_room05["exact"])
        bad_room05 = north.trajectory_attribute_integrity(
            [self.trajectory_record(5, 0x2A, 0x06)],
            north.REVIEWED_WALL_CONTEXT,
            north.REVIEWED_WALL_TILE_CONTEXT,
        )
        self.assertFalse(bad_room05["exact"])

    def write_json(self, name: str, value: dict) -> Path:
        path = self.root / name
        path.write_text(json.dumps(value, indent=2) + "\n")
        return path

    def write_menu_window_report(
        self, name: str, **overrides: str
    ) -> Path:
        menu_lut, menu_mode = ready.menu_window_oracle.expected_window_lut(
            self.candidate.read_bytes()
        )
        report = {
            "frames": str(ready.MENU_WINDOW_FRAMES),
            "window_frames": "180",
            "bad_frames": "0",
            "window_frames_after_close": "0",
            "stale_injected": "0",
            "stale_scene": "native",
            "stale_window_frames_after_grace": "0",
            "worst_mismatches": "0",
            "map_alias_frames": "0",
            "forced_commit": "1",
            "forced_commit_protocol": (
                ready.menu_window_oracle.authenticate_commit_protocol(
                    self.candidate.read_bytes()
                )["name"]
            ),
            "forced_commit_consumed": "1",
            "post_close_selector_checked_frames": "116",
            "post_close_selector_alias_frames": "0",
            "post_close_hud_leak_frames": "0",
            "route_frame_limit": str(ready.MENU_WINDOW_FRAMES),
            "route_open_frame": str(ready.MENU_WINDOW_OPEN_FRAME),
            "route_close_frame": str(ready.MENU_WINDOW_CLOSE_FRAME),
            "route_force_alias_frame": "-1",
            "route_force_commit_frame": str(ready.MENU_WINDOW_CLOSE_FRAME),
            "route_stale_frame": "-1",
            "rom": str(self.candidate.resolve()),
            "rom_sha256": self.candidate_sha,
            "attr_mode": menu_mode,
            "attr_lut_sha256": hashlib.sha256(menu_lut).hexdigest(),
            "attr_checked_frames": "180",
            "attr_bad_frames": "0",
            "attr_mismatch_cells": "0",
            "attr_unsafe_cells": "0",
            "attr_entry_frames": "8",
            "attr_settled_frames": "160",
            "attr_exit_frames": "12",
            "window_hidden_at_close_frames": "116",
            "worst_attr_mismatches": "0",
            "final_state": (
                "scene:02 room:05 ffe4:01 lcdc:8B scx:0C scy:00 "
                "wx:07 wy:90 dc00:3C dc01:00 dc02:20 dc03:07 c1a4:03"
            ),
            "transitions": "f1203:E3/60/9C00/0;f1386:8B/90/9800/0",
            "first_bad": "none",
            "first_visible": (
                "frame:1203 scene:02 room:05 lcdc:E3 wy:60 "
                "map:9C00 mismatches:0"
            ),
            "first_alias": "none",
            "first_post_close_alias": "none",
            "first_attr_bad": "none",
            "content_mode": "native-fixture",
            "content_fixture_sha256": (
                ready.menu_window_oracle.CONTENT_FIXTURE_SHA256
            ),
            "content_checked_frames": "180",
            "content_bad_frames": "0",
            "content_source_mismatch_cells": "0",
            "content_window_mismatch_cells": "0",
            "worst_content_source_mismatches": "0",
            "worst_content_window_mismatches": "0",
            "content_raster_trace": "synthetic-raster-trace",
            "first_content_bad": "none",
            "content_raster_checked_frames": "7",
            "content_raster_bad_frames": "0",
            "content_raster_invariant_sha256": (
                "33b9a6994263127cb7b53e252600c396b6bddfa639d4f645e69d90001f78441f"
            ),
            "first_content_raster_bad": "none",
        }
        report.update(overrides)
        path = self.root / name
        path.write_text("".join(
            f"{key}={value}\n" for key, value in report.items()
        ))
        return path

    def no_bleed_receipt(self) -> dict:
        expected_table = ready.no_bleed_oracle.expected_stage1_table(
            self.candidate.read_bytes()
        )
        captures = [
            {
                "play_frame": 120 * (index + 1),
                "elapsed_seconds": round(120 * (index + 1) / 59.7275, 3),
                "screenshot": f"play-{index:04d}.png",
                "attribute_histogram": {
                    str(palette): (
                        359 if palette == 0 else 1 if palette == 1 else 0
                    )
                    for palette in range(8)
                },
                "palette_1_cells": 1,
                "unexpected_palette_cells": 0,
                "unsafe_attribute_cells": 0,
                "screenshot_sha256": f"{index + 1:064x}",
                "native_size": [160, 144],
            }
            for index in range(6)
        ]
        raster_captures = [
            {
                "play_frame": index,
                "elapsed_seconds": round(index / 59.7275, 3),
                "screenshot": f"raster-{index:04d}.png",
                "lcdc": 0x83,
                "scx": index & 0xFF,
                "scy": (index // 2) & 0xFF,
                "source_signature": index,
                "dc00": 0x3C,
                "dc01": 0,
                "dc02": 0x20,
                "dc03": 7,
                "cache_9800": 1,
                "cache_9c00": 1,
                "c1a4": 3,
                "raw_hash": index,
                "attr_hash": index,
                "layout_id": 0,
                "source_prefix": [0] * 8,
                "pickup_rectangles": [[8, 8, 15, 15]],
                "oam_rectangles": [],
                "screenshot_sha256": f"{index + 1000:064x}",
                "native_size": [160, 144],
                "raster_alignment_frames": [
                    max(1, index - 12), min(1000, index + 12)
                ],
                "raster_audit": {
                    "background_pickup_accent_pixels": 1,
                    "stray_pickup_accent_pixels": 0,
                    "first_stray_coordinates": [],
                },
            }
            for index in range(1, 1001)
        ]
        probe = {
            key: 0 for key in ready.NO_BLEED_PROBE_KEYS
        }
        probe.update({
            "captures": captures,
            "raster_captures": raster_captures,
            "helper_events": [],
            "frames": 3606,
            "sampled_frames": 3606,
            "checked_cells": 100000,
            "pal1_cells": 24,
            "unexpected_cells": 3,
            "unexpected_semantic_pickup_cells": 0,
            "unexpected_floor_cells": 3,
            "contextual_mismatch_pairs": {
                "27/6/0": 1, "30/6/0": 1, "33/6/0": 1,
            },
            "unsafe_cells": 0,
            "runtime_lut_mismatch_frames": 1,
            "runtime_lut_mismatch_cells": 4,
            "runtime_lut_mismatch_max": 4,
            "runtime_lut_mismatch_pairs": {
                "24/6/0": 1, "27/6/0": 1,
                "30/6/0": 1, "33/6/0": 1,
            },
            "runtime_lut_dma_unreadable_frames": 0,
            "first_runtime_lut_dma_unreadable": "",
            "first_runtime_lut_mismatch_frame": -1,
            "first_runtime_lut_mismatch_details": "",
            "first_pal1_frame": 1,
            "first_unexpected_frame": -1,
            "first_unexpected_floor_frame": -1,
            "first_unexpected_floor_details": "",
            "scene_frames": 3606,
            "scene_histogram": {"02": 3606},
            "first_non_stage_scene_frame": -1,
            "first_non_stage_scene": -1,
            "compiler_unreadable_scene_frames": 0,
            "active_frames": 3606,
            "scroll_changes": 500,
            "scx_changes": 250,
            "scy_changes": 250,
            "source_signature_changes": 500,
            "final_scene": 2,
            "final_ffc1": 1,
            "final_pc": 0x1234,
            "final_sp": 0xDFFF,
            "final_svbk": 1,
            "final_compiler_unreadable": 0,
            "debug_copy_hits": 1,
            "debug_atomic_hits": 1,
            "debug_pure_hits": 1,
            "debug_main_hits": 1,
            "debug_last_address": 0x1234,
            "capture_count": len(captures),
            "raster_capture_count": len(raster_captures),
            "helper_event_count": 0,
            "layout_record_count": 0,
            "first_unexpected_screenshot": "",
            "first_unexpected_details": "",
            "pal1_tiles": {"88": 24},
            "pal1_captures": ["120|r1,c1,t88"],
        })
        return {
            "schema": ready.NO_BLEED_SCHEMA,
            "status": "pass",
            "rom": str(self.candidate.resolve()),
            "rom_md5": hashlib.md5(self.candidate.read_bytes()).hexdigest(),
            "rom_sha256": self.candidate_sha,
            "route": {
                "source": ready.NO_BLEED_ROUTE_SOURCE,
                "mode": ready.NO_BLEED_MODE,
                "play_frames_requested": ready.NO_BLEED_FRAMES,
                "emulated_seconds": round(
                    ready.NO_BLEED_FRAMES / ready.no_bleed_oracle.FPS, 3
                ),
            },
            "diagnostic_state": None,
            "raster_alignment_radius_frames": (
                ready.no_bleed_oracle.RASTER_ALIGNMENT_RADIUS
            ),
            "stage1_table_histogram": {
                str(palette): expected_table.count(palette)
                for palette in sorted(set(expected_table))
            },
            "probe": probe,
            "checks": {name: True for name in ready.NO_BLEED_CHECKS},
            "contact_sheet": "actual-play-stage1.png",
            "contact_sheet_sha256": "a" * 64,
            "raster_contact_sheet": "stage1-raster-audit.png",
            "raster_contact_sheet_sha256": "b" * 64,
            "failures": [],
        }

    def test_scene0b_launch_freshness_helpers_fail_closed(self) -> None:
        roots: set[Path] = set()
        tokens: set[str] = set()
        first = (self.root / "replay-a").resolve()
        scene0b.register_replay_freshness(
            first, "1" * 64, roots, tokens, "first replay"
        )
        with self.assertRaisesRegex(
            scene0b.ContractError, "overlaps another replay root"
        ):
            scene0b.register_replay_freshness(
                first / "nested", "2" * 64, roots, tokens,
                "nested replay",
            )
        with self.assertRaisesRegex(
            scene0b.ContractError, "reuses another startup token"
        ):
            scene0b.register_replay_freshness(
                (self.root / "replay-b").resolve(), "1" * 64,
                roots, tokens, "duplicate-token replay",
            )
        order = (
            "startup", "ready", "core_ready", "config_ready",
            "trace_ready", "raw_trace", "report", "done",
        )
        causal = {
            name: {"modified_at_ns": index}
            for index, name in enumerate(order, 1)
        }
        scene0b.require_causal_launch_artifact_order(causal)
        causal["config_ready"]["modified_at_ns"] = 0
        with self.assertRaisesRegex(
            scene0b.ContractError, "ordering is non-causal"
        ):
            scene0b.require_causal_launch_artifact_order(causal)

    @mock.patch.object(
        ready.menu_window_oracle, "authenticate_commit_protocol"
    )
    @mock.patch.object(
        ready.menu_window_oracle, "content_raster_receipt"
    )
    def test_native_menu_window_validator_is_exact_and_candidate_bound(
        self, raster_receipt: mock.Mock, commit_protocol: mock.Mock,
    ) -> None:
        commit_protocol.return_value = {
            "name": "ffc4-absolute-ready-page-scy-df5c-scx-r443",
            "post_pc": 0x7415,
            "source_sha256": "1" * 64,
        }
        raster_receipt.return_value = {
            "checked_frames": 7,
            "bad_frames": 0,
            "expected_rgb_sha256": (
                "33b9a6994263127cb7b53e252600c396b6bddfa639d4f645e69d90001f78441f"
            ),
            "first_bad": None,
            "passed": True,
        }
        evidence = ready.validate_menu_window_report(
            self.write_menu_window_report("menu-window-good.txt"),
            self.candidate,
            self.candidate_sha,
        )
        self.assertEqual(evidence["route"], {
            "frames": 1500,
            "open_frame": 1200,
            "close_frame": 1380,
            "force_alias_frame": -1,
            "force_commit_frame": 1380,
            "stale_frame": -1,
            "key": "select",
            "move": "none",
            "fire_every": 0,
        })
        self.assertGreaterEqual(evidence["coverage"]["settled_frames"], 60)
        self.assertGreaterEqual(
            evidence["coverage"]["hidden_post_close_frames"], 60
        )

        mutations = {
            "wrong-route.txt": {"route_close_frame": "1379"},
            "missing-close-race.txt": {
                "forced_commit": "0", "forced_commit_consumed": "0",
            },
            "wrong-commit-protocol.txt": {
                "forced_commit_protocol": "retired-dfc4-df5c",
            },
            "post-close-alias.txt": {
                "post_close_selector_alias_frames": "1",
                "first_post_close_alias": "frame:1386",
            },
            "wrong-rom.txt": {"rom_sha256": "0" * 64},
            "bad-tile.txt": {"bad_frames": "1", "first_bad": "frame:1"},
            "bad-attr.txt": {
                "attr_bad_frames": "1", "attr_mismatch_cells": "1",
                "first_attr_bad": "frame:1203 mismatches:1",
            },
            "blank-source.txt": {
                "content_bad_frames": "180",
                "content_source_mismatch_cells": "14400",
                "first_content_bad": "frame:1203 source_mismatches:80",
            },
            "blank-raster.txt": {
                "content_raster_bad_frames": "7",
                "first_content_raster_bad": "frame:1203 white",
            },
            "no-close.txt": {"window_hidden_at_close_frames": "0"},
        }
        for name, overrides in mutations.items():
            with self.subTest(name=name):
                with self.assertRaises(ready.NotReady):
                    ready.validate_menu_window_report(
                        self.write_menu_window_report(name, **overrides),
                        self.candidate,
                        self.candidate_sha,
                    )

        malformed = self.write_menu_window_report("extra-field.txt")
        with malformed.open("a") as handle:
            handle.write("unreviewed_field=1\n")
        with self.assertRaisesRegex(ready.NotReady, "schema changed"):
            ready.validate_menu_window_report(
                malformed, self.candidate, self.candidate_sha
            )

    def test_natural_pickup_temporal_raster_validator_is_fail_closed(
        self,
    ) -> None:
        receipt = self.no_bleed_receipt()
        evidence = ready.validate_no_bleed_receipt(
            self.write_json("no-bleed-good.json", receipt),
            self.candidate,
            self.candidate_sha,
        )
        self.assertEqual(evidence["route"]["mode"], "box")
        self.assertEqual(evidence["route"]["play_frames_requested"], 3600)
        self.assertEqual(evidence["coverage"]["raster_captures"], 1000)
        self.assertGreater(
            evidence["coverage"]["background_pickup_accent_pixels"], 0
        )

        private_tail = copy.deepcopy(receipt)
        private_tail["probe"].update({
            "scene_histogram": {"02": 3605, "00": 1},
            "first_non_stage_scene_frame": 3606,
            "first_non_stage_scene": 0,
            "compiler_unreadable_scene_frames": 1,
            "final_scene": 0,
            "final_pc": 0x741F,
            "final_svbk": 3,
            "final_compiler_unreadable": 1,
        })
        evidence = ready.validate_no_bleed_receipt(
            self.write_json("no-bleed-private-tail.json", private_tail),
            self.candidate,
            self.candidate_sha,
        )
        self.assertEqual(evidence["coverage"]["scene_frames"], 3606)

        mutations = []
        wrong_sha = copy.deepcopy(receipt)
        wrong_sha["rom_sha256"] = "0" * 64
        mutations.append(("wrong-sha", wrong_sha, "targets another ROM"))
        short_route = copy.deepcopy(receipt)
        short_route["route"]["play_frames_requested"] = 3599
        mutations.append(("short-route", short_route, "route is not exact"))
        fixture_route = copy.deepcopy(receipt)
        fixture_route["diagnostic_state"] = {"path": "fixture.ss0"}
        mutations.append(("fixture-route", fixture_route, "injected state"))
        failed_check = copy.deepcopy(receipt)
        failed_check["checks"][
            "no detached pickup colors or floor-pattern bleed in rendered raster"
        ] = False
        mutations.append(("failed-check", failed_check, "checks failed"))
        semantic_bleed = copy.deepcopy(receipt)
        semantic_bleed["probe"]["unexpected_semantic_pickup_cells"] = 1
        mutations.append((
            "semantic-bleed", semantic_bleed,
            "unexpected_semantic_pickup_cells is not zero",
        ))
        bad_interval_count = copy.deepcopy(receipt)
        bad_interval_count["probe"]["captures"][0][
            "unexpected_palette_cells"
        ] = 4
        mutations.append((
            "bad-interval-count", bad_interval_count,
            "interval capture 0 mismatch accounting is invalid",
        ))
        wrong_scene = copy.deepcopy(receipt)
        wrong_scene["probe"]["scene_histogram"] = {
            "02": 3605, "0C": 1,
        }
        wrong_scene["probe"]["first_non_stage_scene_frame"] = 3000
        wrong_scene["probe"]["first_non_stage_scene"] = 0x0C
        mutations.append((
            "wrong-scene", wrong_scene,
            "sampled a non-Stage-1 scene",
        ))
        bad_scene_count = copy.deepcopy(receipt)
        bad_scene_count["probe"]["scene_histogram"] = {"02": 3605}
        mutations.append((
            "bad-scene-count", bad_scene_count,
            "scene accounting is inconsistent",
        ))
        spurious_scene_witness = copy.deepcopy(receipt)
        spurious_scene_witness["probe"]["first_non_stage_scene_frame"] = 1
        spurious_scene_witness["probe"]["first_non_stage_scene"] = 0
        mutations.append((
            "spurious-scene-witness", spurious_scene_witness,
            "witness is spurious",
        ))
        short_raster = copy.deepcopy(receipt)
        short_raster["probe"]["raster_captures"] = short_raster["probe"][
            "raster_captures"
        ][:999]
        short_raster["probe"]["raster_capture_count"] = 999
        mutations.append((
            "short-raster", short_raster,
            "fewer than 1,000 raster transition samples",
        ))
        extra_check = copy.deepcopy(receipt)
        extra_check["checks"]["unreviewed pass"] = True
        mutations.append(("extra-check", extra_check, "checks schema changed"))
        unbounded_private = copy.deepcopy(private_tail)
        unbounded_private["probe"]["final_pc"] = 0x5000
        mutations.append((
            "unbounded-private", unbounded_private,
            "private-WRAM scene sample is not bounded",
        ))
        wrong_private_bank = copy.deepcopy(private_tail)
        wrong_private_bank["probe"]["final_svbk"] = 1
        mutations.append((
            "wrong-private-bank", wrong_private_bank,
            "private-WRAM scene sample is not bounded",
        ))

        for name, mutant, message in mutations:
            with self.subTest(name=name):
                with self.assertRaisesRegex(ready.NotReady, message):
                    ready.validate_no_bleed_receipt(
                        self.write_json(f"no-bleed-{name}.json", mutant),
                        self.candidate,
                        self.candidate_sha,
                    )

    def test_release_north_validator_accepts_only_exact_oracle(self) -> None:
        receipt = self.north_receipt()
        path = self.write_json("north-good.json", receipt)
        evidence = ready.validate_north_receipt(
            path, self.candidate, self.candidate_sha
        )
        self.assertEqual(evidence["expected_attr"], "06")
        self.assertEqual(evidence["reviewed_cells_per_record"], 64)

        slow = copy.deepcopy(receipt)
        for label in ("candidate", "candidate_replay"):
            slow[label]["frames"] = "1818"
            slow[label]["gameplay_frames"] = "1329"
            slow[label]["native_gameplay_frames"] = "1295"
        slow["gameplay_frame_lag"] = 313
        with self.assertRaisesRegex(ready.NotReady, "north traversal speed"):
            ready.validate_north_receipt(
                self.write_json("north-visually-clean-but-slow.json", slow),
                self.candidate, self.candidate_sha)
        missing = copy.deepcopy(receipt)
        del missing["candidate"]["native_gameplay_frames"]
        with self.assertRaisesRegex(ready.NotReady, "timing missing"):
            ready.validate_north_traversal_speed(missing)

        inconsistent = copy.deepcopy(receipt)
        inconsistent["candidate"]["native_gameplay_frames"] = "985"
        with self.assertRaisesRegex(
            ready.NotReady, "native gameplay timing arithmetic"
        ):
            ready.validate_north_traversal_speed(inconsistent)

        boundary_mismatch = copy.deepcopy(receipt)
        boundary_mismatch["candidate_replay"]["first_gameplay"] = "490"
        boundary_mismatch["candidate_replay"]["gameplay_frames"] = "1019"
        with self.assertRaisesRegex(ready.NotReady, "not repeatable"):
            ready.validate_north_traversal_speed(boundary_mismatch)

        bad = copy.deepcopy(receipt)
        bad["reviewed_room01_wall_oracle"]["room01"]["attr_mismatches"] = 1
        bad["reviewed_room01_wall_oracle"]["room01"]["exact"] = False
        with self.assertRaises(ready.NotReady):
            ready.validate_north_receipt(
                self.write_json("north-bad-wall.json", bad),
                self.candidate,
                self.candidate_sha,
            )

        bad = copy.deepcopy(receipt)
        bad["reviewed_room01_wall_oracle"][
            "room05_patterned_floor_control"
        ]["expected_attr"] = 6
        with self.assertRaises(ready.NotReady):
            ready.validate_north_receipt(
                self.write_json("north-bad-floor.json", bad),
                self.candidate,
                self.candidate_sha,
            )

        bad = copy.deepcopy(receipt)
        bad["candidate_physical_page_owner_report"]["publication"][
            "publication_pc"
        ] ^= 0x13
        with self.assertRaisesRegex(ready.NotReady, "owner_report"):
            ready.validate_north_receipt(
                self.write_json("north-bad-owner-site.json", bad),
                self.candidate,
                self.candidate_sha,
            )

        bad = copy.deepcopy(receipt)
        bad["candidate_physical_page_owner_report"]["counters"][
            "map_owner_missing_trajectory_frames"
        ] = 1
        with self.assertRaisesRegex(
            ready.NotReady, "map_owner_missing_trajectory_frames"
        ):
            ready.validate_north_receipt(
                self.write_json("north-missing-owner.json", bad),
                self.candidate,
                self.candidate_sha,
            )

        bad = copy.deepcopy(receipt)
        bad["full_route_geometry_maxima"]["world_state"] = 101
        bad["full_route_geometry_differences_present"] = True
        bad["full_route_geometry_worst_example"] = {
            "differences": 101, "gameplay_frame": 1040,
        }
        with self.assertRaisesRegex(ready.NotReady, "geometry difference"):
            ready.validate_north_receipt(
                self.write_json("north-101-cell-viewport.json", bad),
                self.candidate,
                self.candidate_sha,
            )

    def live_receipt(self, live_root: Path) -> dict:
        live_root.mkdir()
        contract = scene0b.load_capture_contract()
        captures = scene0b.capture_evidence(contract)
        candidate_bytes = self.candidate.read_bytes()
        emulator_binary = scene0b.default_qt_emulator()
        canonical_bg_art = b"".join(
            candidate_bytes[offset:offset + 16]
            for tile in range(0x100)
            for offset in ((
                scene0b.STAGE1_LOW_TILE_GFX_OFFSET + tile * 16
                if tile < 0x80
                else scene0b.STAGE1_HIGH_TILE_GFX_OFFSET + tile * 16
            ),)
        )
        canonical_bank1 = (
            candidate_bytes[0x1D640:0x1D6A0]
            + candidate_bytes[0x1D740:0x1D7A0]
        )
        candidate_crc = (
            f"{zlib.crc32(candidate_bytes) & 0xFFFFFFFF:08x}"
        )
        image_buffer = io.BytesIO()
        Image.new("RGB", scene0b.SCREEN_SIZE, (0, 0, 0)).save(
            image_buffer, format="PNG"
        )
        png_payload = image_buffer.getvalue()
        rgb_sha256 = hashlib.sha256(
            bytes(scene0b.SCREEN_SIZE[0] * scene0b.SCREEN_SIZE[1] * 3)
        ).hexdigest()
        phases = (
            ["captured"]
            + ["repair_settle"] * scene0b.REPAIR_SETTLE_FRAMES
            + ["menu_entry"]
            + ["menu_hold"] * 60
            + ["menu_exit"]
            + ["post_close"] * 60
        )
        replays = []
        for capture in captures:
            for replay_index in (1, 2):
                replay_root = live_root / (
                    f"{capture['label']}-replay-{replay_index}"
                )
                runtime = replay_root / "runtime"
                runtime.mkdir(parents=True)
                runtime_rom = runtime / "candidate.gb"
                runtime_rom.write_bytes(candidate_bytes)
                retargeted = runtime / "capture.ss0"
                retarget_rom_identity(
                    Path(capture["path"]), retargeted, self.candidate
                )
                source_payload = scene0b.gbas_payload(Path(capture["path"]))
                retargeted_payload = scene0b.gbas_payload(retargeted)
                changed_offsets = [
                    offset for offset, values in enumerate(zip(
                        source_payload, retargeted_payload, strict=True
                    )) if values[0] != values[1]
                ]
                trace = replay_root / "state-trace.jsonl"
                manifest = replay_root / "rendered-manifest.json"
                initial_menu = capture["captured_state"]["FFE4"]
                room = int(capture["captured_state"]["FFBD"], 16)
                scx = int(capture["captured_state"]["SCX"], 16)
                trace_rows = []
                rendered_rows = []
                trace_lines = []
                for sample, phase in enumerate(phases, 1):
                    if phase == "captured":
                        menu = int(initial_menu, 16)
                        lcdc = int(capture["captured_state"]["LCDC"], 16)
                    else:
                        menu = int(phase in {"menu_hold", "menu_exit"})
                        lcdc = 0xE3 if menu else 0x83
                    row = {
                        "sample": sample,
                        "frame": sample,
                        "phase": phase,
                        "scene": 0x0B,
                        "room": room,
                        "active": 1,
                        "menu": menu,
                        "lcdc": lcdc,
                        "scx": scx,
                        "scy": 0,
                        "attr_mismatches": 0,
                        "semantic_attr_mismatches": 0,
                        "immutable_tile_mismatches": 0,
                        "tile_publication_mismatches": 0,
                        "tile_phase_mismatches": 0,
                        "tile_plane_mismatches": 0,
                        "tile_source_mismatches": 0,
                        "tile_art_mismatches": 0,
                        "bg_cram_mismatches": 0,
                        "lut_mismatches": 0,
                    }
                    trace_rows.append(row)
                    trace_lines.append(json.dumps(
                        {"schema": scene0b.STATE_TRACE_SCHEMA, **row},
                        sort_keys=True, separators=(",", ":"),
                    ))
                    frame_path = replay_root / (
                        f"scene0b.frame{sample:04d}.{phase}.png"
                    )
                    frame_path.write_bytes(png_payload)
                    rendered_rows.append({
                        "sample": sample,
                        "phase": phase,
                        "path": str(frame_path.resolve()),
                        "sha256": hashlib.sha256(png_payload).hexdigest(),
                        "rgb_sha256": rgb_sha256,
                    })
                trace.write_text("\n".join(trace_lines) + "\n")
                rendered_semantic = hashlib.sha256(json.dumps(
                    [
                        {
                            key: row[key]
                            for key in ("sample", "phase", "rgb_sha256")
                        }
                        for row in rendered_rows
                    ],
                    sort_keys=True, separators=(",", ":"),
                ).encode()).hexdigest()
                manifest.write_text(json.dumps({
                    "schema": scene0b.RENDERED_MANIFEST_SCHEMA,
                    "capture_label": capture["label"],
                    "replay_index": replay_index,
                    "semantic_sha256": rendered_semantic,
                    "frames": rendered_rows,
                }, indent=2, sort_keys=True) + "\n")
                fingerprint = scene0b.trace_rendered_fingerprint(
                    trace_rows, rendered_rows
                )
                planes = replay_root / "scene0b.planes.bin"
                plane_meta = replay_root / "scene0b.planes.meta"
                immutable_source = scene0b.immutable_source_from_capture(
                    Path(capture["path"]), source_payload
                )
                immutable_stage1_tables = scene0b.gbax_sram_payload(
                    Path(capture["path"])
                )[:0x800]
                runtime_oracles = replay_root / "scene0b.runtime-oracles.bin"
                runtime_oracles.write_bytes(
                    scene0b.canonical_runtime_oracles(
                        candidate_bytes,
                        immutable_source,
                        immutable_stage1_tables,
                    )
                )
                process_teardown = {
                    "policy": "authenticated-exact-child-termination",
                    "completion_authenticated": True,
                    "exact_child_terminated": True,
                    "termination_method": "SIGTERM",
                    "return_code": -15,
                }
                output_prefix = replay_root / "scene0b"
                startup_token = hashlib.sha256(
                    f"{capture['label']}:{replay_index}".encode()
                ).hexdigest()
                startup = Path(str(output_prefix) + ".startup")
                ready_marker = Path(str(output_prefix) + ".ready")
                core_ready = Path(str(output_prefix) + ".core-ready")
                config_ready = Path(str(output_prefix) + ".config-ready")
                trace_ready = Path(str(output_prefix) + ".trace-ready")
                raw_trace = Path(str(output_prefix) + ".trace.tsv")
                report = Path(str(output_prefix) + ".report")
                done = Path(str(output_prefix) + ".done")
                emulator_log = replay_root / "emulator.log"
                for marker_path in (
                    startup, ready_marker, core_ready, config_ready,
                    trace_ready,
                ):
                    marker_path.write_text(startup_token + "\n")
                byte_fields = {
                    "scene", "room", "active", "menu", "lcdc", "scx", "scy"
                }
                raw_lines = []
                for row in trace_rows:
                    values = []
                    for field in scene0b.RAW_TRACE_FIELDS:
                        if field == "phase":
                            values.append(row[field])
                        elif field == "startup_token":
                            values.append(startup_token)
                        elif field in byte_fields:
                            values.append(f"{row[field]:02X}")
                        else:
                            values.append(str(row[field]))
                    raw_lines.append("\t".join(values))
                raw_trace.write_text("\n".join(raw_lines) + "\n")
                report.write_text(
                    "status=ok\nreason=complete\n"
                    f"startup_token={startup_token}\n"
                    "oam_dma_unreadable_frames=0\n"
                )
                done.write_text(
                    f"status=ok\nstartup_token={startup_token}\n"
                )
                emulator_log.write_text("synthetic offline fixture\n")
                launch_paths = {
                    "startup": startup,
                    "ready": ready_marker,
                    "core_ready": core_ready,
                    "config_ready": config_ready,
                    "trace_ready": trace_ready,
                    "raw_trace": raw_trace,
                    "report": report,
                    "done": done,
                    "emulator_log": emulator_log,
                }
                launch_started_at_ns = startup.stat().st_mtime_ns
                launch_completed_at_ns = max(
                    path.stat().st_mtime_ns for path in launch_paths.values()
                )
                launch_artifacts = {
                    name: {
                        "path": str(path.resolve()),
                        "sha256": scene0b.sha256(path),
                        "modified_at_ns": path.stat().st_mtime_ns,
                    }
                    for name, path in launch_paths.items()
                }
                launch_contract_path = replay_root / "launch-contract.json"
                launch_contract_path.write_text(json.dumps({
                    "schema": "penta-stage1-scene0b-launch-contract-v6",
                    "command": [
                        str(scene0b.SINGLEFLIGHT), "--fastforward",
                        "-C", f"savegamePath={runtime}",
                        "-C", f"savestatePath={runtime}",
                        "--script", str(scene0b.LIVE_PROBE),
                        str(runtime_rom),
                    ],
                    "cwd": str(replay_root.resolve()),
                    "output_prefix": str(output_prefix.resolve()),
                    "capture_label": capture["label"],
                    "replay_index": replay_index,
                    "startup_token_sha256": hashlib.sha256(
                        startup_token.encode()
                    ).hexdigest(),
                    "launch_started_at_ns": launch_started_at_ns,
                    "launch_completed_at_ns": launch_completed_at_ns,
                    "initial_menu": int(initial_menu, 16),
                    "frame_limit": scene0b.FRAME_LIMIT,
                    "capture_frames": scene0b.CAPTURE_FRAMES,
                    "repair_settle_frames": scene0b.REPAIR_SETTLE_FRAMES,
                    "menu_hold_frames": scene0b.MENU_HOLD_FRAMES,
                    "post_close_frames": scene0b.POST_CLOSE_FRAMES,
                    "launcher_sha256": scene0b.sha256(
                        scene0b.SINGLEFLIGHT
                    ),
                    "singleflight_implementation_sha256": scene0b.sha256(
                        scene0b.SINGLEFLIGHT_IMPLEMENTATION
                    ),
                    "emulator_path": str(emulator_binary),
                    "emulator_sha256": scene0b.sha256(emulator_binary),
                    "probe_sha256": scene0b.sha256(scene0b.LIVE_PROBE),
                    "runtime_rom_path": str(runtime_rom.resolve()),
                    "runtime_rom_sha256": self.candidate_sha,
                    "runtime_state_path": str(retargeted.resolve()),
                    "runtime_state_sha256": scene0b.sha256(retargeted),
                    "immutable_source_sha256": hashlib.sha256(
                        immutable_source
                    ).hexdigest(),
                    "immutable_stage1_tables_sha256": hashlib.sha256(
                        immutable_stage1_tables
                    ).hexdigest(),
                    "canonical_bg_art_sha256": scene0b.STAGE1_BG_ART_SHA256,
                    "canonical_hazard_bank1_art_sha256": (
                        scene0b.STAGE1_HAZARD_BANK1_ART_SHA256
                    ),
                    "hazard_oracle_fixture_sha256": scene0b.sha256(
                        scene0b.HAZARD_TILE_ORACLE_FIXTURE
                    ),
                    "hazard_phase_payload_sha256": (
                        scene0b.STAGE1_HAZARD_PHASE_PAYLOAD_SHA256
                    ),
                    "expected_bg_cram_sha256": (
                        scene0b.STAGE1_BG_CRAM_SHA256
                    ),
                    "runtime_oracle_bundle_sha256": scene0b.sha256(
                        runtime_oracles
                    ),
                    "startup": launch_artifacts["startup"],
                    "ready": launch_artifacts["ready"],
                    "core_ready": launch_artifacts["core_ready"],
                    "config_ready": launch_artifacts["config_ready"],
                    "trace_ready": launch_artifacts["trace_ready"],
                    "done": launch_artifacts["done"],
                    "report": launch_artifacts["report"],
                    "raw_trace": launch_artifacts["raw_trace"],
                    "emulator_log": launch_artifacts["emulator_log"],
                    "cache_audit": None,
                    "cache_audit_ready": None,
                    "startup_timeout_seconds": (
                        scene0b.STARTUP_TIMEOUT_SECONDS
                    ),
                    "ready_timeout_seconds": scene0b.READY_TIMEOUT_SECONDS,
                    "core_timeout_seconds": scene0b.CORE_TIMEOUT_SECONDS,
                    "teardown_policy": scene0b.TEARDOWN_POLICY,
                    "provisional_process_outcome": {
                        "exact_child_terminated": True,
                        "termination_method": "SIGTERM",
                        "return_code": -15,
                        "completion_status": "ok",
                    },
                    "validated_process_teardown": process_teardown,
                }, indent=2, sort_keys=True) + "\n")
                tile_map = bytearray(0x400)
                for row_index in range(24):
                    tile_map[row_index * 32:row_index * 32 + 24] = (
                        immutable_source[
                            row_index * 24:(row_index + 1) * 24
                        ]
                    )
                hazard_positions = scene0b._stage1_hazard_positions(
                    bytes(tile_map)
                )
                attrs = scene0b._stage1_semantic_attrs(
                    bytes(tile_map), self.canonical_lut, room,
                    hazard_positions,
                )
                inherited_runtime_lut = bytearray(source_payload[
                    scene0b.WRAM_OFFSET + (0xC600 - 0xC000):
                    scene0b.WRAM_OFFSET + (0xC700 - 0xC000)
                ])
                if capture["label"] == "operator-low-health-menu-loaded":
                    # The exact older operator state predates the native
                    # four-terminal BG6 -> BG5 migration.  The candidate
                    # performs that migration before the live probe reaches
                    # its authenticated baseline; model that native step in
                    # this offline receipt fixture.
                    for tile in (0x6B, 0x6F, 0x7B, 0x7F):
                        self.assertEqual(inherited_runtime_lut[tile], 0x06)
                        inherited_runtime_lut[tile] = 0x05
                inherited_runtime_lut = bytes(inherited_runtime_lut)
                self.assertEqual(
                    hashlib.sha256(inherited_runtime_lut).hexdigest(),
                    scene0b.STAGE1_RELEASE_LUT_SHA256,
                )
                planes.write_bytes(
                    bytes(tile_map) * 2 + attrs * 2
                    + immutable_source + inherited_runtime_lut
                )
                final_sample = len(trace_rows)
                plane_meta.write_text(
                    f"frame={final_sample}\nsample={final_sample}\n"
                    "phase=post_close\nlcdc=83\n"
                    f"scx={scx:02X}\nscy=00\nscene=0B\nroom={room:02X}\n"
                    "menu=00\nschema=maps-v1\nbytes=4928\n"
                )
                chr_payload = bytearray(scene0b.FINAL_BG_CHR_BYTES)
                plane_payload = planes.read_bytes()
                for map_index in range(2):
                    map_tiles = plane_payload[
                        map_index * 0x400:(map_index + 1) * 0x400
                    ]
                    map_attrs = plane_payload[
                        0x800 + map_index * 0x400:
                        0x800 + (map_index + 1) * 0x400
                    ]
                    for row_index in range(24):
                        for column_index in range(24):
                            offset = row_index * 32 + column_index
                            tile = map_tiles[offset]
                            bank = (map_attrs[offset] >> 3) & 1
                            if bank == 0:
                                pattern = canonical_bg_art[
                                    tile * 16:(tile + 1) * 16
                                ]
                            elif (
                                capture["label"] in scene0b.HAZARD_CAPTURE_LABELS
                                and 0x64 <= tile <= 0x69
                            ):
                                base = (tile - 0x64) * 16
                                pattern = canonical_bank1[base:base + 16]
                            elif (
                                capture["label"] in scene0b.HAZARD_CAPTURE_LABELS
                                and 0x74 <= tile <= 0x79
                            ):
                                base = 96 + (tile - 0x74) * 16
                                pattern = canonical_bank1[base:base + 16]
                            else:
                                self.fail(
                                    "synthetic plane references illegal "
                                    f"bank-one tile {tile:02X}"
                                )
                            address = (
                                bank * 0x2000
                                + scene0b._stage1_chr_address(tile, 0x83)
                            )
                            chr_payload[address:address + 16] = pattern
                final_bg_chr_path = replay_root / "scene0b.chr.bin"
                final_bg_chr_path.write_bytes(chr_payload)
                final_bg_chr = scene0b.recompute_final_bg_chr(
                    final_bg_chr_path,
                    planes,
                    plane_meta,
                    candidate_bytes,
                    capture["label"],
                )
                physical_planes = scene0b.recompute_physical_planes(
                    planes, plane_meta, self.canonical_lut,
                    immutable_source, capture["label"],
                )
                replays.append({
                    "capture_label": capture["label"],
                    "replay_index": replay_index,
                    "source_capture_path": capture["path"],
                    "source_capture_sha256": capture["sha256"],
                    "source_state_loaded": True,
                    "initial_scene": "0B",
                    "initial_menu_flag": initial_menu,
                    "scene_values": ["0B"],
                    "normalization": "rom-identity-only",
                    "normalization_writes": 0,
                    "fixture_writes": 0,
                    "scene_injection": False,
                    "vram_injection_bytes": 0,
                    "retargeted_state_sha256": scene0b.sha256(retargeted),
                    "retargeted_state": {
                        "path": str(retargeted),
                        "sha256": scene0b.sha256(retargeted),
                    },
                    "retarget_changed_gbAs_offsets": changed_offsets,
                    "retargeted_state_rom_crc32": candidate_crc,
                    "retargeted_state_rom_identity": candidate_bytes[
                        0x134:0x144
                    ].hex(),
                    "native_menu_transitions": True,
                    "process_teardown": process_teardown,
                    "menu_open_events": 1,
                    "menu_close_events": 1 if initial_menu == "00" else 2,
                    "captured_state_frames": 1,
                    "repair_settle_frames": scene0b.REPAIR_SETTLE_FRAMES,
                    "menu_entry_frames": 1,
                    "menu_held_frames": 60,
                    "menu_exit_frames": 1,
                    "post_close_frames": 60,
                    "rendered_frames": len(trace_rows),
                    "wall_edge_artifact_frames": 0,
                    "red_green_artifact_frames": 0,
                    "clear_tile_frames": 0,
                    "weird_edge_tile_frames": 0,
                    "postsettle_wall_edge_artifact_frames": 0,
                    "postsettle_red_green_artifact_frames": 0,
                    "postsettle_weird_edge_tile_frames": 0,
                    "visible_attr_mismatch_frames": 0,
                    "yellow_trail_frames": 0,
                    "gray_spike_frames": 0,
                    "runtime_lut_mutation_frames": 0,
                    "runtime_oracles": {
                        "path": str(runtime_oracles.resolve()),
                        "sha256": scene0b.sha256(runtime_oracles),
                    },
                    "launch_contract": {
                        "path": str(launch_contract_path.resolve()),
                        "sha256": scene0b.sha256(launch_contract_path),
                    },
                    "final_bg_chr": final_bg_chr,
                    "postrepair_semantic_attr_mismatch_frames": 0,
                    "postsettle_semantic_attr_mismatch_frames": 0,
                    "semantic_checked_samples": len(trace_rows),
                    "semantic_unreadable_samples": 0,
                    "postrepair_immutable_tile_mismatch_frames": 0,
                    "postsettle_immutable_tile_mismatch_frames": 0,
                    "late_tile_art_mismatch_frames": 0,
                    "immutable_tile_checked_samples": len(trace_rows),
                    "immutable_tile_unreadable_samples": 0,
                    "postrepair_bg_cram_mismatch_frames": 0,
                    "cram_checked_samples": len(trace_rows),
                    "cram_unreadable_samples": 0,
                    "final_physical_planes": physical_planes,
                    "baseline_ready": True,
                    "attr_checked_samples": 60,
                    "attr_unreadable_samples": 0,
                    "observation_restore_failures": 0,
                    "scene_violation_frames": 0,
                    "active_violation_frames": 0,
                    "oam_dma_unreadable_frames": 0,
                    "semantic_fingerprint_sha256": fingerprint,
                    "state_trace": {
                        "path": str(trace), "sha256": scene0b.sha256(trace)
                    },
                    "rendered_manifest": {
                        "path": str(manifest),
                        "sha256": scene0b.sha256(manifest),
                    },
                })
        return {
            "schema": scene0b.LIVE_SCHEMA,
            "status": "PASS",
            "candidate": str(self.candidate.resolve()),
            "candidate_sha256": self.candidate_sha,
            "archived_incompatible_capture": (
                scene0b.archived_incompatible_evidence(
                    contract, self.candidate, self.candidate_sha
                )
            ),
            "source_captures": captures,
            "route_policy": contract["live_policy"],
            "replays": replays,
            "checks": {name: True for name in scene0b.LIVE_CHECKS},
            "failures": [],
            "tool_identity": scene0b.expected_live_tool_identity(),
        }

    def test_scene0b_requires_live_duplicate_menu_roundtrips(self) -> None:
        self.candidate = (
            ROOT / "tmp/r536-penta-seam-vram-current636/candidate.gb"
        ).resolve()
        self.candidate_sha = scene0b.sha256(self.candidate)
        self.canonical_lut = self.candidate.read_bytes()[
            scene0b.STAGE1_LUT_OFFSET:
            scene0b.STAGE1_LUT_OFFSET + 0x100
        ]
        self.assertEqual(
            hashlib.sha256(self.canonical_lut).hexdigest(),
            scene0b.STAGE1_COMPILED_TOOTH_LUT_SHA256,
        )
        live_root = self.root / "live"
        live = self.live_receipt(live_root)
        live_path = live_root / "receipt.json"
        live_path.write_text(json.dumps(live, indent=2) + "\n")
        bound = scene0b.bound_payload(
            live_path, self.candidate, self.candidate_sha
        )
        bound_path = self.write_json("scene0b-bound.json", bound)
        evidence = ready.validate_scene0b_receipt(
            bound_path, self.candidate, self.candidate_sha, live_path
        )
        self.assertTrue(evidence["scene0b_live"])
        self.assertEqual(evidence["capture_count"], 2)
        self.assertEqual(evidence["replay_count"], 4)

        oracle_mutant = copy.deepcopy(live)
        original_oracles = Path(
            oracle_mutant["replays"][0]["runtime_oracles"]["path"]
        )
        mutated_oracle_payload = bytearray(original_oracles.read_bytes())
        mutated_oracle_payload[0] ^= 0x01
        mutated_oracles = live_root / "mutated-runtime-oracles.bin"
        mutated_oracles.write_bytes(mutated_oracle_payload)
        oracle_mutant["replays"][0]["runtime_oracles"] = {
            "path": str(mutated_oracles.resolve()),
            "sha256": scene0b.sha256(mutated_oracles),
        }
        with self.assertRaisesRegex(
            scene0b.ContractError, "parsed noncanonical oracle bytes"
        ):
            scene0b.validate_live_receipt(
                self.write_json(
                    "scene0b-mutated-runtime-oracles.json", oracle_mutant
                ),
                self.candidate,
                self.candidate_sha,
            )

        launch_mutant = copy.deepcopy(live)
        launch_claim = launch_mutant["replays"][0]["launch_contract"]
        launch_path = Path(launch_claim["path"])
        canonical_launch_bytes = launch_path.read_bytes()
        mutated_launch = json.loads(canonical_launch_bytes)
        mutated_launch["command"][1] = "--mutated-fastforward"
        launch_path.write_text(
            json.dumps(mutated_launch, indent=2, sort_keys=True) + "\n"
        )
        launch_claim["sha256"] = scene0b.sha256(launch_path)
        try:
            with self.assertRaisesRegex(
                scene0b.ContractError, "launched another command"
            ):
                scene0b.validate_live_receipt(
                    self.write_json(
                        "scene0b-mutated-launch-command.json",
                        launch_mutant,
                    ),
                    self.candidate,
                    self.candidate_sha,
                )
        finally:
            launch_path.write_bytes(canonical_launch_bytes)

        for field, value, expected_error in (
            ("startup_token_sha256", "0" * 64,
             "startup-token hash differs"),
            (
                "launch_started_at_ns",
                json.loads(canonical_launch_bytes)["startup"][
                    "modified_at_ns"
                ] + 1,
                "outside this replay's launch window",
            ),
        ):
            freshness_mutant = copy.deepcopy(live)
            freshness_claim = freshness_mutant["replays"][0][
                "launch_contract"
            ]
            freshness_path = Path(freshness_claim["path"])
            freshness_bytes = freshness_path.read_bytes()
            freshness_contract = json.loads(freshness_bytes)
            freshness_contract[field] = value
            freshness_path.write_text(json.dumps(
                freshness_contract, indent=2, sort_keys=True
            ) + "\n")
            freshness_claim["sha256"] = scene0b.sha256(freshness_path)
            try:
                with self.assertRaisesRegex(
                    scene0b.ContractError, expected_error
                ):
                    scene0b.validate_live_receipt(
                        self.write_json(
                            f"scene0b-mutated-{field}.json",
                            freshness_mutant,
                        ),
                        self.candidate,
                        self.candidate_sha,
                    )
            finally:
                freshness_path.write_bytes(freshness_bytes)

        raw_token_mutant = copy.deepcopy(live)
        raw_launch_claim = raw_token_mutant["replays"][0]["launch_contract"]
        raw_launch_path = Path(raw_launch_claim["path"])
        raw_launch_bytes = raw_launch_path.read_bytes()
        raw_contract = json.loads(raw_launch_bytes)
        raw_path = Path(raw_contract["raw_trace"]["path"])
        raw_bytes = raw_path.read_bytes()
        raw_stat = raw_path.stat()
        raw_lines = raw_bytes.decode().splitlines()
        fields = raw_lines[0].split("\t")
        fields[-1] = "f" * 64
        raw_lines[0] = "\t".join(fields)
        raw_path.write_text("\n".join(raw_lines) + "\n")
        os.utime(
            raw_path,
            ns=(raw_stat.st_atime_ns, raw_stat.st_mtime_ns),
        )
        raw_contract["raw_trace"]["sha256"] = scene0b.sha256(raw_path)
        raw_launch_path.write_text(json.dumps(
            raw_contract, indent=2, sort_keys=True
        ) + "\n")
        raw_launch_claim["sha256"] = scene0b.sha256(raw_launch_path)
        try:
            with self.assertRaisesRegex(
                scene0b.ContractError, "raw trace token differs"
            ):
                scene0b.validate_live_receipt(
                    self.write_json(
                        "scene0b-mutated-raw-trace-token.json",
                        raw_token_mutant,
                    ),
                    self.candidate,
                    self.candidate_sha,
                )
        finally:
            raw_path.write_bytes(raw_bytes)
            os.utime(
                raw_path,
                ns=(raw_stat.st_atime_ns, raw_stat.st_mtime_ns),
            )
            raw_launch_path.write_bytes(raw_launch_bytes)

        aliased = copy.deepcopy(live)
        first_manifest = json.loads(Path(
            aliased["replays"][0]["rendered_manifest"]["path"]
        ).read_text())
        second_manifest_claim = aliased["replays"][1]["rendered_manifest"]
        second_manifest_path = Path(second_manifest_claim["path"])
        second_manifest_bytes = second_manifest_path.read_bytes()
        second_manifest = json.loads(second_manifest_bytes)
        second_manifest["frames"][0] = first_manifest["frames"][0]
        second_manifest_path.write_text(json.dumps(
            second_manifest, indent=2, sort_keys=True
        ) + "\n")
        second_manifest_claim["sha256"] = scene0b.sha256(
            second_manifest_path
        )
        try:
            with self.assertRaisesRegex(
                scene0b.ContractError, "aliases evidence outside its root"
            ):
                scene0b.validate_live_receipt(
                    self.write_json(
                        "scene0b-cross-replay-frame-alias.json", aliased
                    ),
                    self.candidate,
                    self.candidate_sha,
                )
        finally:
            second_manifest_path.write_bytes(second_manifest_bytes)

        chr_mutant = copy.deepcopy(live)
        chr_replay = chr_mutant["replays"][0]
        original_chr = Path(chr_replay["final_bg_chr"]["path"])
        mutated_chr_payload = bytearray(original_chr.read_bytes())
        chr_planes_path = Path(chr_replay["final_physical_planes"]["path"])
        chr_planes_payload = chr_planes_path.read_bytes()
        used_tile = chr_planes_payload[0]
        used_bank = (chr_planes_payload[0x800] >> 3) & 1
        used_address = (
            used_bank * 0x2000
            + scene0b._stage1_chr_address(
                used_tile,
                int(chr_replay["final_physical_planes"]["lcdc"], 16),
            )
        )
        mutated_chr_payload[used_address] ^= 0x01
        mutated_chr = live_root / "mutated-used-final-bg-chr.bin"
        mutated_chr.write_bytes(mutated_chr_payload)
        chr_replay["final_bg_chr"] = scene0b.recompute_final_bg_chr(
            mutated_chr,
            chr_planes_path,
            Path(chr_replay["final_physical_planes"]["metadata_path"]),
            self.candidate.read_bytes(),
            chr_replay["capture_label"],
        )
        self.assertGreater(
            chr_replay["final_bg_chr"]["pattern_mismatches"], 0
        )
        with self.assertRaisesRegex(
            scene0b.ContractError, "referenced BG CHR is noncanonical"
        ):
            scene0b.validate_live_receipt(
                self.write_json(
                    "scene0b-mutated-used-final-bg-chr.json", chr_mutant
                ),
                self.candidate,
                self.candidate_sha,
            )

        static_only = copy.deepcopy(live)
        static_only["replays"] = []
        with self.assertRaises(scene0b.ContractError):
            scene0b.validate_live_receipt(
                self.write_json("scene0b-static-only.json", static_only),
                self.candidate,
                self.candidate_sha,
            )

        unauthenticated = copy.deepcopy(live)
        unauthenticated["replays"][0]["process_teardown"][
            "completion_authenticated"
        ] = False
        with self.assertRaisesRegex(scene0b.ContractError, "not authenticated"):
            scene0b.validate_live_receipt(
                self.write_json(
                    "scene0b-unauthenticated-teardown.json", unauthenticated
                ),
                self.candidate,
                self.candidate_sha,
            )

        bad_scene = copy.deepcopy(live)
        bad_scene["replays"][0]["scene_values"] = ["02"]
        with self.assertRaises(scene0b.ContractError):
            scene0b.validate_live_receipt(
                self.write_json("scene0b-wrong-scene.json", bad_scene),
                self.candidate,
                self.candidate_sha,
            )

        # The reviewed corrupted-wall mask is release-failing.  The separate
        # low-health mask still contains intended hazard color and remains a
        # structural-plane/hazard-oracle route instead.
        legacy_color = copy.deepcopy(live)
        legacy_color["replays"][0]["red_green_artifact_frames"] = 1
        with self.assertRaisesRegex(
            scene0b.ContractError, "rendered visual counters differ"
        ):
            scene0b.validate_live_receipt(
                self.write_json("scene0b-legacy-color.json", legacy_color),
                self.candidate,
                self.candidate_sha,
            )
        low_health_color = copy.deepcopy(live)
        low_health = next(
            row for row in low_health_color["replays"]
            if row["capture_label"] == "operator-low-health-menu-loaded"
        )
        low_health["red_green_artifact_frames"] = 1
        with self.assertRaisesRegex(
            scene0b.ContractError, "rendered visual counters differ"
        ):
            scene0b.validate_live_receipt(
                self.write_json(
                    "scene0b-low-health-color.json", low_health_color
                ),
                self.candidate,
                self.candidate_sha,
            )

        plane_counter = copy.deepcopy(live)
        plane_counter["replays"][0]["final_physical_planes"]["maps"][
            "9800"
        ]["hazard_positions"] += 1
        with self.assertRaisesRegex(
            scene0b.ContractError, "claims differ from the bound dump"
        ):
            scene0b.validate_live_receipt(
                self.write_json(
                    "scene0b-forged-plane-counter.json", plane_counter
                ),
                self.candidate,
                self.candidate_sha,
            )

        stale_final = copy.deepcopy(live)
        stale_replay = stale_final["replays"][0]
        stale_planes = stale_replay["final_physical_planes"]
        original_meta = Path(stale_planes["metadata_path"])
        stale_meta = live_root / "stale-first-post-close.planes.meta"
        first_post_close = (
            stale_replay["rendered_frames"]
            - stale_replay["post_close_frames"] + 1
        )
        stale_meta.write_text(
            original_meta.read_text()
            .replace(
                f"frame={stale_planes['frame']}",
                f"frame={first_post_close}",
            )
            .replace(
                f"sample={stale_planes['sample']}",
                f"sample={first_post_close}",
            )
        )
        capture = next(
            row for row in stale_final["source_captures"]
            if row["label"] == stale_replay["capture_label"]
        )
        source_state = scene0b.gbas_payload(Path(capture["path"]))
        stale_replay["final_physical_planes"] = (
            scene0b.recompute_physical_planes(
                Path(stale_planes["path"]), stale_meta,
                self.canonical_lut,
                scene0b.immutable_source_from_capture(
                    Path(capture["path"]), source_state
                ),
                stale_replay["capture_label"],
            )
        )
        with self.assertRaisesRegex(
            scene0b.ContractError, "not the final post-close sample"
        ):
            scene0b.validate_live_receipt(
                self.write_json("scene0b-stale-final-plane.json", stale_final),
                self.candidate,
                self.candidate_sha,
            )

        # Mirror a non-hazard tile mutation through C1A0, both physical maps,
        # and both attribute planes. Publication consistency and semantics are
        # still clean; only the independently reconstructed operator world
        # baseline can reject this self-consistent corruption.
        mirrored = copy.deepcopy(live)
        replay = mirrored["replays"][0]
        original_plane = Path(replay["final_physical_planes"]["path"])
        mutated_payload = bytearray(original_plane.read_bytes())
        capture = live["source_captures"][0]
        captured_state = scene0b.gbas_payload(Path(capture["path"]))
        immutable_source = scene0b.immutable_source_from_capture(
            Path(capture["path"]), captured_state
        )
        immutable_map = bytearray(0x400)
        for row_index in range(24):
            immutable_map[row_index * 32:row_index * 32 + 24] = (
                immutable_source[row_index * 24:(row_index + 1) * 24]
            )
        hazard_contract = scene0b.load_hazard_tile_contract()
        hazard_envelope = {
            (offset // 24) * 32 + offset % 24
            for offset in hazard_contract.coverage.exact_object_cells
        }
        target = next(
            row_index * 32 + column_index
            for row_index in range(18)
            for column_index in range(1, 20)
            if row_index * 32 + column_index not in hazard_envelope
        )
        target_row, target_column = divmod(target, 32)
        replacement = 0x02 if immutable_map[target] != 0x02 else 0x03
        expected_attr = self.canonical_lut[replacement] & 0x07
        for map_offset in (0, 0x400):
            mutated_payload[map_offset + target] = replacement
        for attr_offset in (0x800, 0xC00):
            mutated_payload[attr_offset + target] = expected_attr
        mutated_payload[
            0x1000 + target_row * 24 + target_column
        ] = replacement
        mirrored_plane = live_root / "mirrored-self-baseline.planes.bin"
        mirrored_plane.write_bytes(mutated_payload)
        metadata = Path(replay["final_physical_planes"]["metadata_path"])
        replay["final_physical_planes"] = scene0b.recompute_physical_planes(
            mirrored_plane, metadata, self.canonical_lut, immutable_source,
            replay["capture_label"],
        )
        self.assertEqual(
            replay["final_physical_planes"]["maps"]["9800"][
                "semantic_mismatches_visible"
            ],
            0,
        )
        self.assertEqual(
            replay["final_physical_planes"]["maps"]["9800"][
                "tile_source_mismatches_visible"
            ],
            0,
        )
        self.assertEqual(
            replay["final_physical_planes"][
                "source_immutable_mismatches_outside_hazard_visible"
            ],
            1,
        )
        with self.assertRaisesRegex(
            scene0b.ContractError, "operator baseline"
        ):
            scene0b.validate_live_receipt(
                self.write_json(
                    "scene0b-mirrored-self-baseline.json", mirrored
                ),
                self.candidate,
                self.candidate_sha,
            )

        short_repair = copy.deepcopy(live)
        short_repair["replays"][0]["repair_settle_frames"] = (
            scene0b.REPAIR_SETTLE_FRAMES - 1
        )
        with self.assertRaisesRegex(
            scene0b.ContractError, "repair_settle_frames"
        ):
            scene0b.validate_live_receipt(
                self.write_json("scene0b-short-repair.json", short_repair),
                self.candidate,
                self.candidate_sha,
            )

        for field in (
            "attr_unreadable_samples", "semantic_unreadable_samples",
            "immutable_tile_unreadable_samples", "cram_unreadable_samples",
        ):
            unreadable = copy.deepcopy(live)
            unreadable["replays"][0][field] = 1
            with self.assertRaises(scene0b.ContractError):
                scene0b.validate_live_receipt(
                    self.write_json(
                        f"scene0b-{field}.json", unreadable
                    ),
                    self.candidate,
                    self.candidate_sha,
                )

        trace_mutant = copy.deepcopy(live)
        original_trace = Path(trace_mutant["replays"][0]["state_trace"]["path"])
        trace_rows = [
            json.loads(line) for line in original_trace.read_text().splitlines()
        ]
        trace_rows[1]["immutable_tile_mismatches"] = 1
        mutated_trace = live_root / "mutated-state-trace.jsonl"
        mutated_trace.write_text("\n".join(
            json.dumps(row, sort_keys=True, separators=(",", ":"))
            for row in trace_rows
        ) + "\n")
        trace_mutant["replays"][0]["state_trace"] = {
            "path": str(mutated_trace),
            "sha256": scene0b.sha256(mutated_trace),
        }
        with self.assertRaisesRegex(
            scene0b.ContractError, "raw/token trace differs"
        ):
            scene0b.validate_live_receipt(
                self.write_json("scene0b-mutated-trace.json", trace_mutant),
                self.candidate,
                self.candidate_sha,
            )

        lcdc_mutant = copy.deepcopy(live)
        lcdc_rows = [
            json.loads(line) for line in original_trace.read_text().splitlines()
        ]
        lcdc_rows[1]["lcdc"] = 0x03
        mutated_lcdc_trace = live_root / "mutated-lcdc-state-trace.jsonl"
        mutated_lcdc_trace.write_text("\n".join(
            json.dumps(row, sort_keys=True, separators=(",", ":"))
            for row in lcdc_rows
        ) + "\n")
        lcdc_mutant["replays"][0]["state_trace"] = {
            "path": str(mutated_lcdc_trace),
            "sha256": scene0b.sha256(mutated_lcdc_trace),
        }
        with self.assertRaisesRegex(
            scene0b.ContractError, "required Stage-1 LCDC bits"
        ):
            scene0b.validate_live_receipt(
                self.write_json("scene0b-mutated-lcdc.json", lcdc_mutant),
                self.candidate,
                self.candidate_sha,
            )

        fingerprint_mutant = copy.deepcopy(live)
        fingerprint_mutant["replays"][0][
            "semantic_fingerprint_sha256"
        ] = "0" * 64
        with self.assertRaisesRegex(
            scene0b.ContractError, "semantic fingerprint differs"
        ):
            scene0b.validate_live_receipt(
                self.write_json(
                    "scene0b-mutated-fingerprint.json", fingerprint_mutant
                ),
                self.candidate,
                self.candidate_sha,
            )

        artifact = copy.deepcopy(live)
        artifact["replays"][0][
            "postrepair_semantic_attr_mismatch_frames"
        ] = 1
        with self.assertRaises(scene0b.ContractError):
            scene0b.validate_live_receipt(
                self.write_json("scene0b-semantic-artifact.json", artifact),
                self.candidate,
                self.candidate_sha,
            )

        no_baseline = copy.deepcopy(live)
        no_baseline["replays"][0]["baseline_ready"] = False
        with self.assertRaises(scene0b.ContractError):
            scene0b.validate_live_receipt(
                self.write_json("scene0b-no-baseline.json", no_baseline),
                self.candidate,
                self.candidate_sha,
            )

        lut_mutant = copy.deepcopy(live)
        lut_mutant["replays"][0]["runtime_lut_mutation_frames"] = 1
        with self.assertRaises(scene0b.ContractError):
            scene0b.validate_live_receipt(
                self.write_json("scene0b-lut-mutant.json", lut_mutant),
                self.candidate,
                self.candidate_sha,
            )

        bad_retarget = copy.deepcopy(live)
        bad_retarget["replays"][0][
            "retarget_changed_gbAs_offsets"
        ] = [4, 5, 6, 7, 8, 31]
        with self.assertRaises(scene0b.ContractError):
            scene0b.validate_live_receipt(
                self.write_json("scene0b-bad-retarget.json", bad_retarget),
                self.candidate,
                self.candidate_sha,
            )

        bad_identity = copy.deepcopy(live)
        bad_identity["replays"][0][
            "retargeted_state_rom_identity"
        ] = "00" * 16
        with self.assertRaises(scene0b.ContractError):
            scene0b.validate_live_receipt(
                self.write_json("scene0b-bad-identity.json", bad_identity),
                self.candidate,
                self.candidate_sha,
            )

    def test_standalone_ready_gate_set_remains_complete(self) -> None:
        gate_names = deploy.HARDWARE_TEST_READY_GATES
        command_gates = deploy.HARDWARE_TEST_READY_COMMAND_GATES
        self.assertIn("independent_room01_wall_north_replay", gate_names)
        self.assertIn("captured_scene0b_transition_menu", gate_names)
        self.assertIn("stage1_current_pickup_state", gate_names)
        self.assertIn(
            "stage1_current_pickup_host_palettes", gate_names
        )
        self.assertIn("native_select_menu_window_exact", gate_names)
        self.assertIn("cold_and_returned_title_nightfall", gate_names)
        self.assertIn(
            "natural_stage1_pickup_temporal_raster", gate_names
        )
        self.assertIn(
            "independent_room01_wall_north_replay", command_gates
        )
        self.assertIn("captured_scene0b_transition_menu", command_gates)
        self.assertIn("stage1_current_pickup_state", command_gates)
        self.assertIn(
            "stage1_current_pickup_host_palettes", command_gates
        )
        self.assertIn(
            "native_select_menu_window_exact", command_gates
        )
        self.assertIn(
            "cold_and_returned_title_nightfall", command_gates
        )
        self.assertIn(
            "natural_stage1_pickup_temporal_raster", command_gates
        )
        tools = ready.tool_identity()
        self.assertEqual(
            Path(tools["native_menu_window_verifier"]["path"]),
            ready.MENU_WINDOW_VERIFIER,
        )
        self.assertEqual(
            Path(tools["natural_pickup_raster_verifier"]["path"]),
            ready.STAGE1_NO_BLEED_VERIFIER,
        )
        self.assertEqual(
            ready.SCHEMA, "penta-stage1-reported-regressions-ready-v10"
        )
        old = json.loads(
            (ROOT / "tmp/stage1-report-hook/r292-final-interceptor-v2/receipt.json")
            .read_text()
        )
        self.assertNotEqual(old["schema"], ready.SCHEMA)
        self.assertNotEqual(set(old["gates"]), set(gate_names))

    def test_every_reported_issue_is_bound_to_a_passing_gate(self) -> None:
        gates = {
            name: {"status": deploy.HARDWARE_TEST_READY_GATE_STATUSES[name]}
            for name in deploy.HARDWARE_TEST_READY_GATES
        }
        coverage = ready.reported_issue_coverage(gates)
        self.assertEqual(set(coverage), set(ready.REPORTED_ISSUE_CONTRACT))
        self.assertEqual(len(coverage), 13)
        for issue, item in coverage.items():
            with self.subTest(issue=issue):
                self.assertEqual(item["status"], "DETERMINISTIC_GATE")
                self.assertTrue(item["gates"])
                self.assertTrue(item["assertions"])

        broken = copy.deepcopy(gates)
        broken["natural_blank_sram_menu_and_art_loader"]["status"] = "FAIL"
        with self.assertRaisesRegex(ready.NotReady, "menu_exit_red_green"):
            ready.reported_issue_coverage(broken)

    def test_standalone_tool_identity_omits_retired_stop_gate(self) -> None:
        tools = ready.tool_identity()
        self.assertNotIn("codex_stop_hook", tools)
        self.assertNotIn("codex_hooks_definition", tools)
        self.assertNotIn("codex_stop_gate_config", tools)

    def test_deployer_tool_identity_matches_standalone_verifier(self) -> None:
        self.assertEqual(
            set(ready.tool_identity()),
            set(deploy.hardware_test_ready_tool_paths()),
        )

    def test_menu_race_accepts_exact_reviewed_reset_generations(self) -> None:
        legacy = (
            ROOT / "tmp/stage1-exact-background-r292/candidate.gb"
        ).read_bytes()
        routed = (
            ROOT / "tmp/stage1-scene0b-runtime-selfheal-r313/candidate.gb"
        ).read_bytes()
        atomic = (
            ROOT / "tmp/stage4-cache-key-r534/candidate.gb"
        ).read_bytes()
        visible_close = (
            ROOT / "tmp/r536-penta-seam-vram-current636/candidate.gb"
        ).read_bytes()
        self.assertEqual(
            menu_race.require_menu_reset_lifecycle(legacy),
            "legacy-direct-clear",
        )
        self.assertEqual(
            menu_race.require_menu_reset_lifecycle(routed),
            "r313-selfheal-mux",
        )
        self.assertEqual(
            menu_race.require_menu_reset_lifecycle(atomic),
            "r364-atomic-menu-exit",
        )
        self.assertEqual(
            menu_race.require_menu_reset_lifecycle(visible_close),
            "r535-visible-menu-close",
        )
        # Exercise the complete static contract, not only the lifecycle helper.
        menu_race.require_static_bytes(legacy)
        menu_race.require_static_bytes(routed)
        menu_race.require_static_bytes(atomic)
        menu_race.require_static_bytes(visible_close)

        atomic_offsets = (
            menu_race.bank_offset_for(
                menu_race.MENU_RESET_ROUTED_BANK,
                menu_race.MENU_RESET_ROUTED_R325_WRAPPER_ADDR,
            ) + 26,
            menu_race.bank_offset_for(
                menu_race.MENU_RESET_ROUTED_BANK,
                menu_race.MENU_RESET_ROUTED_R364_ATOMIC_EXIT_ADDR,
            ),
        )
        for offset in atomic_offsets:
            with self.subTest(atomic_contract=hex(offset)):
                mutant = bytearray(atomic)
                mutant[offset] ^= 0x01
                with self.assertRaises(menu_race.StaticGateError):
                    menu_race.require_menu_reset_lifecycle(bytes(mutant))

        visible_close_offsets = (
            menu_race.bank_offset_for(
                menu_race.MENU_RESET_ROUTED_BANK,
                menu_race.MENU_RESET_ROUTED_HELPER_ADDR,
            ) + 77,
            menu_race.bank_offset_for(
                menu_race.MENU_RESET_ROUTED_BANK,
                menu_race.MENU_RESET_ROUTED_R535_PAGE_ADDR,
            ),
            menu_race.bank_offset_for(
                menu_race.MENU_RESET_ROUTED_BANK,
                menu_race.MENU_RESET_ROUTED_R535_VISIBLE_REPAIR_ADDR,
            ),
            menu_race.bank_offset_for(
                menu_race.MENU_RESET_ROUTED_BANK,
                menu_race.MENU_RESET_ROUTED_R535_PAGE_ADDR,
            ) + 0xFF,
        )
        for offset in visible_close_offsets:
            with self.subTest(visible_close_contract=hex(offset)):
                mutant = bytearray(visible_close)
                mutant[offset] ^= 0x01
                with self.assertRaises(menu_race.StaticGateError):
                    menu_race.require_menu_reset_lifecycle(bytes(mutant))

    def test_menu_race_rejects_tail_and_routed_bridge_mutations(self) -> None:
        routed = bytearray((
            ROOT / "tmp/stage1-scene0b-runtime-selfheal-r313/candidate.gb"
        ).read_bytes())
        tail = menu_race.MENU_RESET_ADDR + len(
            menu_race.MENU_RESET_PREFIX
        )
        for index in range(len(menu_race.MENU_RESET_ROUTED_TAIL)):
            with self.subTest(tail_byte=index):
                mutant = bytearray(routed)
                mutant[tail + index] ^= 0x01
                with self.assertRaises(menu_race.StaticGateError):
                    menu_race.require_menu_reset_lifecycle(bytes(mutant))

        legacy_tail_mutant = bytearray(routed)
        legacy_tail_mutant[
            tail:tail + len(menu_race.MENU_RESET_LEGACY_TAIL)
        ] = menu_race.MENU_RESET_LEGACY_TAIL
        with self.assertRaisesRegex(
            menu_race.StaticGateError, "legacy menu reset fixed-stub"
        ):
            menu_race.require_menu_reset_lifecycle(bytes(legacy_tail_mutant))

        infrastructure = (
            menu_race.MENU_RESET_ROUTED_FIXED_STUB_ADDR,
            menu_race.MENU_RESET_ROUTED_DISPATCH_ADDR,
            menu_race.MENU_RESET_ROUTED_MAPPER_ENTRY_ADDR,
            menu_race.MENU_RESET_ROUTED_MAPPER_BODY_ADDR,
            menu_race.MENU_RESET_ROUTED_BANK1_THUNK_ADDR,
            menu_race.bank_offset_for(
                menu_race.MENU_RESET_ROUTED_BANK,
                menu_race.MENU_RESET_ROUTED_HELPER_ADDR,
            ),
        )
        for offset in infrastructure:
            with self.subTest(routed_infrastructure=hex(offset)):
                mutant = bytearray(routed)
                mutant[offset] ^= 0x01
                with self.assertRaises(menu_race.StaticGateError):
                    menu_race.require_menu_reset_lifecycle(bytes(mutant))


if __name__ == "__main__":
    unittest.main()
