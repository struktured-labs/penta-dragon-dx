"""#45 exact replay evidence: late handoff remains unresolved."""
import csv
import hashlib
import json
import mmap
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]


def receipt(name):
    return json.loads((ROOT/'tmp'/name/'receipt.json').read_text())


class FixedFadeLateHandoff(unittest.TestCase):
    def test_sound_observers_are_neutral_for_both_short_replays(self):
        for stem in ('fixed-fade-late-control', 'fixed-fade-late-sound'):
            on, off = receipt(stem+'-01'), receipt(stem+'-off-01')
            for key in ('rom_sha256','source_state_sha256','guard_sha256',
                        'runner_sha256','probe_sha256','native_tap_sha256','audio_options'):
                self.assertEqual(on[key],off[key])
            for r in (on,off):
                capture=r['native_capture']
                self.assertEqual(capture['restored_replay_epoch']['status'],'PASS')
                self.assertEqual(capture['metadata']['frames'],120)
                for name, expected in capture['hashes'].items():
                    with (Path(r['native_capture_directory'])/name).open('rb') as f:
                        self.assertEqual(hashlib.file_digest(f,'sha256').hexdigest(),expected)
            self.assertEqual(on['native_capture']['hashes'],off['native_capture']['hashes'])

    def test_full_replay_gameplay_resume_is_one_frame_late(self):
        for name, expected in (('initial-map-native-control-exit-01',4722),
                               ('fixed-fade-route-exit-01',4723)):
            r=receipt(name)
            p=Path(r['native_capture_directory'])/'native.states'
            with p.open('rb') as f:
                self.assertEqual(hashlib.file_digest(f,'sha256').hexdigest(),
                                 r['native_capture']['hashes']['native.states'])
                with mmap.mmap(f.fileno(),0,access=mmap.ACCESS_READ) as states:
                    frame=next(i+1 for i in range(4670,4800)
                               if states[i*71680+0x3C1]==1 and states[i*71680+0x3E4]==0)
            self.assertEqual(frame,expected)

    def test_later_effect_is_delivered_but_delayed(self):
        events=[]
        for stem in ('fixed-fade-late-control','fixed-fade-late-sound'):
            with (ROOT/'tmp'/f'{stem}-01'/'sound-commands.tsv').open() as f:
                rows=list(csv.DictReader(f,delimiter='\t'))
            events.append(next(r for r in rows if r['event']=='accept' and r['command']=='26'))
        self.assertEqual([r['frame'] for r in events],['53','55'])
        self.assertEqual(int(events[1]['cycle'])-int(events[0]['cycle']),188432)


if __name__=='__main__': unittest.main()
