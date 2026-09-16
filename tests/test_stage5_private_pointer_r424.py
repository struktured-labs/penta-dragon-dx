import unittest
from test_metatile_pointer_r406 import execute
import build_stage5_private_pointer_r424 as b

class PrivatePointer(unittest.TestCase):
    def test_observer_identity_and_profile_boundaries(self):
        from verify_stage1_spike_palettes import publication_boundary
        from build_six_tile_groups_r405 import service, OFFSET
        rom=b.build(b.BASE.read_bytes())
        self.assertEqual(publication_boundary(rom)['variant'],
                         'r424-stage5-private-pointer-a36469fe')
        self.assertEqual(rom[OFFSET:OFFSET+len(service())],service())
        self.assertEqual(rom[0x3745B:0x37464],bytes.fromhex('AF E0 C4 F0 40 EE 48 E0 40'))
        mutated=bytearray(rom);mutated[0x63814]^=1
        with self.assertRaises(RuntimeError):publication_boundary(mutated)

    def test_clone_scope_and_dispatch(self):
        source=b.BASE.read_bytes();rom=b.build(source)
        self.assertEqual(rom[0x63300:0x6334B],source[0x63300:0x6334B])
        self.assertEqual(rom[0x63800:0x63814],source[0x63300:0x63314])
        self.assertEqual(rom[0x63820:0x6384B],source[0x63320:0x6334B])
        for tile in range(256):
            self.assertEqual(execute(rom[0x63814:0x63820],tile),0xA000+tile*4)
        # Relative loop displacements target the same offsets in the clone.
        for site,target in ((0x37,0x0F),(0x45,0x0D)):
            offset=rom[0x63800+site+1]
            self.assertEqual(site+2+offset-256,target)
        self.assertEqual(b.DISPATCH,bytes.fromhex('F0 BA FE 04 CA 00 78 C3 00 73'))
        allowed={0x14D,0x14E,0x14F}|set(range(0x63089,0x6308C))
        allowed.update(range(0x63380,0x63380+len(b.DISPATCH)))
        allowed.update(range(0x63800,0x6384B))
        self.assertTrue(all(x==y or i in allowed for i,(x,y) in enumerate(zip(source,rom))))
        with self.assertRaises(ValueError):b.build(rom)

if __name__=='__main__':unittest.main()
