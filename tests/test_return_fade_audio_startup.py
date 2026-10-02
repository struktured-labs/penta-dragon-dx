"""#43/#45: regenerated audio-enabled states remove the startup confound."""
import hashlib
import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'scripts/diagnostics'))
from verify_pickup_class_palettes import serialized_state
from verify_native_audio_pair import load, compare


class FadeAudioStartup(unittest.TestCase):
    def test_explicit_audio_states_and_full_pcm_failure(self):
        names = ('parent-01', '14')
        states = []
        arrays = []
        for name in names:
            entry = ROOT/'tmp'/('return-fade-audio-enabled-entry-'+name)
            if not (entry/'frame-3600.ss0').exists():
                self.skipTest('local source evidence unavailable')
            receipt = json.loads((entry/'receipt.json').read_text())
            self.assertEqual(receipt['diagnostic_environment']['ENTRY_AUDIO_ENABLED'], '1')
            states.append(serialized_state(entry/'frame-3600.ss0'))
            base = ROOT/'tmp'/('return-fade-audio-enabled-exit-'+name)
            receipt = json.loads((base/'receipt.json').read_text())
            self.assertEqual(receipt['source_state_sha256'], hashlib.sha256((entry/'frame-3600.ss0').read_bytes()).hexdigest())
            wav = Path(receipt['native_capture_directory'])/'native.wav'
            with wav.open('rb') as stream:
                self.assertEqual(hashlib.file_digest(stream, 'sha256').hexdigest(), receipt['native_capture']['hashes']['native.wav'])
            rate, samples = load(wav)
            self.assertEqual(rate, 131072)
            self.assertEqual(samples.shape, (13167008, 2))
            arrays.append(samples)
        self.assertEqual(states[0][0x48:0xb4], states[1][0x48:0xb4])
        self.assertEqual(states[0][0x1d8:0x280], states[1][0x1d8:0x280])
        result, differences = compare(*arrays, rate)
        self.assertEqual(result['status'], 'fail')
        self.assertEqual(result['first_different_sample'], 10485477)
        self.assertEqual(result['different_sample_frames'], 745710)
        self.assertEqual(differences.shape, (13167008, 2))
        self.assertTrue(result['checks']['same_full_route_silent_blocks'])
        self.assertFalse(result['checks']['same_digital_silence_intervals'])


if __name__ == '__main__':
    unittest.main()
