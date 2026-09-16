"""Closed-set ownership checks for the split arena-cache helper tail."""

from __future__ import annotations

from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from arena_semantic_key import (
    HELPER_BANK,
    TROOP_REPEAT_RAW_TAIL,
    TROOP_REPEAT_RAW_TAIL_ADDR,
    TROOP_REPEAT_RAW_WRITER_POST_PC,
    cache_writer_is_owned,
)


class ArenaCacheWriterOwnershipTests(unittest.TestCase):
    def fixture(self) -> bytearray:
        rom = bytearray([0xFF]) * (32 * 0x4000)
        offset = (
            HELPER_BANK * 0x4000 + TROOP_REPEAT_RAW_TAIL_ADDR - 0x4000
        )
        rom[offset:offset + len(TROOP_REPEAT_RAW_TAIL)] = TROOP_REPEAT_RAW_TAIL
        return rom

    def test_exact_relocated_store_is_owned(self) -> None:
        rom = self.fixture()
        self.assertTrue(cache_writer_is_owned(
            rom, HELPER_BANK, TROOP_REPEAT_RAW_WRITER_POST_PC,
            shalamar_native_exact_class=4,
        ))

    def test_tail_mutation_and_foreign_sites_reject(self) -> None:
        rom = self.fixture()
        offset = (
            HELPER_BANK * 0x4000 + TROOP_REPEAT_RAW_TAIL_ADDR - 0x4000
        )
        rom[offset] ^= 1
        self.assertFalse(cache_writer_is_owned(
            rom, HELPER_BANK, TROOP_REPEAT_RAW_WRITER_POST_PC,
            shalamar_native_exact_class=4,
        ))
        clean = self.fixture()
        self.assertFalse(cache_writer_is_owned(
            clean, HELPER_BANK + 1, TROOP_REPEAT_RAW_WRITER_POST_PC,
            shalamar_native_exact_class=4,
        ))
        self.assertFalse(cache_writer_is_owned(
            clean, HELPER_BANK, TROOP_REPEAT_RAW_WRITER_POST_PC + 1,
            shalamar_native_exact_class=4,
        ))


if __name__ == "__main__":
    unittest.main()
