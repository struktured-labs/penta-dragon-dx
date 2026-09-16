"""Deterministic build and inheritance tests for ending handoff r527."""

from __future__ import annotations

import hashlib
from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts/diagnostics"))
import compose_ending_bgp_handoff_r518 as base_builder
import compose_ending_bgp_handoff_r524 as parent_builder
import compose_ending_bgp_handoff_r527 as ending
from arena_palette_storage import arena_palette_table
from generate_stream_boss_states import relocated_ted_latches


EXPECTED_SHA256 = (
    "13beaa1b0867dc71153538531838e00c101b355c2b3bdb8823184784ea78cc6b"
)
EXPECTED_RETRY = bytes.fromhex(
    "F0 41 E6 03 FE 02 30 F8 "
    "3E FE E0 68 E5 3E 07 D7 2B "
    "2A E0 69 2A E0 69 E1 C9"
)


class EndingBgpHandoffR527(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not base_builder.BASE.is_file():
            raise unittest.SkipTest("retained exact r475 base is unavailable")
        cls.source = base_builder.BASE.read_bytes()
        cls.parent, _ = parent_builder.build(cls.source)
        cls.candidate, cls.receipt = ending.build(cls.source)
        _r518_candidate, r518_receipt = base_builder.build(cls.source)
        cls.labels = {
            name: int(address, 16)
            for name, address in r518_receipt["labels"].items()
        }

    def test_exact_identity_and_retained_output(self) -> None:
        self.assertEqual(hashlib.sha256(self.candidate).hexdigest(), EXPECTED_SHA256)
        self.assertEqual(self.receipt["candidate_sha256"], EXPECTED_SHA256)
        self.assertEqual(self.receipt["parent_sha256"], ending.PARENT_SHA256)
        self.assertEqual(self.receipt["final_color_retry_len"], 25)
        self.assertFalse(self.receipt["promotable"])
        retained = ending.OUT / "candidate.gb"
        self.assertTrue(retained.is_file())
        self.assertEqual(retained.read_bytes(), self.candidate)

    def test_exact_parent_delta_is_bounded(self) -> None:
        retry = self.labels["copy_repeat_retry_last_wait"]
        retry_offset = base_builder.off(base_builder.CAVE_BANK, retry)
        cave_offset = base_builder.off(
            base_builder.CAVE_BANK, ending.FINAL_COLOR_RETRY
        )
        allowed = set(range(0x14D, 0x150))
        allowed.update(range(retry_offset, retry_offset + 3))
        allowed.update(range(cave_offset, cave_offset + len(EXPECTED_RETRY)))
        changed = {
            index for index, (before, after) in enumerate(
                zip(self.parent, self.candidate)
            ) if before != after
        }
        self.assertEqual(len(changed), 30)
        self.assertLessEqual(changed, allowed)
        self.assertEqual(
            changed,
            {int(value, 16) for value in self.receipt["changed_from_parent"]},
        )

    def test_retry_is_exact_and_interrupt_neutral(self) -> None:
        retry = self.labels["copy_repeat_retry_last_wait"]
        retry_offset = base_builder.off(base_builder.CAVE_BANK, retry)
        self.assertEqual(
            self.candidate[retry_offset:retry_offset + 3],
            bytes((0xC3, ending.FINAL_COLOR_RETRY & 0xFF,
                   ending.FINAL_COLOR_RETRY >> 8)),
        )
        cave_offset = base_builder.off(
            base_builder.CAVE_BANK, ending.FINAL_COLOR_RETRY
        )
        self.assertEqual(
            self.parent[cave_offset:cave_offset + len(EXPECTED_RETRY)],
            bytes((0xFF,)) * len(EXPECTED_RETRY),
        )
        self.assertEqual(
            self.candidate[cave_offset:cave_offset + len(EXPECTED_RETRY)],
            EXPECTED_RETRY,
        )
        self.assertNotIn(0xF3, EXPECTED_RETRY)
        self.assertNotIn(0xFB, EXPECTED_RETRY)

    def test_r524_handoff_and_global_fade_are_untouched(self) -> None:
        call = slice(
            parent_builder.EPILOGUE_PRE_FADE_RESET_CALL,
            parent_builder.EPILOGUE_PRE_FADE_RESET_CALL + 3,
        )
        self.assertEqual(self.candidate[call], self.parent[call])
        self.assertEqual(self.candidate[call], bytes.fromhex("CD 89 42"))
        self.assertEqual(self.candidate[0x0F5A:0x0F66], self.parent[0x0F5A:0x0F66])

    def test_all_arena_tables_and_ted_latches_are_inherited(self) -> None:
        for target in range(9):
            self.assertEqual(
                arena_palette_table(self.candidate, target),
                arena_palette_table(self.parent, target),
            )
        self.assertTrue(relocated_ted_latches(self.candidate))

    def test_exact_base_mutations_reject(self) -> None:
        for offset in (0x14F, base_builder.off(20, base_builder.BODY)):
            damaged = bytearray(self.source)
            damaged[offset] ^= 1
            with self.assertRaises(ValueError):
                ending.build(bytes(damaged))


if __name__ == "__main__":
    unittest.main()
