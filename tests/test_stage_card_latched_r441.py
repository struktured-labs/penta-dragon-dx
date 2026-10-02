"""Exact r441 recognition must not admit altered handoff code or unknown ROMs."""
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'scripts'))
import stage_card_palette_handoff as handoff


class LatchedStageCard(unittest.TestCase):
    def test_exact_candidate_and_mutations(self):
        rom = (ROOT/'tmp/stage2-seven-rows-r441/candidate.gb').read_bytes()
        result = handoff.inspect_stage_card_palette_handoff(rom)
        self.assertTrue(result['installed'])
        self.assertEqual(result['variant'], 'vblank-latched-single-art-r441')
        self.assertEqual(result['vblank_commit'], rom[0x373FC:0x37464])
        for offset in (0x4357, handoff.PRIVATE_OFFSET,
                       handoff.STAGE1_ENTRY_GATE_OFFSET+6,
                       handoff.HANDOFF_EXTENSION_OFFSET,
                       0x37403, 0x3745B, 0x3746D, 0x150):
            with self.subTest(offset=offset):
                bad = bytearray(rom)
                bad[offset] ^= 1
                self.assertFalse(handoff.inspect_stage_card_palette_handoff(bad)['installed'])

    def test_previous_guarded_variant_still_recognized(self):
        rom = (ROOT/'tmp/deferred-commit-guard-r374/candidate.gb').read_bytes()
        result = handoff.inspect_stage_card_palette_handoff(rom)
        self.assertTrue(result['installed'])
        self.assertEqual(result['variant'], 'vblank-atomic-window-fast-final-guard-r374')

    def test_r453_runtime_receipted_candidate_is_whole_image_pinned(self):
        rom = (ROOT/'tmp/title-nightfall-port/r443e3f2-v6-r449f/candidate.gb').read_bytes()
        result = handoff.inspect_stage_card_palette_handoff(rom)
        self.assertTrue(result['installed'])
        self.assertEqual(result['variant'], 'runtime-receipted-r453')
        for offset in (0x42BC, handoff.PRIVATE_OFFSET, 0x150):
            with self.subTest(offset=offset):
                bad = bytearray(rom)
                bad[offset] ^= 1
                self.assertFalse(handoff.inspect_stage_card_palette_handoff(bad)['installed'])
