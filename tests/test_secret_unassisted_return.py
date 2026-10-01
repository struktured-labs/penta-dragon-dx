"""#26 exact-ROM continuations: real return, not death followed by new game.

The source checkpoint retains its declared assisted setup history. These two
continuations themselves use controller inputs only; this is not a claim of an
unassisted cold playthrough or complete raster/audio qualification.
"""
import csv
import hashlib
import json
import mmap
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
ROM = '2b797a6af30598141d874a8a272e9a7c77012044fe82f649f1b3e9142d31f306'


class SecretReturn(unittest.TestCase):
    def test_menu_close_fight_and_actual_stage1_return(self):
        for name, length in (('secret-exit-close-menu-01', 1800),
                             ('secret-exit-after-menu-fight-01', 2400)):
            base = ROOT / 'tmp' / name
            if not (base / 'receipt.json').exists():
                self.skipTest('local return capture unavailable')
            receipt = json.loads((base / 'receipt.json').read_text())
            self.assertEqual(receipt['status'], 0)
            self.assertFalse(receipt['observer_memory_writes'])
            self.assertEqual(receipt['rom_sha256'], ROM)
            self.assertEqual(hashlib.sha256((base / 'candidate.gb').read_bytes()).hexdigest(), ROM)
            with (base / 'trace.tsv').open() as stream:
                rows = list(csv.DictReader(stream, delimiter='\t'))
            self.assertEqual(len(rows), length)
            self.assertFalse(any(r['scene'] == '17' for r in rows))
            native = Path(receipt['native_capture_directory']) / 'native.states'
            with native.open('rb') as stream, mmap.mmap(stream.fileno(), 0, access=mmap.ACCESS_READ) as states:
                self.assertEqual(len(states), length * 71680)
                if length == 1800:
                    self.assertEqual(states[0x3e4], 0)  # Select closes it by first captured frame
                    self.assertEqual(states[119 * 71680 + 0x3e4], 0)
                    self.assertEqual(states[119 * 71680 + 0x3bf], 15)
                    self.assertEqual(states[959 * 71680 + 0x3bf], 0)
                    continue
                returned = next(r for r in rows if r['stage'] == '00')
                self.assertEqual(returned['frame'], '756')
                dungeon = next(r for r in rows if (r['scene'], r['stage']) == ('02', '00'))
                self.assertEqual(dungeon['frame'], '963')
                for frame in range(962, length):
                    s = states[frame * 71680:(frame + 1) * 71680]
                    self.assertEqual(s[0x3b7], 2)  # canonical dungeon, including sound alias
                    # Retain the observed three-frame handoff gap, not a claim
                    # that dungeon policy is ready immediately at scene entry.
                    expected = ('b3757dbb934881df967b2c4d8a335745f73470327fd580b83ee0f61fbf2a1878'
                                if frame < 965 else
                                '90b7393e610c67b97cd32664fae294ec76d10fd9a25384e004320b76c4ad4cb4')
                    self.assertEqual(hashlib.sha256(s[0x4a00:0x4b00]).hexdigest(), expected)


if __name__ == '__main__':
    unittest.main()
