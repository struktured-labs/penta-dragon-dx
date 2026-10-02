"""#45 bounded data-reader evidence, explicitly not an allocation proof."""
import csv
import hashlib
import json
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
PIN = 'ec8be28897810fac01a8918a0403900780015bf6703531f0f82ae259f209f21b'


class FadeReferenceReaders(unittest.TestCase):
    def test_reader_and_full_observer_neutrality(self):
        receipts = []
        for variant in ('on', 'off'):
            directory = ROOT / 'tmp' / f'fade-reference-readers-{variant}-01'
            if not (directory / 'receipt.json').exists():
                self.skipTest('local reference-reader evidence unavailable')
            r = json.loads((directory / 'receipt.json').read_text())
            rom = (directory / 'candidate.gb').read_bytes()
            self.assertEqual(hashlib.sha256(rom).hexdigest(), PIN)
            self.assertEqual(r['rom_sha256'], PIN)
            self.assertEqual(r['status'], 0)
            self.assertFalse(r['observer_memory_writes'])
            self.assertEqual(r['probe_sha256'], hashlib.sha256((directory / 'probe.lua').read_bytes()).hexdigest())
            state = ROOT / 'tmp/fade-reference-readers-cold-01/frame-0600.ss0'
            self.assertEqual(r['source_state_sha256'], hashlib.sha256(state.read_bytes()).hexdigest())
            self.assertEqual(r['native_capture']['restored_replay_epoch']['status'], 'PASS')
            self.assertEqual(r['native_capture']['metadata']['frames'], 120)
            for name, expected in r['native_capture']['hashes'].items():
                with (Path(r['native_capture_directory']) / name).open('rb') as stream:
                    self.assertEqual(hashlib.file_digest(stream, 'sha256').hexdigest(), expected)
            receipts.append(r)
        self.assertEqual(receipts[0]['native_capture']['hashes'], receipts[1]['native_capture']['hashes'])
        self.assertEqual(receipts[0]['native_tap_sha256'], receipts[1]['native_tap_sha256'])
        self.assertEqual(receipts[0]['probe_sha256'], receipts[1]['probe_sha256'])
        with (ROOT / 'tmp/fade-reference-readers-on-01/fade-reference-readers.tsv').open() as stream:
            rows = list(csv.DictReader(stream, delimiter='\t'))
        self.assertEqual([int(row['frame']) for row in rows], [37,51,65,78,91,104,117])
        for row in rows:
            self.assertEqual((row['kind'], row['file_offset'], row['pc'], row['bank_shadow'], row['hl']),
                             ('read', '034364', '0E0F', '0D', '4365'))
        # Reader instruction is LD A,(HL+), not execution of C4 D3 00.
        self.assertEqual(rom[0xE0E:0xE10], bytes.fromhex('2AF5'))
        self.assertEqual(rom[0x34364:0x34367], bytes.fromhex('C4D300'))
        placement = json.loads((ROOT / 'tmp/fixed-fade-route-trial-01/receipt.json').read_text())
        self.assertFalse(placement['allocation_review_complete'])
        self.assertFalse(placement['release_qualified'])


if __name__ == '__main__':
    unittest.main()
