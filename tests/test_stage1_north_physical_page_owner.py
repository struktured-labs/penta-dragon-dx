"""Focused controls for Stage-1 north physical-page ownership evidence."""

from __future__ import annotations

import importlib.util
from pathlib import Path
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
VERIFIER = ROOT / "scripts/diagnostics/verify_stage1_north_integrity.py"
PROBE = ROOT / "scripts/diagnostics/probe_stage1_north_integrity.lua"
sys.path.insert(0, str(ROOT / "scripts/diagnostics"))


def load_verifier():
    spec = importlib.util.spec_from_file_location("north_owner_test", VERIFIER)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


north = load_verifier()


def trajectory_record(
    *,
    status: int = north.OWNER_STATUS_CGB_OWNED,
    owner_room: int = 5,
    epoch: int = 1,
    logical_room: int = 5,
    lcdc: int = 0x83,
    gameplay_frame: int = 1,
    tile: int = 0,
    attr: int = 0,
) -> bytes:
    header = bytearray(north.TRAJECTORY_HEADER_SIZE)
    header[0:2] = gameplay_frame.to_bytes(2, "little")
    header[2] = logical_room
    header[3:5] = (1).to_bytes(2, "little")
    header[5] = lcdc
    header[19] = 2
    header[20] = 1
    header[26] = 1
    header[27] = status
    header[28] = owner_room
    header[29:31] = epoch.to_bytes(2, "little")
    tiles = bytearray(north.TRAJECTORY_VIEW_SIZE)
    attrs = bytearray(north.TRAJECTORY_VIEW_SIZE)
    tiles[0] = tile
    attrs[0] = attr
    return bytes(header + tiles + attrs)


class NorthPhysicalPageOwnerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        (ROOT / "tmp").mkdir(exist_ok=True)

    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory(
            prefix="north-owner-", dir=ROOT / "tmp"
        )
        self.root = Path(self.temp.name)

    def tearDown(self) -> None:
        self.temp.cleanup()

    @staticmethod
    def rom_with(primary: bytes) -> bytes:
        rom = bytearray(0x80000)
        rom[
            north.PRIMARY_PUBLISHER_ADDR:north.PRIMARY_PUBLISHER_END
        ] = primary
        return bytes(rom)

    def test_exact_legacy_and_r320_publication_boundaries(self) -> None:
        legacy = north.detect_publication_boundary(
            self.rom_with(north.OLD_PRIMARY)
        )
        self.assertEqual(legacy["variant"], "legacy-v1")
        self.assertEqual(legacy["publication_pc"], 0x12EC)
        modern = north.detect_publication_boundary(
            self.rom_with(north.NEW_PRIMARY)
        )
        self.assertEqual(modern["variant"], "r320-v1")
        self.assertEqual(modern["publication_pc"], 0x12FF)
        self.assertNotEqual(
            legacy["primary_sha256"], modern["primary_sha256"]
        )

    def test_every_primary_byte_mutation_is_rejected(self) -> None:
        for name, primary in (
            ("legacy", north.OLD_PRIMARY),
            ("r320", north.NEW_PRIMARY),
        ):
            for offset in range(len(primary)):
                with self.subTest(variant=name, offset=offset):
                    mutant = bytearray(primary)
                    mutant[offset] ^= 0x01
                    with self.assertRaisesRegex(
                        ValueError, "primary publisher evidence is missing"
                    ):
                        north.detect_publication_boundary(
                            self.rom_with(bytes(mutant))
                        )

    def test_neither_and_synthetic_ambiguity_fail_closed(self) -> None:
        with self.assertRaisesRegex(ValueError, "missing"):
            north.select_publication_variant([])
        matches = list(north.PUBLICATION_VARIANTS.items())
        with self.assertRaisesRegex(ValueError, "ambiguous"):
            north.select_publication_variant(matches)

    @staticmethod
    def owner_report(
        publication: dict[str, object], *, cgb: bool = True
    ) -> dict[str, str]:
        report = {
            "trajectory_schema": north.TRAJECTORY_SCHEMA,
            "cgb_rom": "1" if cgb else "0",
            "map_owner_publication_variant": str(publication["variant"]),
            "map_owner_publication_pc": str(
                publication["publication_pc_hex"]
            ),
            "map_owner_publication_primary_sha256": str(
                publication["primary_sha256"]
            ),
            "map_owner_publication_primary_hex": str(
                publication["primary_hex"]
            ),
            "map_owner_arm_events": "3" if cgb else "0",
            "map_owner_publications": "2" if cgb else "0",
            "map_owner_reused_commits": "1" if cgb else "0",
            "map_owner_superseded_arms": "0",
            "map_owner_invalid_arms": "0",
            "map_owner_invalid_commits": "0",
            "map_owner_missing_commits": "0",
            "map_owner_missing_trajectory_frames": "0",
            "map_owner_invalid_trajectory_frames": "0",
            "map_owner_trace": "fixture",
        }
        return report

    def test_swapped_or_hidden_publication_metadata_is_rejected(self) -> None:
        publication = north.detect_publication_boundary(
            self.rom_with(north.NEW_PRIMARY)
        )
        report = self.owner_report(publication)
        exact = north.physical_page_owner_report(
            report, expect_cgb=True, expected_publication=publication
        )
        self.assertTrue(exact["exact"])
        mutations = {
            "map_owner_publication_pc": "12EC",
            "map_owner_publication_variant": "legacy-v1",
            "map_owner_publication_primary_sha256": "0" * 64,
            "map_owner_publication_primary_hex": "00" * 35,
        }
        for field, value in mutations.items():
            with self.subTest(field=field):
                mutant = dict(report)
                mutant[field] = value
                result = north.physical_page_owner_report(
                    mutant,
                    expect_cgb=True,
                    expected_publication=publication,
                )
                self.assertFalse(result["exact"])
                self.assertIn(f"{field}-mismatch", result["errors"])

    def write_trajectory(self, name: str, records: list[bytes]) -> Path:
        path = self.root / name
        path.write_bytes(b"".join(records))
        return path

    def test_v3_parser_supports_owned_cgb_and_explicit_dmg(self) -> None:
        cgb_path = self.write_trajectory(
            "cgb.bin", [trajectory_record(owner_room=5, epoch=7)]
        )
        parsed = north.read_trajectory(
            cgb_path, expected_owner_mode="cgb"
        )
        self.assertEqual(parsed[0]["page_owner_room"], 5)
        self.assertEqual(parsed[0]["page_owner_epoch"], 7)
        self.assertEqual(parsed[0]["page_owner_base"], 0x9800)

        dmg_path = self.write_trajectory(
            "dmg.bin",
            [trajectory_record(
                status=north.OWNER_STATUS_DMG,
                owner_room=0xFF,
                epoch=0xFFFF,
            )],
        )
        dmg = north.read_trajectory(dmg_path, expected_owner_mode="dmg")
        self.assertEqual(dmg[0]["page_owner_status"], north.OWNER_STATUS_DMG)
        with self.assertRaisesRegex(ValueError, "DMG ownership"):
            north.read_trajectory(dmg_path, expected_owner_mode="cgb")

    def test_parser_rejects_malformed_and_mutating_owner_evidence(self) -> None:
        cases = {
            "unknown-status": [trajectory_record(
                status=0x77, owner_room=0xFF, epoch=0xFFFF
            )],
            "bad-missing-sentinel": [trajectory_record(
                status=north.OWNER_STATUS_CGB_MISSING,
                owner_room=5,
                epoch=1,
            )],
            "epoch-regression": [
                trajectory_record(epoch=2, gameplay_frame=1),
                trajectory_record(epoch=1, gameplay_frame=2),
            ],
            "room-mutation": [
                trajectory_record(owner_room=5, epoch=2, gameplay_frame=1),
                trajectory_record(owner_room=1, epoch=2, gameplay_frame=2),
            ],
        }
        for name, records in cases.items():
            with self.subTest(case=name):
                path = self.write_trajectory(f"{name}.bin", records)
                with self.assertRaises(ValueError):
                    north.read_trajectory(path, expected_owner_mode="cgb")

    def test_prepublication_visual_stream_cannot_claim_page_ownership(self) -> None:
        opening = self.write_trajectory(
            "opening-visual.bin",
            [trajectory_record(
                status=north.OWNER_STATUS_CGB_MISSING,
                owner_room=0xFF,
                epoch=0xFFFF,
            )],
        )
        self.assertTrue(north.prepublication_visual_report(opening)["exact"])
        contaminated = self.write_trajectory(
            "contaminated-opening-visual.bin", [trajectory_record()]
        )
        report = north.prepublication_visual_report(contaminated)
        self.assertFalse(report["exact"])
        self.assertEqual(
            report["first_error"]["owner_status"], "cgb-publication-owned"
        )

    def test_attr_oracle_uses_owner_not_early_logical_room(self) -> None:
        path = self.write_trajectory(
            "owner-vs-logical.bin",
            [trajectory_record(
                logical_room=1,
                owner_room=5,
                tile=0x24,
                attr=0x00,
            )],
        )
        row = north.read_trajectory(path, expected_owner_mode="cgb")[0]
        result = north.trajectory_attribute_integrity(
            [row], north.REVIEWED_WALL_CONTEXT,
            north.REVIEWED_WALL_TILE_CONTEXT,
        )
        self.assertTrue(result["exact"])
        self.assertEqual(
            result["physical_page_ownership"]["owner_transitions"][0]
            ["room"],
            5,
        )

        wrong = dict(row)
        wrong["attrs"] = bytes([0x06]) + bytes(
            north.TRAJECTORY_VIEW_SIZE - 1
        )
        rejected = north.trajectory_attribute_integrity(
            [wrong], north.REVIEWED_WALL_CONTEXT,
            north.REVIEWED_WALL_TILE_CONTEXT,
        )
        self.assertFalse(rejected["exact"])
        self.assertEqual(rejected["first_mismatch"]["display_room"], 5)

    def test_lua_wires_ffe5_owner_to_exact_detected_lcdc_store(self) -> None:
        source = PROBE.read_text()
        self.assertIn("room = emu:read8(0xFFE5)", source)
        self.assertIn(
            "arm_physical_map_publication, 0x42A7, 1", source
        )
        self.assertIn(
            "commit_physical_map_publication, publication_pc,", source
        )
        self.assertIn("publication_segment) > 0", source)
        self.assertIn("STAGE1_NORTH_PUBLICATION_VARIANT", source)
        self.assertIn("STAGE1_NORTH_PUBLICATION_PRIMARY_SHA256", source)
        self.assertIn("owner_status, owner_room", source)
        self.assertIn("owner_epoch & 0xFF", source)

    def test_cli_prioritizes_geometry_before_secondary_oracles(self) -> None:
        source = VERIFIER.read_text()
        geometry = source.index("if geometry_differences_present:")
        ownership = source.index("if not physical_page_ownership_ok:")
        wall = source.index("if not reviewed_wall_oracle_ok:")
        attrs = source.index("if not attribute_trajectory_ok:")
        self.assertLess(geometry, ownership)
        self.assertLess(geometry, wall)
        self.assertLess(geometry, attrs)

    def test_target_only_cannot_bypass_geometry_or_owner_evidence(self) -> None:
        source = VERIFIER.read_text()
        start = source.index("def target_only_route_contract(")
        end = source.index("\n\ndef compare_visible_terrain", start)
        gate = source[start:end]
        self.assertIn("and not geometry_differences_present", gate)
        self.assertIn("and physical_page_ownership_ok", gate)
        self.assertIn("and attribute_trajectory_ok", gate)

        trajectory = {
            "matched_records": 100,
            "unmatched_progress_records": 0,
            "maximum_viewport_tile_differences": 0,
            "unexpected_logical_state_records": 0,
            "unmatched_display_state_records": 0,
        }
        self.assertTrue(north.target_only_route_contract(
            trajectory,
            geometry_differences_present=False,
            service_presentation_ok=True,
            physical_page_ownership_ok=True,
            attribute_trajectory_ok=True,
        ))
        # Model the exact class of r318 failure: one full-route viewport has
        # 101 bad cells while every secondary oracle remains green.
        trajectory["maximum_viewport_tile_differences"] = 101
        self.assertFalse(north.target_only_route_contract(
            trajectory,
            geometry_differences_present=True,
            service_presentation_ok=True,
            physical_page_ownership_ok=True,
            attribute_trajectory_ok=True,
        ))
        trajectory["maximum_viewport_tile_differences"] = 0
        self.assertFalse(north.target_only_route_contract(
            trajectory,
            geometry_differences_present=False,
            service_presentation_ok=True,
            physical_page_ownership_ok=False,
            attribute_trajectory_ok=True,
        ))


if __name__ == "__main__":
    unittest.main()
