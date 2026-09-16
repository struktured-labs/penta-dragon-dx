#!/usr/bin/env python3
"""Exercise hash-qualified MiSTer release inputs without contacting hardware."""

from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace
import sys
import tempfile
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "mister.py"


def load_mister_module():
    spec = importlib.util.spec_from_file_location("mister_release_inputs", SCRIPT)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {SCRIPT}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class MisterReleaseInputTests(unittest.TestCase):
    def setUp(self) -> None:
        self.mister = load_mister_module()
        (ROOT / "tmp").mkdir(exist_ok=True)
        self.temporary = tempfile.TemporaryDirectory(
            prefix="mister-release-inputs-",
            dir=ROOT / "tmp",
        )
        self.scratch = Path(self.temporary.name)
        self.rom = self.scratch / "candidate.gb"
        self.patch = self.scratch / "candidate.ips"
        self.emulator = self.scratch / "emulator.json"
        self.rom.write_bytes(b"candidate-rom")
        self.patch.write_bytes(b"candidate-patch")
        self.mister.REQUIRED_GATE_ORDER = ("gate-a", "gate-b")
        self.runtime = {"mgba_qt": {"sha256": "runtime-hash"}}
        source_mock = mock.patch.object(self.mister, "source_snapshot", return_value=("source-hash", [{}]))
        runtime_mock = mock.patch.object(self.mister, "emulator_runtime_snapshot", return_value=self.runtime)
        source_mock.start()
        runtime_mock.start()
        self.addCleanup(source_mock.stop)
        self.addCleanup(runtime_mock.stop)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def write_emulator_manifest(self, names: tuple[str, ...]) -> None:
        rom_md5 = hashlib.md5(self.rom.read_bytes()).hexdigest()
        runtime = {"mgba_qt": {"sha256": "runtime-hash"}}
        manifest = {
            "status": "emulator-pass",
            "scope": "full",
            "failures": 0,
            "rom_md5": rom_md5,
            "rom_size": self.rom.stat().st_size,
            "source_rom_md5_after": rom_md5,
            "tested_rom_md5_after": rom_md5,
            "rom_hashes_intact": True,
            "source_inputs_intact": True,
            "runtime_tools_intact": True,
            "source_fingerprint": "source-hash",
            "source_fingerprint_after": "source-hash",
            "source_input_count": 1,
            "source_rom": str(self.rom),
            "tested_rom": str(self.rom),
            "runtime_tools": runtime,
            "runtime_tools_after": runtime,
            "selected_gates": list(names),
            "results": [
                {"name": name, "status": "passed", "returncode": 0}
                for name in names
            ],
        }
        self.emulator.write_text(json.dumps(manifest))

    def test_preflight_accepts_exact_explicit_rom_and_patch(self) -> None:
        self.write_emulator_manifest(self.mister.REQUIRED_GATE_ORDER)
        completed = SimpleNamespace(returncode=0, stdout="", stderr="")
        with mock.patch.object(
            self.mister.subprocess,
            "run",
            return_value=completed,
        ) as run:
            _manifest, rom_md5 = self.mister.verify_release_sweep_inputs(
                self.emulator,
                self.rom,
                self.patch,
            )

        self.assertEqual(rom_md5, hashlib.md5(self.rom.read_bytes()).hexdigest())
        command = run.call_args.args[0]
        self.assertEqual(Path(command[2]), self.rom)
        self.assertEqual(Path(command[4]), self.patch)

    def test_preflight_rejects_truncated_gate_roster(self) -> None:
        self.write_emulator_manifest(("gate-a",))
        with self.assertRaisesRegex(RuntimeError, "authoritative 2-gate order"):
            self.mister.verify_release_sweep_inputs(
                self.emulator,
                self.rom,
                self.patch,
            )

    def test_deploy_uses_explicit_rom(self) -> None:
        expected_md5 = hashlib.md5(self.rom.read_bytes()).hexdigest()
        captured: list[Path] = []
        with (
            mock.patch.object(
                self.mister,
                "get_rom_md5",
                side_effect=["MISSING", expected_md5],
            ),
            mock.patch.object(
                self.mister,
                "scp_to_mister",
                side_effect=lambda path, _remote: captured.append(path),
            ),
        ):
            self.mister.cmd_deploy(self.rom)

        self.assertEqual(captured, [self.rom])

    def test_generated_launch_sidecar_is_not_in_system_scratch(self) -> None:
        self.assertEqual(Path(self.mister.MISTER_MGL_PATH).parent, Path(self.mister.MISTER_ROM_DIR))
        self.assertEqual(Path(self.mister.MISTER_MGL_PATH).name, "penta_dragon_dx_launch.mgl")

    def test_preflight_rejects_stale_source_runtime_and_changed_tested_rom(self) -> None:
        self.write_emulator_manifest(self.mister.REQUIRED_GATE_ORDER)
        changes = (
            ({"source_fingerprint": "stale", "source_fingerprint_after": "stale"}, "source snapshot is not current"),
            ({"runtime_tools": {"old": True}, "runtime_tools_after": {"old": True}}, "runtime identities are not current"),
            ({"tested_rom": str(self.patch)}, "tested_rom bytes differ"),
            ({"rom_hashes_intact": 1}, "rom_hashes_intact does not match"),
        )
        value = json.loads(self.emulator.read_text())
        for changed, error in changes:
            with self.subTest(error=error), mock.patch.object(self.mister, "load_json_object", return_value={**value, **changed}), \
                 mock.patch.object(self.mister.subprocess, "run", side_effect=AssertionError("unexpected patch launch")):
                with self.assertRaisesRegex(RuntimeError, error):
                    self.mister.verify_release_sweep_inputs(self.emulator, self.rom, self.patch)

    def test_preflight_rechecks_inputs_after_patch_validation(self) -> None:
        self.write_emulator_manifest(self.mister.REQUIRED_GATE_ORDER)
        completed = SimpleNamespace(returncode=0, stdout="", stderr="")
        def mutate(*args, **kwargs):
            self.patch.write_bytes(b"changed-during-unit-test")
            return completed
        with mock.patch.object(self.mister.subprocess, "run", side_effect=mutate):
            with self.assertRaisesRegex(RuntimeError, "changed during preflight"):
                self.mister.verify_release_sweep_inputs(self.emulator, self.rom, self.patch)

    def test_checkpoint_rechecks_qualification_before_contacting_hardware(self) -> None:
        self.write_emulator_manifest(self.mister.REQUIRED_GATE_ORDER)
        manifest = {
            "schema": "penta-dragon-dx-mister-release-v1", "status": "hardware-sweep-incomplete",
            "mister_host": self.mister.MISTER_HOST, "local_rom": str(self.rom), "local_patch": str(self.patch),
            "rom_md5": self.mister.md5_file(self.rom), "rom_sha256": self.mister.sha256_file(self.rom),
            "release_patch_sha256": self.mister.sha256_file(self.patch), "emulator_manifest": str(self.emulator),
            "emulator_manifest_sha256": self.mister.sha256_file(self.emulator),
        }
        with mock.patch.object(self.mister, "require_mister_reservation") as reservation, \
             mock.patch.object(self.mister, "verify_release_sweep_inputs", side_effect=RuntimeError("stale qualification")) as verify, \
             mock.patch.object(self.mister, "get_corename", side_effect=AssertionError("unexpected hardware")):
            with self.assertRaisesRegex(RuntimeError, "stale qualification"):
                self.mister.verify_live_sweep_identity(manifest)
        reservation.assert_called_once()
        verify.assert_called_once_with(self.emulator, self.rom, self.patch)


if __name__ == "__main__":
    unittest.main()
