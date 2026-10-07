"""#59: every supported footer keeps its own rearm-only negative control."""
import hashlib
from pathlib import Path
import unittest
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts/diagnostics'))

import verify_playtest_boss_handoff as gate

ROOT = Path(__file__).resolve().parents[1]
VARIANTS = (
    ('later-lowhealth-camera-source-01',
     'a73288eb3ae486f8c431cde5ba69ba59d6932ccb3d579848926ef8bba01888fd'),
    ('later-lowhealth-title-source-01',
     'acc3d07674300458053942b2afc0c8ac9e6000b2c4c77b8a758619b68739ab60'),
    ('later-lowhealth-title-retry-source-01',
     '15264f4c19e649bf9c0c85e863e13d9b8f1586f4d5af574524046c1efff488fc'),
)


class ExactControls(unittest.TestCase):
    def setUp(self):
        if any(not (ROOT / 'tmp' / directory / 'candidate.gb').is_file()
               for directory, _ in VARIANTS):
            self.skipTest('optional source-built historical variants absent')

    def test_all_three_source_authenticated_reversals(self):
        allowed = set(range(gate.layout.HOOK,
                            gate.layout.HOOK + len(gate.layout.OLD))) | {334, 335}
        for directory, expected in VARIANTS:
            with self.subTest(candidate=directory):
                rom = (ROOT / 'tmp' / directory / 'candidate.gb').read_bytes()
                control = gate.broken_control(rom)
                self.assertEqual(hashlib.sha256(control).hexdigest(), expected)
                changed = {i for i, (a, b) in enumerate(zip(rom, control)) if a != b}
                self.assertEqual(len(changed), 11)
                self.assertLessEqual(changed, allowed)
                self.assertEqual(rom[0x36dd0:0x36e00], control[0x36dd0:0x36e00])

    def test_unrelated_mutation_cannot_inherit_control_pin(self):
        for directory, _ in VARIANTS:
            rom = bytearray((ROOT / 'tmp' / directory / 'candidate.gb').read_bytes())
            rom[0x500] ^= 1
            with self.subTest(candidate=directory), self.assertRaises(ValueError):
                gate.broken_control(rom)


if __name__ == '__main__':
    unittest.main()
