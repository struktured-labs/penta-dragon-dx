import sys
from pathlib import Path
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts/diagnostics'))
import build_remove_entry_color_seed_r431 as builder


class RemoveSeedTest(unittest.TestCase):
    def test_scope_and_side_effects(self):
        source = builder.BASE.read_bytes()
        result = builder.build(source)
        self.assertEqual(builder.REPLACEMENT,
            bytes.fromhex('3E 05 E0 91 3E FF EA 0D DF AF E0 4F 2F C9'))
        changed = {i for i, (a, b) in enumerate(zip(source, result)) if a != b}
        self.assertLessEqual(changed, set(range(0x355E5, 0x355FB)) | {0x14D, 0x14E, 0x14F})
        # Native scene-service caller immediately overwrites both halves of HL
        # after this helper, so removing the old VRAM pointer has no consumer.
        self.assertIn(bytes.fromhex('CD 33 6A 26 DF 1E 7F 2E'), source[0x34000:0x38000])
        with self.assertRaises(ValueError):
            builder.build(source + b'changed')
