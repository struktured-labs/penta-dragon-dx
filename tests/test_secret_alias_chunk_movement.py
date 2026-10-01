"""#26 full frame-boundary map evidence; not raster/audio acceptance."""
import hashlib
import csv
import mmap
from pathlib import Path
import sys
import unittest
import zlib

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts/diagnostics'))
from verify_pickup_class_palettes import PICKUPS


class ChunkMovementEvidence(unittest.TestCase):
    def test_pause_return_attempt_is_death_restart_not_successful_return(self):
        names = ('secret-alias-chunk-lowhealth-return-01', 'secret-fast-lowhealth-return-control-01')
        timelines = []
        for name in names:
            base = ROOT / 'tmp' / name
            if not (base / 'trace.tsv').exists(): self.skipTest('local return evidence unavailable')
            with (base / 'trace.tsv').open() as stream:
                timelines.append(list(csv.DictReader(stream, delimiter='\t')))
            with (base / 'item-action.tsv').open() as stream:
                activation = next(r for r in csv.DictReader(stream, delimiter='\t') if int(r['pause_timer']) > 0)
            self.assertEqual((activation['frame'], activation['pause_timer']), ('161', '60'))
        candidate, parent = timelines
        self.assertEqual(len(candidate), 6000)
        self.assertEqual(len(parent), 1800)
        first_death = next(r for r in candidate if r['scene'] == '17')
        self.assertEqual((first_death['frame'], first_death['stage']), ('1041', '07'))
        self.assertTrue(all(r['stage'] == '07' for r in candidate[:1041]))
        self.assertFalse(any(r['scene'] == '17' for r in parent))
        # A later clean stage00 endpoint must not be mistaken for a secret exit.
        first_dungeon = next(r for r in candidate if r['scene'] == '02' and r['stage'] == '00')
        self.assertEqual(first_dungeon['frame'], '1660')

    def test_every_frame_map_policy_with_broken_control(self):
        cases = (
            ('secret-sound-alias-parent-audio-01', 'd901357a105036469b8debbff138fb63e87afb3a0cfbe5a24eeaafa91353910a', 474, 470),
            ('secret-sound-alias-fast-audio-01', '665a33b6b26d0a8ec1622a7c897d4fc10bdf7c8c5e0e5a2edaae98df0dafe0e7', 4, 0),
            ('secret-alias-chunk-movement-01', '2b797a6af30598141d874a8a272e9a7c77012044fe82f649f1b3e9142d31f306', 3, 0),
        )
        policy = [0] * 256
        for item in PICKUPS:
            for tile in item.tiles: policy[tile] = item.palette
        for name, pin, expected_bad, expected_active in cases:
            path = Path('/mnt/data/tmp', 'penta-' + name + '-av', 'native.states')
            if not path.exists(): self.skipTest('local emulator corpus unavailable')
            rom = (ROOT / 'tmp' / name / 'candidate.gb').read_bytes()
            self.assertEqual(hashlib.sha256(rom).hexdigest(), pin)
            self.assertEqual(path.stat().st_size, 480 * 71680)
            bad, active_bad = [], []
            with path.open('rb') as stream, mmap.mmap(stream.fileno(), 0, access=mmap.ACCESS_READ) as data:
                for i in range(480):
                    s = data[i * 71680:(i + 1) * 71680]
                    self.assertEqual(int.from_bytes(s[4:8], 'little'), zlib.crc32(rom) & 0xffffffff)
                    self.assertEqual(s[0x3ba], 7)
                    self.assertTrue(s[0x5c80] in (9, 10) or s[0x5c80] == 11 and s[0x3b7] in (9, 10))
                    active = 0x1c00 if s[0x340] & 8 else 0x1800
                    counts = {base: sum((s[0x2400 + base + j] & 7) != policy[s[0x400 + base + j]]
                                       for j in range(768)) for base in (0x1800, 0x1c00)}
                    if sum(counts.values()): bad.append((i + 1, sum(counts.values())))
                    if counts[active]: active_bad.append((i + 1, counts[active]))
            self.assertEqual((len(bad), len(active_bad)), (expected_bad, expected_active))
            if name == 'secret-alias-chunk-movement-01':
                self.assertEqual(bad, [(1, 32), (5, 28), (13, 14)])


if __name__ == '__main__': unittest.main()
