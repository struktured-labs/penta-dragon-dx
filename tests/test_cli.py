"""CLI regressions: no test launches an emulator or builds a ROM."""

import os
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import patch

from click.testing import CliRunner
from penta_dragon_dx import cli


ROOT = Path(__file__).resolve().parents[1]


class CliTests(unittest.TestCase):
    def test_module_and_imported_commands_match(self):
        env = dict(os.environ, PYTHONPATH=str(ROOT / "src"), PYTHONDONTWRITEBYTECODE="1")
        module = subprocess.run(
            [sys.executable, "-m", "penta_dragon_dx.cli", "--help"],
            env=env, capture_output=True, text=True, check=True,
        )
        imported = CliRunner().invoke(cli.main, ["--help"])
        self.assertEqual(imported.exit_code, 0)
        for name in ("analyze", "dev-loop", "verify", "inject", "build-patch"):
            self.assertIn(name, module.stdout)
            self.assertIn(name, imported.output)
        for name in ("analyze", "dev-loop"):
            result = subprocess.run(
                [sys.executable, "-m", "penta_dragon_dx.cli", name, "--help"],
                env=env, capture_output=True, text=True,
            )
            self.assertEqual(result.returncode, 0, result.stderr)

    def invoke_dev(self, extra=(), returncode=0, launcher_exists=True, launch_error=None):
        with patch.object(cli.Path, "mkdir"), \
             patch.object(cli.Path, "is_file", return_value=launcher_exists), \
             patch.object(cli.rom_utils, "read_rom_bytes", return_value=b"ROM") as read, \
             patch.object(cli.palette_injector, "load_palettes", return_value={}), \
             patch.object(cli.palette_injector, "apply_palettes", return_value=(b"ROM", [])), \
             patch.object(cli.rom_utils, "set_cgb_supported", return_value=b"ROM"), \
             patch.object(cli.rom_utils, "write_rom_bytes") as write, \
             patch.object(cli.subprocess, "Popen") as raw_launch, \
             patch.object(cli.subprocess, "run", side_effect=launch_error) as launch:
            launch.return_value.returncode = returncode
            result = CliRunner().invoke(cli.main, [
                "dev-loop", "--rom", str(ROOT / "AGENTS.md"),
                "--palette-file", str(ROOT / "AGENTS.md"), "--vblank", *extra,
            ])
            raw_launch.assert_not_called()
            return result, launch, read, write

    def test_guarded_synchronous_launch(self):
        result, launch, _, write = self.invoke_dev()
        self.assertEqual(result.exit_code, 0, result.output)
        launch.assert_called_once_with([
            "bash", str(ROOT / "scripts/launch_mgba.sh"),
            str(Path("rom/working/penta_dx.gb").resolve()),
        ])
        write.assert_called_once()

    def test_busy_exit_preserved(self):
        result, launch, _, _ = self.invoke_dev(returncode=75)
        self.assertEqual(result.exit_code, 75)
        self.assertIn("slot is busy", result.output)
        launch.assert_called_once()

    def test_other_failure_preserved(self):
        result, _, _, _ = self.invoke_dev(returncode=4)
        self.assertEqual(result.exit_code, 4)

    def test_signal_failure_normalized(self):
        result, _, _, _ = self.invoke_dev(returncode=-15)
        self.assertEqual(result.exit_code, 143)

    def test_missing_launcher_fails_before_build(self):
        result, launch, read, write = self.invoke_dev(launcher_exists=False)
        self.assertEqual(result.exit_code, 1)
        self.assertIn("Guarded launcher", result.output)
        launch.assert_not_called()
        read.assert_not_called()
        write.assert_not_called()

    def test_arbitrary_emulator_rejected_before_build(self):
        for emulator in ("mgba", "/usr/bin/mgba-qt", "sameboy", "sh"):
            with self.subTest(emulator=emulator):
                result, launch, read, write = self.invoke_dev(["--emu", emulator])
                self.assertEqual(result.exit_code, 2)
                launch.assert_not_called()
                read.assert_not_called()
                write.assert_not_called()

    def test_launch_os_error_is_clear(self):
        result, _, _, _ = self.invoke_dev(launch_error=OSError("no bash"))
        self.assertEqual(result.exit_code, 1)
        self.assertIn("Failed to start guarded launcher", result.output)


if __name__ == "__main__":
    unittest.main()
