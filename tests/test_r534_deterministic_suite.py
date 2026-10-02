"""Offline r534 suite controls; no emulator or passing release fixture emitted."""
import copy
from contextlib import redirect_stderr, redirect_stdout
import io
import json
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "scripts/diagnostics"), str(ROOT / "scripts")]
import run_deterministic_suite as runner
import r534_suite_evidence as evidence
import build_release_bundle as bundle
import suite_release_ledger as ledger


class R534DeterministicSuiteTests(unittest.TestCase):
    def test_cli_rejects_legacy_resume_and_nonfresh_outputs_before_process_check(self):
        for options in (["--resume"], ["--expanded-ted"], ["--menu-icon-colors"],
                        ["--output", str(ROOT)], ["--output", str(ROOT / "tmp")]):
            with self.subTest(options=options), patch.object(sys, "argv", ["suite", "--r534-source", *options]), \
                 patch.object(runner.subprocess, "run", side_effect=AssertionError("unexpected process check")), \
                 redirect_stderr(io.StringIO()):
                with self.assertRaises(SystemExit) as error:
                    runner.main()
                self.assertEqual(error.exception.code, 2)

    def test_failed_source_builder_never_launches_matrix(self):
        output = ROOT / "tmp/never-written-suite-unit-source-failure"
        argv = ["suite", "--r534-source", "--output", str(output)]
        with patch.object(sys, "argv", argv), \
             patch.dict(runner.os.environ, {"LD_LIBRARY_PATH": "unit-emulator-runtime", "LD_PRELOAD": "unit-emulator-preload"}), \
             patch.object(runner.subprocess, "run", return_value=SimpleNamespace(returncode=0, stdout="unit-test")), \
             patch.object(Path, "mkdir"), patch.object(runner, "configure_repo_temp", return_value=output), \
             patch.object(runner, "write_json") as write, \
             patch.object(runner, "source_snapshot", return_value=("unit-test", [])), \
             patch.object(runner, "run_logged", return_value=1) as build, \
             patch.object(runner, "run_matrix_guarded", side_effect=AssertionError("unexpected emulator")), \
             redirect_stdout(io.StringIO()):
            self.assertEqual(runner.main(), 1)
        self.assertEqual(build.call_args.args[0], [sys.executable, str(ROOT / "scripts/build_r534_candidate.py"),
                         "--out-dir", str(output / "build/source-a")])
        self.assertNotIn("LD_LIBRARY_PATH", build.call_args.kwargs["environment"])
        self.assertNotIn("LD_PRELOAD", build.call_args.kwargs["environment"])
        self.assertEqual(write.call_args.args[1]["status"], "build-failed")
        self.assertFalse(output.exists())

    def bindings(self):
        return [{"receipt": str(ROOT / f"tmp/unit-source-{label}/build-receipt.json"),
                 "receipt_sha256": "unit-test", "source_fingerprint": "unit-test"} for label in ("a", "b")]

    def test_source_evidence_requires_two_distinct_builds(self):
        bindings = self.bindings()
        for bad in (None, [], [bindings[0]], [bindings[0], bindings[0]], [None, bindings[1]]):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                evidence.source_builds(bad, {})

    def test_source_evidence_rechecks_both_candidates_and_fingerprints(self):
        rom = b"offline-unit-test"
        candidate = {"sha256": evidence.digest(rom), "size": len(rom)}
        bindings = self.bindings()
        with patch.object(Path, "read_bytes", return_value=rom), \
             patch.object(evidence, "verify_binding", return_value={"source_fingerprint": "unit-test"}) as verify:
            self.assertEqual(evidence.source_builds(bindings, candidate), rom)
            self.assertEqual(verify.call_count, 2)
            with self.assertRaisesRegex(ValueError, "candidate differs"):
                evidence.source_builds(bindings, {**candidate, "size": 0})
        with patch.object(Path, "read_bytes", return_value=rom), \
             patch.object(evidence, "verify_binding", side_effect=[{"source_fingerprint": "unit-test"}, {"source_fingerprint": "different"}]):
            with self.assertRaisesRegex(ValueError, "different fingerprints"):
                evidence.source_builds(bindings, candidate)

    def test_matrix_checks_actual_source_and_tested_rom_bytes(self):
        manifest = {"source_rom": "source.gb", "tested_rom": "tested.gb"}
        with patch("build_release_bundle.validate_emulator_manifest", return_value=manifest) as validate, \
             patch.object(Path, "read_bytes", return_value=b"rom"):
            self.assertEqual(evidence.matrix_evidence(Path("unit-matrix.json"), b"rom"), manifest)
            validate.assert_called_once()
        for values, error in (([b"wrong"], "source_rom"), ([b"rom", b"wrong"], "tested_rom")):
            with patch("build_release_bundle.validate_emulator_manifest", return_value=manifest), \
                 patch.object(Path, "read_bytes", side_effect=values), self.assertRaisesRegex(ValueError, error):
                evidence.matrix_evidence(Path("unit-matrix.json"), b"rom")

    def test_receipt_rechecks_matrix_summary_hash_and_nested_ledger(self):
        path = ROOT / "tmp/unit-matrix/manifest.json"
        rows = [{"name": "unit-only", "status": "passed", "returncode": 0, "duration_seconds": 1}]
        receipt = {"build_profile": dict(evidence.PROFILE), "source_builds": self.bindings(),
                   "candidate": {}, "source_fingerprint": "unit-test",
                   "matrix": {"manifest_path": str(path), "manifest_sha256": evidence.digest(b"matrix"), "results": rows},
                   "release_ledger": {"unit-only": True}}
        changes = (
            (lambda r: r["build_profile"].update(name="expanded-ted-menu"), "build profile differs"),
            (lambda r: r.update(source_fingerprint="stale"), "fingerprint binding differs"),
            (lambda r: r["matrix"].update(manifest_path="relative.json"), "canonical path"),
            (lambda r: r["matrix"].update(manifest_sha256="wrong"), "manifest hash differs"),
            (lambda r: r["matrix"].update(results=[]), "summary differs"),
            (lambda r: r.update(release_ledger={}), "ledger differs"),
        )
        with patch.object(evidence, "source_builds", return_value=b"rom"), \
             patch.object(evidence, "matrix_evidence", return_value={"results": rows}), \
             patch.object(evidence, "collect_release_ledger", return_value={"unit-only": True}), \
             patch.object(Path, "read_bytes", return_value=b"matrix"):
            evidence.verify(receipt)
            for mutate, error in changes:
                bad = copy.deepcopy(receipt)
                mutate(bad)
                with self.subTest(error=error), self.assertRaisesRegex(ValueError, error):
                    evidence.verify(bad)

    def test_current_ledger_uses_real_patrol_and_reports_observed_not_historical_misses(self):
        root = ROOT / "tmp/r534-full-release-current497"
        if not root.is_dir():
            self.skipTest("historical full matrix fixture unavailable")
        value = ledger.collect_release_ledger(root, expanded=True, r534=True)
        self.assertEqual(ledger.validate_release_ledger(value, expanded=True, r534=True), [])
        self.assertEqual(value["evidence"]["gameplay_movement_stress"]["path"],
                         "artifacts/gameplay-movement-stress/receipt.json")
        ids = {item["id"] for item in value["accepted_deviations"]}
        self.assertNotIn("stage_1_speed", ids)
        self.assertNotIn("boss_crystal_dragon_speed", ids)
        self.assertIn("boss_shalamar_loop_speedup", ids)
        self.assertIn("boss_riff_publication_phase_deviation", ids)
        load = ledger.load_json
        def changed(path):
            value = load(path)
            if path.name == "boss-speed-parity.json":
                value["bosses"][0]["accepted_bounded_speedup"] = False
            return value
        with patch.object(ledger, "load_json", side_effect=changed):
            with self.assertRaisesRegex(RuntimeError, "target miss lacks explicit"):
                ledger.collect_release_ledger(root, expanded=True, r534=True)


if __name__ == "__main__":
    unittest.main()
