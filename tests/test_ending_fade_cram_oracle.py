from __future__ import annotations

import importlib.util
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "scripts/diagnostics/analyze_ending_page_discriminators.py"
SPEC = importlib.util.spec_from_file_location("ending_oracle", MODULE_PATH)
assert SPEC and SPEC.loader
ending_oracle = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(ending_oracle)


class EndingFadeCramOracleTests(unittest.TestCase):
    @staticmethod
    def panel(bgp: int, rows: dict[int, bytes]) -> dict:
        state: dict[str, int] = {"bgp": bgp}
        for palette, row in rows.items():
            for offset, value in enumerate(row):
                state[f"bg{palette * 8 + offset:02x}"] = value
        return {"story_state": state}

    def test_exact_referenced_rows_are_proven_hidden(self) -> None:
        row = ending_oracle.dmg_cram_row(0xFF)
        panel = self.panel(0xFF, {0: row, 6: row})
        self.assertTrue(
            ending_oracle.hidden_by_exact_fade_cram(panel, {0: 285, 6: 75})
        )

    def test_unreferenced_rows_do_not_affect_proof(self) -> None:
        row = ending_oracle.dmg_cram_row(0xFE)
        panel = self.panel(0xFE, {1: row, 7: bytes.fromhex("1234") * 4})
        self.assertTrue(
            ending_oracle.hidden_by_exact_fade_cram(panel, {1: 360})
        )

    def test_corrupt_referenced_row_fails_closed(self) -> None:
        row = bytearray(ending_oracle.dmg_cram_row(0xF9))
        row[-1] ^= 1
        panel = self.panel(0xF9, {3: bytes(row)})
        self.assertFalse(
            ending_oracle.hidden_by_exact_fade_cram(panel, {3: 360})
        )

    def test_artistic_or_missing_telemetry_is_never_hidden(self) -> None:
        artistic = self.panel(0xE4, {0: ending_oracle.dmg_cram_row(0xE4)})
        self.assertFalse(
            ending_oracle.hidden_by_exact_fade_cram(artistic, {0: 360})
        )
        self.assertFalse(
            ending_oracle.hidden_by_exact_fade_cram(
                {"story_state": {"bgp": 0xFF}}, {0: 360}
            )
        )

    def test_attribute_alias_requires_byte_exact_cram_rows(self) -> None:
        row0 = bytes.fromhex("ff7f947e4a3d0000")
        state = self.panel(0xE4, {0: row0, 6: row0})["story_state"]
        actual = bytes((6, 2, 7, 0))
        expected = bytes((0, 2, 7, 0))
        self.assertTrue(
            ending_oracle.attributes_visually_match_cram(
                actual, expected, state
            )
        )
        state["bg37"] ^= 1
        self.assertFalse(
            ending_oracle.attributes_visually_match_cram(
                actual, expected, state
            )
        )

    def test_native_fade_cannot_be_excused_by_an_artistic_alias(self) -> None:
        black = ending_oracle.dmg_cram_row(0xFF)
        panel = self.panel(0xFE, {0: black, 1: black})
        self.assertFalse(
            ending_oracle.native_fade_cram_precedence(
                panel, {0: 12, 1: 348}, ordinary_valid=True
            )
        )
        panel = self.panel(
            0xFE, {0: ending_oracle.dmg_cram_row(0xFE)}
        )
        self.assertTrue(
            ending_oracle.native_fade_cram_precedence(
                panel, {0: 360}, ordinary_valid=False
            )
        )


if __name__ == "__main__":
    unittest.main()
