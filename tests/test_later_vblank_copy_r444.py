from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts/diagnostics'))
import build_later_vblank_copy_r444 as builder


class LaterVblankCopyTests(unittest.TestCase):
    def test_exact_patch_and_unchanged_wait_and_write_group(self):
        source = builder.BASE.read_bytes()
        result = builder.build(source)
        self.assertEqual(result[0x4331:0x4336], bytes.fromhex('AF 00 00 00 00'))
        self.assertEqual(result[0x4336:0x4354], source[0x4336:0x4354])
        self.assertEqual(result[0x42CF:0x42ED], source[0x42CF:0x42ED])

    def test_ly_window_excludes_last_two_vblank_lines(self):
        self.assertEqual([ly for ly in range(154) if ly & 0xF8 == 0x90],
                         list(range(144, 152)))

    def test_wrong_source_fails_closed(self):
        source = bytearray(builder.BASE.read_bytes())
        source[0x42CF] ^= 1
        with self.assertRaisesRegex(AssertionError, 'wrong exact'):
            builder.build(source)


if __name__ == '__main__':
    unittest.main()
