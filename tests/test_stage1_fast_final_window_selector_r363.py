from __future__ import annotations

import hashlib
from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
DIAGNOSTICS = SCRIPTS / "diagnostics"
sys.path.insert(0, str(SCRIPTS))
sys.path.insert(0, str(DIAGNOSTICS))

import build_stage1_fast_final_window_selector_r363 as r363  # noqa: E402
from stage_card_palette_handoff import (  # noqa: E402
    VBLANK_ATOMIC_WINDOW_FAST_COMMIT,
    VBLANK_ATOMIC_WINDOW_FAST_FINAL_COMMIT,
    inspect_stage_card_palette_handoff,
)


SELECTOR_BITS = 0x48


def commit_absolute_selector(lcdc: int, target: int) -> int:
    """Model r363's absolute selector transaction at LCDC.3/LCDC.6."""
    bg_mask = (target & 0x04) << 1
    paired_mask = bg_mask if bg_mask else 0x40
    return (lcdc & ~SELECTOR_BITS) | paired_mask


class FastFinalWindowSelectorTests(unittest.TestCase):
    def test_exact_builder_is_deterministic_and_hash_bound(self) -> None:
        source = r363.BASE.read_bytes()
        receipt = r363.BASE_RECEIPT.read_bytes()
        first, first_receipt = r363.build(source, receipt)
        second, second_receipt = r363.build(source, receipt)

        self.assertEqual(first, second)
        self.assertEqual(first_receipt, second_receipt)
        self.assertEqual(
            hashlib.sha256(first).hexdigest(),
            r363.EXPECTED_CANDIDATE_SHA256,
        )
        inspection = inspect_stage_card_palette_handoff(first)
        self.assertEqual(
            inspection["variant"], "vblank-atomic-window-fast-final-v9"
        )
        self.assertTrue(
            inspection["vblank_atomic_window_fast_final_installed"]
        )

    def test_absolute_path_retests_zero_after_rlca(self) -> None:
        corrected = bytes.fromhex("E6 04 07 B7 20 02 3E 40 47")
        broken = bytes.fromhex("E6 04 07 20 02 3E 40 47")

        self.assertIn(corrected, VBLANK_ATOMIC_WINDOW_FAST_FINAL_COMMIT)
        self.assertIn(broken, VBLANK_ATOMIC_WINDOW_FAST_COMMIT)
        self.assertNotIn(corrected, VBLANK_ATOMIC_WINDOW_FAST_COMMIT)

    def test_absolute_and_relative_paths_preserve_opposite_selectors(self) -> None:
        for lcdc in range(0x100):
            for target in (0x00, 0x04):
                committed = commit_absolute_selector(lcdc, target)
                self.assertEqual(
                    committed & SELECTOR_BITS,
                    0x40 if target == 0 else 0x08,
                )
                self.assertNotEqual(
                    bool(committed & 0x08), bool(committed & 0x40)
                )

                toggled = committed ^ SELECTOR_BITS
                self.assertNotEqual(
                    bool(toggled & 0x08), bool(toggled & 0x40)
                )
                self.assertEqual(toggled ^ SELECTOR_BITS, committed)


if __name__ == "__main__":
    unittest.main()
