import sys
from pathlib import Path
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts/diagnostics'))
import build_metatile_pointer_r406 as b

def execute(code,tile):
    r=dict(a=tile,b=73,c=89,h=0xC2,l=17);pc=0
    while pc<len(code):
        op=code[pc];pc+=1
        if op in (0x4F,0x47,0x79,0x6F,0x4C,0x4D,0x44):
            dst,src={0x4F:('c','a'),0x47:('b','a'),0x79:('a','c'),0x6F:('l','a'),
                     0x4C:('c','h'),0x4D:('c','l'),0x44:('b','h')}[op];r[dst]=r[src]
        elif op==0x07:r['a']=((r['a']<<1)|(r['a']>>7))&255
        elif op==0x87:r['a']=(2*r['a'])&255
        elif op in (0xE6,0xF6,0x26):
            n=code[pc];pc+=1
            if op==0xE6:r['a']&=n
            elif op==0xF6:r['a']|=n
            else:r['h']=n
        elif op==0x01:r['c'],r['b']=code[pc:pc+2];pc+=2
        elif op in (0x29,0x09):
            hl=256*r['h']+r['l'];hl=(hl+(hl if op==0x29 else 256*r['b']+r['c']))&65535
            r['h'],r['l']=divmod(hl,256)
        else:raise AssertionError(hex(op))
    return 256*r['b']+r['c']

class PointerTests(unittest.TestCase):
    def test_all_tile_values(self):
        for tile in range(256):
            self.assertEqual(execute(b.OLD,tile),0xA000+4*tile)
            self.assertEqual(execute(b.NEW,tile),0xA000+4*tile)
    def test_patch_scope(self):
        source=b.BASE.read_bytes();rom=b.build(source)
        allowed={0x14D,0x14E,0x14F}
        for site in b.SITES:allowed.update(range(site,site+12))
        self.assertTrue(all(x==y or i in allowed for i,(x,y) in enumerate(zip(source,rom))))

if __name__=='__main__':unittest.main()
