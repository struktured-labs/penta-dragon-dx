#!/usr/bin/env python3
"""Negative controls for the pre-commit ROM/save/state artifact rule.

Savestates (.ss, .ss0-.ss4) are allowed only as direct children of
scripts/diagnostics/fixtures/. ROMs and SRAM stay blocked everywhere.
"""

from __future__ import annotations

from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))
from verify_suite_receipt import FORBIDDEN_SUFFIXES, is_forbidden_artifact  # noqa: E402


class ArtifactPolicyTests(unittest.TestCase):
    def test_fixture_savestates_allowed(self) -> None:
        for name in ("og_boss8_penta_dragon.ss0", "x.ss", "x.ss1", "x.ss2",
                     "x.ss3", "x.ss4", "UPPER.SS0"):
            with self.subTest(name=name):
                self.assertFalse(
                    is_forbidden_artifact(Path("scripts/diagnostics/fixtures") / name))

    def test_roms_blocked_everywhere(self) -> None:
        for suffix in (".gb", ".gbc", ".gba", ".GBC"):
            for parent in ("scripts/diagnostics/fixtures", "rom", "tmp", "."):
                with self.subTest(suffix=suffix, parent=parent):
                    self.assertTrue(is_forbidden_artifact(Path(parent) / f"x{suffix}"))

    def test_sram_blocked_even_in_fixtures(self) -> None:
        for suffix in (".sav", ".ram"):
            self.assertTrue(is_forbidden_artifact(
                Path("scripts/diagnostics/fixtures") / f"x{suffix}"))

    def test_savestates_blocked_outside_exact_fixture_dir(self) -> None:
        for path in (
            "save_states_for_claude/x.ss0",
            "tmp/scripts/diagnostics/fixtures/x.ss0",
            "scripts/diagnostics/fixtures/sub/x.ss0",
            "scripts/diagnostics/fixtures/../x.ss0",
            "scripts/diagnostics/fixturesX/x.ss0",
            "scripts/diagnostics/x.ss0",
            "/abs/scripts/diagnostics/fixtures/x.ss0",
            "x.ss0",
        ):
            with self.subTest(path=path):
                self.assertTrue(is_forbidden_artifact(Path(path)))

    def test_ordinary_files_allowed(self) -> None:
        for path in ("scripts/diagnostics/fixtures/x.json", "docs/a.md", "scripts/x.py"):
            self.assertFalse(is_forbidden_artifact(Path(path)))

    def test_suffix_inventory_unchanged(self) -> None:
        self.assertEqual(
            FORBIDDEN_SUFFIXES,
            {".gb", ".gbc", ".gba", ".sav", ".ram", ".ss",
             ".ss0", ".ss1", ".ss2", ".ss3", ".ss4"},
        )


if __name__ == "__main__":
    unittest.main()
