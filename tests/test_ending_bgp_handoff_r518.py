"""Deterministic build and patch-boundary tests for ending handoff r518."""

from __future__ import annotations

import hashlib
from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts/diagnostics"))
import compose_ending_bgp_handoff_r518 as ending
from arena_palette_storage import arena_palette_table
from generate_stream_boss_states import relocated_ted_latches


EXPECTED_SHA256 = (
    "918d95a88349aa2bb29c5a52285c79d5dba7a014848e5ccf41bae46890961808"
)


def span(bank: int, address: int, length: int) -> range:
    start = ending.off(bank, address)
    return range(start, start + length)


class EndingBgpHandoffR518(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not ending.BASE.is_file():
            raise unittest.SkipTest("retained exact r475 base is unavailable")
        cls.source = ending.BASE.read_bytes()
        cls.candidate, cls.receipt = ending.build(cls.source)

    def test_exact_identity_and_retained_output(self):
        digest = hashlib.sha256(self.candidate).hexdigest()
        self.assertEqual(digest, EXPECTED_SHA256)
        self.assertEqual(self.receipt["candidate_sha256"], EXPECTED_SHA256)
        self.assertEqual(self.receipt["base_sha256"], ending.BASE_SHA256)
        self.assertEqual(self.receipt["schema"], "penta-ending-bgp-handoff-r518-build-v1")
        self.assertEqual(self.receipt["body_len"], 1851)
        self.assertFalse(self.receipt["promotable"])

        retained = ending.OUT / "candidate.gb"
        self.assertTrue(retained.is_file())
        self.assertEqual(retained.read_bytes(), self.candidate)

    def test_patch_footprint_is_fully_bounded(self):
        allowed: set[int] = set(range(0x14D, 0x150))
        for address in (
            ending.CREDITS_FADE_CALL,
            ending.CREDITS_FADE_OUT_CALL,
            ending.STORY_FADE_OUT_CALL,
            ending.STORY_FADE_IN_JUMP,
            ending.STORY_COMBINED_FADE_OUT_CALL,
            ending.EPILOGUE_COMBINED_FADE_OUT_CALL,
            ending.EPILOGUE_FADE_OUT_CALL,
        ):
            allowed.update(range(address, address + 3))
        allowed.update(range(ending.CREDITS_FADE_WRAPPER, ending.STORY_FADE_WRAPPER + 6))
        allowed.update(span(1, ending.POSTFINAL_SCENE, 6))
        allowed.update(span(20, ending.CREDITS_FADE_BANK20_CONT, 4))
        allowed.update(span(20, ending.STORY_FADE_BANK20_CONT, 4))
        allowed.update(span(20, ending.POSTFINAL_BANK20_ENTRY, 3))
        allowed.update(span(20, ending.BODY, self.receipt["body_len"]))

        for bank in (13, 16):
            allowed.update(span(bank, ending.PALETTE_PUBLISHER, 8))
            allowed.update(span(bank, ending.PALETTE_RESUME_STUB, 4))
            for address, _preimage, _continuation, _entry in ending.SITES.values():
                allowed.update(span(bank, address, 6))
        allowed.update(span(20, ending.PALETTE_BANK20_ENTRY, 3))
        for _name, (_address, _preimage, _continuation, entry) in ending.SITES.items():
            allowed.update(span(20, entry, 3))

        changed = {
            index
            for index, (before, after) in enumerate(zip(self.source, self.candidate))
            if before != after
        }
        self.assertEqual(len(changed), 1934)
        self.assertLessEqual(changed, allowed)
        self.assertEqual(changed, {int(value, 16) for value in self.receipt["changed_offsets"]})

    def test_native_loader_and_global_fade_service_are_untouched(self):
        self.assertEqual(self.candidate[0x0F5A:0x0F66], self.source[0x0F5A:0x0F66])
        for bank in (13, 16):
            loader = ending.off(bank, 0x6900)
            self.assertEqual(
                self.candidate[loader:loader + 6],
                self.source[loader:loader + 6],
            )
            tail = ending.off(bank, ending.PALETTE_QUAD_WRITE)
            self.assertEqual(
                self.candidate[tail:tail + 9],
                self.source[tail:tail + 9],
            )

    def test_all_arena_palette_tables_are_inherited_from_r475(self):
        for target in range(9):
            self.assertEqual(
                arena_palette_table(self.candidate, target),
                arena_palette_table(self.source, target),
            )
        self.assertTrue(relocated_ted_latches(self.source))
        self.assertTrue(relocated_ted_latches(self.candidate))

    def test_private_callers_and_scene_sites_route_to_bank20(self):
        call = bytes((0xCD, ending.CREDITS_FADE_WRAPPER & 0xFF,
                      ending.CREDITS_FADE_WRAPPER >> 8))
        for address in (ending.CREDITS_FADE_CALL, ending.CREDITS_FADE_OUT_CALL):
            self.assertEqual(self.candidate[address:address + 3], call)

        story_call = bytes((0xCD, ending.STORY_FADE_WRAPPER & 0xFF,
                            ending.STORY_FADE_WRAPPER >> 8))
        for address in (
            ending.STORY_FADE_OUT_CALL,
            ending.STORY_COMBINED_FADE_OUT_CALL,
            ending.EPILOGUE_COMBINED_FADE_OUT_CALL,
            ending.EPILOGUE_FADE_OUT_CALL,
        ):
            self.assertEqual(self.candidate[address:address + 3], story_call)
        self.assertEqual(
            self.candidate[ending.STORY_FADE_IN_JUMP:ending.STORY_FADE_IN_JUMP + 3],
            bytes((0xC3, ending.STORY_FADE_WRAPPER & 0xFF,
                   ending.STORY_FADE_WRAPPER >> 8)),
        )

        switch = bytes((0x3E, ending.CAVE_BANK, 0xEA, 0x00, 0x21, 0x00))
        for bank in (13, 16):
            for address, _preimage, _continuation, _entry in ending.SITES.values():
                offset = ending.off(bank, address)
                self.assertEqual(self.candidate[offset:offset + 6], switch)

    def test_exact_base_mutations_reject(self):
        for offset in (0x14F, ending.off(13, 0x6900), ending.off(20, ending.BODY)):
            damaged = bytearray(self.source)
            damaged[offset] ^= 1
            with self.assertRaises(ValueError):
                ending.build(bytes(damaged))


if __name__ == "__main__":
    unittest.main()
