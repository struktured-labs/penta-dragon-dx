from __future__ import annotations

import importlib.util
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "scripts/diagnostics/verify_story_attr_production.py"
SPEC = importlib.util.spec_from_file_location("story_attr", MODULE_PATH)
assert SPEC and SPEC.loader
story_attr = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(story_attr)


class StoryAttrCramEquivalenceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.expected = bytes(range(64))

    def matches(
        self,
        actual: bytes,
        kind: str,
        palette: int,
        mask: str = "",
    ) -> bool:
        return story_attr.referenced_cram_matches(
            actual.hex(), self.expected.hex(), kind, palette, mask
        )

    def test_exact_deck_matches(self) -> None:
        self.assertTrue(self.matches(self.expected, "story", 1, "15" * 80))

    def test_story_ignores_only_unreferenced_rows(self) -> None:
        actual = bytearray(self.expected)
        actual[2 * 8:5 * 8] = bytes(24)
        actual[7 * 8:8 * 8] = bytes(8)
        self.assertTrue(self.matches(actual, "story", 1, "15" * 80))

    def test_story_rejects_mask_palette_mismatch(self) -> None:
        actual = bytearray(self.expected)
        actual[5 * 8] ^= 0xFF
        self.assertFalse(self.matches(actual, "story", 1, "15" * 80))

    def test_story_rejects_dialogue_bg0_mismatch(self) -> None:
        actual = bytearray(self.expected)
        actual[0] ^= 0xFF
        self.assertFalse(self.matches(actual, "story", 1, "15" * 80))

    def test_ending_requires_only_selected_uniform_row(self) -> None:
        actual = bytearray(64)
        actual[3 * 8:4 * 8] = self.expected[3 * 8:4 * 8]
        self.assertTrue(self.matches(actual, "ending", 3))
        actual[3 * 8] ^= 0xFF
        self.assertFalse(self.matches(actual, "ending", 3))

    def test_malformed_cram_is_rejected(self) -> None:
        self.assertFalse(story_attr.referenced_cram_matches(
            "GG", self.expected.hex(), "ending", 1, ""
        ))
        self.assertFalse(story_attr.referenced_cram_matches(
            bytes(63).hex(), self.expected.hex(), "ending", 1, ""
        ))


if __name__ == "__main__":
    unittest.main()
