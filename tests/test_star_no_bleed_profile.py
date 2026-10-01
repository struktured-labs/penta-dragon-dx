"""#22/#37: explicit experimental palette policy, never learned from a bad LUT."""
from pathlib import Path
import hashlib
import json
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts/diagnostics'))
from verify_stage1_no_bleed import expected_stage1_table, EXPECTED_TABLE


class StarNoBleedProfile(unittest.TestCase):
    def test_fresh_full_route_pass_and_prior_fail_remain_distinct(self):
        directory = ROOT / 'tmp/late-return-stage1-no-bleed-profile-01'
        if not (directory / 'receipt.json').exists():
            self.skipTest('fresh no-bleed evidence unavailable')
        receipt = json.loads((directory / 'receipt.json').read_text())
        self.assertEqual(receipt['rom_sha256'],
                         '46eb95a0c0f770fb3cf8c3211b8030a9e881f59077e558b93703ba08da71d3fb')
        self.assertEqual(receipt['status'], 'pass')
        self.assertEqual(receipt['failures'], [])
        self.assertTrue(all(receipt['checks'].values()))
        self.assertEqual(receipt['route']['play_frames_requested'], 7200)
        for key, filename in [('probe_sha256', 'probe_stage1_no_bleed.lua'),
                              ('verifier_sha256', 'verify_stage1_no_bleed.py')]:
            self.assertEqual(receipt[key], hashlib.sha256(
                (ROOT / 'scripts/diagnostics' / filename).read_bytes()).hexdigest())
        old = ROOT / 'tmp/late-return-stage1-no-bleed-physical-01'
        self.assertEqual(json.loads((old / 'receipt.json').read_text())['status'], 'fail')
        images = sorted(directory.glob('raster-*.png')) + sorted(directory.glob('play-*.png'))
        self.assertEqual(len(images), 7120)
        for image in images:
            self.assertEqual(image.read_bytes(), (old / image.name).read_bytes(), image.name)

    def test_late_return_inherits_only_authored_tooth_and_star_entries(self):
        path = ROOT / 'tmp/stream-late-return-source-01/candidate.gb'
        if not path.exists():
            self.skipTest('late-return candidate unavailable')
        rom = path.read_bytes()
        expected = bytearray(EXPECTED_TABLE)
        for tile in (*range(0x64, 0x6A), *range(0x74, 0x7A)):
            self.assertEqual(expected[tile], 7)
            expected[tile] |= 8
        for tile in (0x82, 0x83, 0x92, 0x93):
            self.assertEqual(expected[tile], 0)
            expected[tile] = 5
        self.assertEqual(rom[0x37000:0x37100], bytes(expected))
        self.assertEqual(expected_stage1_table(rom), bytes(expected))
        for tile in range(256):
            mutated = bytearray(rom)
            mutated[0x37000 + tile] ^= 1
            with self.subTest(tile=tile):
                self.assertNotEqual(mutated[0x37000:0x37100], expected_stage1_table(mutated))
        # Correct LUT bytes alone cannot authorize an unknown ROM/profile.
        mutated = bytearray(rom)
        mutated[0x100] ^= 1
        self.assertNotEqual(mutated[0x37000:0x37100], expected_stage1_table(mutated))

    def test_exact_combined_profile_and_corruption_rejection(self):
        path = ROOT / 'tmp/stream-presentation-source-01/candidate.gb'
        if not path.exists():
            self.skipTest('combined candidate unavailable')
        rom = path.read_bytes()
        expected = bytearray(EXPECTED_TABLE)
        for tile in (*range(0x64, 0x6A), *range(0x74, 0x7A)):
            expected[tile] = 15
        for tile in (0x82, 0x83, 0x92, 0x93):
            expected[tile] = 5
        self.assertEqual(expected_stage1_table(rom), bytes(expected))
        self.assertEqual(rom[0x37000:0x37100], bytes(expected))
        # Every single-cell wrong assignment must remain a failure, including
        # star cells, hazard bank bits, and ordinary floor cells.
        for tile in range(256):
            mutated = bytearray(rom)
            mutated[0x37000 + tile] ^= 1
            with self.subTest(tile=tile):
                self.assertNotEqual(mutated[0x37000:0x37100],
                                    expected_stage1_table(mutated))


if __name__ == '__main__':
    unittest.main()
