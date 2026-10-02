import sys
from pathlib import Path
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts/diagnostics'))
import build_stage1_pointer_r407 as b

class IsolatedPointerTests(unittest.TestCase):
    def test_exact_observer_identity(self):
        from verify_stage1_spike_palettes import publication_boundary
        rom=b.build(b.BASE.read_bytes())
        self.assertEqual(publication_boundary(rom)['variant'],'r407-stage1-pointer-1438d4d8')
        changed=bytearray(rom);changed[0x63422]^=1
        with self.assertRaises(RuntimeError):publication_boundary(changed)

    def test_native_fallback_and_predicates_unchanged(self):
        source=b.BASE.read_bytes();rom=b.build(source)
        self.assertEqual(rom[0x63300:0x6334B],source[0x63300:0x6334B])
        self.assertEqual(rom[0x63000:0x63011],source[0x63000:0x63011])
        self.assertEqual(rom[0x63400:0x6340E],source[0x63400:0x6340E])
        allowed={0x14D,0x14E,0x14F}
        for site in b.prior.SITES[1:]:
            allowed.update(range(site,site+12));self.assertEqual(rom[site:site+12],b.prior.NEW)
        self.assertTrue(all(x==y or i in allowed for i,(x,y) in enumerate(zip(source,rom))))

if __name__=='__main__':unittest.main()
