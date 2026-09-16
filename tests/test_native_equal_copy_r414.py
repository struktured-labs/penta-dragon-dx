from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts/diagnostics'))
import build_native_equal_copy_r414 as b

class EqualCopyTests(unittest.TestCase):
    def test_scope_stack_restore_and_native_destination(self):
        source=b.BASE.read_bytes();rom=b.build(source)
        self.assertEqual(rom[0x13CD:0x13D1],bytes.fromhex('F1 C3 DE 13'))
        self.assertEqual(rom[0x13DE:0x13E4],bytes.fromhex('11 A0 C1 C3 BB 42'))
        self.assertEqual(rom[0x42BB:0x42C3],bytes.fromhex('3E 18 F5 0E 06 C3 30 43'))
        allowed={0x13CE,0x13CF,0x13D0,0x14D,0x14E,0x14F}
        self.assertTrue(all(x==y or i in allowed for i,(x,y) in enumerate(zip(source,rom))))
        from verify_stage1_spike_palettes import publication_boundary
        self.assertEqual(publication_boundary(rom)['variant'],'r414-native-equal-a377d079')

if __name__=='__main__':unittest.main()
