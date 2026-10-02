"""Offline r536 deterministic-suite and approval-profile controls."""
from __future__ import annotations

import copy
from contextlib import redirect_stderr, redirect_stdout
import io
import json
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import mock_open, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "scripts/diagnostics"), str(ROOT / "scripts")]

import build_release_bundle as bundle
import r536_source_profile as profile
import r536_suite_evidence as evidence
import record_palette_approval as recorder
import run_deterministic_suite as runner
import suite_release_ledger as ledger


class R536DeterministicSuiteTests(unittest.TestCase):
    def test_cli_rejects_ambiguous_legacy_resume_and_nonfresh_outputs(self):
        cases = (
            ["--resume"],
            ["--expanded-ted"],
            ["--menu-icon-colors"],
            ["--r534-source"],
            ["--output", str(ROOT)],
            ["--output", str(ROOT / "tmp")],
        )
        for options in cases:
            with self.subTest(options=options), \
                 patch.object(sys, "argv", ["suite", "--r536-source", *options]), \
                 patch.object(runner.subprocess, "run", side_effect=AssertionError("unexpected process check")), \
                 redirect_stderr(io.StringIO()):
                with self.assertRaises(SystemExit) as error:
                    runner.main()
                self.assertEqual(error.exception.code, 2)

    def test_failed_r536_builder_never_launches_matrix(self):
        output = ROOT / "tmp/never-written-r536-suite-source-failure"
        argv = ["suite", "--r536-source", "--output", str(output)]
        with patch.object(sys, "argv", argv), \
             patch.dict(runner.os.environ, {"LD_LIBRARY_PATH": "unit-runtime", "LD_PRELOAD": "unit-preload"}), \
             patch.object(runner.subprocess, "run", return_value=SimpleNamespace(returncode=0, stdout="unit-head")), \
             patch.object(Path, "mkdir"), \
             patch.object(runner, "configure_repo_temp", return_value=output), \
             patch.object(runner, "write_json") as write, \
             patch.object(runner, "source_snapshot", return_value=("unit-source", [])), \
             patch.object(runner, "run_logged", return_value=1) as build, \
             patch.object(runner, "run_matrix_guarded", side_effect=AssertionError("unexpected emulator")), \
             redirect_stdout(io.StringIO()):
            self.assertEqual(runner.main(), 1)
        self.assertEqual(
            build.call_args.args[0],
            [sys.executable, str(ROOT / "scripts/build_r536_candidate.py"),
             "--out-dir", str(output / "build/source-a")],
        )
        self.assertNotIn("LD_LIBRARY_PATH", build.call_args.kwargs["environment"])
        self.assertNotIn("LD_PRELOAD", build.call_args.kwargs["environment"])
        self.assertEqual(write.call_args.args[1]["status"], "build-failed")

    def bindings(self):
        return [
            {
                "receipt": str(ROOT / f"tmp/unit-r536-source-{label}/build-receipt.json"),
                "receipt_sha256": "unit-test",
                "source_fingerprint": "unit-source",
            }
            for label in ("a", "b")
        ]

    def test_suite_evidence_rechecks_two_distinct_source_builds(self):
        rom = b"offline-r536-unit-rom"
        candidate = {"sha256": evidence.digest(rom), "size": len(rom)}
        bindings = self.bindings()
        with patch.object(Path, "read_bytes", return_value=rom), \
             patch.object(evidence, "verify_binding", return_value={"source_fingerprint": "unit-source"}) as verify:
            self.assertEqual(evidence.source_builds(bindings, candidate), rom)
            self.assertEqual(verify.call_count, 2)
        for bad in (None, [], [bindings[0]], [bindings[0], bindings[0]], [None, bindings[1]]):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                evidence.source_builds(bad, candidate)

    def test_suite_receipt_rechecks_profile_matrix_and_nested_ledger(self):
        path = ROOT / "tmp/unit-r536-matrix/manifest.json"
        rows = [{"name": "unit-only", "status": "passed", "returncode": 0, "duration_seconds": 1}]
        receipt = {
            "build_profile": dict(profile.PROFILE),
            "source_builds": self.bindings(),
            "candidate": {},
            "source_fingerprint": "unit-source",
            "matrix": {
                "manifest_path": str(path),
                "manifest_sha256": evidence.digest(b"matrix"),
                "results": rows,
            },
            "release_ledger": {"unit-only": True},
        }
        with patch.object(evidence, "source_builds", return_value=b"rom"), \
             patch.object(evidence, "matrix_evidence", return_value={"results": rows}), \
             patch.object(evidence, "collect_release_ledger", return_value={"unit-only": True}), \
             patch.object(Path, "read_bytes", return_value=b"matrix"):
            evidence.verify(receipt)
            bad = copy.deepcopy(receipt)
            bad["build_profile"]["name"] = "r534-original-source-v1"
            with self.assertRaisesRegex(ValueError, "build profile differs"):
                evidence.verify(bad)

    def test_r536_ledger_uses_source_profile_and_current_world_position(self):
        matrix = ROOT / "tmp/r536-full-regression-current653"
        if not matrix.is_dir():
            self.skipTest("retained r536 full matrix unavailable")
        value = ledger.collect_release_ledger(
            matrix, expanded=True, source_profile=profile.PROFILE["name"]
        )
        self.assertEqual(
            ledger.validate_release_ledger(
                value, expanded=True, source_profile=profile.PROFILE["name"]
            ),
            [],
        )
        self.assertEqual(value["profile"], profile.PROFILE["name"])
        self.assertTrue(value["stage7_world_position"]["metric"]["strict_target_met"])

    def test_palette_cli_routes_r536_without_implicit_approval(self):
        cases = (
            (["--r536-source"], "requires --source-output"),
            (["--r536-source", "--source-output", "tmp/unused"], "requires --output and --confirm"),
            (["--r536-source", "--r534-source"], "select only one"),
            (["--source-output", "tmp/unused"], "requires --r534-source or --r536-source"),
        )
        for argv, message in cases:
            with self.subTest(argv=argv), patch.object(sys, "argv", ["recorder", *argv]), \
                 patch.object(recorder, "record_r536_source", side_effect=AssertionError("unexpected build")):
                with self.assertRaisesRegex(SystemExit, message):
                    recorder.main()
        argv = ["recorder", "--r536-source", "--verify-only", "--source-output", "tmp/unused"]
        with patch.object(sys, "argv", argv), patch.object(recorder, "record_r536_source", return_value=0) as run:
            self.assertEqual(recorder.main(), 0)
            self.assertTrue(run.call_args.args[0].verify_only)

    def test_packager_requires_r536_source_approval_profile(self):
        rom = b"exact-r536"
        palette = profile.builder.DEFAULT_PALETTE
        approval = {
            "schema": "penta-dragon-dx-palette-approval-v1",
            "status": "audience-approved",
            "confirmation": "AUDIENCE APPROVED",
            "rom_md5": bundle.digest(rom, "md5"),
            "rom_sha256": profile.digest(rom),
            "palette_yaml": str(palette.resolve()),
            "palette_yaml_sha256": profile.digest(palette.read_bytes()),
            "build_profile": dict(profile.PROFILE),
            "source_build": {"unit": True},
        }
        with patch.object(bundle, "load_json", return_value=approval), \
             patch("r536_source_profile.verify_binding", return_value={}) as verify:
            self.assertEqual(bundle.validate_palette_approval(Path("synthetic.json"), rom, palette), approval)
        verify.assert_called_once()


if __name__ == "__main__":
    unittest.main()
