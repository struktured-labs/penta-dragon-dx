from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts/diagnostics'))
import build_native_increment_r416 as b
class IncrementTests(unittest.TestCase):
    def test_every_source_group_and_untouched_fourth_increment(self):
        source=b.BASE.read_bytes();rom=b.build(source)
        for start in range(0xC1A0,0xC3E0,4):
            for n in range(3):
                de=start+n
                self.assertEqual((de&0xFF00)|((de+1)&255),de+1)
        self.assertEqual(rom[0x42D9],0x13)
        # INC E preserves carry; DEC C overwrites other flags before JR NZ.
        self.assertEqual(rom[0x42DB:0x42DF],bytes.fromhex('FB 0D 20 E1'))
        self.assertTrue(all(x==y or i in set(b.SITES)|{0x14D,0x14E,0x14F} for i,(x,y) in enumerate(zip(source,rom))))
    def test_observer_identity_rejects_mutations(self):
        from verify_stage1_spike_palettes import publication_boundary
        rom=b.build(b.BASE.read_bytes())
        self.assertEqual(publication_boundary(rom)['variant'],'r416-native-increment-13f34a8f')
        changed=bytearray(rom);changed[0x42D0]^=1
        with self.assertRaises(RuntimeError):publication_boundary(changed)
if __name__=='__main__':unittest.main()
