#!/usr/bin/env python3
"""Offline mutation controls for the Stage-1 tilemap publication oracle."""

from __future__ import annotations

import copy
from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
DIAGNOSTICS = ROOT / "scripts" / "diagnostics"
sys.path.insert(0, str(DIAGNOSTICS))

import verify_stage1_tilemap_copy as tilemap  # noqa: E402
import verify_pocket_visual_receipts as pocket  # noqa: E402


class Stage1TilemapPublicationOracleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.probe = tilemap.PROBE.read_text()
        cls.rom_sha256 = "a" * 64
        cls.valid = tilemap._synthetic_passing_report(cls.rom_sha256)

    def assert_report_rejected(self, **changes: str) -> None:
        report = copy.deepcopy(self.valid)
        report.update(changes)
        self.assertTrue(
            tilemap.publication_oracle_report_failures(
                report, expected_rom_sha256=self.rom_sha256,
            ),
            changes,
        )

    def assert_probe_replacement_rejected(self, old: str, new: str) -> None:
        mutant = self.probe.replace(old, new, 1)
        self.assertNotEqual(mutant, self.probe, old)
        self.assertTrue(
            tilemap.probe_publication_oracle_failures(mutant),
            new,
        )

    def test_checked_probe_has_no_completion_source_or_live_lut_oracle(self) -> None:
        self.assertEqual(
            tilemap.probe_publication_oracle_failures(self.probe), []
        )
        source_mutant = self.probe.replace(
            "local wanted = expected[source_offset + 1]",
            "local wanted = completion_source[source_offset + 1]",
            1,
        )
        self.assertTrue(
            tilemap.probe_publication_oracle_failures(source_mutant)
        )
        lut_mutant = self.probe.replace(
            "local wanted_attr = expected_attributes[source_offset + 1]",
            "local wanted_attr = emu:read8(0xC600 + wanted)",
            1,
        )
        self.assertTrue(tilemap.probe_publication_oracle_failures(lut_mutant))

    def test_lua_expected_builder_semantics_are_pinned(self) -> None:
        controls = (
            (
                "expected[offset] = "
                "independent_expected_palette(tile, room, ffe5)",
                "expected[offset] = emu:read8(0xC600 + tile)",
            ),
            (
                "local effective_room = ffe5 ~= 0 and ffe5 or room",
                "local effective_room = room",
            ),
            (
                "local effective_room = ffe5 ~= 0 and ffe5 or room",
                "local effective_room = ffe5",
            ),
            (
                "return string.byte(canonical_lut, tile + 1)",
                "return 0x00",
            ),
            (
                "expected[offset] = "
                "independent_expected_palette(tile, room, ffe5)",
                "expected[offset] = tile & 0x07",
            ),
        )
        for old, new in controls:
            with self.subTest(new=new):
                self.assert_probe_replacement_rejected(old, new)

    def test_completion_source_is_diagnostic_only(self) -> None:
        controls = (
            (
                "      local wanted = expected[source_offset + 1]",
                "      expected[source_offset + 1] = "
                "completion_source[source_offset + 1]\n"
                "      local wanted = expected[source_offset + 1]",
            ),
            (
                "      local wanted = expected[source_offset + 1]",
                "      local completion_alias = "
                "completion_source[source_offset + 1]\n"
                "      local wanted = completion_alias",
            ),
        )
        for old, new in controls:
            with self.subTest(new=new):
                self.assert_probe_replacement_rejected(old, new)

    def test_entry_to_completion_handoff_is_immutable(self) -> None:
        controls = (
            (
                "assert(#canonical_lut == 0x100,\n"
                '  "Stage-1 canonical attribute LUT must be exactly 256 bytes")',
                "assert(#canonical_lut == 0x100,\n"
                '  "Stage-1 canonical attribute LUT must be exactly 256 bytes")\n'
                "canonical_lut = string.rep(string.char(0), 0x100)",
            ),
            (
                "      pending_attributes = expected_attribute_plane(\n"
                "        pending_source, pending_room, pending_ffe5)",
                "      pending_attributes = expected_attribute_plane(\n"
                "        pending_source, pending_room, pending_ffe5)\n"
                "      for offset, tile in ipairs(pending_source) do\n"
                "        pending_attributes[offset] = "
                "emu:read8(0xC600 + tile)\n"
                "      end",
            ),
            (
                "    compare_completed_copy(base, pending_source, "
                "pending_attributes, true)",
                "    pending_source = packed_source()\n"
                "    compare_completed_copy(base, pending_source, "
                "pending_attributes, true)",
            ),
            (
                "    compare_completed_copy(base, pending_source, "
                "pending_attributes, true)",
                "    pending_attributes = expected_attribute_plane(\n"
                "      packed_source(), pending_room, pending_ffe5)\n"
                "    compare_completed_copy(base, pending_source, "
                "pending_attributes, true)",
            ),
        )
        for old, new in controls:
            with self.subTest(new=new):
                self.assert_probe_replacement_rejected(old, new)

    def test_model_is_entry_owned_and_independent_of_live_c600(self) -> None:
        canonical = bytes(index & 7 for index in range(256))
        entry = bytes([0x41] * tilemap.CELLS_PER_PUBLICATION)
        expected = tilemap.independent_expected_plane(
            entry, 0x12, 0x00, canonical,
        )
        completion_source = bytes([0x42]) + entry[1:]
        corrupt_live_c600 = bytearray(canonical)
        corrupt_live_c600[0x41] = 0
        self.assertNotEqual(completion_source, entry)
        self.assertEqual(expected[0], canonical[0x41])
        self.assertNotEqual(expected[0], corrupt_live_c600[0x41])
        self.assertEqual(
            tilemap.independent_expected_plane(
                entry, 0x12, 0x00, canonical,
            ),
            expected,
        )

    def test_effective_room_wall_override_is_explicit(self) -> None:
        canonical = bytes(256)
        for tile in (0x24, 0x27, 0x30, 0x33):
            with self.subTest(tile=f"{tile:02X}"):
                self.assertEqual(
                    tilemap.independent_expected_palette(
                        tile, 0x12, 0x01, canonical,
                    ),
                    6,
                )
                self.assertEqual(
                    tilemap.independent_expected_palette(
                        tile, 0x12, 0x00, canonical,
                    ),
                    0,
                )

    def test_compiled_tooth_bank_bit_is_an_expected_attribute_bit(self) -> None:
        canonical = bytearray(0x100)
        canonical[0x64] = 0x0F
        self.assertEqual(
            tilemap.independent_expected_palette(
                0x64, 0x08, 0x08, bytes(canonical),
            ),
            0x0F,
        )

    def test_dirty_destination_decode_rejects_all_tag_aliases(self) -> None:
        self.assertIn("if tag == 0x99 then base = 0x9800", self.probe)
        self.assertIn("elseif tag == 0x9D then base = 0x9C00", self.probe)
        self.assertNotIn("tag & 0xFC", self.probe)
        self.assert_probe_replacement_rejected(
            "if tag == 0x99 then base = 0x9800\n"
            "      elseif tag == 0x9D then base = 0x9C00",
            "if (tag & 0xFC) == 0x98 then base = 0x9800\n"
            "      elseif (tag & 0xFC) == 0x9C then base = 0x9C00",
        )
        for tag in range(256):
            decoded = 0x9800 if tag == 0x99 else (
                0x9C00 if tag == 0x9D else 0
            )
            with self.subTest(tag=f"{tag:02X}"):
                self.assertEqual(decoded != 0, tag in {0x99, 0x9D})

    def test_valid_owned_report_is_accepted(self) -> None:
        self.assertEqual(
            tilemap.publication_oracle_report_failures(
                self.valid, expected_rom_sha256=self.rom_sha256,
            ),
            [],
        )

    def test_source_drift_false_pass_is_rejected(self) -> None:
        self.assert_report_rejected(
            source_changed_copies="1", source_changed_cells="1",
        )

    def test_live_lut_false_pass_is_rejected(self) -> None:
        self.assert_report_rejected(
            attribute_mismatch_copies="1", attribute_mismatch_cells="1",
        )

    def test_pure_only_attribute_vacuity_is_rejected(self) -> None:
        self.assert_report_rejected(
            atomic_completions="0",
            pure_completions="2",
            exact_copies="2",
            attribute_checked_copies="0",
            ordinary_attribute_model_copies="0",
            ordinary_attribute_model_cells="0",
        )

    def test_per_fixture_publication_vacuity_is_rejected(self) -> None:
        self.assert_report_rejected(
            atomic_completions="0",
            pure_completions="0",
            exact_copies="0",
            publication_model_copies="0",
            publication_model_cells="0",
            attribute_checked_copies="0",
            ordinary_attribute_model_copies="0",
            ordinary_attribute_model_cells="0",
        )

    def test_missing_or_incomplete_ownership_is_rejected(self) -> None:
        for field, value in (
            ("publication_model_copies", "1"),
            ("publication_model_cells", "575"),
            ("ordinary_attribute_model_copies", "0"),
            ("ordinary_attribute_model_cells", "575"),
            ("oracle_schema", "old-self-grading-schema"),
            ("semantic_overlay_owner", "ordinary-tilemap-oracle"),
        ):
            with self.subTest(field=field):
                self.assert_report_rejected(**{field: value})

    def test_pocket_aggregate_requires_each_owned_fixture(self) -> None:
        rom_bytes = (
            ROOT / "tmp/stage4-cache-key-r534/candidate.gb"
        ).read_bytes()
        copier_sha256 = tilemap.sha256_bytes(
            tilemap.reviewed_postcomputed_copier(rom_bytes)
        )
        lut_sha256 = tilemap.sha256_bytes(
            tilemap.reviewed_stage1_lut(rom_bytes)
        )
        reports: list[tuple[Path, dict[str, str]]] = []
        for index, destination in enumerate(("9800", "9C00", "9800,9C00")):
            report = tilemap._synthetic_passing_report(self.rom_sha256)
            report.update({
                "copier_sha256": copier_sha256,
                "canonical_lut_sha256": lut_sha256,
                "atomic_completions": "1",
                "pure_completions": "999",
                "exact_copies": "1000",
                "publication_model_copies": "1000",
                "publication_model_cells": str(
                    1000 * tilemap.CELLS_PER_PUBLICATION
                ),
                "destinations": destination,
            })
            reports.append((Path(f"fixture-{index}.report"), report))
        failures: list[str] = []
        evidence = pocket.validate_tilemap_reports(
            reports, self.rom_sha256, failures, rom_bytes,
        )
        self.assertEqual(failures, [])
        self.assertEqual(evidence["exact_copies"], 3000)
        self.assertEqual(evidence["atomic_completions"], 3)

        mutated = copy.deepcopy(reports)
        mutated[1][1]["atomic_completions"] = "0"
        mutated[1][1]["pure_completions"] = "1000"
        mutated[1][1]["attribute_checked_copies"] = "0"
        mutated[1][1]["ordinary_attribute_model_copies"] = "0"
        mutated[1][1]["ordinary_attribute_model_cells"] = "0"
        failures = []
        pocket.validate_tilemap_reports(
            mutated, self.rom_sha256, failures, rom_bytes,
        )
        self.assertTrue(failures)

        mutated = copy.deepcopy(reports)
        mutated[2][1]["source_changed_copies"] = "1"
        mutated[2][1]["source_changed_cells"] = "1"
        failures = []
        pocket.validate_tilemap_reports(
            mutated, self.rom_sha256, failures, rom_bytes,
        )
        self.assertTrue(failures)

    def test_reviewed_candidate_lut_is_sha_pinned(self) -> None:
        candidate = (
            ROOT / "tmp/stage4-delay-trim-r344/candidate.gb"
        )
        if not candidate.is_file():
            self.skipTest("r344 candidate artifact is not present")
        table = tilemap.reviewed_stage1_lut(candidate.read_bytes())
        self.assertEqual(tilemap.sha256_bytes(table),
                         tilemap.CANONICAL_STAGE1_LUT_SHA256)
        copier = tilemap.reviewed_postcomputed_copier(candidate.read_bytes())
        self.assertEqual(
            tilemap.sha256_bytes(copier),
            tilemap.REVIEWED_POSTCOMPUTED_COPIER_SHA256,
        )
        mutated = bytearray(candidate.read_bytes())
        mutated[tilemap.STAGE1_LUT_ROM_OFFSET] ^= 1
        with self.assertRaisesRegex(ValueError, "not the reviewed canonical"):
            tilemap.reviewed_stage1_lut(bytes(mutated))
        mutated = bytearray(candidate.read_bytes())
        mutated[tilemap.COPIER_START] ^= 1
        with self.assertRaisesRegex(ValueError, "not the reviewed"):
            tilemap.reviewed_postcomputed_copier(bytes(mutated))

    def test_compiled_tooth_bank_variant_is_narrowly_pinned(self) -> None:
        table = bytearray(0x100)
        # Start from the canonical bytes when the nearby fixture is present;
        # otherwise this test only documents the exact accepted digest.
        candidate = ROOT / "tmp/stage4-delay-trim-r344/candidate.gb"
        if not candidate.is_file():
            self.skipTest("r344 candidate artifact is not present")
        rom = bytearray(candidate.read_bytes())
        for tile in tilemap.COMPILED_TOOTH_BANK_TILES:
            rom[tilemap.STAGE1_LUT_ROM_OFFSET + tile] = 0x0F
        self.assertEqual(
            tilemap.sha256_bytes(
                rom[tilemap.STAGE1_LUT_ROM_OFFSET:
                    tilemap.STAGE1_LUT_ROM_OFFSET + 0x100]
            ),
            tilemap.COMPILED_TOOTH_BANK_LUT_SHA256,
        )
        self.assertEqual(
            tilemap.reviewed_stage1_lut(bytes(rom)),
            bytes(rom[tilemap.STAGE1_LUT_ROM_OFFSET:
                      tilemap.STAGE1_LUT_ROM_OFFSET + 0x100]),
        )
        rom[tilemap.STAGE1_LUT_ROM_OFFSET + 0x63] ^= 0x08
        with self.assertRaisesRegex(ValueError, "not the reviewed canonical"):
            tilemap.reviewed_stage1_lut(bytes(rom))

    def test_r417_precomputed_copier_is_pinned(self) -> None:
        candidate = ROOT / "tmp/title-nightfall-port/d82-r451c-lutrepatch/candidate.gb"
        if not candidate.is_file():
            self.skipTest("r451c candidate artifact is not present")
        copier = tilemap.reviewed_postcomputed_copier(candidate.read_bytes())
        self.assertEqual(
            tilemap.sha256_bytes(copier),
            tilemap.R417_PRECOMPUTED_COPIER_SHA256,
        )
        mutated = bytearray(candidate.read_bytes())
        mutated[tilemap.COPIER_START + 1] ^= 1
        with self.assertRaisesRegex(ValueError, "not the reviewed"):
            tilemap.reviewed_postcomputed_copier(bytes(mutated))

    def test_r446_later_stage_helper_route_is_pinned(self) -> None:
        candidate = ROOT / "tmp/title-nightfall-port/r443e3f2-v6-r449f/candidate.gb"
        if not candidate.is_file():
            self.skipTest("r449f candidate artifact is not present")
        copier = tilemap.reviewed_postcomputed_copier(candidate.read_bytes())
        self.assertEqual(
            tilemap.sha256_bytes(copier),
            tilemap.R446_LATER_STAGE_HELPER_COPIER_SHA256,
        )
        self.assertEqual(
            copier[0x42BB - tilemap.COPIER_START:0x42C3 - tilemap.COPIER_START],
            bytes.fromhex("3E 1C CD 47 08 C3 ED 42"),
        )
        mutated = bytearray(candidate.read_bytes())
        mutated[0x42BC] ^= 1
        with self.assertRaisesRegex(ValueError, "not the reviewed"):
            tilemap.reviewed_postcomputed_copier(bytes(mutated))


if __name__ == "__main__":
    unittest.main()
