"""#45 experimental fastpath: retain visual success AND audio rejection."""
import hashlib
import json
import mmap
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]


class FastpathReturn(unittest.TestCase):
    def test_initial_map_hidden_until_complete(self):
        folder = ROOT/'tmp/initial-map-fastpath-exit-01'
        if not (folder/'receipt.json').exists(): self.skipTest('local native run unavailable')
        receipt = json.loads((folder/'receipt.json').read_text())
        self.assertEqual(receipt['rom_sha256'], 'ec8be28897810fac01a8918a0403900780015bf6703531f0f82ae259f209f21b')
        self.assertEqual(receipt['native_capture']['restored_replay_epoch']['status'], 'PASS')
        native = Path(receipt['native_capture_directory'])
        for name in ('native.states', 'native.video'):
            with (native/name).open('rb') as f:
                self.assertEqual(hashlib.file_digest(f, 'sha256').hexdigest(), receipt['native_capture']['hashes'][name])
        with (native/'native.states').open('rb') as sf, mmap.mmap(sf.fileno(), 0, access=mmap.ACCESS_READ) as states, (native/'native.video').open('rb') as vf, mmap.mmap(vf.fileno(), 0, access=mmap.ACCESS_READ) as video:
            self.assertEqual(len(states), 6000*71680)
            start = next(i for i in range(6000) if states[i*71680+0x5c80]==2 and states[i*71680+0x3ba]==0)
            self.assertEqual(start+1, 4679)
            bad, visible = [], []
            for i in range(start, start+65):
                s = states[i*71680:(i+1)*71680]
                page = 0x2000 if s[0x340]&8 else 0x1c00
                mismatch = any(s[page+y*32+x]!=s[0x45a0+y*24+x] for y in range(24) for x in range(24))
                white = video[i*92160:(i+1)*92160] == bytes((255,255,255,0))*23040
                if mismatch:
                    bad.append(i+1)
                    self.assertTrue(white, f'incomplete map exposed at {i+1}')
                if not white: visible.append(i+1)
            self.assertEqual(bad, list(range(4679,4684)))
            self.assertTrue(visible, 'all-white terminal output must not qualify')

    def test_audio_failure_is_not_relabelled_as_acceptance(self):
        p = ROOT/'tmp/initial-map-fastpath-audio-pair-01/receipt.json'
        if not p.exists(): self.skipTest('local audio comparison unavailable')
        r = json.loads(p.read_text())
        for name, sha in r['identities'].items():
            with Path(name).open('rb') as f:
                self.assertEqual(hashlib.file_digest(f, 'sha256').hexdigest(), sha)
        self.assertEqual(r['status'], 'fail')
        self.assertEqual(r['first_different_sample'], 0)
        self.assertFalse(r['checks']['same_digital_silence_intervals'])
        self.assertFalse(r['checks']['no_larger_sample_discontinuity'])


if __name__ == '__main__': unittest.main()
