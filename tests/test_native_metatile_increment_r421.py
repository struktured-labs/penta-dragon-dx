from pathlib import Path
import sys
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts/diagnostics'))
import build_native_metatile_increment_r421 as b

class NativeMetatileIncrement(unittest.TestCase):
    def test_source_addresses_and_scope(self):
        for tile in range(256):
            for n in range(3):
                bc = 0xA000 + 4 * tile + n
                self.assertEqual(bc+1, (bc & 0xFF00) | ((bc+1) & 255))
        source = b.BASE.read_bytes()
        rom = b.build(source)
        allowed = set(b.SITES) | {0x14D, 0x14E, 0x14F}
        self.assertTrue(all(x == y or i in allowed
                            for i, (x, y) in enumerate(zip(source, rom))))
        # Carry is preserved by INC C. Intermediate Z/N/H are dead:
        # third increment follows ADD HL,DE; POP BC then DEC C overwrites
        # Z/N/H before the first conditional branch in the native loop.
        self.assertEqual(rom[0x63322:0x63339], bytes.fromhex(
            '0A 0C 22 0A 0C 22 E5 11 16 00 19 0A 0C 22 '
            '0A 77 E1 D1 C1 13 0D 20 D6'))
        self.assertEqual(rom[0x63314:0x63320], bytes.fromhex(
            '6F 26 00 4C 29 29 01 00 A0 09 4D 44'))
        with self.assertRaises(ValueError): b.build(rom)

if __name__ == '__main__': unittest.main()
