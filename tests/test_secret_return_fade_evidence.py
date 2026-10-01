"""#45 preserve original fade behavior and known-broken CGB counterexample."""
import hashlib
import json
import mmap
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]


class ReturnFadeEvidence(unittest.TestCase):
    def test_original_blank_setup_and_candidate_exposure(self):
        cases = (
            ('stock-secret-return-visual-01',
             '2f32570cff62b8664bfa06b939988c3fd6a7efabf870a990a5fa65bab37eac30',
             range(4820, 4840), True),
            ('secret-exit-after-menu-fight-01',
             '2b797a6af30598141d874a8a272e9a7c77012044fe82f649f1b3e9142d31f306',
             range(963, 968), False),
        )
        for name, pin, frames, blank in cases:
            base = ROOT / 'tmp' / name
            if not (base / 'receipt.json').exists():
                self.skipTest('local return capture unavailable')
            receipt = json.loads((base / 'receipt.json').read_text())
            self.assertEqual(receipt['status'], 0)
            self.assertEqual(hashlib.sha256((base / 'candidate.gb').read_bytes()).hexdigest(), pin)
            if blank:
                self.assertTrue(receipt['observer_memory_writes'])  # explicit health-assisted control
            native = Path(receipt['native_capture_directory'])
            with (native / 'native.video').open('rb') as vf, (native / 'native.states').open('rb') as sf:
                with mmap.mmap(vf.fileno(),0,access=mmap.ACCESS_READ) as v, mmap.mmap(sf.fileno(),0,access=mmap.ACCESS_READ) as s:
                    for frame in frames:
                        raw = v[(frame-1)*92160:frame*92160]
                        state = s[(frame-1)*71680:frame*71680]
                        self.assertEqual(state[0x5c80], 2)
                        colors = {raw[i:i+3] for i in range(0,len(raw),4)}
                        self.assertEqual(len(colors) == 1, blank)
                        if blank:
                            self.assertEqual(state[0x347], 0)


if __name__ == '__main__':
    unittest.main()
