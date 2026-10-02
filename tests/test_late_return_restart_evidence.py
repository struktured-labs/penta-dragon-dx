"""#18/#45 bounded restart checks on the source-rebuilt46eb trial."""
import hashlib
import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts/diagnostics'))
from verify_gameover_restart import validate, validate_stage_cards
from gameover_sequence import validate_sequence


class LateReturnRestart(unittest.TestCase):
    def test_saved_selector_and_two_restart_cycles(self):
        for name, hazard in (('late-return-gameover-restart-01', False),
                             ('late-return-hazard-restart-01', True)):
            with self.subTest(route=name):
                folder = ROOT/'tmp'/name
                receipt = json.loads((folder/'receipt.json').read_text())
                self.assertEqual(receipt['rom_sha256'],
                                 '46eb95a0c0f770fb3cf8c3211b8030a9e881f59077e558b93703ba08da71d3fb')
                self.assertEqual(hashlib.sha256((folder/'runtime/candidate.gb').read_bytes()).hexdigest(),
                                 receipt['rom_sha256'])
                self.assertEqual(receipt['status'], 'pass')
                self.assertEqual(receipt['hazard_death'], hazard)
                self.assertTrue(receipt['saved_game_fixture'])
                self.assertEqual(hashlib.sha256((ROOT/'tmp/restart-source-before-physical-save-01/probe_gameover_restart.lua').read_bytes()).hexdigest(),
                                 receipt['probe_sha256'])
                for filename, digest in receipt['artifacts'].items():
                    self.assertEqual(hashlib.sha256((folder/filename).read_bytes()).hexdigest(),digest)
                validate(folder)
                validate_stage_cards(folder, True)
                self.assertEqual(validate_sequence(folder),
                                 dict(title_frame_pairs=482, gameover_frames=102))


if __name__ == '__main__':
    unittest.main()
