from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts/diagnostics'))
import build_stationary_copy_r415 as b

class StationaryCopyTests(unittest.TestCase):
    def test_helper_all_movement_results_and_maps(self):
        for marker in range(256):
            for high in (0x98,0x9C):
                a=0; h=high; de=0x1234;c=0x56;z=False;pc=0
                while True:
                    op=b.HELPER[pc];pc+=1
                    if op==0xF0:self.assertEqual(b.HELPER[pc],0xCE);pc+=1;a=marker
                    elif op==0xB7:z=a==0
                    elif op==0x28:
                        delta=b.HELPER[pc];pc+=1
                        if z:pc+=delta
                    elif op==0x7C:a=h
                    elif op==0xC6:a=(a+b.HELPER[pc])&255;pc+=1;z=a==0
                    elif op==0x67:h=a
                    elif op==0x11:de=int.from_bytes(b.HELPER[pc:pc+2],'little');pc+=2
                    elif op==0x0E:c=b.HELPER[pc];pc+=1
                    elif op==0x3E:a=b.HELPER[pc];pc+=1
                    elif op==0xC9:break
                    else:self.fail(hex(op))
                self.assertEqual((a,z),(1,marker==0))
                self.assertEqual((h,de,c),(high,0x1234,0x56) if marker==0 else (high+3,0xC3E0,0))

    def test_scope_and_native_stack_paths(self):
        source=b.BASE.read_bytes();rom=b.build(source)
        self.assertEqual(rom[0x13C0:0x13CD],source[0x13C0:0x13CD])
        self.assertEqual(rom[0x13DA:0x13E4],source[0x13DA:0x13E4])
        self.assertEqual(b.ENTRY[5:12],bytes.fromhex('CA C6 42 F1 C3 ED 42'))
        self.assertEqual(b.NATIVE,bytes.fromhex('F1 C3 DE 13'))
        allowed=set(range(0x13CD,0x13DA))|set(range(0x42C6,0x42CA))|set(range(b.OFFSET,b.OFFSET+len(b.HELPER)))|{0x14D,0x14E,0x14F}
        self.assertTrue(all(x==y or i in allowed for i,(x,y) in enumerate(zip(source,rom))))

if __name__=='__main__':unittest.main()
