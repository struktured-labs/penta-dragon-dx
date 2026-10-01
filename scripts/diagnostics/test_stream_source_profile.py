"""Offline controls for the 126dd stream source suite profile (no emulator)."""
from __future__ import annotations

from contextlib import redirect_stderr
import io
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / "scripts/diagnostics"), str(ROOT / "scripts")]

import build_stream_source_candidate as builder
import run_deterministic_suite as runner
import stream_source_profile as profile
import suite_contract


class StreamSourceProfileTests(unittest.TestCase):
    def test_cli_rejects_ambiguous_legacy_resume_and_nonfresh_outputs(self):
        cases = (["--resume"], ["--expanded-ted"], ["--menu-icon-colors"],
                 ["--restart-source"], ["--r536-source"], ["--r534-source"],
                 ["--output", str(ROOT)], ["--output", str(ROOT / "tmp")])
        for options in cases:
            with self.subTest(options=options), \
                 patch.object(sys, "argv", ["suite", "--stream-source", *options]), \
                 patch.object(runner.subprocess, "run", side_effect=AssertionError("process check")), \
                 redirect_stderr(io.StringIO()):
                with self.assertRaises(SystemExit) as error:
                    runner.main()
                self.assertEqual(error.exception.code, 2)

    def test_profile_and_contract_pins(self):
        self.assertEqual(profile.PROFILE["name"], "stream-126dd-original-source-v1")
        self.assertTrue(profile.PROFILE["expanded_ted"])
        self.assertEqual(builder.CONTRACT["candidate_sha256"][:8], "126dd0b7")
        self.assertEqual(builder.CONTRACT["source_parent_sha256"][:8], "c693eafb")
        self.assertFalse(builder.CONTRACT["chain_flags"]["experimental_late_return_fade"])
        self.assertFalse(builder.CONTRACT["release_qualification"])

    def test_construction_sources_are_fingerprinted(self):
        inputs = {path.relative_to(ROOT).as_posix() for path in suite_contract.source_paths()}
        for relative in ("scripts/build_stream_regression_candidate.py",
                         "scripts/build_restart_candidate.py",
                         "scripts/diagnostics/build_stream_source_candidate.py",
                         "scripts/stage_card_palette_handoff.py",
                         "scripts/arena_semantic_key.py",
                         "scripts/stage1_hazard_semantic_row.py"):
            self.assertIn(relative, inputs)

    def test_binding_rejects_field_inventory_and_tamper(self):
        with self.assertRaises(ValueError):
            profile.verify_binding({"receipt": "x"}, b"", builder.DEFAULT_PALETTE)
        with self.assertRaises(ValueError):
            profile.verify_binding({"receipt": "", "receipt_sha256": "a", "source_fingerprint": "b"},
                                   b"", builder.DEFAULT_PALETTE)

    def test_verify_rejects_wrong_rom_and_palette(self):
        receipt = ROOT / "tmp/nonexistent-stream/build-receipt.json"
        with self.assertRaises(ValueError):
            builder.verify_receipt(receipt, b"", ROOT / "palettes/penta_palettes_restart_parent.yaml")
        with self.assertRaises(ValueError):
            builder.build(ROOT / "tmp", builder.DEFAULT_PALETTE)


if __name__ == "__main__":
    unittest.main()
