#!/usr/bin/env python3
"""Offline controls for the tilemap publication READY/Stop/deploy gate."""

from __future__ import annotations

import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
DIAGNOSTICS = ROOT / "scripts" / "diagnostics"
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(DIAGNOSTICS))

import deploy_pocket_rom as deploy  # noqa: E402
import verify_stage1_reported_regressions_ready as ready  # noqa: E402
import verify_stage1_tilemap_copy as tilemap  # noqa: E402


def release_report(
    rom_sha256: str, copier_sha256: str,
) -> dict[str, str]:
    report = tilemap._synthetic_passing_report(rom_sha256)
    report["copier_sha256"] = copier_sha256
    publications = 1000
    report.update({
        "atomic_completions": str(publications),
        "pure_completions": "0",
        "wrap_hits": str(publications),
        "exact_copies": str(publications),
        "publication_model_copies": str(publications),
        "publication_model_cells": str(
            publications * tilemap.CELLS_PER_PUBLICATION
        ),
        "attribute_checked_copies": str(publications),
        "ordinary_attribute_model_copies": str(publications),
        "ordinary_attribute_model_cells": str(
            publications * tilemap.CELLS_PER_PUBLICATION
        ),
        "copy_entries": str(publications),
        "first_mismatch": "none",
        "first_attribute_mismatch": "none",
        "final_scene": "02",
        "final_active": "9800",
        "warm_reset": "0",
        "runtime_setup": "release-fixture",
        "force_pure": "0",
        "entry_h_values": "C1",
        "wrap_a_values": "99,9D",
        "wrap_h_values": "98,9C",
    })
    return report


def write_report(path: Path, report: dict[str, str]) -> None:
    path.write_text(
        "".join(f"{key}={value}\n" for key, value in sorted(report.items()))
    )


