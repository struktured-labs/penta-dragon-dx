#!/usr/bin/env python3
"""Offline identity, semantic, ABI, timing, and mutation gates for r319."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
DIAGNOSTICS = ROOT / "scripts" / "diagnostics"
sys.path.insert(0, str(DIAGNOSTICS))

import build_stage1_effective_row_context_r319 as r319  # noqa: E402


EXPECTED_SHA256 = (
    "2afaa7c87b1cb84f00c25a0f9d6edc8b811144b31ef64430fa0fa9d9d8bcc2db"
)
EXPECTED_RECEIPT_SHA256 = (
    "ccf15f3f8d927f8d512329a1428190263e84b1f05c570a7d14fa9e9cd03b0d00"
)
EXPECTED_FUNCTIONAL_OFFSETS = {
    0x0521A1,
    0x0527EE,
    0x052B71,
    0x052D9F,
}


def digest(payload: bytes | bytearray) -> str:
    return hashlib.sha256(payload).hexdigest()


class Stage1EffectiveRowContextR319Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.base = r319.BASE.read_bytes()
        cls.base_receipt = r319.BASE_RECEIPT.read_bytes()
        cls.candidate = r319.DEFAULT_OUTPUT.read_bytes()
        cls.receipt_bytes = r319.DEFAULT_RECEIPT.read_bytes()
        cls.receipt = json.loads(cls.receipt_bytes)

    def test_pinned_base_candidate_receipt_and_rebuild(self) -> None:
        self.assertEqual(digest(self.base), r319.BASE_SHA256)
        self.assertEqual(r319.BASE_SHA256, r319.r318.EXPECTED_CANDIDATE_SHA256)
        self.assertEqual(
            digest(self.base_receipt), r319.BASE_RECEIPT_SHA256
        )
        self.assertEqual(digest(self.candidate), EXPECTED_SHA256)
        self.assertEqual(r319.EXPECTED_CANDIDATE_SHA256, EXPECTED_SHA256)
        self.assertEqual(digest(self.receipt_bytes), EXPECTED_RECEIPT_SHA256)
        self.assertEqual(self.receipt["candidate_sha256"], EXPECTED_SHA256)
        self.assertEqual(self.receipt["base"]["candidate_sha256"],
                         r319.BASE_SHA256)
        self.assertEqual(
            self.receipt["base"]["build_receipt_sha256"],
            r319.BASE_RECEIPT_SHA256,
        )
        rebuilt, receipt = r319.build(self.base, self.base_receipt)
        self.assertEqual(rebuilt, self.candidate)
        self.assertEqual(
            r319.r318.r317.r305.r304.receipt_bytes(receipt),
            self.receipt_bytes,
        )
        self.assertFalse(receipt["promotable"])
        self.assertFalse(receipt["emulator_invoked"])

    def test_exact_four_functional_bytes_and_checksums_only(self) -> None:
        changed = {
            offset
            for offset, (before, after) in enumerate(
                zip(self.base, self.candidate, strict=True)
            )
            if before != after
        }
        functional = changed - r319.CHECKSUM_OFFSETS
        self.assertEqual(functional, EXPECTED_FUNCTIONAL_OFFSETS)
        self.assertEqual(functional, r319.owned_ranges())
        self.assertEqual(len(functional), 4)
        self.assertLessEqual(
            changed, EXPECTED_FUNCTIONAL_OFFSETS | r319.CHECKSUM_OFFSETS
        )
        for offset in functional:
            self.assertEqual(self.base[offset], 0xBD)
            self.assertEqual(self.candidate[offset], 0xE5)
        ownership = self.receipt["ownership"]
        self.assertEqual(ownership["functional_changed_bytes_from_r318"], 4)
        self.assertEqual(ownership["escaped_bytes"], 0)
        self.assertEqual(ownership["rom_size_delta_bytes"], 0)

    def test_all_four_full_nine_byte_preimages_and_targets(self) -> None:
        self.assertEqual(len(r319.OLD_TRAMPOLINE), 9)
        self.assertEqual(len(r319.NEW_TRAMPOLINE), 9)
        self.assertEqual(
            r319.OLD_TRAMPOLINE,
            bytes.fromhex("F0 BD 3D C2 00 43 C3 00 45"),
        )
        self.assertEqual(
            r319.NEW_TRAMPOLINE,
            bytes.fromhex("F0 E5 3D C2 00 43 C3 00 45"),
        )
        differences = {
            index
            for index, (before, after) in enumerate(
                zip(
                    r319.OLD_TRAMPOLINE,
                    r319.NEW_TRAMPOLINE,
                    strict=True,
                )
            )
            if before != after
        }
        self.assertEqual(differences, {1})
        self.assertEqual(r319.NEW_TRAMPOLINE[3:6],
                         bytes.fromhex("C2 00 43"))
        self.assertEqual(r319.NEW_TRAMPOLINE[6:9],
                         bytes.fromhex("C3 00 45"))
        for address in r319.TRAMPOLINE_ADDRS:
            with self.subTest(address=address):
                offset = r319.bank_offset(r319.BANK, address)
                self.assertEqual(
                    self.base[offset:offset + 9], r319.OLD_TRAMPOLINE
                )
                self.assertEqual(
                    self.candidate[offset:offset + 9],
                    r319.NEW_TRAMPOLINE,
                )
        self.assertEqual(
            self.receipt["ownership"]["full_nine_byte_targets_exact"], 4
        )
        self.assertEqual(len(self.receipt["base"]["trampolines"]), 4)

    def test_native_ffe5_resolution_is_exhaustive(self) -> None:
        cases = 0
        for table_value in range(0x100):
            for ffbd in range(0x100):
                self.assertEqual(
                    r319.effective_room(table_value, ffbd),
                    table_value if table_value else ffbd,
                )
                cases += 1
        self.assertEqual(cases, 65536)
        semantic = self.receipt["offline_contract"]["semantic"]
        self.assertEqual(
            semantic["native_resolver_cases_exhausted"], cases
        )
        self.assertEqual(semantic["resolved_dispatch_cases_exhausted"],
                         cases)
        self.assertEqual(
            semantic["effective_vs_outgoing_target_differences"], 509
        )
        self.assertEqual(
            self.base[
                r319.EFFECTIVE_ROOM_SETTER_ADDR:
                r319.EFFECTIVE_ROOM_SETTER_ADDR
                + len(r319.EFFECTIVE_ROOM_SETTER)
            ],
            bytes.fromhex("7E E0 CE A7 20 02 F0 BD E0 E5"),
        )

    def test_ffe5_dispatch_abi_flags_and_timing_are_exhaustive(self) -> None:
        cases = 0
        targets = {r319.r300.PRIMARY_HELPER_ADDR: 0,
                   r319.r300.ROOM01_HELPER_ADDR: 0}
        for ffe5 in range(0x100):
            for incoming_f in range(0, 0x100, 0x10):
                result = r319.trampoline_model(
                    ffe5,
                    incoming_f,
                    bc=0x00FF,
                    de=0x5500,
                    hl=0xAA55,
                    sp=0xFFFC,
                )
                expected_f = incoming_f & 0x10
                expected_f |= 0x40
                if ffe5 == 1:
                    expected_f |= 0x80
                if ffe5 & 0x0F == 0:
                    expected_f |= 0x20
                expected_target = (
                    r319.r300.ROOM01_HELPER_ADDR
                    if ffe5 == 1 else r319.r300.PRIMARY_HELPER_ADDR
                )
                self.assertEqual(result["a"], (ffe5 - 1) & 0xFF)
                self.assertEqual(result["f"], expected_f)
                self.assertEqual(result["target"], expected_target)
                self.assertEqual(result["t_cycles"],
                                 44 if ffe5 == 1 else 32)
                self.assertEqual(
                    (result["bc"], result["de"], result["hl"], result["sp"]),
                    (0x00FF, 0x5500, 0xAA55, 0xFFFC),
                )
                targets[expected_target] += 1
                cases += 1
        self.assertEqual(cases, 4096)
        self.assertEqual(
            targets,
            {
                r319.r300.PRIMARY_HELPER_ADDR: 4080,
                r319.r300.ROOM01_HELPER_ADDR: 16,
            },
        )
        semantic = self.receipt["offline_contract"]["semantic"]
        self.assertEqual(semantic["ffe5_flags_cases_exhausted"], cases)
        timing = self.receipt["offline_contract"]["timing"]
        self.assertEqual(timing["all_paths_delta_t_cycles_from_r318"], 0)
        self.assertEqual(timing["instruction_width_delta_bytes"], 0)
        self.assertEqual(timing["room01_target_4500_t_cycles"], 44)
        self.assertEqual(timing["other_room_target_4300_t_cycles"], 32)

    def test_transition_rows_use_incoming_not_outgoing_room(self) -> None:
        incoming_room01 = r319.effective_room(1, 5)
        self.assertEqual(incoming_room01, 1)
        self.assertEqual(
            r319.trampoline_model(incoming_room01, 0)["target"], 0x4500
        )
        incoming_room05 = r319.effective_room(5, 1)
        self.assertEqual(incoming_room05, 5)
        self.assertEqual(
            r319.trampoline_model(incoming_room05, 0)["target"], 0x4300
        )
        self.assertEqual(r319.effective_room(0, 1), 1)
        self.assertEqual(r319.effective_room(0, 5), 5)

    def test_helpers_luts_and_r310_precompile_are_byte_exact(self) -> None:
        artifacts = r319.semantic_artifacts(self.base)
        expected_hashes = {
            "primary_helper": r319.PRIMARY_HELPER_SHA256,
            "primary_lut": r319.PRIMARY_LUT_SHA256,
            "room01_helper": r319.ROOM01_HELPER_SHA256,
            "room01_lut": r319.ROOM01_LUT_SHA256,
        }
        for label, (offset, expected) in artifacts.items():
            with self.subTest(artifact=label):
                self.assertEqual(digest(expected), expected_hashes[label])
                self.assertEqual(
                    self.base[offset:offset + len(expected)], expected
                )
                self.assertEqual(
                    self.candidate[offset:offset + len(expected)], expected
                )

        precompile = r319.r310.PRECOMPILE_SITE
        self.assertEqual(
            self.base[
                precompile:precompile + len(r319.r310.NEW_PRECOMPILE)
            ],
            r319.r310.NEW_PRECOMPILE,
        )
        self.assertEqual(
            self.candidate[
                precompile:precompile + len(r319.r310.NEW_PRECOMPILE)
            ],
            r319.r310.NEW_PRECOMPILE,
        )
        helper = r319.bank_offset(
            r319.r310.HELPER_BANK, r319.r310.HELPER_ADDR
        )
        self.assertEqual(
            self.base[helper:helper + len(r319.r310.NEW_HELPER)],
            r319.r310.NEW_HELPER,
        )
        self.assertEqual(
            self.candidate[helper:helper + len(r319.r310.NEW_HELPER)],
            r319.r310.NEW_HELPER,
        )
        self.assertTrue(
            self.receipt["ownership"]["r310_precompile_fix_exact"]
        )
        self.assertTrue(
            self.receipt["ownership"]["semantic_helpers_and_luts_exact"]
        )

    def test_r318_row_speed_and_cgb_contract_survive(self) -> None:
        start = r319.r318.ROW_OFFSET
        end = start + len(r319.r318.NEW_ROW_PREFIX)
        self.assertEqual(self.base[start:end], r319.r318.NEW_ROW_PREFIX)
        self.assertEqual(self.candidate[start:end], r319.r318.NEW_ROW_PREFIX)
        self.assertEqual(
            self.candidate[r319.r318.r317.r316.CGB_FLAG_OFFSET],
            r319.r318.r317.r316.CGB_ONLY_FLAG,
        )
        checksummed = bytearray(self.candidate)
        r319.r318.r317.r305.r304.update_checksums(checksummed)
        self.assertEqual(bytes(checksummed), self.candidate)

    def test_operand_surrounding_and_artifact_mutations_fail_closed(self) -> None:
        for address in r319.TRAMPOLINE_ADDRS:
            with self.subTest(address=address, mutation="operand"):
                mutant = bytearray(self.candidate)
                mutant[r319.bank_offset(r319.BANK, address) + 1] = 0xBD
                with self.assertRaises(AssertionError):
                    r319.validate_candidate(self.base, bytes(mutant))
            with self.subTest(address=address, mutation="tail"):
                mutant = bytearray(self.candidate)
                mutant[r319.bank_offset(r319.BANK, address) + 2] ^= 0x01
                with self.assertRaises(AssertionError):
                    r319.validate_candidate(self.base, bytes(mutant))

        artifacts = r319.semantic_artifacts(self.base)
        for label, (offset, _) in artifacts.items():
            with self.subTest(artifact=label):
                mutant = bytearray(self.candidate)
                mutant[offset] ^= 0x01
                with self.assertRaises(AssertionError):
                    r319.validate_candidate(self.base, bytes(mutant))

    def test_wrong_base_or_receipt_fails_closed(self) -> None:
        bad_base = bytearray(self.base)
        bad_base[r319.bank_offset(r319.BANK, 0x61A0)] ^= 0x01
        with self.assertRaises(AssertionError):
            r319.build(bytes(bad_base), self.base_receipt)
        bad_receipt = bytearray(self.base_receipt)
        bad_receipt[-2] ^= 0x01
        with self.assertRaises(AssertionError):
            r319.build(self.base, bytes(bad_receipt))


if __name__ == "__main__":
    unittest.main()
