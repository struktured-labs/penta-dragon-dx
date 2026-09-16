from __future__ import annotations

import hashlib
from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "scripts/diagnostics"), str(ROOT / "scripts")]

import compose_r534_reserved_gold as overlay  # noqa: E402
from verify_stage1_spike_palettes import (  # noqa: E402
    publication_boundary,
    semantic_expansion_is_exact,
)


class R534ReservedGoldTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.source = overlay.DEFAULT_BASE.read_bytes()
        cls.native = overlay.NATIVE_ROM.read_bytes()
        cls.result, cls.report = overlay.build(cls.source, cls.native)

    def test_exact_candidate_is_deterministic(self) -> None:
        second, second_report = overlay.build(self.source, self.native)
        self.assertEqual(second, self.result)
        self.assertEqual(second_report, self.report)
        self.assertEqual(
            hashlib.sha256(self.result).hexdigest(),
            overlay.CANDIDATE_SHA256,
        )
        self.assertEqual(self.report["candidate_sha256"],
                         overlay.CANDIDATE_SHA256)
        self.assertFalse(self.report["promotable"])
        self.assertFalse(self.report["visual_equivalence_retained"])
        self.assertIn("menu_window_publish_order",
                      self.report["rejected_by"])

    def test_only_art_mirror_palette_and_checksums_change(self) -> None:
        changed = {
            index for index, (before, after) in enumerate(
                zip(self.source, self.result)
            ) if before != after
        }
        self.assertTrue(changed)
        self.assertLessEqual(changed, overlay.owned_offsets())
        self.assertFalse(self.report["runtime_code_changed"])

    def test_reserved_art_and_gold_are_exact(self) -> None:
        low = self.result[
            overlay.STAGE1_LOW_TILE_GFX_OFFSET:
            overlay.STAGE1_LOW_TILE_GFX_OFFSET + overlay.TILE_HALF_SIZE
        ]
        high = self.result[
            overlay.HIGH_TILE_START:
            overlay.HIGH_TILE_START + overlay.TILE_HALF_SIZE
        ]
        self.assertEqual(hashlib.sha256(low).hexdigest(),
                         overlay.RESERVED_LOW_SHA256)
        self.assertEqual(hashlib.sha256(high).hexdigest(),
                         overlay.RESERVED_HIGH_SHA256)
        self.assertEqual(
            self.result[
                overlay.BG0_COLOR1_OFFSET:overlay.BG0_COLOR1_OFFSET + 2
            ],
            bytes.fromhex("FF 03"),
        )
        neutral_art = self.result[
            overlay.NEUTRAL_ART_OFFSET:
            overlay.NEUTRAL_ART_OFFSET + overlay.NEUTRAL_ART_SIZE
        ]
        self.assertEqual(
            hashlib.sha256(neutral_art).hexdigest(),
            overlay.RESERVED_NEUTRAL_ART_SHA256,
        )

    def test_runtime_and_later_stage_payload_are_byte_exact_r534(self) -> None:
        owned = overlay.owned_offsets()
        for index in range(len(self.source)):
            if index not in owned:
                self.assertEqual(self.result[index], self.source[index])

    def test_exact_candidate_has_reviewed_publication_identity(self) -> None:
        self.assertEqual(
            publication_boundary(self.result)["variant"],
            "r534-reserved-gold-mirror-c67cea34",
        )
        self.assertTrue(semantic_expansion_is_exact(self.result))
        changed = bytearray(self.result)
        changed[overlay.STAGE1_LOW_TILE_GFX_OFFSET] ^= 1
        with self.assertRaisesRegex(RuntimeError, "no reviewed"):
            publication_boundary(bytes(changed))

    def test_unknown_inputs_are_rejected(self) -> None:
        mutant = bytearray(self.source)
        mutant[0x200] ^= 1
        with self.assertRaisesRegex(ValueError, "exact r534"):
            overlay.build(bytes(mutant), self.native)
        mutant_native = bytearray(self.native)
        mutant_native[0x200] ^= 1
        with self.assertRaisesRegex(ValueError, "exact native"):
            overlay.build(self.source, bytes(mutant_native))


if __name__ == "__main__":
    unittest.main()
