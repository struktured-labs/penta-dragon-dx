import sys
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts/diagnostics'))
from check_secret_pickup_attributes import inspect, serialized_state


class SecretPickupAttributesTests(unittest.TestCase):
    def load(self, folder):
        p = ROOT / 'tmp' / folder
        if not (p / 'frame-2460.ss0').exists():
            self.skipTest('local ROM-bound emulator evidence unavailable')
        return serialized_state(p / 'frame-2460.ss0'), (p / 'candidate.gb').read_bytes()

    def test_trial_snapshot(self):
        result = inspect(*self.load('secret-combined-menu-return-01'))
        self.assertEqual(result['status'], 'PASS_SIGNATURE_PALETTES')
        self.assertEqual(len(result['matches']), 10)

    def test_known_broken_parent_negative_control(self):
        result = inspect(*self.load('secret-parent-menu-return-01'))
        self.assertEqual(result['status'], 'FAIL')
        self.assertEqual(sum(not m['passed'] for m in result['matches']), 9)

    def test_state_identity_mutation_rejected(self):
        raw, rom = self.load('secret-combined-menu-return-01')
        changed = bytearray(raw)
        changed[4] ^= 1
        with self.assertRaisesRegex(ValueError, 'identity'):
            inspect(changed, rom)

    def test_wrong_scene_rejected(self):
        raw, rom = self.load('secret-combined-menu-return-01')
        changed = bytearray(raw)
        changed[0x5c80] = 2
        with self.assertRaisesRegex(ValueError, 'scene09'):
            inspect(changed, rom)
