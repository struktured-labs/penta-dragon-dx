"""#45 preserve the failed upload-cost hypothesis, not a release gate."""
import hashlib
import json
import mmap
from pathlib import Path
import sys
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts/diagnostics'))
from build_fixed_fade_compact_trial import build


class FixedFadeCompactTrial(unittest.TestCase):
    def test_patch_scope_preserves_waits_and_card(self):
        parent=(ROOT/'tmp/fixed-fade-route-trial-01/candidate.gb').read_bytes()
        rom,sites=build(parent)
        self.assertEqual(hashlib.sha256(rom).hexdigest(),
            'f653ed03f2cc3274b4dc53eb286b6b5d00ff095d093edc8427fd14aa09daa280')
        allowed={0x14E,0x14F}
        for site in sites: allowed.update(range(site['offset'],site['offset']+site['size']))
        self.assertTrue(all(i in allowed for i,(a,b) in enumerate(zip(parent,rom)) if a!=b))
        self.assertEqual(rom[0x51C20:0x51CDC],parent[0x51C20:0x51CDC])

    def test_failed_late_resume_and_audio_are_retained(self):
        r=json.loads((ROOT/'tmp/fixed-fade-compact-exit-01/receipt.json').read_text())
        self.assertEqual(r['native_capture']['restored_replay_epoch']['status'],'PASS')
        for name,expected in r['native_capture']['hashes'].items():
            with (Path(r['native_capture_directory'])/name).open('rb') as f:
                self.assertEqual(hashlib.file_digest(f,'sha256').hexdigest(),expected)
        with (Path(r['native_capture_directory'])/'native.states').open('rb') as f, mmap.mmap(f.fileno(),0,access=mmap.ACCESS_READ) as states:
            frame=next(i+1 for i in range(4670,4800)
                if states[i*71680+0x3C1]==1 and states[i*71680+0x3E4]==0)
        self.assertEqual(frame,4723)
        a=json.loads((ROOT/'tmp/fixed-fade-compact-audio-pair-01/receipt.json').read_text())
        self.assertEqual(a['status'],'fail')
        self.assertEqual(a['first_different_sample'],10316126)
        self.assertFalse(a['checks']['same_digital_silence_intervals'])


if __name__=='__main__':unittest.main()
