"""#45 full-port sound observation; residual timing is not waveform equality."""
import csv
import hashlib
import json
from pathlib import Path
import unittest

ROOT=Path(__file__).resolve().parents[1]


class FinalFadeSoundTiming(unittest.TestCase):
    def test_all_register_observation_is_neutral(self):
        for stem in ('final-fade-all-audio','final-fade-all-audio-control'):
            rs=[]
            for side in ('on','off'):
                r=json.loads((ROOT/'tmp'/f'{stem}-{side}-01'/'receipt.json').read_text())
                self.assertEqual(r['native_capture']['restored_replay_epoch']['status'],'PASS')
                for name,digest in r['native_capture']['hashes'].items():
                    with (Path(r['native_capture_directory'])/name).open('rb') as f:
                        self.assertEqual(hashlib.file_digest(f,'sha256').hexdigest(),digest)
                rs.append(r)
            for key in ('rom_sha256','source_state_sha256','probe_sha256','runner_sha256',
                        'guard_sha256','native_tap_sha256','audio_options'):
                self.assertEqual(rs[0][key],rs[1][key])
            self.assertEqual(rs[0]['native_capture']['hashes'],rs[1]['native_capture']['hashes'])

    def test_same_register_values_with_retained_frequency_timing_differences(self):
        streams=[]
        for name in ('final-fade-all-audio-control-on-01','final-fade-all-audio-on-01'):
            with (ROOT/'tmp'/name/'sound-timing.tsv').open() as f:
                streams.append([r for r in csv.DictReader(f,delimiter='\t') if r['kind']!='timer'])
        self.assertEqual([len(r) for r in streams],[497,497])
        self.assertEqual([(r['kind'],r['value']) for r in streams[0]],
                         [(r['kind'],r['value']) for r in streams[1]])
        differences=[]
        for a,b in zip(*streams):
            delta=int(b['cycle'])-int(a['cycle'])
            if abs(delta)>32: differences.append((a['kind'],int(a['frame']),delta))
        # Smaller phase offsets are retained in the source TSVs, not discarded
        # from any audio acceptance comparison.
        self.assertEqual(differences,[('FF18',23,11856),('FF18',26,-28440),
                                     ('FF18',28,1496),('FF18',28,56)])


if __name__=='__main__':unittest.main()
