"""#43 retained failing startup and full-output neutrality evidence."""
import hashlib
import json
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]


class StartupCPUGate(unittest.TestCase):
    def receipt(self, name):
        path = ROOT / 'tmp' / name / 'receipt.json'
        if not path.exists():
            self.skipTest('local native replay evidence unavailable')
        return json.loads(path.read_text())

    def test_rejected_endpoint_now_captures_without_memory_assistance(self):
        old = self.receipt('secret-alias-chunk-moving-left-01')
        diagnostic = self.receipt('secret-endpoint-startup-diagnostic-01')
        fixed = self.receipt('secret-endpoint-startup-fixed-01')
        self.assertEqual(old['status'], 74)
        self.assertEqual(diagnostic['status'], 74)
        log = (ROOT / 'tmp/secret-endpoint-startup-diagnostic-01/emulator.log').read_text()
        self.assertIn('restored=1 samples=32 frames=0', log)
        self.assertEqual(fixed['status'], 0)
        for field in ('rom_sha256', 'source_state_sha256', 'keys', 'probe_sha256'):
            self.assertEqual(old[field], fixed[field])
        self.assertFalse(fixed['observer_memory_writes'])
        self.assertEqual(fixed['native_capture']['metadata']['frames'], 240)
        self.assertEqual(fixed['native_capture']['restored_replay_epoch']['status'], 'PASS')

    def test_full_primary_outputs_unchanged_on_existing_control(self):
        old = self.receipt('checked-secret-health-replay-01')
        new = self.receipt('secret-startup-fixed-neutrality-01')
        for field in ('rom_sha256', 'source_state_sha256', 'keys', 'probe_sha256'):
            self.assertEqual(old[field], new[field])
        self.assertEqual(new['status'], 0)
        for suffix in ('s16le', 'video', 'states', 'timeline.tsv'):
            paths = [Path(r['native_capture_directory']) / ('native.' + suffix)
                     for r in (old, new)]
            self.assertEqual(hashlib.sha256(paths[0].read_bytes()).digest(),
                             hashlib.sha256(paths[1].read_bytes()).digest())

    def test_endpoint_is_invariant_under_startup_delay(self):
        plain = self.receipt('secret-endpoint-startup-fixed-01')
        delayed = self.receipt('secret-endpoint-startup-fixed-delay-01')
        self.assertEqual(delayed['status'], 0)
        self.assertEqual(plain['source_state_sha256'], delayed['source_state_sha256'])
        self.assertEqual(delayed['diagnostic_environment']['ENTRY_NATIVE_START_DELAY_US'], '10000')
        for suffix in ('s16le', 'video', 'states', 'timeline.tsv'):
            paths = [Path(r['native_capture_directory']) / ('native.' + suffix)
                     for r in (plain, delayed)]
            self.assertEqual(hashlib.sha256(paths[0].read_bytes()).digest(),
                             hashlib.sha256(paths[1].read_bytes()).digest())


if __name__ == '__main__':
    unittest.main()
