from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import build_v302_title_fix as build


class Stage5SignatureCadenceTest(unittest.TestCase):
    def test_destination_selector_is_cycle_neutral(self):
        front, _ = build.build_lava_attr_decider()

        # BIT 2,H distinguishes the only legal destination pages ($98/$9C)
        # in two M-cycles.  The previous LD A,H / CP $9C pair took three.
        selector = bytes.fromhex("CB 54 28 02 1E 57")
        self.assertEqual(front[9:15], selector)
        self.assertEqual(len(front), 21)

        selected_e = {}
        for destination_h in (0x98, 0x9C):
            bit_is_zero = not (destination_h & 0x04)
            selected_e[destination_h] = (
                build.LAVA_ATTR_STAGE5_9800_META_ADDR & 0xFF
                if bit_is_zero
                else build.LAVA_ATTR_STAGE5_9C00_META_ADDR & 0xFF
            )
        self.assertEqual(selected_e, {0x98: 0x53, 0x9C: 0x57})

    def test_four_cell_signature_is_unchanged(self):
        signature = build.build_lava_attr_sample_signature(
            build.LAVA_ATTR_STAGE5_SAMPLES,
            build.LAVA_ATTR_STAGE5_SIGNATURE_ADDR,
            build.LAVA_ATTR_STAGE7_SOURCE_B_ADDR,
        )
        self.assertEqual(
            signature,
            bytes.fromhex("FA 50 C3 21 21 C2 AE 2E 69 AE 2E A3 AE 47 C9"),
        )


if __name__ == "__main__":
    unittest.main()
