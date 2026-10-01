"""Synthetic #28 evidence controls; no cartridge assets or emulator required."""
import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts/diagnostics'))
import verify_continue_input as oracle


class ContinueOracleTests(unittest.TestCase):
    def setUp(self):
        (ROOT/'tmp').mkdir(exist_ok=True)
        temp=tempfile.TemporaryDirectory(dir=ROOT/'tmp',prefix='continue-oracle-test-')
        self.addCleanup(temp.cleanup)
        self.folder=Path(temp.name)
        (self.folder/'candidate.gb').write_bytes(b'synthetic ROM')
        (self.folder/'probe.lua').write_bytes(b'synthetic probe')

    def fixture(self,success=True,button=1,prompt=False):
        limit=6000 if prompt else 2400
        input_start=1392 if prompt else 1380
        receipt=dict(status=0,source_state_sha256=None,
                     rom_sha256=oracle.digest(self.folder/'candidate.gb'),
                     probe_sha256=oracle.digest(self.folder/'probe.lua'),
                     diagnostic_environment=dict(ENTRY_CONTINUE_TEST='1',ENTRY_COLD='1',
                                                 ENTRY_FRAMES=str(limit),ENTRY_KEYS=str(button),
                                                 ENTRY_PROMPT_RELATIVE='1' if prompt else '0'))
        (self.folder/'receipt.json').write_text(json.dumps(receipt))
        rows=[]
        state=['frame\tscene\tmode']
        for frame in range(1,limit+1):
            scene=2 if frame<1280 or (success and frame>=1437) else (1 if frame>=2191 else 23)
            credit=1 if 1201<=frame<(input_start+1 if success else 1952) else 0
            countdown=max(0,10-(frame-1335)//60) if frame>=1335 else 0
            key=button if input_start<=frame<input_start+420 and (frame-input_start)%12<6 else 0
            rows.append(f'{frame}\t{scene:02X}\t{credit:02X}\t{countdown:02X}\t00\t{key:02X}')
            state.append(f'{frame}\t{scene:02X}\t01')
        (self.folder/'continue.tsv').write_text('\n'.join(rows)+'\n')
        (self.folder/'trace.tsv').write_text('\n'.join(state)+'\n')
        (self.folder/'continue-poll.tsv').write_text(
            ('1380\t00\t00\t00\tFF\n1392\t01\t01\t01\tFF\n' if prompt else '1380\t01\t01\t01\tFF\n')
            if success else '1380\t00\t00\t00\tFF\n')

    def test_prompt_relative_accepted_and_rejected_a(self):
        self.fixture(prompt=True)
        result=oracle.verify(self.folder)
        self.assertTrue(result['passed'])
        self.assertEqual(result['input_start_frame'],1392)
        self.assertEqual(result['frames'],6000)
        self.fixture(success=False,prompt=True)
        self.assertFalse(oracle.verify(self.folder)['passed'])

    def test_stage2_approach_schedule_and_mutations(self):
        self.fixture(prompt=True)
        (self.folder/'entry.ss0').write_bytes(b'synthetic Stage2 entry')
        path=self.folder/'receipt.json'
        receipt=json.loads(path.read_text())
        receipt['source_state_sha256']=oracle.digest(self.folder/'entry.ss0')
        receipt['diagnostic_environment'].update(ENTRY_COLD='0',ENTRY_STAGE='2',ENTRY_APPROACH_UP='1')
        path.write_text(json.dumps(receipt))
        for name in ('continue.tsv','trace.tsv'):
            path=self.folder/name
            rows=[line.split('\t') for line in path.read_text().splitlines()]
            for row in rows:
                if not row[0].isdigit(): continue
                if row[1]=='02': row[1]='03'
                if name=='continue.tsv' and 1201<int(row[0])<1280: row[5]='40'
            path.write_text('\n'.join('\t'.join(r) for r in rows)+'\n')
        self.assertTrue(oracle.verify(self.folder)['passed'])
        path=self.folder/'continue.tsv'
        original=path.read_text()
        for frame in (1202,1279,1280,2470):
            with self.subTest(frame=frame):
                rows=original.splitlines()
                row=rows[frame-1].split('\t')
                row[5]='00' if frame<1280 else '40'
                rows[frame-1]='\t'.join(row)
                path.write_text('\n'.join(rows)+'\n')
                with self.assertRaisesRegex(ValueError,'button schedule'):
                    oracle.verify(self.folder)
        path.write_text(original)

    def test_prompt_relative_neutral_and_start(self):
        for button in (0,8):
            self.fixture(success=False,button=button,prompt=True)
            self.assertTrue(oracle.verify(self.folder)['passed'])

    def test_prompt_relative_rejects_fixed_schedule(self):
        self.fixture(prompt=True)
        path=self.folder/'continue.tsv'
        rows=path.read_text().splitlines()
        rows[1379]=rows[1379][:-2]+'01'
        path.write_text('\n'.join(rows)+'\n')
        with self.assertRaisesRegex(ValueError,'button schedule'):
            oracle.verify(self.folder)

    def test_accepted_a_and_broken_a(self):
        self.fixture()
        self.assertTrue(oracle.verify(self.folder)['passed'])
        self.fixture(success=False)
        self.assertFalse(oracle.verify(self.folder)['passed'])

    def test_stage2_state_binding_and_return_scene(self):
        self.fixture()
        (self.folder/'entry.ss0').write_bytes(b'synthetic Stage2 state')
        path=self.folder/'receipt.json'
        receipt=json.loads(path.read_text())
        receipt['source_state_sha256']=oracle.digest(self.folder/'entry.ss0')
        receipt['diagnostic_environment'].update(ENTRY_COLD='0',ENTRY_STAGE='2')
        path.write_text(json.dumps(receipt))
        with self.assertRaisesRegex(ValueError,'requested active stage'):
            oracle.verify(self.folder)
        for name in ('continue.tsv','trace.tsv'):
            path=self.folder/name
            path.write_text(path.read_text().replace('\t02\t','\t03\t'))
        self.assertTrue(oracle.verify(self.folder)['passed'])
        (self.folder/'entry.ss0').write_bytes(b'changed')
        with self.assertRaisesRegex(ValueError,'entry state binding'):
            oracle.verify(self.folder)

    def test_neutral_and_start_time_out(self):
        for button in (0,8):
            self.fixture(success=False,button=button)
            self.assertTrue(oracle.verify(self.folder)['passed'])

    def test_missing_input_evidence_rejected(self):
        self.fixture()
        (self.folder/'continue-poll.tsv').write_text('')
        with self.assertRaises(ValueError): oracle.verify(self.folder)

    def test_changed_rom_rejected(self):
        self.fixture()
        (self.folder/'candidate.gb').write_bytes(b'changed')
        with self.assertRaises(ValueError): oracle.verify(self.folder)

    def test_incomplete_trace_rejected(self):
        self.fixture()
        path=self.folder/'continue.tsv'
        path.write_text('\n'.join(path.read_text().splitlines()[:-1]))
        with self.assertRaises(ValueError): oracle.verify(self.folder)

    def test_wrong_button_schedule_rejected(self):
        self.fixture()
        path=self.folder/'continue.tsv'
        rows=path.read_text().splitlines()
        rows[1380]='1381\t17\t00\t0A\t00\t08'
        path.write_text('\n'.join(rows)+'\n')
        with self.assertRaises(ValueError): oracle.verify(self.folder)


if __name__=='__main__': unittest.main()
