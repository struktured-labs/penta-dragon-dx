from pathlib import Path
import sys,unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts/diagnostics'))
import build_skip_equal_tail_r418 as b
class EqualTailTests(unittest.TestCase):
    def test_all_byte_comparisons_preserve_memory_and_dirty_path(self):
        source=b.BASE.read_bytes();rom=b.build(source)
        for new in range(256):
            for old in range(256):
                pc=0x6346C+(rom[0x6346B] if new==old else 0)
                if new==old:
                    self.assertEqual(pc,0x63478)
                    self.assertEqual(rom[pc],0xE1)
                    self.assertEqual(old,new)
                else:
                    self.assertEqual(rom[pc:pc+11],source[pc:pc+11])
        self.assertTrue(all(x==y or i in {0x6346B,0x14D,0x14E,0x14F} for i,(x,y) in enumerate(zip(source,rom))))
if __name__=='__main__':unittest.main()
