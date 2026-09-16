from pathlib import Path
import sys
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts/diagnostics'))
import build_first_dirty_source_r397 as b


class FirstDirtyTests(unittest.TestCase):
    def test_store_switches_only_on_change(self):
        source=b.BASE.read_bytes()
        code,labels=b.clone(source[b.FALLBACK:b.FALLBACK+75])
        starts=[i for i in range(len(code)) if code[i:i+3]==bytes.fromhex('0A BE 28')]
        self.assertEqual(len(starts),4)
        for n,start in enumerate(starts):
            for new in range(256):
                for old in (new,new^255,0,255):
                    pc=start; a=0; equal=False; dirty={}; jumped=False
                    while True:
                        op=code[pc]; pc+=1
                        if op==0x0A: a=new
                        elif op==0xBE: equal=a==old
                        elif op==0x28:
                            delta=code[pc]; pc+=1
                            if equal: pc+=delta
                        elif op==0x3E: a=code[pc]; pc+=1
                        elif op==0xEA:
                            addr=int.from_bytes(code[pc:pc+2],'little');pc+=2
                            dirty[addr]=a
                        elif op==0xC3:
                            dest=int.from_bytes(code[pc:pc+2],'little')
                            self.assertEqual(dest,labels['rawstore'+str(n)])
                            pc=dest-b.ENTRY; jumped=True
                        elif op in (0x22,0x77):
                            self.assertEqual(a,new)
                            self.assertEqual(op,0x22 if n<3 else 0x77)
                            if n<3: self.assertEqual(code[pc],0x03)
                            break
                        else: self.fail(hex(op))
                    self.assertEqual(jumped,new!=old)
                    self.assertEqual(dirty,{0xDF53:255,0xDF57:255} if new!=old else {})

    def test_raw_continuation_and_patch_scope(self):
        source=b.BASE.read_bytes(); original=source[b.FALLBACK:b.FALLBACK+75]
        code,labels=b.clone(original)
        raw=code[labels['rawrow']-b.ENTRY:labels['fallback']-b.ENTRY]
        # Exact native setup, stack choreography and loop tails; only store
        # increment ordering matches the already-tested r395 source writer.
        expected=bytearray(original[13:34])
        expected.extend(bytes.fromhex('0A 22 03 0A 22 03 E5 11 16 00 19 0A 22 03 0A 77 E1'))
        expected.extend(original[51:55]); expected.extend((0x20,0))
        expected.extend(original[57:69]); expected.extend((0x20,0))
        expected.extend(original[-4:])
        for i in (len(expected)-5,len(expected)-19):
            destination=labels['rawrow']+i+1+int.from_bytes(raw[i:i+1],'little',signed=True)
            self.assertEqual(destination,labels['rawrow' if i==len(expected)-5 else 'rawcell'])
            expected[i]=raw[i]
        self.assertEqual(raw,expected)
        for prefix in ('raw','checked'):
            start=labels[prefix+'row']-b.ENTRY
            self.assertEqual(code[start:start+3],bytes.fromhex('0E 0B C5'))
        candidate=b.build(source)
        changed={i for i,(x,y) in enumerate(zip(source,candidate)) if x!=y}
        self.assertTrue(changed <= set(range(b.OFFSET,b.OFFSET+len(code)))|set(range(b.CLONE,b.CLONE+3))|{0x14D,0x14E,0x14F})
        self.assertEqual(candidate[b.FALLBACK:b.FALLBACK+75],original)


if __name__=='__main__': unittest.main()
