"""#27 exhaustive compact-route equivalence, distinct from runtime qualification."""
import hashlib
import json
from pathlib import Path
import sys
import unittest
import zlib

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts/diagnostics'))
import build_arena_alias_fastpath_trial as trial
from verify_pickup_class_palettes import serialized_state


def route(code, pc, scene):
    a=scene
    zero=carry=False
    writes=[]
    for _ in range(80):
        op=code[pc];pc+=1
        if op==0xF0:
            assert code[pc]==0xBA
            return 'dungeon',tuple(writes)
        if op==0x21:
            assert code[pc:pc+2]==bytes.fromhex('0070')
            return 'default',tuple(writes)
        if op==0xC6 and code[pc]==0x72:
            return ('arena',a),tuple(writes)
        if op in (0xFE,0xD6,0xC6,0x3E):
            value=code[pc];pc+=1
            if op==0x3E:a=value;continue
            total=a+value if op==0xC6 else a-value
            zero=(total&255)==0;carry=total<0 or total>255
            if op!=0xFE:a=total&255
        elif op in (0x18,0x20,0x28,0x30,0x38):
            offset=code[pc];pc+=1
            taken={0x18:True,0x20:not zero,0x28:zero,0x30:not carry,0x38:carry}[op]
            if taken:pc+=offset if offset<128 else offset-256
        elif op==0xAF:a=0;zero=True;carry=False
        elif op==0xEA:
            address=int.from_bytes(code[pc:pc+2],'little');pc+=2
            writes.append((address,a))
        elif op==0xC3:
            assert code[pc:pc+2]==bytes.fromhex('436D')
            return 'service',tuple(writes)
        else:raise AssertionError(f'unhandled {op:02x}')
    raise AssertionError('route did not finish')


class Fastpath(unittest.TestCase):
    def test_fresh_menu_replay_and_separate_native_alias_onset(self):
        menu=ROOT/'tmp/arena-alias-fastpath-shalamar-phase721-01'
        onset=ROOT/'tmp/arena-alias-fastpath-shalamar-onset-01'
        if not (onset/'receipt.json').exists():self.skipTest('local exact-ROM replays unavailable')
        rom=(ROOT/'tmp/arena-alias-fastpath-trial-01/candidate.gb').read_bytes()
        self.assertEqual(hashlib.sha256(rom).hexdigest(),
                         '585f5830daa32e59c000f5ddd6b57aab545e55375b46574286702db9fc28e4db')
        verdict=json.loads((menu/'verification.json').read_text())
        self.assertEqual([c['status'] for c in verdict['cycles']],['PASS']*3)
        self.assertFalse(verdict['failures'])
        receipt=json.loads((onset/'receipt.json').read_text())
        self.assertFalse(receipt['observer_memory_writes'])
        aliases=[];active=[]
        for frame in range(1,181):
            raw=serialized_state(onset/f'frame-{frame:04d}.ss0')
            self.assertEqual(int.from_bytes(raw[4:8],'little'),zlib.crc32(rom)&0xffffffff)
            if raw[0x5c80]==11 and raw[0x3b7]==12:
                aliases.append(frame)
                if raw[0x3e4]==0:active.append(frame)
                self.assertEqual(raw[0x630d],12)
                self.assertEqual(raw[0x4a00:0x4b00],bytes([0,0]+[4]*253+[0]))
        self.assertEqual(aliases,list(range(46,181)))
        self.assertEqual(active,list(range(46,93)))

    def test_every_scene_routes_like_original(self):
        p=ROOT/'tmp/stream-presentation-source-01/candidate.gb'
        if not p.exists():self.skipTest('original exact parent unavailable')
        original=p.read_bytes()
        self.assertEqual(hashlib.sha256(original).hexdigest(),
                         'd744124d3d161247e0584bb39e8db1243ade4e428cbc15f82a85c10d0a4ac4d5')
        before=original[0x36F90:0x37000]
        after=trial.detector()
        self.assertEqual(after[:8],before[:8])
        self.assertEqual(len(after),112)
        self.assertEqual(after[19:21],bytes.fromhex('FE02'))
        for scene in range(256):
            self.assertEqual(route(before,12,scene),route(after,19,scene),scene)

    def test_exact_builder_and_banked_return(self):
        p=ROOT/'tmp/arena-graphics-owner-trial-01/candidate.gb'
        if not p.exists():self.skipTest('exact parent unavailable')
        result=trial.build(p.read_bytes())
        self.assertEqual(result[0x36F98:0x36F9F],bytes.fromhex('3E14 CDBE09 F1 C8'))
        self.assertEqual(result[0x52F9A:0x52FA0],bytes.fromhex('CDBE09 C3E06D'))
        with self.assertRaises(ValueError):trial.build(result)


if __name__=='__main__':unittest.main()
