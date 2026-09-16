from pathlib import Path
import sys
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'scripts/diagnostics'))
import build_metatile_increment_r412 as b


class MetatileIncrementTests(unittest.TestCase):
    def test_all_source_addresses_and_flag_liveness(self):
        source = b.BASE.read_bytes()
        rom = b.build(source)
        for tile in range(256):
            bc = 0xA000 + tile*4
            for n in range(3):
                original = bc + 1
                shortened = (bc & 0xFF00) | ((bc+1) & 255)
                self.assertEqual(original, shortened)
                bc = shortened
        # INC C preserves carry; Z/N/H are overwritten by the next CP,
        # ADD HL,DE, or loop DEC C before a conditional branch. The ADD
        # preserves Z, but the subsequent CP/DEC overwrites it before use.
        tails = ('0ABE', 'E5111600190ABE', '0ABE',
                 '0A220C', 'E5111600190A220C', '0A77E1D1C1130D20')
        for site, tail in zip(b.SITES, tails):
            self.assertEqual(rom[site], 0x0C)
            expected = bytes.fromhex(tail)
            self.assertEqual(rom[site+1:site+1+len(expected)], expected)
        allowed = set(b.SITES) | {0x14D, 0x14E, 0x14F}
        self.assertTrue(all(x == y or i in allowed
                            for i, (x, y) in enumerate(zip(source, rom))))

    def test_wrong_base_rejected(self):
        source = bytearray(b.BASE.read_bytes()); source[0x63422] ^= 1
        with self.assertRaises(ValueError): b.build(source)

    def test_exact_instrumentation_identity(self):
        from verify_stage1_spike_palettes import publication_boundary
        rom = b.build(b.BASE.read_bytes())
        self.assertEqual(publication_boundary(rom)['variant'],
                         'r412-metatile-increment-c558d955')
        mutated = bytearray(rom); mutated[b.SITES[0]] ^= 1
        with self.assertRaises(RuntimeError): publication_boundary(mutated)


if __name__ == '__main__': unittest.main()
