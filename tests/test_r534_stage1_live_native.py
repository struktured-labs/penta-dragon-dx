from __future__ import annotations

import hashlib
from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts/diagnostics"))

import compose_r534_stage1_live_native as overlay  # noqa: E402
from verify_stage1_spike_palettes import publication_boundary  # noqa: E402


class R534Stage1LiveNativeTests(unittest.TestCase):
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
            self.report["candidate_sha256"],
        )

    def test_selector_has_exact_stack_and_bank_route(self) -> None:
        self.assertEqual(
            overlay.build_selector(),
            bytes.fromhex("F0 BA B7 20 10 E1 E8 06 01 F9 42 C5 C3 A7 42"),
        )
        self.assertEqual(
            overlay.build_completion(),
            bytes.fromhex("7C E0 C4 F5 C5 D5 E5 21 A1 03 E5 3E 01 C3 61 00"),
        )

    def test_only_authenticated_ranges_change(self) -> None:
        changed = {
            index for index, pair in enumerate(zip(self.source, self.result))
            if pair[0] != pair[1]
        }
        branch = overlay.bank_offset(
            overlay.SELECTOR_BANK, overlay.MUX_SCENE_BRANCH
        )
        selector = overlay.bank_offset(
            overlay.SELECTOR_BANK, overlay.SELECTOR_ADDR
        )
        clone = overlay.bank_offset(
            overlay.NATIVE_BANK, overlay.NATIVE_ENTRY
        )
        completion = overlay.bank_offset(
            overlay.NATIVE_BANK, overlay.NATIVE_COMPLETION
        )
        allowed = set(overlay.CHECKSUM_OFFSETS)
        allowed.update(range(branch, branch + 2))
        allowed.update(range(selector, selector + len(overlay.build_selector())))
        allowed.update(range(
            clone, clone + overlay.NATIVE_END - overlay.NATIVE_ENTRY
        ))
        allowed.update(range(
            completion, completion + len(overlay.build_completion())
        ))
        allowed.update(range(
            overlay.STAGE1_LOW_TILE_GFX_OFFSET,
            overlay.STAGE1_LOW_TILE_GFX_OFFSET + overlay.STAGE1_TILE_HALF_SIZE,
        ))
        allowed.update(range(
            overlay.STAGE1_HIGH_TILE_GFX_START,
            overlay.STAGE1_HIGH_TILE_GFX_START + overlay.STAGE1_TILE_HALF_SIZE,
        ))
        allowed.update(range(
            overlay.STAGE1_BG0_COLOR1_OFFSET,
            overlay.STAGE1_BG0_COLOR1_OFFSET + 2,
        ))
        self.assertTrue(changed <= allowed)

    def test_reserved_gold_uses_r534_semantic_hazard_art(self) -> None:
        low = self.result[
            overlay.STAGE1_LOW_TILE_GFX_OFFSET:
            overlay.STAGE1_LOW_TILE_GFX_OFFSET + overlay.STAGE1_TILE_HALF_SIZE
        ]
        high = self.result[
            overlay.STAGE1_HIGH_TILE_GFX_START:
            overlay.STAGE1_HIGH_TILE_GFX_START + overlay.STAGE1_TILE_HALF_SIZE
        ]
        self.assertEqual(hashlib.sha256(low).hexdigest(),
                         overlay.STAGE1_RESERVED_LOW_SHA256)
        self.assertEqual(hashlib.sha256(high).hexdigest(),
                         overlay.STAGE1_RESERVED_HIGH_SHA256)
        self.assertEqual(
            self.result[
                overlay.STAGE1_BG0_COLOR1_OFFSET:
                overlay.STAGE1_BG0_COLOR1_OFFSET + 2
            ],
            bytes.fromhex("FF 03"),
        )
        self.assertEqual(self.report["stage1_pickup_art_mode"],
                         "reserved-pickup-gold")

    def test_exact_candidate_has_reviewed_publication_identity(self) -> None:
        self.assertEqual(
            publication_boundary(self.result)["variant"],
            "r534-stage1-native-gold-703c7c1c",
        )
        changed = bytearray(self.result)
        changed[overlay.bank_offset(
            overlay.SELECTOR_BANK, overlay.SELECTOR_ADDR
        )] ^= 1
        with self.assertRaisesRegex(RuntimeError, "no reviewed"):
            publication_boundary(bytes(changed))

    def test_scene0b_and_later_hot_resume_stay_exact(self) -> None:
        for start, end in (
            (0x6CFB, overlay.SELECTOR_ADDR),
            (overlay.HOT_RESUME, 0x6D5C),
        ):
            offset = overlay.bank_offset(overlay.SELECTOR_BANK, start)
            size = end - start
            self.assertEqual(
                self.result[offset:offset + size],
                self.source[offset:offset + size],
            )

    def test_clone_is_native_except_for_restoring_completion(self) -> None:
        clone = overlay.bank_offset(
            overlay.NATIVE_BANK, overlay.NATIVE_ENTRY
        )
        native_copy = self.native[overlay.NATIVE_ENTRY:overlay.NATIVE_END]
        prefix = overlay.NATIVE_COMPLETION - overlay.NATIVE_ENTRY
        self.assertEqual(self.result[clone:clone + prefix], native_copy[:prefix])
        completion = overlay.build_completion()
        self.assertEqual(
            self.result[clone + prefix:clone + prefix + len(completion)],
            completion,
        )

    def test_unknown_base_is_rejected(self) -> None:
        mutant = bytearray(self.source)
        mutant[0x200] ^= 1
        with self.assertRaisesRegex(ValueError, "exact r534"):
            overlay.build(bytes(mutant), self.native)


if __name__ == "__main__":
    unittest.main()
