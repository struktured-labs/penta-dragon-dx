"""Pure instruction-model checks; emulator/audio qualification stays separate."""
from pathlib import Path
import sys
import unittest
import random
import hashlib
import json

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts/diagnostics'))
from build_return_palette_compact_trial import body,PREFIX,SUFFIX,build


def writes(code,memory):
    # Deliberately tiny model for the straight-line upload body, not a GB core.
    code=code[len(PREFIX):-len(SUFFIX)]
    pc=0;a=b=c=hl=0;output=[];cycles=0
    while pc<len(code):
        op=code[pc];pc+=1
        if op in (0x3e,0x06,0x0e):
            value=code[pc];pc+=1;cycles+=8
            if op==0x3e:a=value
            elif op==0x06:b=value
            else:c=value
        elif op==0x21:
            hl=int.from_bytes(code[pc:pc+2],'little');pc+=2;cycles+=12
        elif op in (0x2a,0x7e):
            a=memory[hl-0xdf00];cycles+=8
            if op==0x2a:hl+=1
        elif op in (0x78,0x79):a=b if op==0x78 else c;cycles+=4
        elif op==0xe0:
            assert code[pc]==0x69;pc+=1;output.append(a);cycles+=12
        else:raise AssertionError(f'unmodeled opcode {op:02x}')
    return bytes(output),cycles


class CompactPalette(unittest.TestCase):
    def test_deadline_composition_keeps_schedule_and_audio_failure(self):
        root=Path(__file__).resolve().parents[1]
        path=root/'tmp/return-cgb-fade-trial-14/candidate.gb'
        if not path.exists():self.skipTest('local parent unavailable')
        parent=path.read_bytes();rom,sites=build(parent)
        self.assertEqual(hashlib.sha256(rom).hexdigest(),'de9f55bacefa10e55c65d6346ef504a18813925d2ff1aebf0efe10db30c5ec93')
        self.assertEqual(rom[0x51c20:0x51cdc],parent[0x51c20:0x51cdc])
        self.assertEqual(len(sites),4)
        evidence=root/'tmp/return-fade-audio-enabled-pair-15/receipt.json'
        if evidence.exists():
            r=json.loads(evidence.read_text())
            self.assertEqual(r['status'],'fail')
            self.assertTrue(r['checks']['same_digital_silence_intervals'])
            self.assertFalse(r['checks']['no_larger_sample_discontinuity'])
            self.assertEqual((r['parent']['maximum_sample_step'],r['candidate']['maximum_sample_step']),(18624,21326))

    def test_all_shades_preserve_every_color_and_reduce_upload_cycles(self):
        rng=random.Random(45)
        for _ in range(32):
            memory=bytes(rng.randrange(256) for _ in range(64))
            for mapping in (0,0x40,0x90,0xe4):
                old,cost=writes(body(mapping,False),memory)
                new,lower=writes(body(mapping,True),memory)
                self.assertEqual(len(new),64)
                self.assertEqual(old,new)
                self.assertLess(lower,cost)
                expected=b''.join(bytes.fromhex('ff7f') if ((mapping>>(2*c))&3)==0 and mapping!=0xe4
                                  else memory[r*8+((mapping>>(2*c))&3)*2:r*8+((mapping>>(2*c))&3)*2+2]
                                  for r in range(8) for c in range(4))
                self.assertEqual(new,expected)


if __name__=='__main__':unittest.main()
