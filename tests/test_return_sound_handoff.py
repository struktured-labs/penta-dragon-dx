"""#45 sound timing investigation; preserves the unresolved late handoff."""
import csv
import hashlib
import json
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]


def receipt(name):
    return json.loads((ROOT/'tmp'/name/'receipt.json').read_text())


def commands(name):
    with (ROOT/'tmp'/name/'sound-commands.tsv').open() as f:
        return list(csv.DictReader(f, delimiter='\t'))


class ReturnSoundHandoff(unittest.TestCase):
    def setUp(self):
        if not (ROOT/'tmp/return-handoff-trial-off-01/receipt.json').exists():
            self.skipTest('local native investigation unavailable')

    def test_sound_observers_preserve_each_exact_replay(self):
        for on, off in (('return-sound-trial-01','return-sound-trial-off-01'),
                        ('return-handoff-control-01','return-handoff-control-off-01'),
                        ('return-handoff-trial-01','return-handoff-trial-off-01')):
            a, b = receipt(on), receipt(off)
            for key in ('rom_sha256','source_state_sha256','guard_sha256',
                        'runner_sha256','probe_sha256','native_tap_sha256'):
                self.assertEqual(a[key],b[key])
            for name in ('native.video','native.states','native.s16le','native.timeline.tsv'):
                digests = []
                for r in (a,b):
                    with (Path(r['native_capture_directory'])/name).open('rb') as f:
                        digest = hashlib.file_digest(f,'sha256').hexdigest()
                    self.assertEqual(digest,r['native_capture']['hashes'][name])
                    digests.append(digest)
                self.assertEqual(*digests)
            self.assertEqual((ROOT/'tmp'/on/'trace.tsv').read_bytes(),
                             (ROOT/'tmp'/off/'trace.tsv').read_bytes())

    def test_music_request_is_late_not_missing(self):
        parent = [r for r in commands('return-handoff-control-01') if r['command']=='13']
        trial = [r for r in commands('return-handoff-trial-01') if r['command']=='13']
        self.assertEqual([r['event'] for r in parent],['request','read','accept'])
        self.assertEqual([r['event'] for r in trial],['request','read','accept'])
        self.assertEqual(int(trial[0]['cycle'])-int(parent[0]['cycle']),142368)
        self.assertEqual(int(trial[2]['cycle'])-int(parent[2]['cycle']),87704)
        self.assertEqual((parent[0]['frame'],trial[0]['frame']),('105','106'))
        self.assertEqual((parent[2]['scene'],trial[2]['scene']),('02','18'))

    def test_early_audio_pass_does_not_replace_full_failure(self):
        early = receipt('return-sound-short-audio-01')
        full = receipt('return-only-fade-audio-pair-01')
        self.assertEqual(early['status'],'pass')
        self.assertEqual(early['first_different_sample'],323694)
        self.assertEqual(early['different_sample_frames'],82772)
        self.assertEqual(full['status'],'fail')
        self.assertFalse(full['checks']['same_digital_silence_intervals'])
        a = full['parent']['digital_silence_at_least_20ms']
        b = full['candidate']['digital_silence_at_least_20ms'] if 'candidate' in full else full['trial']['digital_silence_at_least_20ms']
        self.assertEqual(a[:18],b[:18])
        self.assertEqual(a[18],[10180407,10239690])
        self.assertEqual(b[18],[10180407,10241167])


if __name__ == '__main__': unittest.main()
