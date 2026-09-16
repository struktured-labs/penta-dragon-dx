"""Offline restart deterministic-suite and approval-profile controls."""
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

import restart_source_profile as profile
import restart_suite_evidence as evidence
import run_deterministic_suite as runner


class RestartDeterministicSuiteTests(unittest.TestCase):
    def test_cli_rejects_ambiguous_legacy_resume_and_nonfresh_outputs(self):
        cases = (
            ["--resume"],
            ["--expanded-ted"],
            ["--menu-icon-colors"],
            ["--r534-source"],
            ["--r536-source"],
            ["--output", str(ROOT)],
            ["--output", str(ROOT / "tmp")],
        )
        for options in cases:
            with self.subTest(options=options), \
                 patch.object(sys, "argv", ["suite", "--restart-source", *options]), \
                 patch.object(runner.subprocess, "run", side_effect=AssertionError("unexpected process check")), \
                 redirect_stderr(io.StringIO()):
                with self.assertRaises(SystemExit) as error:
                    runner.main()
                self.assertEqual(error.exception.code, 2)

    def test_failed_restart_builder_never_launches_matrix(self):
        output = ROOT / "tmp/never-written-restart-suite-source-failure"
        argv = ["suite", "--restart-source", "--output", str(output)]
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
            [sys.executable, str(ROOT / "scripts/build_restart_candidate.py"),
             "--out-dir", str(output / "build/source-a")],
        )
        self.assertNotIn("LD_LIBRARY_PATH", build.call_args.kwargs["environment"])
        self.assertNotIn("LD_PRELOAD", build.call_args.kwargs["environment"])
        self.assertEqual(write.call_args.args[1]["status"], "build-failed")

    def bindings(self):
        return [
            {
                "receipt": str(ROOT / f"tmp/unit-restart-source-{label}/build-receipt.json"),
                "receipt_sha256": "unit-test",
                "source_fingerprint": "unit-source",
            }
            for label in ("a", "b")
        ]

    def test_suite_evidence_rechecks_two_distinct_source_builds(self):
        rom = b"offline-restart-unit-rom"
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
        path = ROOT / "tmp/unit-restart-matrix/manifest.json"
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
