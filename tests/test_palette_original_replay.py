"""Experimental source verification must never become an audience approval."""
import copy
import json
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "scripts"), str(ROOT / "scripts/diagnostics")]
import record_palette_approval as approval
import rebuild_r534_from_original as original


class PaletteOriginalReplayTests(unittest.TestCase):
    def test_experimental_mode_rejects_approval_and_ambiguous_profiles(self):
        cases = (
            (["--r534-original-replay"], "verification-only"),
            (["--r534-original-replay", "--verify-only", "--confirm", "AUDIENCE APPROVED"], "cannot record"),
            (["--r534-original-replay", "--verify-only", "--output", "never-written.json"], "cannot record"),
            (["--r534-original-replay", "--verify-only", "--expanded-ted"], "distinct complete profile"),
            (["--r534-original-replay", "--verify-only"], "requires --historical-input-manifest"),
            (["--verify-only", "--historical-input-manifest", "missing.json"], "require --r534-original-replay"),
            (["--verify-only", "--replay-output", "tmp/unused"], "require --r534-original-replay"),
            (["--verify-only", "--menu-icon-colors"], "requires --expanded-ted"),
        )
        for arguments, error in cases:
            with self.subTest(arguments=arguments):
                with patch.object(sys, "argv", ["record_palette_approval.py", *arguments]):
                    with patch.object(subprocess, "run", side_effect=AssertionError("unexpected build")):
                        with self.assertRaisesRegex(SystemExit, error):
                            approval.main()

    def test_verification_only_routes_explicit_paths_without_confirmation(self):
        arguments = ["record_palette_approval.py", "--r534-original-replay", "--verify-only",
                     "--rom", "candidate.gb", "--palettes", "palette.yaml",
                     "--historical-input-manifest", "inputs.json", "--replay-output", "tmp/replay"]
        with patch.object(sys, "argv", arguments), patch.object(approval, "verify_original_replay", return_value=0) as verify:
            self.assertEqual(approval.main(), 0)
        verify.assert_called_once_with(Path("candidate.gb"), Path("palette.yaml"), Path("inputs.json"), Path("tmp/replay"))

    def _fixture(self):
        path = ROOT / "tmp/r534-original-current493/build-receipt.json"
        if not path.is_file():
            self.skipTest("retained original-build audit fixture is unavailable")
        receipt = json.loads(path.read_text())
        rom = (path.parent / "candidate.gb").read_bytes()
        return path, receipt, rom, Path(receipt["palette"]["path"])

    def test_receipt_verifier_rejects_stale_nested_filesystem_fixture(self):
        path, receipt, rom, palette = self._fixture()
        # Even if an offline caller substitutes the historical top-level
        # snapshot, current verification must still reject the now-stale
        # traced factory inventory.  Never refresh or bless immutable evidence
        # merely because its candidate bytes remain available.
        snapshot = (receipt["source_fingerprint"], receipt["source_files"])
        # The immutable receipt captured the same resolved Python runtime via a
        # different argv[0] spelling.  Pin that spelling so this test reaches
        # the intentionally stale nested filesystem evidence it exercises.
        python_argv0 = receipt["python"]["path"]
        with patch.object(original, "source_snapshot", return_value=snapshot), \
             patch.object(original.lineage, "digest", side_effect=self.fixture_digest(receipt, palette)), \
             patch.object(original.sys, "executable", python_argv0):
            with self.assertRaisesRegex(ValueError, "filesystem evidence differs"):
                original.verify_receipt(path, rom, palette)

    def fixture_digest(self, receipt, palette):
        # Issue #11: isolate historical palette drift only in these downstream
        # negative controls. Production and the explicit stale-palette test
        # still validate actual bytes; nested source evidence remains stale.
        actual_digest = original.lineage.digest
        palette_bytes = palette.read_bytes()
        def digest(payload):
            return receipt["palette"]["sha256"] if payload == palette_bytes else actual_digest(payload)
        return digest

    def test_receipt_rejects_stale_palette_before_factory_checks(self):
        path, receipt, rom, palette = self._fixture()
        changed = copy.deepcopy(receipt)
        changed["palette"]["sha256"] = "0" * 64
        read_text = Path.read_text
        def reader(target, *args, **kwargs):
            return json.dumps(changed) if target == path else read_text(target, *args, **kwargs)
        with patch.object(Path, "read_text", new=reader), \
             patch.object(original, "source_snapshot",
                          return_value=(receipt["source_fingerprint"], receipt["source_files"])), \
             patch.object(original, "verify_factory_run", side_effect=AssertionError("unexpected factory")):
            with self.assertRaisesRegex(ValueError, "palette identity differs"):
                original.verify_receipt(path, rom, palette)

    def test_receipt_verifier_rejects_stale_source_and_wrong_rom(self):
        path, receipt, rom, palette = self._fixture()
        with patch.object(original, "source_snapshot", return_value=("stale", {})):
            with self.assertRaisesRegex(ValueError, "source snapshot is stale"):
                original.verify_receipt(path, rom, palette)
        with self.assertRaisesRegex(ValueError, "candidate_sha256 differs"):
            original.verify_receipt(path, rom[:-1], palette)

    def test_receipt_verifier_rejects_changed_evidence_and_claims(self):
        path, receipt, rom, palette = self._fixture()
        changes = (
            (lambda r: r.update(promotable=True), "promotable differs"),
            (lambda r: r.update(retained_candidate_roms_read=True), "retained_candidate_roms_read differs"),
            (lambda r: r["historical_evidence"]["phase_cold_live"].update(fresh_live_qualification=True), "historical input provenance differs"),
            (lambda r: r.update(factory_runs=r["factory_runs"][:1]), "two traced factory runs"),
            (lambda r: r["factory_runs"][0]["command"].append("--unknown"), "factory invocation differs"),
            (lambda r: r["factory_runs"][0]["environment_policy"].update(bytecode_writes_disabled=False), "environment policy differs"),
            (lambda r: r["factory_runs"][0].update(file_access_trace_sha256="0" * 64), "file-access trace changed"),
            (lambda r: r["factory_runs"][0]["filesystem_audit"].update(open_calls_checked=0), "filesystem evidence differs"),
            # Deep replay mutation is covered by fresh source-profile controls;
            # this immutable fixture now fails earlier at its traced filesystem
            # inventory, as production verification requires.
            (lambda r: r["replay"].update(retained_input="r120"), "filesystem evidence differs"),
        )
        read_text = Path.read_text
        snapshot = (receipt["source_fingerprint"], receipt["source_files"])
        python_argv0 = receipt["python"]["path"]
        for change, error in changes:
            damaged = copy.deepcopy(receipt)
            change(damaged)
            def reader(target, *args, **kwargs):
                return json.dumps(damaged) if target == path else read_text(target, *args, **kwargs)
            with self.subTest(error=error), patch.object(Path, "read_text", new=reader):
                with patch.object(original, "source_snapshot", return_value=snapshot), \
                     patch.object(original.lineage, "digest", side_effect=self.fixture_digest(receipt, palette)), \
                     patch.object(original.sys, "executable", python_argv0):
                    with self.assertRaisesRegex(ValueError, error):
                        original.verify_receipt(path, rom, palette)


if __name__ == "__main__":
    unittest.main()
