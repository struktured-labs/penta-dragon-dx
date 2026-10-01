"""#45: visual improvement must not conceal full-route native audio failure."""
import hashlib
import csv
import json
from pathlib import Path
import sys
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts/diagnostics'))
from verify_native_audio_pair import load,compare


class ReturnFadeAudioEvidence(unittest.TestCase):
    def test_sound_trace_is_neutral_and_keeps_command_latency_visible(self):
        commands=[]
        for traced,control in (
            ('return-fade-sound-parent-01','return-fade-sound-parent-control-01'),
            ('return-fade-sound-trial-10','return-fade-sound-trial-control-10'),
        ):
            hashes=[]
            for name in (traced,control):
                base=ROOT/'tmp'/name
                if not (base/'receipt.json').exists():self.skipTest('sound trace unavailable')
                r=json.loads((base/'receipt.json').read_text())
                self.assertEqual(r['status'],0)
                self.assertFalse(r['observer_memory_writes'])
                actual={}
                for ext in ('states','video','s16le','timeline.tsv'):
                    with (Path(r['native_capture_directory'])/f'native.{ext}').open('rb') as f:
                        actual[ext]=hashlib.file_digest(f,'sha256').hexdigest()
                    self.assertEqual(actual[ext],r['native_capture']['hashes'][f'native.{ext}'])
                hashes.append(actual)
            self.assertEqual(*hashes)
            with (ROOT/'tmp'/traced/'sound-commands.tsv').open() as f:
                commands.append([r for r in csv.DictReader(f,delimiter='\t') if r['command']=='13'])
        for rows in commands:self.assertEqual([r['event'] for r in rows],['request','read','accept'])
        a,b=commands
        self.assertEqual(int(b[0]['cycle'])-int(a[0]['cycle']),148656)
        self.assertEqual(int(b[2]['cycle'])-int(a[2]['cycle']),178968)
        self.assertEqual((a[2]['frame'],b[2]['frame']),('120','122'))
        # Same music command, delayed request AND service. No audio-pass inference.

    def test_trial10_retains_untrimmed_transition_silence_failure(self):
        sources=(
            ('return-initial-map-exit-01','916ebb1858c6b9e91491081d82e93d00d283180ef44323f1f29c37a033e48deb'),
            ('return-cgb-fade-exit-10','f938ae85785b4bc30133dad1c39e5f45ee0bcbea249d94f160132970ce22be29'),
        )
        arrays=[]
        for name,sha in sources:
            base=ROOT/'tmp'/name
            if not (base/'receipt.json').exists():self.skipTest('native route evidence unavailable')
            receipt=json.loads((base/'receipt.json').read_text())
            self.assertEqual(receipt['status'],0)
            self.assertEqual(receipt['rom_sha256'],sha)
            self.assertEqual(hashlib.sha256((base/'candidate.gb').read_bytes()).hexdigest(),sha)
            path=Path(receipt['native_capture_directory'])/'native.wav'
            if not path.exists():self.skipTest('native audio unavailable')
            with path.open('rb') as f:
                self.assertEqual(hashlib.file_digest(f,'sha256').hexdigest(),receipt['native_capture']['hashes']['native.wav'])
            rate,samples=load(path)
            self.assertEqual(rate,131072)
            self.assertEqual(samples.shape,(13167008,2))
            arrays.append(samples)
        result,differences=compare(*arrays,rate)
        self.assertEqual(result['status'],'fail')
        self.assertEqual(result['first_different_sample'],10460436)
        self.assertEqual(result['different_sample_frames'],2622052)
        self.assertEqual(differences.shape,(13167008,2))
        self.assertFalse(result['checks']['same_full_route_silent_blocks'])
        self.assertFalse(result['checks']['same_digital_silence_intervals'])
        self.assertTrue(result['checks']['no_added_clipping'])
        self.assertTrue(result['checks']['level_within_two_percent'])
        self.assertIn([10486614,10535734],result['parent']['digital_silence_at_least_20ms'])
        self.assertIn([10486614,10538418],result['candidate']['digital_silence_at_least_20ms'])


if __name__=='__main__':unittest.main()
