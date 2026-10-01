"""#23 local emulator corpus: early-menu BG0 symptom, not release acceptance."""
import hashlib
import json
import mmap
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
EXPECTED = bytes.fromhex('ff7f947e4a3d0000')
CASES = (
    ('reported-secret-early-menu-held-01',
     '4f5a67b8a9afb178ac0760daa2357de74fd7eb7f3de4de010385c50ea4cb08f5',
     '6b2732eda732a6b60b0c6231f4f05fea139821a29156bbc4e6f53f3ffca24421'),
    ('secret-fixed-early-menu-held-01',
     '665a33b6b26d0a8ec1622a7c897d4fc10bdf7c8c5e0e5a2edaae98df0dafe0e7',
     '3b4eb9abadea1281d7c8506a6af09635296f018c64e83993e58b14fa663ccb19'),
)


class EarlyMenuPaletteEvidence(unittest.TestCase):
    def test_known_broken_fails_palette_invariant_candidate_passes(self):
        if not all((ROOT / 'tmp' / c[0] / 'receipt.json').exists() for c in CASES):
            self.skipTest('local emulator corpus unavailable; not a passing replay')
        results = []
        for name, rom_hash, state_hash in CASES:
            out = ROOT / 'tmp' / name
            receipt = json.loads((out / 'receipt.json').read_text())
            self.assertEqual(receipt['status'], 0)
            self.assertFalse(receipt['observer_memory_writes'])
            self.assertEqual(receipt['rom_sha256'], rom_hash)
            self.assertEqual(hashlib.sha256((out / 'candidate.gb').read_bytes()).hexdigest(), rom_hash)
            self.assertEqual(hashlib.sha256((out / 'identity.ss0').read_bytes()).hexdigest(), state_hash)
            self.assertEqual(receipt['source_state_sha256'], state_hash)
            env = receipt['diagnostic_environment']
            self.assertEqual((env['ENTRY_KEYS'], env['ENTRY_KEY_FRAMES']), ('4', '120'))
            capture = receipt['native_capture']
            self.assertEqual(capture['restored_replay_epoch']['status'], 'PASS')
            states = Path(receipt['native_capture_directory']) / 'native.states'
            self.assertEqual(states.stat().st_size, 240 * 71680)
            with states.open('rb') as stream, mmap.mmap(stream.fileno(), 0, access=mmap.ACCESS_READ) as data:
                self.assertEqual(hashlib.sha256(data).hexdigest(), capture['hashes']['native.states'])
                bad, menu = [], []
                for i in range(240):
                    offset = i * 71680
                    if data[offset + 0xd4:offset + 0xdc] != EXPECTED:
                        bad.append(i + 1)
                    if data[offset + 0x340] & 32:
                        menu.append(i + 1)
                results.append((bad, menu))
        self.assertEqual(results[0], (list(range(32, 241)), list(range(37, 241))))
        self.assertEqual(results[1], ([], list(range(33, 241))))


if __name__ == '__main__':
    unittest.main()
