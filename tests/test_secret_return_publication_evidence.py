"""#45: retain the observed early map publication, not a fixed-build gate."""
import csv
import hashlib
import json
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
ROM = '2b797a6af30598141d874a8a272e9a7c77012044fe82f649f1b3e9142d31f306'
STATE = '80af2876f2e7284a975395fb90e8e4574c66461c73d7dbe3633d468544739afa'


class ReturnPublicationEvidence(unittest.TestCase):
    def test_tile_graphics_stay_identical_while_both_maps_are_replaced(self):
        path = Path('/mnt/data/tmp/penta-secret-return-publication-01-av/native.states')
        if not path.exists():
            self.skipTest('local publication capture unavailable')
        data = path.read_bytes()
        self.assertEqual(hashlib.sha256(data).hexdigest(),
                         '457fe28f0d6f0beb141fc72f10ca9e7ca877b6d7dc2e5dca7966700cf52d7685')
        states = {f: data[(f-1)*71680:f*71680] for f in (8,24,40,80)}
        for start in (0x400, 0x2400):
            self.assertEqual(states[8][start:start+0x1800], states[80][start:start+0x1800])
        for start in (0x1c00, 0x2000):
            self.assertNotEqual(states[8][start:start+0x400], states[80][start:start+0x400])
        # BGP progresses through the original fade, but native CGB colors do not.
        self.assertEqual([states[f][0x347] for f in (8,24,40)], [0,0x40,0xe4])
        for f in (24,40):
            self.assertEqual(states[8][0xd4:0x114], states[f][0xd4:0x114])

    def test_publication_precedes_native_fade_completion_without_observer_drift(self):
        captures = []
        for name in ('secret-return-publication-01', 'secret-return-boundary-01'):
            base = ROOT / 'tmp' / name
            if not (base / 'receipt.json').exists():
                self.skipTest('local publication capture unavailable')
            receipt = json.loads((base / 'receipt.json').read_text())
            self.assertEqual(receipt['status'], 0)
            self.assertEqual(receipt['rom_sha256'], ROM)
            self.assertEqual(hashlib.sha256((base / 'candidate.gb').read_bytes()).hexdigest(), ROM)
            self.assertEqual(receipt['source_state_sha256'], STATE)
            self.assertFalse(receipt['observer_memory_writes'])
            self.assertEqual(receipt['native_capture']['metadata']['frames'], 120)
            self.assertEqual(receipt['native_capture']['restored_replay_epoch']['status'], 'PASS')
            captures.append((receipt, Path(receipt['native_capture_directory'])))
        for ext in ('s16le', 'video', 'states', 'timeline.tsv'):
            hashes = []
            for receipt, directory in captures:
                name = f'native.{ext}'
                digest = hashlib.sha256((directory / name).read_bytes()).hexdigest()
                self.assertEqual(digest, receipt['native_capture']['hashes'][name])
                hashes.append(digest)
            self.assertEqual(*hashes)
        with (ROOT / 'tmp/secret-return-publication-01/return-publication.tsv').open() as stream:
            rows = list(csv.DictReader(stream, delimiter='\t'))
        maps = [r for r in rows if r['address'] == 'FF40']
        first = maps[0]
        self.assertEqual(tuple(first[k] for k in ('frame', 'old', 'new', 'pc', 'bank', 'active')),
                         ('7', '83', '8B', '7459', '0D', '00'))
        fade = [r for r in rows if r['address'] == 'FF47' and r['pc'] == '0F92']
        self.assertEqual([(int(r['frame']), r['new']) for r in fade],
                         [(15, '00'), (23, '40'), (31, '90'), (39, 'E4')])
        # The PC is post-instruction: the actual map write is bank0D:7457.
        rom = (ROOT / 'tmp/secret-return-publication-01/candidate.gb').read_bytes()
        offset = 13 * 0x4000 + 0x3457
        self.assertEqual(rom[offset:offset+2], bytes.fromhex('E0 40'))
        self.assertLess(int(first['frame']), int(fade[-1]['frame']))


if __name__ == '__main__':
    unittest.main()