class Stage1TilemapReadyGateTests(unittest.TestCase):
    def setUp(self) -> None:
        (ROOT / "tmp").mkdir(exist_ok=True)
        self.temporary = tempfile.TemporaryDirectory(
            prefix="stage1-tilemap-ready-", dir=ROOT / "tmp",
        )
        self.work = Path(self.temporary.name).resolve()
        self.candidate = self.work / "candidate.gb"
        self.candidate.write_bytes(b"offline tilemap READY candidate")
        self.candidate_sha256 = ready.sha256(self.candidate)
        self.copier_sha256 = tilemap.sha256_bytes(b"copier")
        self.output = self.work / "tilemap"

        def fake_run_state(*args, **_kwargs):
            report_path = Path(args[3])
            source_state = Path(args[2])
            retargeted = (
                report_path.parent / report_path.stem / "retargeted-state.ss0"
            )
            retargeted.parent.mkdir(parents=True, exist_ok=True)
            retargeted.write_bytes(source_state.read_bytes())
            report = release_report(
                self.candidate_sha256, self.copier_sha256,
            )
            write_report(report_path, report)
            return report

        argv = [
            str(Path(tilemap.__file__)), str(self.candidate),
            "--state", ready.TILEMAP_RELEASE_STATES[0],
            "--state", ready.TILEMAP_RELEASE_STATES[1],
            "--state", ready.TILEMAP_RELEASE_STATES[2],
            "--frames", str(ready.TILEMAP_RELEASE_FRAMES),
            "--timeout", str(ready.TILEMAP_RELEASE_TIMEOUT_SECONDS),
            "--output", str(self.output),
        ]
        with (
            mock.patch.object(sys, "argv", argv),
            mock.patch.object(
                tilemap, "probe_publication_oracle_failures", return_value=[],
            ),
            mock.patch.object(
                tilemap, "reviewed_stage1_lut", return_value=bytes(0x100),
            ),
            mock.patch.object(
                tilemap, "reviewed_postcomputed_copier", return_value=b"copier",
            ),
            mock.patch.object(tilemap, "run_state", side_effect=fake_run_state),
        ):
            self.assertEqual(tilemap.main(), 0)
        self.receipt_path = self.output / "receipt.json"
        self.receipt = json.loads(self.receipt_path.read_text())

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def rewrite_receipt(self) -> None:
        self.receipt_path.write_text(
            json.dumps(self.receipt, indent=2, sort_keys=True) + "\n"
        )

    def validate(self) -> dict:
        with (
            mock.patch.object(
                ready.tilemap_oracle,
                "reviewed_postcomputed_copier",
                return_value=b"copier",
            ),
            mock.patch.object(
                ready.tilemap_oracle,
                "reviewed_stage1_lut",
                return_value=bytes(0x100),
            ),
        ):
            return ready.validate_tilemap_receipt(
                self.receipt_path, self.candidate, self.candidate_sha256,
            )

    def test_in_run_verifier_receipt_regrades_all_three_reports(self) -> None:
        evidence = self.validate()
        self.assertEqual(evidence["rom_sha256"], self.candidate_sha256)
        self.assertEqual(evidence["total_completions"], 3000)
        self.assertEqual(evidence["total_atomic_completions"], 3000)
        self.assertEqual(evidence["destinations"], ["9800", "9C00"])
        self.assertEqual(len(evidence["reports"]), 3)

    def test_report_mutation_is_regraded_not_trusted(self) -> None:
        item = self.receipt["reports"][0]
        report_path = Path(item["report_path"])
        report = tilemap.parse_report(report_path)
        report["attribute_mismatch_copies"] = "1"
        report["attribute_mismatch_cells"] = "1"
        write_report(report_path, report)
        item["report_sha256"] = ready.sha256(report_path)
        self.rewrite_receipt()
        with self.assertRaisesRegex(
            ready.NotReady, "failed immutable oracle",
        ):
            self.validate()

    def test_missing_fixture_receipt_is_rejected(self) -> None:
        self.receipt["reports"].pop()
        self.receipt["totals"]["completed_reports"] = 2
        self.rewrite_receipt()
        with self.assertRaisesRegex(ready.NotReady, "all three"):
            self.validate()

    def test_release_configuration_is_exact(self) -> None:
        self.receipt["configuration"]["frames"] -= 1
        self.rewrite_receipt()
        with self.assertRaisesRegex(ready.NotReady, "configuration changed"):
            self.validate()

    def test_ready_and_deployer_inventories_cannot_omit_gate(self) -> None:
        gate = "stage1_tilemap_publication_oracle"
        self.assertEqual(
            ready.SCHEMA, "penta-stage1-reported-regressions-ready-v10",
        )
        self.assertEqual(ready.SCHEMA, deploy.HARDWARE_TEST_READY_SCHEMA)
        self.assertIn(gate, deploy.HARDWARE_TEST_READY_GATES)
        self.assertIn(gate, deploy.HARDWARE_TEST_READY_COMMAND_GATES)
        self.assertIn(
            "stage1_tilemap_publication_verifier", ready.tool_identity(),
        )
        self.assertIn(
            "stage1_tilemap_publication_probe", ready.tool_identity(),
        )
        self.assertEqual(
            set(ready.tool_identity()),
            set(deploy.hardware_test_ready_tool_paths()),
        )

    def test_ready_invokes_guarded_verifier_with_fixed_release_scope(self) -> None:
        source = Path(ready.__file__).read_text()
        block = source.split(
            'current_gate = "stage1_tilemap_publication_oracle"', 1
        )[1].split(
            'current_gate = "natural_blank_sram_menu_and_art_loader"', 1
        )[0]
        self.assertIn("str(TILEMAP_VERIFIER)", block)
        self.assertEqual(block.count('"--state"'), 3)
        self.assertIn('"--frames", str(TILEMAP_RELEASE_FRAMES)', block)
        self.assertIn(
            '"--timeout", str(TILEMAP_RELEASE_TIMEOUT_SECONDS)', block,
        )
        self.assertIn("validate_tilemap_receipt", block)
        self.assertNotIn('"--mgba"', block)


if __name__ == "__main__":
    unittest.main()
