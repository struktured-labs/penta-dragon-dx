import unittest
from test_metatile_pointer_r406 import execute
import build_native_pointer_increment_r423 as b

class NativePointer(unittest.TestCase):
    def test_profile_identity_and_addresses(self):
        from verify_stage1_spike_palettes import publication_boundary
        from build_six_tile_groups_r405 import service, OFFSET
        rom=b.build(b.BASE.read_bytes())
        self.assertEqual(publication_boundary(rom)['variant'],
                         'r423-native-pointer-increment-4ba37fda')
        self.assertEqual(rom[OFFSET:OFFSET+len(service())],service())
        self.assertEqual(rom[0x3745B:0x37464],bytes.fromhex('AF E0 C4 F0 40 EE 48 E0 40'))
        mutated=bytearray(rom);mutated[b.SITE]^=1
        with self.assertRaises(RuntimeError):publication_boundary(mutated)

    def test_emitted_pointer_and_scope(self):
        source=b.BASE.read_bytes();rom=b.build(source)
        code=rom[b.SITE:b.SITE+len(b.NEW)]
        for tile in range(256):
            address=execute(code,tile)
            self.assertEqual(address,execute(b.OLD,tile))
            for n in range(3):
                self.assertEqual(address+n+1,
                                 ((address+n)&0xFF00)|((address+n+1)&255))
        allowed=set(range(b.SITE,b.SITE+len(b.NEW)))|{0x14D,0x14E,0x14F}
        self.assertTrue(all(x==y or i in allowed
                            for i,(x,y) in enumerate(zip(source,rom))))
        # HL restored from DE before writes; row ADD HL,DE replaces carry,
        # loop DEC C replaces Z/N/H before any flags-dependent control flow.
        self.assertEqual(rom[0x63320:0x63339],bytes.fromhex(
            '6B 62 0A 0C 22 0A 0C 22 E5 11 16 00 19 0A 0C 22 '
            '0A 77 E1 D1 C1 13 0D 20 D6'))
        with self.assertRaises(ValueError):b.build(rom)

if __name__=='__main__':unittest.main()
