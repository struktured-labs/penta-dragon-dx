"""#45 retain measured arrival, acquisition and IRQ re-entry, without retiming."""
import csv
import hashlib
import json
from pathlib import Path
import unittest

ROOT=Path(__file__).resolve().parents[1]


class FixedFadeWindow(unittest.TestCase):
    def test_observer_neutrality_and_missed_window(self):
        receipts=[]
        for side in ('on','off'):
            r=json.loads((ROOT/'tmp'/f'fixed-fade-window-{side}-01'/'receipt.json').read_text())
            self.assertEqual(r['native_capture']['restored_replay_epoch']['status'],'PASS')
            for name,digest in r['native_capture']['hashes'].items():
                with (Path(r['native_capture_directory'])/name).open('rb') as f:
                    self.assertEqual(hashlib.file_digest(f,'sha256').hexdigest(),digest)
            receipts.append(r)
        for key in ('rom_sha256','source_state_sha256','probe_sha256','runner_sha256',
                    'guard_sha256','native_tap_sha256','audio_options'):
            self.assertEqual(receipts[0][key],receipts[1][key])
        self.assertEqual(receipts[0]['native_capture']['hashes'],receipts[1]['native_capture']['hashes'])
        with (ROOT/'tmp/fixed-fade-window-on-01/return-fade-window.tsv').open() as f:
            rows=list(csv.DictReader(f,delimiter='\t'))
        acquire=[r for r in rows if r['kind']=='acquire']
        ready=[r for r in rows if r['kind']=='ready']
        self.assertEqual([int(r['frame']) for r in acquire],[5,13,21])
        self.assertEqual([int(r['ly']) for r in acquire],[150]*3)
        self.assertEqual([int(r['frame']) for r in ready],[6,14,22])
        self.assertEqual([int(r['ly']) for r in ready],[144]*3)
        ends=[r for r in rows if r['kind']=='final_upload_end']
        self.assertEqual([int(r['ly']) for r in ends],[147,0,0])
        self.assertEqual(int(ends[0]['cycle'])-int(ready[-1]['cycle']),3544)


if __name__=='__main__':unittest.main()
