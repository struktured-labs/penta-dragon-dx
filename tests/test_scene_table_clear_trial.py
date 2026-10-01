"""Instruction-level clear-loop checks, not full emulator qualification."""
import sys
import unittest
import csv
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts/diagnostics'))
import build_scene_table_clear_trial as trial


def execute(code):
    pc=cycles=0
    a=b=hl=flags=None
    writes=[]
    for _ in range(2000):
        op=code[pc]; pc+=1
        if op==0x21:
            hl=int.from_bytes(code[pc:pc+2],'little'); pc+=2; cycles+=12
        elif op==0xAF:
            a=0; flags=0x80; cycles+=4
        elif op==0x06:
            b=code[pc]; pc+=1; cycles+=8
        elif op==0x22:
            writes.append((hl,a)); hl=(hl+1)&65535; cycles+=8
        elif op==0x05:
            old=b; b=(b-1)&255
            flags=(flags&16)|64|(128 if b==0 else 0)|(32 if old&15==0 else 0)
            cycles+=4
        elif op==0x20:
            offset=int.from_bytes(code[pc:pc+1],'little',signed=True); pc+=1
            if not flags&128: pc+=offset; cycles+=12
            else: cycles+=8
        elif op==0xC9:
            return writes,(a,b,hl,flags),cycles+16
        else:
            raise ValueError(f'Unsupported opcode {op:02x}')
    raise ValueError('Clear loop did not terminate')


class SceneClearTests(unittest.TestCase):
    def test_retained_trial_is_not_audio_qualified(self):
        receipt=ROOT/'tmp/scene-table-clear-audio-comparison-01/receipt.json'
        if not receipt.exists(): self.skipTest('Local trial evidence unavailable')
        result=json.loads(receipt.read_text())
        self.assertEqual(result['status'],'fail')
        self.assertFalse(result['checks']['level_within_two_percent'])
        self.assertFalse(result['checks']['same_digital_silence_intervals'])
        self.assertEqual(result['first_different_sample'],16585)
        for suffix in ('s16le','video','states','timeline.tsv','wav'):
            observed=Path('/mnt/data/tmp/penta-scene-table-clear-transition-01-av')/('native.'+suffix)
            control=Path('/mnt/data/tmp/penta-scene-table-clear-control-01-av')/('native.'+suffix)
            self.assertEqual(observed.read_bytes(),control.read_bytes())
        spans=[]
        for name in ('secret-fast-palette-setup-cost-01','scene-table-clear-transition-01'):
            with (ROOT/'tmp'/name/'vblank-helpers.tsv').open() as stream:
                frame={r['pc']:r for r in csv.DictReader(stream,delimiter='\t') if r['frame']=='6'}
            spans.append(int(frame['548C']['cycle'])-int(frame['5484']['cycle']))
        self.assertEqual(spans,[12456,6312])

    def test_identical_writes_and_exit_state_fewer_cycles(self):
        old=execute(bytes.fromhex('2100c6af0600220520fcc9'))
        new=execute(trial.CODE)
        self.assertEqual(old[:2],new[:2])
        self.assertEqual(new[0],[(address,0) for address in range(0xC600,0xC700)])
        self.assertEqual((old[2],new[2]),(6180,3108))

    def test_missing_store_does_not_pass_equivalence(self):
        bad=execute(bytes.fromhex('2100c6af06402222220520fac9'))
        self.assertNotEqual(bad[:2],execute(trial.CODE)[:2])

    def test_exact_parent_and_patch_boundaries(self):
        path=ROOT/'tmp/secret-sound-alias-fast-trial-01/candidate.gb'
        if not path.exists(): self.skipTest('Exact local parent unavailable')
        parent=path.read_bytes(); changed=trial.build(parent)
        allowed=set(range(trial.CALL,trial.CALL+3))|set(range(trial.CAVE,trial.CAVE+len(trial.CODE)))|{0x14E,0x14F}
        self.assertEqual(len(changed),len(parent))
        self.assertTrue(all(a==b or i in allowed for i,(a,b) in enumerate(zip(parent,changed))))
        self.assertEqual(changed[trial.BANK+0x2D43:trial.CAVE],parent[trial.BANK+0x2D43:trial.CAVE])
        with self.assertRaises(ValueError): trial.build(b'wrong')
