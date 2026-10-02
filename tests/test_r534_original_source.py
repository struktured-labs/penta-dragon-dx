"""Original-cartridge source construction must not depend on historical evidence."""
import copy
from contextlib import redirect_stderr
import io
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "scripts"), str(ROOT / "scripts/diagnostics")]
import build_r534_candidate as original


class OriginalSourceTests(unittest.TestCase):
    def fixture(self):
        path = ROOT / "tmp/r534-original-source-current522/build-receipt.json"
        if not path.is_file():
            self.skipTest("original-source double-build fixture is unavailable")
        receipt = json.loads(path.read_text())
        return path, receipt, (path.parent / "candidate.gb").read_bytes(), Path(receipt["palette"]["path"])

    def test_build_requires_fresh_repository_scratch(self):
        for output in (ROOT, ROOT / "tmp", ROOT / "tmp/r534-source-candidate-current516"):
            with self.subTest(output=output), self.assertRaisesRegex(ValueError, "fresh repository-local tmp"):
                original.build(output, ROOT / "missing-palette.yaml")

    def test_source_snapshot_includes_original_source_entrypoint(self):
        _, entries = original.source_snapshot()
        self.assertIn("scripts/build_r534_candidate.py", {entry["path"] for entry in entries})

    def test_construction_json_round_trip_preserves_serialized_contract(self):
        metadata = {"wall": {4: (1, 2), "other": [3]}, "verified": True}
        persisted = json.loads(json.dumps(metadata))
        self.assertEqual(original.construction_json(metadata), original.construction_json(persisted))
        persisted["verified"] = 1
        self.assertNotEqual(original.construction_json(metadata), original.construction_json(persisted))
        with self.assertRaises(ValueError):
            original.construction_json({"invalid": float("nan")})

    def test_tracer_is_required_before_any_output_is_created(self):
        output = ROOT / "tmp/original-source-unit-missing-tracer"
        self.assertFalse(output.exists())
        with patch.object(original.shutil, "which", return_value=None):
            with self.assertRaisesRegex(ValueError, "strace is required"):
                original.build(output, original.DEFAULT_PALETTE)
        self.assertFalse(output.exists())

    def test_cli_cannot_accept_historical_inputs_or_approval(self):
        for extra in (("--historical-input-manifest", "never-read.json"),
                      ("--factory-image", "never-read.gb"),
                      ("--confirm", "AUDIENCE APPROVED")):
            argv = ["build_r534_candidate.py", "--out-dir", "tmp/not-created", *extra]
            with self.subTest(extra=extra), patch.object(sys, "argv", argv), \
                 patch.object(original, "build", side_effect=AssertionError("unexpected build")), \
                 redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as raised:
                original.main()
            self.assertEqual(raised.exception.code, 2)

    def test_in_memory_guard_is_fail_closed_and_deactivates(self):
        for path in (original.ORIGINAL, ROOT / "tmp/r534-source-candidate-current516/construction-receipt.json"):
            with self.subTest(path=path):
                with original.construction_guard():
                    with self.assertRaisesRegex(ValueError, "undeclared artifact"):
                        path.read_bytes()
                self.assertTrue(path.read_bytes())

    def test_verifier_rejects_stale_nested_factory_inventory(self):
        path, receipt, rom, palette = self.fixture()
        snapshot = (receipt["source_fingerprint"], receipt["source_files"])
        # The receipt stores a resolved Python identity but the traced factory
        # command preserves the equivalent symlink spelling used as argv[0].
        python_argv0 = receipt["factory_runs"][0]["command"][0]
        # Substituting the historical top-level snapshot must not bless the
        # immutable factory trace after its repository-input inventory becomes
        # stale.  The CLI always uses the actual current source snapshot.
        with patch.object(original, "source_snapshot", return_value=snapshot), \
             patch.object(original, "identity", side_effect=self.fixture_identity(receipt, palette)), \
             patch.object(original.sys, "executable", python_argv0):
            with self.assertRaisesRegex(ValueError, "filesystem evidence differs"):
                original.verify_receipt(path, rom, palette)

    def fixture_identity(self, receipt, palette):
        # Issue #11: isolate downstream negative controls from unrelated drift
        # in the historical palette. Only the test's top-level input identity is
        # substituted; production validation and nested filesystem audits stay
        # intact, and stale real inputs have their own explicit rejection test.
        identity = original.identity
        def selected(path):
            return receipt["palette"] if path.resolve() == palette.resolve() else identity(path)
        return selected

    def test_verifier_rejects_changed_palette_before_factory_validation(self):
        path, receipt, rom, palette = self.fixture()
        identity = original.identity
        def changed(path):
            value = identity(path)
            return {**value, "sha256": "0" * 64} if path.resolve() == palette.resolve() else value
        with patch.object(original, "source_snapshot",
                          return_value=(receipt["source_fingerprint"], receipt["source_files"])), \
             patch.object(original, "identity", side_effect=changed), \
             patch.object(original.sys, "executable", receipt["factory_runs"][0]["command"][0]), \
             patch.object(original.factory_stage, "verify_factory_run",
                          side_effect=AssertionError("unexpected factory verification")):
            with self.assertRaisesRegex(ValueError, "input identity differs"):
                original.verify_receipt(path, rom, palette)

    def test_verifier_rejects_stale_source_and_wrong_rom(self):
        path, _, rom, palette = self.fixture()
        with patch.object(original, "source_snapshot", return_value=("stale", [])):
            with self.assertRaisesRegex(ValueError, "source snapshot is stale"):
                original.verify_receipt(path, rom, palette)
        with self.assertRaisesRegex(ValueError, "exact pinned r534"):
            original.verify_receipt(path, rom[:-1], palette)

    def test_verifier_rejects_changed_policy_tools_inputs_and_both_runs(self):
        path, receipt, rom, palette = self.fixture()
        snapshot = (receipt["source_fingerprint"], receipt["source_files"])
        python_argv0 = receipt["factory_runs"][0]["command"][0]
        changes = (
            (lambda r: r.update(historical_input_manifest={}), "field inventory differs"),
            (lambda r: r.update(promotable=True), "promotable differs"),
            (lambda r: r.update(double_build_identical=1), "double_build_identical differs"),
            (lambda r: r.update(audience_approval_recorded=True), "audience_approval_recorded differs"),
            (lambda r: r.update(historical_evidence_consumed=True), "historical_evidence_consumed differs"),
            (lambda r: r["python"].update(sha256="0" * 64), "tool identity is not current"),
            (lambda r: r["strace"].update(path="/not-the-current-tracer"), "tool identity is not current"),
            (lambda r: r["original_rom"].update(sha256="0" * 64), "input identity differs"),
            (lambda r: r["palette"].update(path="/not-the-selected-palette"), "input identity differs"),
            (lambda r: r.update(factory_runs=r["factory_runs"][:1]), "two traced factory runs"),
            (lambda r: r["factory_runs"][0].update(extra={}), "factory record inventory differs"),
            (lambda r: r["factory_runs"][0]["command"].append("--unknown"), "factory invocation differs"),
            (lambda r: r["factory_runs"][0]["environment_policy"].update(bytecode_writes_disabled=False), "environment policy differs"),
            (lambda r: r["factory_runs"][0].update(file_access_trace_sha256="0" * 64), "file-access trace changed"),
            (lambda r: r["factory_runs"][0]["filesystem_audit"].update(open_calls_checked=0), "filesystem evidence differs"),
            # Deep mutations below are dominated by the immutable fixture's
            # now-stale first-run repository inventory. Fresh profile tests
            # separately exercise the corresponding downstream controls.
            (lambda r: r["factory_runs"][0].update(factory_sha256="0" * 64), "filesystem evidence differs"),
            (lambda r: r["factory_runs"][1].update(file_access_trace_sha256="0" * 64), "filesystem evidence differs"),
            (lambda r: r["construction"].update(total_steps=1), "filesystem evidence differs"),
            (lambda r: r["construction"].update(promotable=0), "filesystem evidence differs"),
        )
        read_text = Path.read_text
        for mutate, message in changes:
            changed = copy.deepcopy(receipt)
            mutate(changed)
            def overridden(target, *args, **kwargs):
                return json.dumps(changed) if target == path else read_text(target, *args, **kwargs)
            with self.subTest(message=message), patch.object(original, "source_snapshot", return_value=snapshot), \
                 patch.object(original, "identity", side_effect=self.fixture_identity(receipt, palette)), \
                 patch.object(original.sys, "executable", python_argv0), \
                 patch.object(Path, "read_text", overridden):
                with self.assertRaisesRegex(ValueError, message):
                    original.verify_receipt(path, rom, palette)

    def test_verifier_rejects_different_output_bytes(self):
        path, _, rom, palette = self.fixture()
        read_bytes = Path.read_bytes
        def overridden(target):
            return b"" if target == path.parent / "candidate.gb" else read_bytes(target)
        with patch.object(Path, "read_bytes", overridden):
            with self.assertRaisesRegex(ValueError, "candidate bytes differ"):
                original.verify_receipt(path, rom, palette)


if __name__ == "__main__":
    unittest.main()
