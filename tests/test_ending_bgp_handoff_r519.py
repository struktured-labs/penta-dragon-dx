"""Deterministic build and inheritance tests for ending handoff r519."""

from __future__ import annotations

import hashlib
from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts/diagnostics"))
import compose_ending_bgp_handoff_r518 as parent_builder
import compose_ending_bgp_handoff_r519 as ending
from arena_palette_storage import arena_palette_table
from generate_stream_boss_states import relocated_ted_latches


EXPECTED_SHA256 = (
    "9b368aaef0e48757fb0bfed108e30f20490150f329e78b6001ed0b53fa7f7af9"
)


class EndingBgpHandoffR519(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not parent_builder.BASE.is_file():
            raise unittest.SkipTest("retained exact r475 base is unavailable")
        cls.source = parent_builder.BASE.read_bytes()
        cls.parent, _ = parent_builder.build(cls.source)
        cls.candidate, cls.receipt = ending.build(cls.source)

    def test_exact_identity_and_retained_output(self) -> None:
        self.assertEqual(hashlib.sha256(self.candidate).hexdigest(), EXPECTED_SHA256)
        self.assertEqual(self.receipt["candidate_sha256"], EXPECTED_SHA256)
        self.assertEqual(self.receipt["parent_sha256"], ending.PARENT_SHA256)
        self.assertEqual(self.receipt["extension_len"], 40)
        self.assertFalse(self.receipt["promotable"])
        retained = ending.OUT / "candidate.gb"
        self.assertTrue(retained.is_file())
        self.assertEqual(retained.read_bytes(), self.candidate)

    def test_exact_parent_delta_is_bounded(self) -> None:
        allowed = set(range(0x14D, 0x150))
        allowed.update(range(
            ending.EPILOGUE_PRE_FADE_RESET_CALL,
            ending.EPILOGUE_PRE_FADE_RESET_CALL + 3,
        ))
        for address, length in ((ending.DISPATCH, 8),
                                (ending.EXTENSION, self.receipt["extension_len"])):
            start = parent_builder.off(parent_builder.CAVE_BANK, address)
            allowed.update(range(start, start + length))
        changed = {
            index for index, (before, after) in enumerate(
                zip(self.parent, self.candidate)
            ) if before != after
        }
        self.assertEqual(len(changed), 47)
        self.assertLessEqual(changed, allowed)
        self.assertEqual(
            changed,
            {int(value, 16) for value in self.receipt["changed_from_parent"]},
        )

    def test_native_reset_and_global_fade_are_untouched(self) -> None:
        reset = slice(ending.NATIVE_MONO_RESET, ending.NATIVE_MONO_RESET + 4)
        self.assertEqual(self.candidate[reset], self.parent[reset])
        self.assertEqual(self.candidate[reset], bytes.fromhex("3E FF 18 F5"))
        self.assertEqual(self.candidate[0x0F5A:0x0F66], self.parent[0x0F5A:0x0F66])

    def test_all_arena_tables_and_ted_latches_are_inherited(self) -> None:
        for target in range(9):
            self.assertEqual(
                arena_palette_table(self.candidate, target),
                arena_palette_table(self.parent, target),
            )
        self.assertTrue(relocated_ted_latches(self.candidate))

    def test_exact_base_mutations_reject(self) -> None:
        for offset in (0x14F, parent_builder.off(20, parent_builder.BODY)):
            damaged = bytearray(self.source)
            damaged[offset] ^= 1
            with self.assertRaises(ValueError):
                ending.build(bytes(damaged))


if __name__ == "__main__":
    unittest.main()
