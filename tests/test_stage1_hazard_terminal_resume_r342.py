from __future__ import annotations

import hashlib
from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
DIAGNOSTICS = ROOT / "scripts/diagnostics"
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(DIAGNOSTICS))

import build_stage1_hazard_terminal_resume_r342 as r342  # noqa: E402


class Stage1HazardTerminalResumeR342Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        if not r342.BASE.is_file() or not r342.BASE_RECEIPT.is_file():
            raise unittest.SkipTest("exact r341 build fixtures are absent from repo tmp/")
        cls.base = r342.BASE.read_bytes()
        cls.candidate, cls.receipt = r342.build(
            cls.base,
            r342.BASE_RECEIPT.read_bytes(),
        )

    def test_build_is_exactly_derived_from_r341(self) -> None:
        self.assertEqual(hashlib.sha256(self.base).hexdigest(), r342.BASE_SHA256)
        self.assertEqual(
            hashlib.sha256(self.candidate).hexdigest(),
            r342.R342_SHA256,
        )
        self.assertEqual(self.receipt["candidate_sha256"], r342.R342_SHA256)
        self.assertTrue(self.receipt["nonmatching_cells_preserved"])

    def test_conditional_helper_and_call_stream_are_installed(self) -> None:
        helper = r342.patch_helper()
        helper_offset = r342.bank31_offset(r342.PATCH_HELPER_ADDR)
        self.assertEqual(
            self.candidate[helper_offset:helper_offset + len(helper)],
            helper,
        )
        stream = r342.terminal_repair_stream()
        self.assertEqual(
            stream.count(r342.PATCH_HELPER_ADDR.to_bytes(2, "little")),
            8,
        )

    def test_model_repairs_only_exact_terminal_cells(self) -> None:
        tiles = bytearray(0x800)
        attrs = bytearray([6] * 0x800)
        expected_indexes = set()
        for address, tile in r342.TERMINAL_CELLS:
            map_index = 0 if address < 0x9C00 else 1
            offset = address - (0x9800 if map_index == 0 else 0x9C00)
            index = map_index * 0x400 + offset
            tiles[index] = tile
            expected_indexes.add(index)
        repaired = r342.repair_attr_model(bytes(tiles), bytes(attrs))
        changed = {index for index, pair in enumerate(zip(attrs, repaired)) if pair[0] != pair[1]}
        self.assertEqual(changed, expected_indexes)
        self.assertTrue(all(repaired[index] == 5 for index in expected_indexes))

    def test_model_preserves_nonmatching_wall_capture(self) -> None:
        tiles = bytes([0x02] * 0x800)
        attrs = bytes([6] * 0x800)
        self.assertEqual(r342.repair_attr_model(tiles, attrs), attrs)

    def test_runtime_lut_migration_is_exactly_four_entries(self) -> None:
        lut = bytearray(range(0x100))
        before = bytes(lut)
        migrated = r342.repair_runtime_lut_model(before)
        changed = {
            index for index, pair in enumerate(zip(before, migrated))
            if pair[0] != pair[1]
        }
        self.assertEqual(changed, set(r342.RUNTIME_LUT_TILES))
        self.assertTrue(all(migrated[tile] == 5 for tile in changed))


if __name__ == "__main__":
    unittest.main()
