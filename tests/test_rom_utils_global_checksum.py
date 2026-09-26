"""Global checksum excludes the stored bytes at 0x014E-0x014F."""

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts/diagnostics"))
sys.path.insert(0, str(ROOT / "src"))

from penta_dragon_dx.rom_utils import _global_checksum, parse_header
from prototype_ted_expanded_bank import global_checksum


def reference_global_checksum(data: bytes) -> int:
    """Independent 16-bit sum of every ROM byte except 0x014E and 0x014F."""
    total = 0
    for index, byte in enumerate(data):
        if index != 0x014E and index != 0x014F:
            total += byte
    return total & 0xFFFF


def synthetic_rom() -> bytes:
    rom = bytearray(0x200)
    for index in range(len(rom)):
        rom[index] = (index * 17 + 3) & 0xFF
    rom[0x014E] = 0
    rom[0x014F] = 0
    checksum = reference_global_checksum(bytes(rom))
    rom[0x014E] = checksum >> 8
    rom[0x014F] = checksum & 0xFF
    return bytes(rom)


class GlobalChecksumTests(unittest.TestCase):
    def test_excludes_stored_checksum_bytes(self):
        rom = synthetic_rom()
        self.assertNotEqual(rom[0x014E] + rom[0x014F], 0)
        expected = reference_global_checksum(rom)
        self.assertEqual(_global_checksum(rom), expected)
        header = parse_header(rom)
        self.assertEqual(header["global_checksum"], expected)
        self.assertEqual(header["global_checksum_calc"], expected)
        self.assertEqual(_global_checksum(rom), global_checksum(bytearray(rom)))


if __name__ == "__main__":
    unittest.main()
