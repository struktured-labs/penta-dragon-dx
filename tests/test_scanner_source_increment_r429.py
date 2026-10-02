import sys
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts/diagnostics'))
import build_scanner_source_increment_r429 as b

class ScannerIncrement(unittest.TestCase):
    def test_emitted_predicates(self):
        from test_inline_hazard_scanner_r379 import classify_row,original_predicate
        import random
        code=b.scanner.make_body(fast_source=True)
        for col in b.scanner.COLS:
            for value in range(256):
                row=[0]*24;row[col]=value
                self.assertEqual(classify_row(row,code),original_predicate(row))
        rng=random.Random(429)
        for _ in range(1000):
            row=[rng.randrange(256) for _ in range(24)]
            self.assertEqual(classify_row(row,code),original_predicate(row))

    def test_addresses_flags_and_exact_scope(self):
        for row in range(24):
            start=0xC1A0+24*row
            for col in range(10):
                address=start+col
                self.assertEqual(address+1,(address&0xFF00)|((address+1)&255))
        old=b.scanner.make_body();new=b.scanner.make_body(fast_source=True)
        changes=[i for i,(x,y) in enumerate(zip(old,new)) if x!=y]
        self.assertEqual(len(changes),10)
        for i in changes:
            self.assertEqual((old[i],new[i]),(0x13,0x1C))
            # After any extra step, the next load is followed by a classifier
            # CP or AND: INC E flags cannot reach a conditional branch alive.
            tail=new[i+1:]
            while tail[0]==0x1C:tail=tail[1:]
            self.assertEqual(tail[0],0x1A)
            self.assertIn(tail[1],(0xFE,0xE6))
        source=b.BASE.read_bytes();rom=b.build(source)
        allowed={b.OFFSET+i for i in changes}|{0x14D,0x14E,0x14F}
        self.assertTrue(all(x==y or i in allowed for i,(x,y) in enumerate(zip(source,rom))))
        self.assertEqual(rom[b.OFFSET+len(old)-11:b.OFFSET+len(old)],source[b.OFFSET+len(old)-11:b.OFFSET+len(old)])
        with self.assertRaises(ValueError):b.build(rom)

if __name__=='__main__':unittest.main()
