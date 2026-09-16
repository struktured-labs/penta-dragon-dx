"""Offline profile controls; synthetic approvals here are never release evidence."""
import copy
from contextlib import redirect_stdout
import io
import json
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import patch, mock_open

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "scripts"), str(ROOT / "scripts/diagnostics")]
import record_palette_approval as recorder
import r534_source_profile as profile
import build_release_bundle as bundle


class R534PaletteSourceTests(unittest.TestCase):
    def fixture(self):
        path = ROOT / "tmp/r534-original-source-current522/build-receipt.json"
        if not path.is_file():
            self.skipTest("retained source-only construction fixture unavailable")
        receipt = json.loads(path.read_text())
        rom = (path.parent / "candidate.gb").read_bytes()
        palette = Path(receipt["palette"]["path"])
        binding = {"receipt": str(path), "receipt_sha256": profile.digest(path.read_bytes()),
                   "source_fingerprint": receipt["source_fingerprint"]}
        return receipt, rom, palette, binding

    def test_cli_rejects_ambiguous_profiles_and_implicit_approval(self):
        cases = (
            (["--r534-source"], "requires --source-output"),
            (["--r534-source", "--source-output", "tmp/unused"], "requires --output and --confirm"),
            (["--r534-source", "--verify-only", "--source-output", "tmp/unused", "--confirm", "AUDIENCE APPROVED"], "cannot record"),
            (["--r534-source", "--verify-only", "--source-output", "tmp/unused", "--output", "never-written.json"], "cannot record"),
            (["--source-output", "tmp/unused"], "requires --r534-source"),
        )
        for flag in ("--r534-original-replay", "--expanded-ted", "--menu-icon-colors"):
            cases += ((["--r534-source", flag], "distinct complete profile"),)
        for flag in ("--historical-input-manifest", "--replay-output"):
            cases += ((["--r534-source", flag, "unused"], "distinct complete profile"),)
        for argv, error in cases:
            with self.subTest(argv=argv), patch.object(sys, "argv", ["recorder", *argv]), \
                 patch.object(recorder, "record_r534_source", side_effect=AssertionError("unexpected build")):
                with self.assertRaisesRegex(SystemExit, error):
                    recorder.main()

    def test_cli_routes_verification_only_and_rejects_existing_approval(self):
        argv = ["recorder", "--r534-source", "--verify-only", "--source-output", "tmp/unused"]
        with patch.object(sys, "argv", argv), patch.object(recorder, "record_r534_source", return_value=0) as run:
            self.assertEqual(recorder.main(), 0)
            self.assertTrue(run.call_args.args[0].verify_only)
        argv = ["recorder", "--r534-source", "--source-output", "tmp/unused",
                "--confirm", "AUDIENCE APPROVED", "--output", str(ROOT / "AGENTS.md")]
        with patch.object(sys, "argv", argv), patch.object(recorder, "record_r534_source") as run:
            with self.assertRaisesRegex(SystemExit, "already exists"):
                recorder.main()
            run.assert_not_called()

    def test_binding_rechecks_receipt_hash_and_verified_fingerprint(self):
        receipt, rom, palette, binding = self.fixture()
        # The retained receipt's nested filesystem trace is intentionally stale
        # after source changes.  Isolate the already-tested receipt verifier so
        # this unit continues to exercise the binding layer itself.
        with patch.object(profile.builder, "verify_receipt", return_value=receipt) as verify:
            self.assertEqual(profile.verify_binding(binding, rom, palette), receipt)
        verify.assert_called_once_with(Path(binding["receipt"]), rom, palette)

    def test_binding_rejects_inventory_types_paths_hashes_and_staleness(self):
        receipt, rom, palette, binding = self.fixture()
        changes = (
            (lambda b: b.update(extra=True), "field inventory"),
            (lambda b: b.update(receipt=3), "nonempty strings"),
            (lambda b: b.update(receipt="tmp/relative.json"), "canonical path"),
            (lambda b: b.update(receipt_sha256="0" * 64), "receipt hash differs"),
        )
        for change, error in changes:
            bad = copy.deepcopy(binding)
            change(bad)
            with self.subTest(error=error), self.assertRaisesRegex(ValueError, error):
                profile.verify_binding(bad, rom, palette)
        with patch.object(profile.builder, "source_snapshot", return_value=("stale", [])):
            with self.assertRaisesRegex(ValueError, "source snapshot is stale"):
                profile.verify_binding(binding, rom, palette)
        with patch.object(profile.builder, "verify_receipt", return_value=receipt):
            with self.assertRaisesRegex(ValueError, "fingerprint binding differs"):
                profile.verify_binding({**binding, "source_fingerprint": "wrong"}, rom, palette)

    def test_source_build_rejects_wrong_rom_before_launch(self):
        with patch.object(Path, "read_bytes", return_value=b"not r534"), \
             patch.object(profile.subprocess, "run", side_effect=AssertionError("unexpected launch")):
            with self.assertRaisesRegex(ValueError, "exact pinned r534"):
                profile.build_verification(Path("wrong.gb"), Path("palette.yaml"), ROOT / "tmp/unused")

    def test_source_profile_launches_only_new_builder_and_retains_build_failure(self):
        rom = ROOT / "tmp/stage4-cache-key-r534/candidate.gb"
        palette = profile.builder.DEFAULT_PALETTE
        output = ROOT / "tmp/never-created-profile-failure"
        result = SimpleNamespace(returncode=1, stdout="", stderr="source preimage failed")
        with patch.object(profile.subprocess, "run", return_value=result) as run:
            with self.assertRaisesRegex(ValueError, "source build failed: source preimage failed"):
                profile.build_verification(rom, palette, output)
        self.assertEqual(run.call_args.args[0], [sys.executable, str(ROOT / "scripts/build_r534_candidate.py"),
                         "--palette-yaml", str(palette.resolve()), "--out-dir", str(output.resolve())])
        self.assertFalse(output.exists())

    def verification(self):
        _, rom, palette, binding = self.fixture()
        return {"rom_sha256": profile.digest(rom), "palette_yaml_sha256": profile.digest(palette.read_bytes()),
                "source_build": binding}, rom, palette

    def test_verify_only_never_opens_approval_output(self):
        verification, _, palette = self.verification()
        args = SimpleNamespace(rom=ROOT / "tmp/stage4-cache-key-r534/candidate.gb", palettes=palette,
                               source_output=ROOT / "tmp/unused", verify_only=True, confirm="", output=None)
        with patch.object(profile, "build_verification", return_value=verification), \
             patch.object(Path, "open", side_effect=AssertionError("unexpected approval write")), \
             redirect_stdout(io.StringIO()):
            self.assertEqual(recorder.record_r534_source(args), 0)

    def test_explicit_approval_serialization_is_bound_and_exclusive_without_writing(self):
        verification, _, palette = self.verification()
        output = ROOT / "tmp/never-written-source-profile-approval.json"
        args = SimpleNamespace(rom=ROOT / "tmp/stage4-cache-key-r534/candidate.gb", palettes=palette,
                               source_output=ROOT / "tmp/unused", verify_only=False,
                               confirm="AUDIENCE APPROVED", output=output, notes="SYNTHETIC UNIT TEST ONLY")
        opener = mock_open()
        real_open = Path.open
        def open_selected(path, *args, **kwargs):
            return opener(*args, **kwargs) if path == output else real_open(path, *args, **kwargs)
        with patch.object(profile, "build_verification", return_value=verification), \
             patch.object(profile, "verify_binding", return_value={}) as verify, \
             patch.object(Path, "open", open_selected), redirect_stdout(io.StringIO()):
            self.assertEqual(recorder.record_r534_source(args), 0)
        verify.assert_called_once()
        opener.assert_called_once_with("x")
        approval = json.loads(opener().write.call_args.args[0])
        self.assertEqual(approval["build_profile"], profile.PROFILE)
        self.assertEqual(approval["source_build"], verification["source_build"])
        self.assertEqual(approval["confirmation"], "AUDIENCE APPROVED")
        self.assertFalse(output.exists())
        args.confirm = ""
        with patch.object(profile, "build_verification", side_effect=AssertionError("unexpected build")):
            with self.assertRaisesRegex(SystemExit, "explicit confirmation"):
                recorder.record_r534_source(args)

    def approval(self):
        verification, rom, palette = self.verification()
        return {"schema": "penta-dragon-dx-palette-approval-v1", "status": "audience-approved",
                "confirmation": "AUDIENCE APPROVED", "rom_md5": bundle.digest(rom, "md5"),
                "rom_sha256": profile.digest(rom), "palette_yaml": str(palette.resolve()),
                "palette_yaml_sha256": verification["palette_yaml_sha256"],
                "build_profile": dict(profile.PROFILE), "source_build": verification["source_build"]}, rom, palette

    def test_packager_requires_new_profile_and_independent_source_validation(self):
        approval, rom, palette = self.approval()
        with patch.object(bundle, "load_json", return_value=approval), \
             patch.object(profile, "verify_binding", return_value={}) as verify:
            self.assertEqual(bundle.validate_palette_approval(Path("synthetic-never-written.json"), rom, palette), approval)
        verify.assert_called_once_with(approval["source_build"], rom, palette)
        mutations = (
            (lambda a: a.update(confirmation=""), "explicit audience confirmation"),
            (lambda a: a.update(palette_yaml="wrong"), "selected YAML path"),
            (lambda a: a["build_profile"].update(name="expanded-ted-menu"), "original-source approval profile"),
            (lambda a: a["build_profile"].update(expanded_ted=1), "original-source approval profile"),
            (lambda a: a.update(status="source-build-pass"), "status does not match"),
        )
        for mutate, error in mutations:
            bad = copy.deepcopy(approval)
            mutate(bad)
            with self.subTest(error=error), patch.object(bundle, "load_json", return_value=bad):
                with self.assertRaisesRegex(SystemExit, error):
                    bundle.validate_palette_approval(Path("synthetic-never-written.json"), rom, palette)
        with patch.object(bundle, "load_json", return_value=approval), \
             patch.object(profile, "verify_binding", side_effect=ValueError("stale source")):
            with self.assertRaisesRegex(SystemExit, "source proof is invalid: stale source"):
                bundle.validate_palette_approval(Path("synthetic-never-written.json"), rom, palette)

    def test_packager_keeps_legacy_profile_for_other_roms(self):
        rom, palette = b"legacy unit test ROM", profile.builder.DEFAULT_PALETTE
        approval = {"schema": "penta-dragon-dx-palette-approval-v1", "status": "audience-approved",
                    "rom_md5": bundle.digest(rom, "md5"), "rom_sha256": profile.digest(rom),
                    "palette_yaml_sha256": profile.digest(palette.read_bytes()),
                    "build_profile": {**profile.PROFILE, "name": "expanded-ted-menu"}}
        with patch.object(bundle, "load_json", return_value=approval):
            self.assertEqual(bundle.validate_palette_approval(Path("synthetic-never-written.json"), rom, palette), approval)


