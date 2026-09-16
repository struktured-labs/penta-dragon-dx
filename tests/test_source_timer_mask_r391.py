"""The source wrapper must retain only Timer IE and restore caller state."""
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts/diagnostics'))
import build_source_timer_mask_r391 as builder
from test_menu_timer_wait_r369 import execute


class SourceTimerTests(unittest.TestCase):
    def test_mask_and_restore_all_ie_values(self):
        candidate = builder.build(builder.BASE.read_bytes())
        code = candidate[0x1399:0x1399+len(builder.TRAMPOLINE)+1]
        prefix = code[:8]
        suffix = code[code.index(0xEF)+1:]
        for ie in range(256):
            for flags in range(0, 256, 16):
                _, _, bc, masked, ime, stack = execute(prefix, 0, 0, 0x1234, ie, [0x6EE3])
                self.assertEqual(masked, ie & 4)
                self.assertFalse(ime)  # no forced EI in this wrapper
                a, f, bc, restored, _, stack = execute(suffix, 0x56, flags, bc, masked, stack)
                self.assertEqual((a, f, bc, restored, stack), (0x56, flags, 0x1234, ie, []))


if __name__ == '__main__':
    unittest.main()
