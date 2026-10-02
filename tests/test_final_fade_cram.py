import copy
import csv
import hashlib
import json
from pathlib import Path
import sys
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts/diagnostics'))
from check_final_fade_cram import failures
from verify_pickup_class_palettes import serialized_state


class FinalFadeCram(unittest.TestCase):
    def test_actual_upload_and_negative_controls(self):
        with (ROOT/'tmp/final-fade-cram-on-01/cram-timing.tsv').open() as f:
            all_rows=list(csv.DictReader(f,delimiter='\t'))
        self.assertEqual(len(all_rows),320)
        self.assertFalse(any(int(r['lcdc'],16)&128 and r['mode']=='3' for r in all_rows))
        rows=[r for r in all_rows if r['bank']=='14' and 0x6336<=int(r['pc'],16)<=0x63B6]
        self.assertEqual(sorted({int(r['ly']) for r in rows}),[150,151,152])
        backup=serialized_state(ROOT/'tmp/final-fade-late-window-exit-01/frame-4680.ss0')[0xC300:0xC340]
        r=json.loads((ROOT/'tmp/final-fade-cram-on-01/receipt.json').read_text())
        with (Path(r['native_capture_directory'])/'native.states').open('rb') as f:
            f.seek(21*71680);actual=f.read(71680)[0xD4:0x114]
        self.assertEqual(failures(rows,backup,actual),[])
        for key,value in [('mode','3'),('index','C7'),('value','00'),('bank','01')]:
            changed=copy.deepcopy(rows);changed[0][key]=value
            self.assertTrue(failures(changed,backup,actual),key)
        self.assertTrue(failures(rows[:-1],backup,actual))
        self.assertTrue(failures(rows,backup,bytes(64)))

    def test_full_primary_observer_neutrality(self):
        receipts=[]
        for side in ('on','off'):
            r=json.loads((ROOT/'tmp'/f'final-fade-cram-{side}-01'/'receipt.json').read_text())
            self.assertEqual(r['rom_sha256'],'46eb95a0c0f770fb3cf8c3211b8030a9e881f59077e558b93703ba08da71d3fb')
            self.assertEqual(r['native_capture']['restored_replay_epoch']['status'],'PASS')
            for name,digest in r['native_capture']['hashes'].items():
                with (Path(r['native_capture_directory'])/name).open('rb') as f:
                    self.assertEqual(hashlib.file_digest(f,'sha256').hexdigest(),digest)
            receipts.append(r)
        for key in ('source_state_sha256','probe_sha256','runner_sha256',
                    'guard_sha256','native_tap_sha256','audio_options'):
            self.assertEqual(receipts[0][key],receipts[1][key])
        self.assertEqual(receipts[0]['native_capture']['hashes'],receipts[1]['native_capture']['hashes'])


if __name__=='__main__':unittest.main()