class ReleaseCurrentEvidenceTests(unittest.TestCase):
    def test_final_packaging_still_requires_both_external_approvals(self):
        cases = (
            (["--final"], "requires --hardware-manifest and --palette-approval"),
            (["--final", "--palette-approval", "source-proof-is-not-approval.json"], "requires --hardware-manifest"),
            (["--final", "--hardware-manifest", "hardware.json"], "requires --hardware-manifest"),
            (["--palette-approval", "approval.json"], "accepted only together with --final"),
        )
        for options, error in cases:
            argv = ["bundle", "--emulator-manifest", "matrix.json", *options]
            with self.subTest(options=options), patch.object(sys, "argv", argv), \
                 patch.object(Path, "is_file", return_value=True), \
                 patch.object(Path, "read_bytes", side_effect=AssertionError("unexpected packaging")):
                with self.assertRaisesRegex(SystemExit, error):
                    bundle.main()

    def manifest(self):
        rom = b"offline unit test ROM"
        md5 = bundle.digest(rom, "md5")
        runtime = {"identity": "synthetic test only"}
        manifest = {"status": "emulator-pass", "scope": "full", "failures": 0,
                    "rom_md5": md5, "rom_size": len(rom), "source_rom_md5_after": md5,
                    "tested_rom_md5_after": md5, "rom_hashes_intact": True,
                    "source_inputs_intact": True, "source_fingerprint": "snapshot",
                    "source_fingerprint_after": "snapshot", "source_input_count": 1,
                    "runtime_tools_intact": True, "runtime_tools": runtime, "runtime_tools_after": runtime,
                    "selected_gates": list(bundle.REQUIRED_GATE_ORDER),
                    "results": [{"name": name, "status": "passed", "returncode": 0} for name in bundle.REQUIRED_GATE_ORDER]}
        return manifest, rom, runtime

    def test_packager_requires_current_full_ordered_source_and_runtime(self):
        manifest, rom, runtime = self.manifest()
        with patch.object(bundle, "load_json", return_value=manifest), \
             patch.object(bundle, "source_snapshot", return_value=("snapshot", [{}])), \
             patch.object(bundle, "emulator_runtime_snapshot", return_value=runtime):
            self.assertEqual(bundle.validate_emulator_manifest(Path("synthetic.json"), rom), manifest)
        mutations = (
            (lambda m: (m["results"].reverse(), m["selected_gates"].reverse()), "gate order differs"),
            (lambda m: m.update(source_fingerprint="stale", source_fingerprint_after="stale"), "source snapshot is not current"),
            (lambda m: m.update(source_input_count=0), "source snapshot is not current"),
            (lambda m: m.update(runtime_tools_intact=False), "runtime identities"),
            (lambda m: m.update(runtime_tools={"identity": "old"}, runtime_tools_after={"identity": "old"}), "runtime identities"),
            (lambda m: m.update(runtime_tools_after={}), "runtime identities"),
        )
        for mutate, error in mutations:
            bad = copy.deepcopy(manifest)
            mutate(bad)
            with self.subTest(error=error), patch.object(bundle, "load_json", return_value=bad), \
                 patch.object(bundle, "source_snapshot", return_value=("snapshot", [{}])), \
                 patch.object(bundle, "emulator_runtime_snapshot", return_value=runtime):
                with self.assertRaisesRegex(SystemExit, error):
                    bundle.validate_emulator_manifest(Path("synthetic.json"), rom)


if __name__ == "__main__":
    unittest.main()
