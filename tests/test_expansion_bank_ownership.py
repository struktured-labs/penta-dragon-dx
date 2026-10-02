"""Reconstruction never learns its expectations from the candidate."""
import hashlib
from functools import wraps
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'scripts'),str(ROOT/'scripts/diagnostics')]
import expansion_bank_ownership_r456 as ownership
import compose_attract_blank_r456d as build


class ExpansionOwnership(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rom=build.build(build.BASE.read_bytes())
        cls.images=ownership.owned_banks()

    def test_exact_source_reconstruction_including_padding(self):
        report=ownership.inspect_tail(self.rom)
        self.assertTrue(report['exact'])
        self.assertEqual(len(report['banks']),11)
        for bank,image in self.images.items():
            self.assertEqual(image,self.rom[bank*16384:(bank+1)*16384])

    def test_each_bank_rejects_code_and_padding_corruption(self):
        for bank,image in self.images.items():
            occupied=next(i for i,v in enumerate(image) if v!=255)
            padding=next(i for i,v in enumerate(image) if v==255)
            for offset in {0,16383,occupied,padding,0x2C80}:
                mutant=bytearray(self.rom);mutant[bank*16384+offset]^=1
                report=ownership.inspect_tail(mutant)
                self.assertFalse(report['exact'])
                self.assertFalse(report['banks'][str(bank)]['exact'])

    def test_bank18_requires_both_service_and_entry(self):
        self.assertTrue(ownership.inspect_bank18(self.rom)['exact'])
        for offset in [0x416C,0x4175,18*16384,19*16384-1]+list(range(18*16384+0x2C80,18*16384+0x2C80+len(build.service()))):
            mutant=bytearray(self.rom);mutant[offset]^=1
            self.assertFalse(ownership.inspect_bank18(mutant)['exact'])

    def test_pinned_replay_rejects_changed_builder_output(self):
        import expansion_bank31_r455 as replay
        import build_stage1_live_menu_selector_r290 as first
        original=first.build
        @wraps(original)
        def corrupt(*args):
            result=original(*args)
            if isinstance(result,tuple):
                payload=bytearray(result[0]);payload[-1]^=1
                return (bytes(payload),*result[1:])
            payload=bytearray(result);payload[-1]^=1
            return bytes(payload)
        with patch.object(first,'build',corrupt):
            with self.assertRaises(replay.Drift): replay.expected_bank31()

    def test_truncated_rom_rejected(self):
        self.assertFalse(ownership.inspect_tail(self.rom[:-1])['exact'])
