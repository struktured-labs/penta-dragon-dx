"""Exact-state mode must reject stale identity before copying machine state."""
import json
from pathlib import Path
import sys
import tempfile
import subprocess
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts/diagnostics"))
import verify_low_health_flicker as gate
from source_observer_fixtures import observer_fixtures


class BootStateTest(unittest.TestCase):
    def test_r453_release_uses_authenticated_current_hazard_fixture(self):
        import verify_release_candidate as release
        with tempfile.TemporaryDirectory(dir=ROOT / "tmp") as directory:
            rom = Path(directory) / "candidate.gb"
            rom.write_bytes(observer_fixtures()['r453'])
            selected = {item.name: item for item in release.build_gates(rom, Path(directory) / "out")}
        check = selected["low_health_flicker"]
        self.assertEqual(check.dependencies, ("stage1_current_hazard_state",))
        for flag in ("--boot-derived-state", "--hazard-state-receipt",
                     "--require-scene0b-low-health", "--trace-scanner",
                     "--require-hazard-attributes", "--require-hazard-publication-owner"):
            self.assertIn(flag, check.command)
        self.assertIn("stage1-hazard.ss0", check.command[check.command.index("--state") + 1])

    def test_r453_observer_identity_rejects_changed_rom(self):
        rom = observer_fixtures()['r453']
        self.assertEqual(gate.owner_address(rom), 0xFF01)
        self.assertEqual(gate.bulk_compiler_profile(rom), "r426-bulk-v1")
        self.assertEqual(gate.publication_route_profile(rom), "r451c-bounded-room03")
        changed = bytearray(rom)
        changed[0x4324] ^= 1
        self.assertEqual(gate.owner_address(changed), 0xFFA5)
        self.assertEqual(gate.bulk_compiler_profile(changed), "")
        self.assertEqual(gate.publication_route_profile(changed), "")

    def test_r453_negative_control_uses_same_observer(self):
        import hashlib
        import verify_stage1_exact_destination_mutation as mutation
        rom = bytearray(observer_fixtures()['r453'])
        offset = 0x4EBD4
        self.assertEqual(rom[offset:offset + 12], mutation.AUTHORITATIVE_DESTINATION)
        rom[offset:offset + 12] = mutation.FORCED_WRONG_DESTINATION
        self.assertEqual(hashlib.sha256(rom).hexdigest(), gate.R453_WRONG_DESTINATION_SHA256)
        self.assertEqual(gate.owner_address(rom), 0xFF01)
        self.assertEqual(gate.bulk_compiler_profile(rom), "r426-bulk-v1")
        self.assertEqual(gate.publication_route_profile(rom), "r451c-bounded-room03")
        rom[offset] ^= 1
        self.assertEqual(gate.owner_address(rom), 0xFFA5)
        self.assertEqual(gate.bulk_compiler_profile(rom), "")
        self.assertEqual(gate.publication_route_profile(rom), "")

    def test_recovery_drive_rejects_invalid_requests_before_launch(self):
        for options in (("--recovery-drive-frames", "-1"),
                        ("--recovery-drive-frames", "1"),
                        ("--post-trigger-keys", "256"),
                        ("--require-scene0b-low-health", "--recovery-drive-frames", "9999")):
            run = subprocess.run([sys.executable, str(Path(gate.__file__)), *options],
                                 capture_output=True, text=True)
            self.assertEqual(run.returncode, 2, run.stderr)

    def test_bulk_contract_requires_complete_valid_publications(self):
        for prefix in ("", "scene0b_"):
            counts = {prefix + key: value for key, value in {
                "compiler_publications": 3, "bulk_completions": 3,
                "bulk_mismatches": 0, "compiler_row_calls": 0,
                "compiler_first_rows": 0, "compiler_contract_mismatches": 0,
            }.items()}
            check = lambda c: gate.authenticated_compiler_counter_contract(
                c, "r426-bulk-v1", prefix=prefix)
            self.assertTrue(check(counts))
            for key in counts:
                missing = dict(counts); missing.pop(key)
                self.assertFalse(check(missing), key)
                wrong = dict(counts); wrong[key] += 1
                self.assertFalse(check(wrong), key)
            self.assertFalse(gate.authenticated_compiler_counter_contract(
                counts, "unreviewed", prefix=prefix))

    def test_owner_binding_is_exact(self):
        rom = observer_fixtures()['r424']
        self.assertEqual(gate.owner_address(rom), 0xFF01)
        self.assertEqual(gate.owner_address(rom + b"mutation"), 0xFFA5)
        self.assertEqual(gate.owner_address(b"unknown"), 0xFFA5)
        current = observer_fixtures()['r435']
        self.assertEqual(gate.owner_address(current), 0xFF01)
        self.assertEqual(gate.owner_address(current + b"mutation"), 0xFFA5)
        self.assertEqual(gate.bulk_compiler_profile(current), "r426-bulk-v1")
        self.assertEqual(gate.bulk_compiler_profile(current + b"mutation"), "")
        recovery = observer_fixtures()['r436']
        self.assertEqual(gate.owner_address(recovery), 0xFF01)
        self.assertEqual(gate.bulk_compiler_profile(recovery), "r426-bulk-v1")
        self.assertEqual(gate.owner_address(recovery + b"mutation"), 0xFFA5)
        self.assertEqual(gate.bulk_compiler_profile(recovery + b"mutation"), "")

    def test_copy_and_reject_mutated_sources(self):
        with tempfile.TemporaryDirectory(dir=ROOT / "tmp") as directory:
            root = Path(directory)
            rom, state, report, target = [root / name for name in
                                          ("rom.gb", "state.ss0", "report", "copy.ss0")]
            rom.write_bytes(b"candidate")
            state.write_bytes(b"all CPU and video bytes preserved")
            report.write_text("boot report")
            provenance = {"schema": "penta-boot-derived-state-v1",
                          "probe_sha256": gate.digest(ROOT / "scripts/diagnostics/probe_stage1_natural_menu_bg.lua")}
            for name, path in (("rom", rom), ("state", state), ("report", report)):
                provenance[name + "_path"] = str(path.resolve())
                provenance[name + "_sha256"] = gate.digest(path)
            Path(str(state) + ".json").write_text(json.dumps(provenance))
            result = gate.copy_boot_state(state, rom, target)
            self.assertEqual(target.read_bytes(), state.read_bytes())
            self.assertEqual(result["normalization_writes"], 0)
            for path in (rom, state, report):
                original = path.read_bytes()
                path.write_bytes(original + b"mutation")
                with self.assertRaises(ValueError):
                    gate.copy_boot_state(state, rom, target)
                path.write_bytes(original)

    def test_hazard_boot_copy_requires_identity_tools_and_coverage(self):
        with tempfile.TemporaryDirectory(dir=ROOT / "tmp") as directory:
            root = Path(directory)
            rom, state, target, receipt = [root / name for name in
                                         ("rom.gb", "state.ss0", "copy.ss0", "receipt.json")]
            rom.write_bytes(b"rom")
            state.write_bytes(b"exact machine state")
            data = dict(schema="penta-stage1-hazard-state-v1", passed=True,
                        rom=str(rom), state=str(state), rom_sha256=gate.digest(rom),
                        state_sha256=gate.digest(state), hardware={"settled": True},
                        minimum_hazard_cells=40, minimum_tooth_cells=10,
                        hazard_cells=77, tooth_cells=25)
            for name, filename in (("generator", "generate_stage1_hazard_state.py"),
                                   ("probe", "probe_stage1_north_integrity.lua")):
                data[name + "_sha256"] = gate.digest(ROOT / "scripts/diagnostics" / filename)
            receipt.write_text(json.dumps(data))
            self.assertEqual(gate.copy_hazard_boot_state(state, rom, target, receipt)["normalization_writes"], 0)
            self.assertEqual(target.read_bytes(), state.read_bytes())
            # Actual observed coverage, not the requested minimum, must meet
            # the absolute ten-tooth floor. Current cold routes may ask for 1.
            receipt.write_text(json.dumps(dict(data, minimum_tooth_cells=1)))
            self.assertEqual(gate.copy_hazard_boot_state(state, rom, target, receipt)["normalization_writes"], 0)
            for key, value in (("rom_sha256", "bad"), ("state_sha256", "bad"),
                               ("generator_sha256", "bad"), ("probe_sha256", "bad"),
                               ("passed", False), ("tooth_cells", 0),
                               ("minimum_tooth_cells", 26), ("tooth_cells", 9), ("hardware", {})):
                receipt.write_text(json.dumps(dict(data, **{key: value})))
                with self.subTest(key=key), self.assertRaises(ValueError):
                    gate.copy_hazard_boot_state(state, rom, target, receipt)


if __name__ == "__main__":
    unittest.main()
