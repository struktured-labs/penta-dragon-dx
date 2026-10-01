"""#45 direct RST fixes publication ordering, not the remaining audio delay."""
import csv
import hashlib
import json
import mmap
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]


class DirectSoundEvidence(unittest.TestCase):
    def setUp(self):
        self.folder = ROOT/'tmp/return-direct-sound-exit-01'
        if not (self.folder/'receipt.json').exists(): self.skipTest('local replay unavailable')
        self.receipt = json.loads((self.folder/'receipt.json').read_text())
        self.assertEqual(self.receipt['rom_sha256'],
                         '73ee08d7b5ad4f2af16a0e5c297856150908af76a0d2543ec0865ffcafcfb770')

    def test_music_consumed_after_scene_publication(self):
        with (self.folder/'sound-commands.tsv').open() as f:
            rows = [r for r in csv.DictReader(f,delimiter='\t')
                    if r['command']=='13' and int(r['frame'])>4000]
        self.assertEqual([r['event'] for r in rows], ['request','read','accept'])
        self.assertEqual([r['scene'] for r in rows], ['18','02','02'])
        self.assertEqual(int(rows[0]['cycle']),1161391592)
        self.assertEqual(int(rows[2]['cycle']),1161408856)
        # The previous far-call experiment consumes while the card is active.
        with (ROOT/'tmp/return-handoff-trial-01/sound-commands.tsv').open() as f:
            broken = [r for r in csv.DictReader(f,delimiter='\t')
                      if r['command']=='13' and r['event']=='accept']
        self.assertEqual(broken[0]['scene'],'18')

    def test_map_stays_hidden_until_complete(self):
        r = self.receipt
        self.assertEqual(r['native_capture']['restored_replay_epoch']['status'],'PASS')
        native = Path(r['native_capture_directory'])
        for name in ('native.video','native.states'):
            with (native/name).open('rb') as f:
                self.assertEqual(hashlib.file_digest(f,'sha256').hexdigest(),
                                 r['native_capture']['hashes'][name])
        with (native/'native.states').open('rb') as sf, mmap.mmap(sf.fileno(),0,access=mmap.ACCESS_READ) as s, (native/'native.video').open('rb') as vf, mmap.mmap(vf.fileno(),0,access=mmap.ACCESS_READ) as v:
            bad, visible = [], []
            for frame in range(4667,4767):
                i = frame-1; state = s[i*71680:(i+1)*71680]
                page = 0x2000 if state[0x340]&8 else 0x1C00
                mismatch = any(state[page+y*32+x]!=state[0x45A0+y*24+x]
                               for y in range(24) for x in range(24))
                white = v[i*92160:(i+1)*92160]==bytes((255,255,255,0))*23040
                if mismatch:
                    bad.append(frame)
                    self.assertTrue(white)
                if not white: visible.append(frame)
            self.assertEqual(bad,list(range(4667,4672)))
            self.assertEqual(visible[0],4687)

    def test_full_audio_still_rejected(self):
        r = json.loads((ROOT/'tmp/return-direct-sound-audio-pair-01/receipt.json').read_text())
        for path, digest in r['identities'].items():
            with Path(path).open('rb') as f:
                self.assertEqual(hashlib.file_digest(f,'sha256').hexdigest(),digest)
        self.assertEqual(r['status'],'fail')
        self.assertFalse(r['checks']['same_digital_silence_intervals'])
        self.assertEqual(r['first_different_sample'],9803918)
        self.assertEqual(r['different_sample_frames'],3031865)


if __name__ == '__main__': unittest.main()
