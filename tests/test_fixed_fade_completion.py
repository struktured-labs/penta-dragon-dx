"""#45 observer-neutral attribution of the extra frame to fade completion."""
import csv
import hashlib
import json
from pathlib import Path
import unittest

ROOT=Path(__file__).resolve().parents[1]


def rows(name,file):
    with (ROOT/'tmp'/name/file).open() as f:
        return list(csv.DictReader(f,delimiter='\t'))


class FixedFadeCompletion(unittest.TestCase):
    def test_observers_match_retained_same_rom_off_runs(self):
        for side,off in [('control','fixed-fade-late-control-off-01'),
                         ('trial','fixed-fade-late-sound-off-01')]:
            receipts=[json.loads((ROOT/'tmp'/name/'receipt.json').read_text())
                      for name in (f'fixed-fade-completion-{side}-01',off)]
            for key in ('rom_sha256','source_state_sha256','probe_sha256',
                        'runner_sha256','guard_sha256','native_tap_sha256','audio_options'):
                self.assertEqual(receipts[0][key],receipts[1][key])
            for r in receipts:
                c=r['native_capture']
                self.assertEqual(c['restored_replay_epoch']['status'],'PASS')
                self.assertEqual(c['metadata']['frames'],120)
                for file,digest in c['hashes'].items():
                    with (Path(r['native_capture_directory'])/file).open('rb') as f:
                        self.assertEqual(hashlib.file_digest(f,'sha256').hexdigest(),digest)
            self.assertEqual(receipts[0]['native_capture']['hashes'],
                             receipts[1]['native_capture']['hashes'])

    def test_fade_returns_late_before_same_seven_settle_calls(self):
        exits=[]
        for side,frame,ly in [('control',21,150),('trial',22,0)]:
            name=f'fixed-fade-completion-{side}-01'
            exit_rows=[r for r in rows(name,'secret-fade-timing.tsv') if r['pc']=='15DD']
            self.assertEqual(len(exit_rows),1)
            exit=exit_rows[0]
            self.assertEqual((int(exit['frame']),int(exit['ly'])),(frame,ly))
            settle=[r for r in rows(name,'return-build.tsv') if r['pc']=='16DD']
            self.assertEqual(len(settle),7)
            self.assertEqual(int(settle[0]['frame']),frame)
            self.assertGreater(int(settle[0]['cycle']),int(exit['cycle']))
            exits.append(int(exit['cycle']))
        self.assertEqual(exits[1]-exits[0],144704)


if __name__=='__main__':unittest.main()
