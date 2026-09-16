import sys
from pathlib import Path
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts/diagnostics'))
import build_respawn_entry_colors_r430 as builder


class EntryGuardTest(unittest.TestCase):
    def test_scope_and_branch(self):
        source = builder.BASE.read_bytes()
        result = builder.build(source)
        code = builder.service(source)
        self.assertEqual(code[:4], bytes.fromhex('F0 E1 B7 20'))
        skip = code[5 + code[4]:]
        self.assertEqual(skip, bytes.fromhex('3E 05 E0 91 3E FF EA 0D DF 3E 0D C9'))
        # Respawn branch contains no VRAM store; cold path retains all four
        # original store blocks byte-for-byte, removing only inter-block jumps.
        cold = (source[0x355E5:0x355F8] + source[0x36C30:0x36C3D]
                + source[0x36E70:0x36E7D] + source[0x3560A:0x35628]
                + bytes.fromhex('3E 0D C9'))
        self.assertEqual(code[5:5 + code[4]], cold)
        allowed = set(range(0x355E5, 0x355FB)) | set(range(0x76C80, 0x76C80 + len(code))) | {0x14D, 0x14E, 0x14F}
        self.assertTrue(all(i in allowed for i, (a, b) in enumerate(zip(source, result)) if a != b))
        with self.assertRaises(ValueError):
            builder.build(source + b'changed')
