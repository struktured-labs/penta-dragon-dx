"""Repository launcher failure paths: these tests never launch an emulator."""
import contextlib
import io
import json
import os
from pathlib import Path
import runpy
import subprocess
import sys
import unittest
from unittest.mock import patch
import uuid

ROOT = Path(__file__).resolve().parents[1]
RUNNER = ROOT/'scripts/diagnostics/run_secret_entry_probe.py'
STATE = 'tmp/secret-alias-chunk-lowhealth-return-01/frame-0960.ss0'
ROM = 'tmp/secret-alias-chunk-trial-01/candidate.gb'


class SecretRunner(unittest.TestCase):
    def invoke(self, rom, state, output, code=75):
        if not (ROOT/rom).exists() or not (ROOT/state).exists():
            self.skipTest('local fixture unavailable')
        with patch.dict(os.environ, {'ENTRY_ROM':str(ROOT/rom), 'ENTRY_FRAMES':'1'}, clear=True), \
             patch.object(sys, 'argv', [str(RUNNER), state, output]), \
             patch('subprocess.run', return_value=subprocess.CompletedProcess([], code)) as run, \
             contextlib.redirect_stdout(io.StringIO()):
            try:
                runpy.run_path(str(RUNNER), run_name='__main__')
            except (ValueError, SystemExit) as error:
                return error, run.call_args_list
        self.fail('launcher failed to report termination')

    def test_cross_rom_state_rejected_before_launch_or_output(self):
        name = 'runner-mismatch-' + uuid.uuid4().hex
        error, calls = self.invoke('tmp/secret-sound-alias-fast-trial-01/candidate.gb', STATE, name)
        self.assertIsInstance(error, ValueError)
        self.assertIn('identity mismatch', str(error))
        self.assertEqual(calls, [])
        self.assertFalse((ROOT/'tmp'/name).exists())

    def test_output_escape_rejected_before_launch(self):
        error, calls = self.invoke(ROM, STATE, '../runner-escape')
        self.assertIsInstance(error, ValueError)
        self.assertEqual(calls, [])

    def test_busy_lock_status_is_preserved_without_retry(self):
        name = 'runner-busy-' + uuid.uuid4().hex
        error, calls = self.invoke(ROM, STATE, name)
        self.assertIsInstance(error, SystemExit)
        self.assertEqual(error.code, 75)
        self.assertEqual(len(calls), 1)
        self.assertEqual(Path(calls[0].args[0][0]), ROOT.resolve()/'scripts/mgba-qt-singleflight')
        receipt = json.loads((ROOT/'tmp'/name/'receipt.json').read_text())
        self.assertEqual(receipt['status'], 75)
        self.assertNotIn('native_capture', receipt)

    def test_audio_configuration_is_explicit_without_native_capture(self):
        name = 'runner-explicit-audio-' + uuid.uuid4().hex
        error, calls = self.invoke(ROM, STATE, name)
        self.assertIsInstance(error, SystemExit)
        self.assertEqual(error.code, 75)
        self.assertEqual(len(calls), 1)
        command = calls[0].args[0]
        expected = ['-C', 'mute=0', '-C', 'volume=256', '-C',
                    'fastForwardMute=-1', '-C', 'fastForwardVolume=256']
        self.assertEqual(command[2:10], expected)
        self.assertEqual(calls[0].kwargs['env']['ENTRY_AUDIO_ENABLED'], '1')
        receipt = json.loads((ROOT/'tmp'/name/'receipt.json').read_text())
        self.assertEqual(receipt['audio_options'], expected)
        self.assertEqual(receipt['diagnostic_environment']['ENTRY_AUDIO_ENABLED'], '1')


if __name__ == '__main__': unittest.main()
