#!/usr/bin/env python3
"""Focused static controls for r300's room-local semantic hazard rows."""

from __future__ import annotations

import hashlib
from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
DIAGNOSTICS = ROOT / "scripts" / "diagnostics"
sys.path.insert(0, str(DIAGNOSTICS))

import build_stage1_room01_contextual_rearm_r299 as r299  # noqa: E402
import build_stage1_room01_semantic_row_r300 as r300  # noqa: E402


EXPECTED_SHA256 = (
    "abc06464cb331fb93da5b7a573374775896306b3aefdbe7908280dea70edf3d7"
)


def sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


class Stage1Room01SemanticRowR300Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.base = r300.BASE.read_bytes()
        cls.base_receipt = r300.BASE_RECEIPT.read_bytes()
        cls.r297_candidate, _ = r300.r297.build(
            cls.base, cls.base_receipt, variant="full"
        )
        cls.candidate, cls.receipt = r300.build(
            cls.base, cls.base_receipt
        )

    def test_candidate_identity_checksums_and_exact_base_chain(self) -> None:
        self.assertEqual(sha256(self.candidate), EXPECTED_SHA256)
        self.assertEqual(self.receipt["candidate_sha256"], EXPECTED_SHA256)
        self.assertEqual(self.receipt["base_sha256"], r300.r297.BASE_SHA256)
        self.assertEqual(
            self.receipt["r297_generated_sha256"],
            sha256(self.r297_candidate),
        )
        self.assertFalse(self.receipt["promotable"])
        header = 0
        for value in self.candidate[0x0134:0x014D]:
            header = (header - value - 1) & 0xFF
        self.assertEqual(self.candidate[0x014D], header)
        total = (
            sum(self.candidate[:0x014E])
            + sum(self.candidate[0x0150:])
        ) & 0xFFFF
        self.assertEqual(
            int.from_bytes(self.candidate[0x014E:0x0150], "big"), total
        )

    def test_r299_cannot_change_the_bank20_semantic_writes(self) -> None:
        candidate, _ = r299.build(self.base, self.base_receipt)
        bank_start = r300.SEMANTIC_BANK * r300.r297.BANK_SIZE
        bank_end = bank_start + r300.r297.BANK_SIZE
        self.assertEqual(
            candidate[bank_start:bank_end], self.base[bank_start:bank_end]
        )
        lookup = r300.semantic.bank_offset(
            r300.SEMANTIC_BANK, r300.PRIMARY_HELPER_ADDR + 0x63
        )
        self.assertEqual(
            candidate[lookup:lookup + 7],
            bytes.fromhex("E5 6F 26 44 7E E1 C9"),
        )
        lut = r300.semantic.bank_offset(
            r300.SEMANTIC_BANK, r300.PRIMARY_LUT_ADDR
        )
        self.assertEqual(
            {tile: candidate[lut + tile] for tile in r300.TARGET_TILES},
            {tile: 0x00 for tile in r300.TARGET_TILES},
        )

    def test_every_semantic_return_dispatches_once_on_ffbd(self) -> None:
        for address in r300.TRAMPOLINE_ADDRS:
            with self.subTest(address=f"{address:04X}"):
                offset = r300.semantic.bank_offset(
                    r300.SEMANTIC_BANK, address
                )
                self.assertEqual(
                    self.candidate[
                        offset:offset + len(r300.CONTEXT_TRAMPOLINE)
                    ],
                    r300.CONTEXT_TRAMPOLINE,
                )
        self.assertEqual(
            r300.CONTEXT_TRAMPOLINE,
            bytes.fromhex("F0 BD 3D C2 00 43 C3 00 45"),
        )
        cycles = self.receipt["offline_contract"]["trampoline_t_cycles"]
        self.assertEqual(
            cycles,
            {
                "r292": 16,
                "r300_room01": 44,
                "r300_other_room": 32,
                "room01_delta_per_published_row": 28,
                "other_room_delta_per_published_row": 16,
            },
        )

    def test_room01_helper_keeps_exact_inner_instruction_cadence(self) -> None:
        primary = r300.semantic.build_helper()
        clone = r300.build_room01_helper(primary)
        self.assertEqual(len(primary), len(clone))
        differences = {
            index for index, pair in enumerate(zip(primary, clone, strict=True))
            if pair[0] != pair[1]
        }
        self.assertEqual(len(differences), 5)
        for index in differences:
            self.assertIn((primary[index], clone[index]), {
                (0x43, 0x45),
                (0x44, 0x46),
            })
        room_helper = r300.semantic.bank_offset(
            r300.SEMANTIC_BANK, r300.ROOM01_HELPER_ADDR
        )
        self.assertEqual(
            self.candidate[room_helper:room_helper + len(clone)], clone
        )
        # The LCD-off guard, mode3->mode0 waits, VBK writes, and bank return
        # are opcodes/relative branches and therefore byte-exact in the clone.
        for sequence in (
            bytes.fromhex("F0 40 CB 7F"),
            bytes.fromhex("F0 41 E6 03 FE 03 20 F8"),
            bytes.fromhex("F0 41 E6 03 20 FA"),
            bytes.fromhex("AF E0 4F C3 DF 6C"),
        ):
            self.assertIn(sequence, primary)
            self.assertIn(sequence, clone)
        self.assertTrue(
            self.receipt["offline_contract"]
            ["per_cell_opcodes_and_t_cycles_exact"]
        )
        scanner_entry = r300.r297.bank_offset(r300.r297.ROW_BANK, 0x6BE3)
        self.assertEqual(
            self.candidate[scanner_entry:scanner_entry + 4],
            bytes.fromhex("F3 AF E0 4F"),
        )
        self.assertTrue(
            self.receipt["offline_contract"]
            ["scanner_entry_DI_and_VBK0_exact"]
        )

    def test_only_four_room01_lut_entries_change_and_room05_stays_exact(self) -> None:
        primary_offset = r300.semantic.bank_offset(
            r300.SEMANTIC_BANK, r300.PRIMARY_LUT_ADDR
        )
        room_offset = r300.semantic.bank_offset(
            r300.SEMANTIC_BANK, r300.ROOM01_LUT_ADDR
        )
        primary = self.candidate[primary_offset:primary_offset + 0x100]
        room = self.candidate[room_offset:room_offset + 0x100]
        differences = {
            index for index, pair in enumerate(zip(primary, room, strict=True))
            if pair[0] != pair[1]
        }
        self.assertEqual(differences, set(r300.TARGET_TILES))
        for tile in range(0x100):
            with self.subTest(tile=f"{tile:02X}"):
                expected_room01 = (
                    0x06 if tile in r300.TARGET_TILES else primary[tile]
                )
                self.assertEqual(
                    r300.semantic_attr(1, tile, primary), expected_room01
                )
                self.assertEqual(
                    r300.semantic_attr(5, tile, primary), primary[tile]
                )
        for tile in r300.semantic.TOOTH_TILES:
            self.assertEqual(primary[tile], 0x0F)
            self.assertEqual(room[tile], 0x0F)

    def test_original_helper_lut_bank14_and_bank21_semantic_delta_are_exact(self) -> None:
        primary_helper = r300.semantic.bank_offset(
            r300.SEMANTIC_BANK, r300.PRIMARY_HELPER_ADDR
        )
        helper_width = len(r300.semantic.build_helper())
        self.assertEqual(
            self.candidate[primary_helper:primary_helper + helper_width],
            self.base[primary_helper:primary_helper + helper_width],
        )
        primary_lut = r300.semantic.bank_offset(
            r300.SEMANTIC_BANK, r300.PRIMARY_LUT_ADDR
        )
        self.assertEqual(
            self.candidate[primary_lut:primary_lut + 0x100],
            self.base[primary_lut:primary_lut + 0x100],
        )
        bank14 = slice(
            14 * r300.r297.BANK_SIZE, 15 * r300.r297.BANK_SIZE
        )
        bank21 = slice(
            21 * r300.r297.BANK_SIZE, 22 * r300.r297.BANK_SIZE
        )
        self.assertEqual(self.candidate[bank14], self.base[bank14])
        self.assertEqual(self.candidate[bank21], self.r297_candidate[bank21])
        self.assertEqual(
            self.receipt["ownership"]["bank21_semantic_delta_bytes"], 0
        )

    def test_static_preimage_mutations_fail_closed(self) -> None:
        mutants: list[tuple[str, bytearray]] = []

        trampoline = bytearray(self.base)
        trampoline[
            r300.semantic.bank_offset(
                r300.SEMANTIC_BANK, r300.TRAMPOLINE_ADDRS[0]
            ) + 3
        ] = 0x00
        mutants.append(("trampoline padding", trampoline))

        active_lut = bytearray(self.base)
        active_lut[
            r300.semantic.bank_offset(
                r300.SEMANTIC_BANK, r300.PRIMARY_LUT_ADDR
            ) + 0x27
        ] = 0x06
        mutants.append(("active semantic LUT", active_lut))

        erased_helper = bytearray(self.base)
        erased_helper[
            r300.semantic.bank_offset(
                r300.SEMANTIC_BANK, r300.ROOM01_HELPER_ADDR
            )
        ] = 0x00
        mutants.append(("room helper storage", erased_helper))

        erased_lut = bytearray(self.base)
        erased_lut[
            r300.semantic.bank_offset(
                r300.SEMANTIC_BANK, r300.ROOM01_LUT_ADDR
            )
        ] = 0x00
        mutants.append(("room LUT storage", erased_lut))

        for label, mutant in mutants:
            with self.subTest(label=label):
                with self.assertRaises(AssertionError):
                    r300.validate_semantic_contract(bytes(mutant))


if __name__ == "__main__":
    unittest.main()
