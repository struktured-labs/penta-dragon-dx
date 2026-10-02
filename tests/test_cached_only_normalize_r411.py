import sys
from pathlib import Path
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts/diagnostics'))
import build_cached_only_normalize_r411 as b

class CachedBranchTests(unittest.TestCase):
    def test_exact_identity(self):
        from verify_stage1_spike_palettes import publication_boundary
        rom=b.build(b.BASE.read_bytes())
        self.assertEqual(publication_boundary(rom)['variant'],'r411-cached-only-edfade4e')
        bad=bytearray(rom);bad[0x42C6]^=1
        with self.assertRaises(RuntimeError):publication_boundary(bad)

    def test_branch_destinations_and_native_miss(self):
        rom=b.build(b.BASE.read_bytes())
        native=b.prior.BASE.read_bytes()
        self.assertEqual(rom[0x42FC:0x4303],native[0x42FC:0x4301]+bytes.fromhex('C4 F3'))
        for marker in range(256):
            pc=0x42FC
            self.assertEqual(rom[pc:pc+4],bytes.fromhex('F0 E0 FE 03'))
            pc+=4;self.assertEqual(rom[pc],0x28)
            delta=rom[pc+1];delta=delta if delta<128 else delta-256
            pc+=2
            if marker==3:pc+=delta;self.assertEqual(pc,0x42C6)
            else:self.assertEqual(pc,0x4302);self.assertEqual(rom[pc],0xF3)
        self.assertEqual(rom[0x42CF:0x42FC],native[0x42CF:0x42FC])
        self.assertEqual(rom[0x4303:0x4354],native[0x4303:0x4354])
        self.assertEqual(rom[0x42C6:0x42CF],b.STUB)

if __name__=='__main__':unittest.main()
