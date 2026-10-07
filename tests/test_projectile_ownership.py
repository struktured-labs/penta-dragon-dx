import copy
import importlib.util
from pathlib import Path
import unittest

spec = importlib.util.spec_from_file_location('ownership', Path(__file__).resolve().parents[1] / 'scripts/diagnostics/check_projectile_ownership.py')
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


class OwnershipEvidenceTest(unittest.TestCase):
    def pair(self, power=1):
        old = bytearray(160)
        old[:12] = bytes([70, 60, 15, 0, 80, 90, power + 1, 0, 60, 120, 48, 3])
        new = old.copy()
        new[3] = 3
        return tuple([dict(frame=str(f), power_requested=str(power), form='0', scene='02', oam=o.hex())
                      for f in range(1, 241)] for o in (old, new))

    def mutate(self, rows, index, value):
        raw = bytearray.fromhex(rows[119]['oam'])
        raw[index] = value
        rows[119]['oam'] = raw.hex()

    def test_three_weapons(self):
        for power in range(3):
            self.assertEqual(m.assess(*self.pair(power), power)['simultaneous_frames'], 240)

    def test_broken_parent_rejected(self):
        old, _ = self.pair()
        with self.assertRaisesRegex(ValueError, 'enemy still'):
            m.assess(old, copy.deepcopy(old), 1)

    def test_weapon_recolor_rejected(self):
        old, new = self.pair()
        self.mutate(new, 7, 3)
        with self.assertRaisesRegex(ValueError, 'unrelated sprite recolored'):
            m.assess(old, new, 1)

    def test_geometry_rejected(self):
        old, new = self.pair()
        self.mutate(new, 1, 61)
        with self.assertRaisesRegex(ValueError, 'timeline changed'):
            m.assess(old, new, 1)

    def test_priority_rejected(self):
        old, new = self.pair()
        self.mutate(new, 3, 131)
        with self.assertRaisesRegex(ValueError, 'non-palette'):
            m.assess(old, new, 1)

    def test_unrelated_enemy_recolor_rejected(self):
        old, new = self.pair()
        self.mutate(new, 11, 4)
        with self.assertRaisesRegex(ValueError, 'unrelated'):
            m.assess(old, new, 1)

    def test_incomplete_rejected(self):
        old, new = self.pair()
        with self.assertRaisesRegex(ValueError, 'incomplete'):
            m.assess(old, new[:-1], 1)

    def test_missing_frame_rejected(self):
        old, new = self.pair()
        new[119]['frame'] = '119'
        with self.assertRaisesRegex(ValueError, 'sequence'):
            m.assess(old, new, 1)

    def test_invisible_samples_rejected(self):
        old, new = self.pair()
        for rows in (old, new):
            for row in rows:
                raw = bytearray.fromhex(row['oam'])
                raw[1] = 0
                row['oam'] = raw.hex()
        with self.assertRaisesRegex(ValueError, 'coverage'):
            m.assess(old, new, 1)


if __name__ == '__main__':
    unittest.main()
