"""#45 retain bounded return visibility success and full audio rejection."""
import hashlib
import json
import mmap
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]


class ReturnOnlyEvidence(unittest.TestCase):
    def test_incomplete_map_is_hidden_and_finished_map_becomes_visible(self):
        folder = ROOT/'tmp/return-only-fade-exit-01'
        if not (folder/'receipt.json').exists(): self.skipTest('native replay unavailable')
        r = json.loads((folder/'receipt.json').read_text())
        self.assertEqual(r['rom_sha256'],
                         '9c7e4f94a5dcb898faac58c9f9af66a416fa92be6b6843b1468549d3f61788ea')
        self.assertEqual(r['native_capture']['restored_replay_epoch']['status'], 'PASS')
        native = Path(r['native_capture_directory'])
        for name in ('native.states', 'native.video'):
            with (native/name).open('rb') as f:
                self.assertEqual(hashlib.file_digest(f,'sha256').hexdigest(),
                                 r['native_capture']['hashes'][name])
        with (native/'native.states').open('rb') as sf, mmap.mmap(sf.fileno(),0,access=mmap.ACCESS_READ) as s, (native/'native.video').open('rb') as vf, mmap.mmap(vf.fileno(),0,access=mmap.ACCESS_READ) as v:
            self.assertEqual(len(s),6000*71680)
            self.assertEqual(len(v),6000*92160)
            start = next(i for i in range(6000) if s[i*71680+0x5C80]==2 and s[i*71680+0x3BA]==0)
            self.assertEqual(start+1,4667)
            incomplete, visible = [], []
            for i in range(start,start+100):
                state = s[i*71680:(i+1)*71680]
                page = 0x2000 if state[0x340]&8 else 0x1C00
                mismatch = any(state[page+y*32+x] != state[0x45A0+y*24+x]
                               for y in range(24) for x in range(24))
                white = v[i*92160:(i+1)*92160] == bytes((255,255,255,0))*23040
                if mismatch:
                    incomplete.append(i+1)
                    self.assertTrue(white, f'exposed incomplete map at {i+1}')
                if not white: visible.append(i+1)
            self.assertEqual(incomplete, list(range(4667,4672)))
            self.assertTrue(visible)
            self.assertEqual(visible[0],4687)

    def test_full_audio_failure_and_actual_prefix_are_preserved(self):
        p = ROOT/'tmp/return-only-fade-audio-pair-01/receipt.json'
        if not p.exists(): self.skipTest('native audio comparison unavailable')
        r = json.loads(p.read_text())
        for path, digest in r['identities'].items():
            with Path(path).open('rb') as f:
                self.assertEqual(hashlib.file_digest(f,'sha256').hexdigest(),digest)
        self.assertEqual(r['status'],'fail')
        self.assertEqual(r['first_different_sample'],9803918)
        self.assertEqual(r['different_sample_frames'],3037073)
        self.assertFalse(r['checks']['same_digital_silence_intervals'])
        self.assertFalse(r['checks']['same_full_route_silent_blocks'])
        self.assertTrue(r['checks']['no_added_clipping'])
        self.assertTrue(r['checks']['no_larger_sample_discontinuity'])


if __name__ == '__main__': unittest.main()
