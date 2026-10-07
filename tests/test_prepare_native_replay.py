"""#67 source-built startup adapter contracts (no emulator launch)."""
import importlib.util
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "prepare_replay", ROOT / "scripts/diagnostics/prepare_native_replay.py")
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class NativeReplayPreparation(unittest.TestCase):
    def test_cmake_quotes_are_arguments_not_shell_evaluation(self):
        flags = 'C_DEFINES = -DENABLE_SCRIPTING -DNAME=\\"value\\"\nC_INCLUDES = -I/path -isystem /system\n'
        self.assertEqual(MODULE.cmake_arguments(flags), [
            '-DENABLE_SCRIPTING', '-DNAME="value"', '-I/path', '-isystem', '/system'])

    def test_incomplete_abi_definitions_fail_closed(self):
        with self.assertRaisesRegex(ValueError, 'compile definitions'):
            MODULE.cmake_arguments('C_INCLUDES = -I/path\n')

    def test_inherited_native_injection_is_not_accepted(self):
        for key in ('LD_PRELOAD', 'PENTA_NATIVE_AV_PREFIX', 'ENTRY_NATIVE_START_GATE'):
            with self.subTest(key=key), self.assertRaisesRegex(ValueError, 'owns'):
                MODULE.prepare(ROOT / 'tmp/never-created', {key: 'external'})


if __name__ == '__main__':
    unittest.main()
