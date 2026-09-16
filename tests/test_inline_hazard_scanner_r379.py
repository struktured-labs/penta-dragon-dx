import sys
from pathlib import Path
import random
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts/diagnostics'))
import build_inline_hazard_scanner_r379 as patch


def classify_row(row,code=None):
    code=patch.BODY if code is None else code;pc=0;a=0;de=0;z=c=False;depth=0
    callbacks={}
    for index in range(9):
        prefix=bytes.fromhex('F5 C5 01')+(0x61C6+5*index).to_bytes(2,'little')
        callbacks[code.index(prefix)]=index
    for _ in range(200):
        if pc in callbacks:return callbacks[pc],de,a,depth
        op=code[pc];pc+=1
        if op in (0xC5,0xD5,0xE5):depth+=1
        elif op==0x13:de+=1
        elif op==0x1C:de+=1;z=(de&255)==0
        elif op==0x1A:a=row[de]
        elif op==0xE6:a &= code[pc];pc+=1;z=a==0;c=False
        elif op==0xD6:
            n=code[pc];pc+=1;c=a<n;a=(a-n)&255;z=a==0
        elif op==0xFE:
            n=code[pc];pc+=1;z=a==n;c=a<n
        elif op in (0xCA,0xDA):
            target=int.from_bytes(code[pc:pc+2],'little')-0x6C80;pc+=2
            if (op==0xCA and z) or (op==0xDA and c):pc=target
        elif op==0xE1:return None # reached original no-match row advancement
        else:raise AssertionError(hex(op))
    raise AssertionError('scanner did not finish row')


def original_predicate(row):
    for index,col in enumerate(patch.COLS):
        value=row[col]
        if col==4 and value==0x6A:return index,col,value,3
        folded=((value&0xEF)-0x64)&255
        if folded<6:return index,col,folded,3
    return None


class ScannerTests(unittest.TestCase):
    def test_all_tile_values_at_all_probe_positions(self):
        for col in patch.COLS:
            for value in range(256):
                row=[0]*24;row[col]=value
                self.assertEqual(classify_row(row),original_predicate(row))
        rng=random.Random(379)
        for _ in range(1000):
            row=[rng.randrange(256) for _ in range(24)]
            self.assertEqual(classify_row(row),original_predicate(row))

    def test_bridges_restore_both_register_pairs_and_old_row_tail(self):
        source=patch.BASE.read_bytes();rom=patch.build(source)
        for index,target in enumerate(patch.TARGETS):
            start=patch.offset(19,0x61C6+index*5)
            self.assertEqual(rom[start:start+5],bytes.fromhex('C1 F1 C3')+target.to_bytes(2,'little'))
        start=patch.offset(19,0x61F6)
        self.assertEqual(rom[start:patch.offset(19,0x620E)],source[start:patch.offset(19,0x620E)])
        for bank in (19,24):
            start=patch.offset(bank,0x61BC)
            self.assertEqual(rom[start:start+len(patch.STUB)],patch.STUB)
        self.assertEqual(rom[0x1188:0x118B],bytes.fromhex('CB BF C9'))


if __name__=='__main__':unittest.main()
