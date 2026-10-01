"""#45 bounded assisted-route improvement; not hardware/full-game acceptance."""
import hashlib
import json
import mmap
from pathlib import Path
import unittest

ROOT=Path(__file__).resolve().parents[1]


class FinalFadeLateWindowEvidence(unittest.TestCase):
    def test_card_ablation_is_not_a_general_return_fix(self):
        run = ROOT/'tmp/late-card-route-exit-01'
        if not (run/'receipt.json').exists():
            self.skipTest('optional local card ablation replay unavailable')
        r = json.loads((run/'receipt.json').read_text())
        self.assertEqual(r['status'], 0)
        self.assertEqual(r['rom_sha256'], '7916d5152ff628fab1b95753bd89fb1c65f850c791d7475480a06b55e28083de')
        self.assertEqual(r['native_capture']['restored_replay_epoch']['status'], 'PASS')
        self.assertNotEqual((run/'trace.tsv').read_bytes(),
                            (ROOT/'tmp/final-fade-late-window-exit-01/trace.tsv').read_bytes())
        folder = Path(r['native_capture_directory'])
        for name, expected in r['native_capture']['hashes'].items():
            with (folder/name).open('rb') as stream:
                self.assertEqual(hashlib.file_digest(stream, 'sha256').hexdigest(), expected)
        with (folder/'native.states').open('rb') as sf, mmap.mmap(sf.fileno(), 0, access=mmap.ACCESS_READ) as s:
            first = next(i+1 for i in range(6000) if s[i*71680+0x5C80] == 2 and s[i*71680+0x3BA] == 0)
            self.assertEqual(first, 4679)  # Qualified parent was4666; do not hide drift.
        audio = json.loads((ROOT/'tmp/late-card-route-audio-pair-01/receipt.json').read_text())
        self.assertEqual(audio['status'], 'fail')
        self.assertFalse(audio['checks']['same_full_route_silent_blocks'])
        self.assertFalse(audio['checks']['same_digital_silence_intervals'])
        self.assertEqual(audio['different_sample_frames'], 13023567)
        self.assertEqual(audio['first_different_sample'], 0)
        # Independently generated pre-states already diverged; this is not an
        # isolated post-return APU effect or a valid retargeted-state comparison.

    def test_full_route_telemetry_and_hidden_map(self):
        run=ROOT/'tmp/final-fade-late-window-exit-01'
        control=ROOT/'tmp/initial-map-native-control-exit-01'
        self.assertEqual((run/'trace.tsv').read_bytes(),(control/'trace.tsv').read_bytes())
        self.assertEqual(len((run/'trace.tsv').read_text().splitlines()),6001)
        r=json.loads((run/'receipt.json').read_text())
        self.assertEqual(r['rom_sha256'],'46eb95a0c0f770fb3cf8c3211b8030a9e881f59077e558b93703ba08da71d3fb')
        self.assertEqual(r['native_capture']['restored_replay_epoch']['status'],'PASS')
        folder=Path(r['native_capture_directory'])
        for name,digest in r['native_capture']['hashes'].items():
            with (folder/name).open('rb') as f:
                self.assertEqual(hashlib.file_digest(f,'sha256').hexdigest(),digest)
        with (folder/'native.states').open('rb') as sf,(folder/'native.video').open('rb') as vf,mmap.mmap(sf.fileno(),0,access=mmap.ACCESS_READ) as s,mmap.mmap(vf.fileno(),0,access=mmap.ACCESS_READ) as v:
            start=next(i for i in range(6000) if s[i*71680+0x5C80]==2 and s[i*71680+0x3BA]==0)
            self.assertEqual(start+1,4666)
            resume=next(i+1 for i in range(4670,4800) if s[i*71680+0x3C1]==1 and s[i*71680+0x3E4]==0)
            self.assertEqual(resume,4722)
            incomplete=[];visible=[]
            for i in range(start,start+100):
                state=s[i*71680:(i+1)*71680];page=0x2000 if state[0x340]&8 else 0x1C00
                mismatch=any(state[page+y*32+x]!=state[0x45A0+y*24+x] for y in range(24) for x in range(24))
                white=v[i*92160:(i+1)*92160]==bytes((255,255,255,0))*23040
                if mismatch: incomplete.append(i+1);self.assertTrue(white)
                if not white: visible.append(i+1)
            self.assertEqual(incomplete,list(range(4666,4671)))
            self.assertEqual(visible[0],4687)

    def test_audio_guard_improves_without_claiming_waveform_equality(self):
        r=json.loads((ROOT/'tmp/final-fade-late-window-audio-pair-01/receipt.json').read_text())
        for file,digest in r['identities'].items():
            with Path(file).open('rb') as f:
                self.assertEqual(hashlib.file_digest(f,'sha256').hexdigest(),digest)
        self.assertEqual(r['status'],'pass')
        self.assertTrue(all(r['checks'].values()))
        self.assertEqual(r['different_sample_frames'],414)
        self.assertEqual((r['first_different_sample'],r['last_different_sample']),(10316126,10316539))
        broken=json.loads((ROOT/'tmp/fixed-fade-route-audio-pair-01/receipt.json').read_text())
        self.assertEqual(broken['status'],'fail')
        self.assertFalse(broken['checks']['same_digital_silence_intervals'])


if __name__=='__main__':unittest.main()
