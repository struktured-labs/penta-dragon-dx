#!/usr/bin/env python3
"""Offline identity, ABI, branch, timing, and mutation tests for r318."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
DIAGNOSTICS = ROOT / "scripts" / "diagnostics"
sys.path.insert(0, str(DIAGNOSTICS))

import build_stage1_row_gate_abi_speed_r318 as r318  # noqa: E402


EXPECTED_SHA256 = (
    "909d7ee16bbf5080fd9992567bbe784e6df3234a08f9bde07ff7a10b2f729abb"
)
EXPECTED_RECEIPT_SHA256 = (
    "57e853011f4ba03252be78a60eefc385cc60bc71a97fc0c5b0d92ea4bc8e8cfd"
)


def digest(payload: bytes | bytearray) -> str:
    return hashlib.sha256(payload).hexdigest()


class Stage1RowGateAbiSpeedR318Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.base = r318.BASE.read_bytes()
        cls.base_receipt = r318.BASE_RECEIPT.read_bytes()
        cls.candidate = r318.DEFAULT_OUTPUT.read_bytes()
        cls.receipt_bytes = r318.DEFAULT_RECEIPT.read_bytes()
        cls.receipt = json.loads(cls.receipt_bytes)

    def test_pinned_identity_and_deterministic_rebuild(self) -> None:
        self.assertEqual(digest(self.base), r318.BASE_SHA256)
        self.assertEqual(
            digest(self.base_receipt), r318.BASE_RECEIPT_SHA256
        )
        self.assertEqual(digest(self.candidate), EXPECTED_SHA256)
        self.assertEqual(r318.EXPECTED_CANDIDATE_SHA256, EXPECTED_SHA256)
        self.assertEqual(
            digest(self.receipt_bytes), EXPECTED_RECEIPT_SHA256
        )
        rebuilt, receipt = r318.build(self.base, self.base_receipt)
        self.assertEqual(rebuilt, self.candidate)
        self.assertEqual(
            r318.r317.r305.r304.receipt_bytes(receipt),
            self.receipt_bytes,
        )
        self.assertFalse(receipt["promotable"])
        self.assertFalse(receipt["emulator_invoked"])

    def test_exact_width_overlay_and_preimage(self) -> None:
        start = r318.ROW_OFFSET
        stop = start + len(r318.NEW_ROW_PREFIX)
        self.assertEqual(len(r318.OLD_ROW_PREFIX), 23)
        self.assertEqual(len(r318.NEW_ROW_PREFIX), 23)
        self.assertEqual(r318.ROW_END - r318.ROW_ADDR, 23)
        self.assertEqual(self.base[start:stop], r318.OLD_ROW_PREFIX)
        self.assertEqual(self.candidate[start:stop], r318.NEW_ROW_PREFIX)
        changed = {
            offset
            for offset, (before, after) in enumerate(
                zip(self.base, self.candidate, strict=True)
            )
            if before != after
            and offset not in r318.r317.r316.CHECKSUM_OFFSETS
        }
        self.assertEqual(
            changed,
            {
                start + relative
                for relative in r318.ROW_CHANGED_RELATIVE_OFFSETS
            },
        )
        self.assertEqual(self.receipt["ownership"]["escaped_bytes"], 0)
        self.assertEqual(
            self.receipt["ownership"]["rom_size_delta_bytes"], 0
        )

    def test_branch_targets_and_downstream_code_are_exact(self) -> None:
        code = r318.NEW_ROW_PREFIX
        self.assertEqual(code[9:11], bytes.fromhex("20 38"))
        self.assertEqual(
            r318.jr_target(r318.ROW_ADDR + 9, code[10]),
            r318.REJECT_LANDING_ADDR,
        )
        self.assertEqual(code[21:23], bytes.fromhex("28 0C"))
        self.assertEqual(
            r318.jr_target(r318.ROW_ADDR + 21, code[22]), 0x6BCA
        )
        self.assertEqual(code[1:5], bytes.fromhex("FA 80 D8 47"))
        self.assertEqual(code[5:9], bytes.fromhex("F0 B7 FE 02"))
        self.assertEqual(code[18:21], bytes.fromhex("78 FE 0A"))
        for address, expected in (
            (r318.POST_PREFIX_ADDR, r318.POST_PREFIX),
            (r318.REJECT_LANDING_ADDR, r318.REJECT_LANDING),
            (r318.DOWNSTREAM_SELECTOR_ADDR, r318.DOWNSTREAM_SELECTOR),
            (r318.ROOM_FAST_GATE_ADDR, r318.ROOM_FAST_GATE),
        ):
            with self.subTest(address=address):
                offset = r318.r317.r316.bank_offset(r318.ROW_BANK, address)
                self.assertEqual(
                    self.candidate[offset:offset + len(expected)], expected
                )
                self.assertEqual(
                    self.candidate[offset:offset + len(expected)],
                    self.base[offset:offset + len(expected)],
                )

    def test_exhaustive_scene_abi_and_route_partition(self) -> None:
        contract = r318.exhaustive_contract()
        self.assertEqual(contract["input_tuples"], 0x100 * 0x100 * 3)
        self.assertTrue(all(contract["route_counts"].values()))
        for scene in range(0x100):
            for dcfd in (0x00, 0x01, 0xFF):
                accepted = r318.row_prefix_route(scene, 0x02, dcfd)
                self.assertEqual(accepted["b_after"], scene)
                if dcfd == 0:
                    self.assertEqual(accepted["target"], 0x6C50)
                elif scene == 0x0A:
                    self.assertEqual(accepted["target"], 0x6BCA)
                else:
                    self.assertEqual(accepted["target"], r318.ROW_END)
            for rejected_owner in (0x00, 0x01, 0x03, 0xFF):
                rejected = r318.row_prefix_route(
                    scene, rejected_owner, 0x01
                )
                self.assertEqual(rejected["b_after"], scene)
                self.assertEqual(
                    rejected["target"], r318.REJECT_LANDING_ADDR
                )
        self.assertEqual(
            r318.row_prefix_route(0x0B, 0x02, 0x01)["route"],
            "ordinary-fallthrough",
        )

    def test_timing_claim_includes_the_landed_reject_jump(self) -> None:
        timing = r318.timing_contract()
        accepted = timing["stage1_owner_ffb7_02"]
        rejected = timing["rejected_ffb7_not_02"]
        self.assertEqual(accepted["r300_t"], accepted["r318_t"])
        self.assertEqual(accepted["r318_t"], 48)
        self.assertEqual(rejected["r300_t"], 52)
        self.assertEqual(rejected["r318_t"], 68)
        self.assertEqual(rejected["delta_from_r300_t"], 16)
        self.assertIn("$6BEA", rejected["reason"])

    def test_r317_selector_and_cgb_contract_survives(self) -> None:
        self.assertEqual(
            self.candidate[r318.r317.r316.CGB_FLAG_OFFSET],
            r318.r317.r316.CGB_ONLY_FLAG,
        )
        start = r318.r317.DISPATCH_OFFSET
        self.assertEqual(
            self.candidate[
                start:start + len(r318.r317.DISPATCH_REPLACEMENT)
            ],
            r318.r317.DISPATCH_REPLACEMENT,
        )
        for site in r318.r317.r316.OPERAND_SITES:
            with self.subTest(site=site.label):
                offset = r318.r317.r316.site_offset(site)
                self.assertEqual(
                    self.candidate[offset:offset + 2],
                    bytes((site.opcode, site.new_operand)),
                )
        checksummed = bytearray(self.candidate)
        r318.r317.r305.r304.update_checksums(checksummed)
        self.assertEqual(bytes(checksummed), self.candidate)

    def test_missing_abi_and_branch_mutations_fail_closed(self) -> None:
        mutations = {
            "missing_ld_b_a": (4, 0x00),
            "wrong_owner_displacement": (10, 0x37),
            "scene0b_alias": (20, 0x0B),
        }
        for label, (relative, replacement) in mutations.items():
            with self.subTest(label=label):
                mutant = bytearray(self.candidate)
                mutant[r318.ROW_OFFSET + relative] = replacement
                with self.assertRaises(AssertionError):
                    r318.validate_candidate(self.base, bytes(mutant))

        surrounding = (
            (r318.REJECT_LANDING_ADDR, 0),
            (r318.DOWNSTREAM_SELECTOR_ADDR, 0),
            (r318.ROOM_FAST_GATE_ADDR, 0),
            (0x6BE7, 0),
        )
        for address, relative in surrounding:
            with self.subTest(address=address):
                mutant = bytearray(self.candidate)
                offset = r318.r317.r316.bank_offset(
                    r318.ROW_BANK, address
                ) + relative
                mutant[offset] ^= 0x01
                with self.assertRaises(AssertionError):
                    r318.validate_candidate(self.base, bytes(mutant))

    def test_wrong_base_or_receipt_fails_closed(self) -> None:
        bad_base = bytearray(self.base)
        bad_base[r318.ROW_OFFSET] ^= 0x01
        with self.assertRaises(AssertionError):
            r318.build(bytes(bad_base), self.base_receipt)
        bad_receipt = bytearray(self.base_receipt)
        bad_receipt[-2] ^= 0x01
        with self.assertRaises(AssertionError):
            r318.build(self.base, bytes(bad_receipt))


if __name__ == "__main__":
    unittest.main()
