"""#45 card-only compaction: bounded source and whole-route audio evidence."""
import hashlib
import json
import csv
from pathlib import Path
import sys
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts/diagnostics'))
from build_return_card_compact_trial import build
from verify_native_audio_pair import load,compare


class CardOnlyCompact(unittest.TestCase):
    def test_repeat_and_observer_capture_identity(self):
        for names in (('return-fade-audio-enabled-exit-16','return-fade-audio-enabled-exit-16-repeat'),
                      ('return-fade-sound-trial-16','return-fade-sound-trial-control-16')):
            hashes=[];inputs=[]
            for name in names:
                p=ROOT/'tmp'/name
                if not (p/'receipt.json').exists():self.skipTest('local replay unavailable')
                r=json.loads((p/'receipt.json').read_text());actual={}
                for filename,digest in r['native_capture']['hashes'].items():
                    with (Path(r['native_capture_directory'])/filename).open('rb') as f:
                        actual[filename]=hashlib.file_digest(f,'sha256').hexdigest()
                    self.assertEqual(actual[filename],digest)
                hashes.append(actual);inputs.append((p/'inputs.tsv').read_bytes())
            self.assertEqual(*hashes);self.assertEqual(*inputs)
        with (ROOT/'tmp/return-fade-sound-trial-16/cram-timing.tsv').open() as f:
            rows=list(csv.DictReader(f,delimiter='\t'))
        self.assertEqual(len(rows),640)
        fade=[r for r in rows if r['bank']=='14']
        self.assertEqual(len(fade),512)
        self.assertTrue(all(r['mode']=='1' and 144<=int(r['ly'])<=147 for r in fade))

    def test_no_continuous_health_replay(self):
        arrays=[];traces=[]
        for name in ('parent-01','16'):
            p=ROOT/'tmp'/('return-fade-nohealth-exit-'+name)
            if not (p/'receipt.json').exists():self.skipTest('local replay unavailable')
            r=json.loads((p/'receipt.json').read_text())
            self.assertFalse(r['observer_memory_writes'])
            wav=Path(r['native_capture_directory'])/'native.wav'
            with wav.open('rb') as f:self.assertEqual(hashlib.file_digest(f,'sha256').hexdigest(),r['native_capture']['hashes']['native.wav'])
            rate,samples=load(wav);self.assertEqual(rate,131072)
            arrays.append(samples);traces.append((p/'trace.tsv').read_bytes())
        self.assertEqual(*traces)
        result,differences=compare(*arrays,rate)
        self.assertEqual(result['status'],'pass')
        self.assertEqual(differences.shape,(13167008,2))
        self.assertEqual(result['different_sample_frames'],13773)

    def test_return_uploads_are_unchanged(self):
        p=ROOT/'tmp/return-cgb-fade-trial-14/candidate.gb'
        if not p.exists():self.skipTest('parent unavailable')
        parent=p.read_bytes();candidate=build(parent)
        self.assertEqual(hashlib.sha256(candidate).hexdigest(),'126dd0b7fff1e03eb6b224f818b85398593c7109ffb676cc538c1bd90742304b')
        self.assertEqual(parent[0x5151c:0x51c20],candidate[0x5151c:0x51c20])
        with self.assertRaises(ValueError):build(candidate)

    def test_full_audio_guard_passes_card_only_but_rejects_all_compact(self):
        arrays=[]
        for name in ('parent-01','15','16'):
            p=ROOT/'tmp'/('return-fade-audio-enabled-exit-'+name)/'receipt.json'
            if not p.exists():self.skipTest('local native evidence unavailable')
            receipt=json.loads(p.read_text());wav=Path(receipt['native_capture_directory'])/'native.wav'
            with wav.open('rb') as f:self.assertEqual(hashlib.file_digest(f,'sha256').hexdigest(),receipt['native_capture']['hashes']['native.wav'])
            rate,samples=load(wav)
            self.assertEqual(rate,131072);self.assertEqual(samples.shape,(13167008,2))
            arrays.append(samples)
        bad,_=compare(arrays[0],arrays[1],rate)
        good,differences=compare(arrays[0],arrays[2],rate)
        self.assertEqual(bad['status'],'fail')
        self.assertFalse(bad['checks']['no_larger_sample_discontinuity'])
        self.assertEqual(good['status'],'pass')
        self.assertEqual(good['different_sample_frames'],752304)
        self.assertEqual(differences.shape,(13167008,2))


if __name__=='__main__':unittest.main()
