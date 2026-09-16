#!/usr/bin/env python3
"""Static controls for r312's candidate-owned WRAM runtime epoch."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
DIAGNOSTICS = ROOT / "scripts" / "diagnostics"
sys.path.insert(0, str(DIAGNOSTICS))

import build_stage1_runtime_epoch_r312 as r312  # noqa: E402
from verify_stage1_scene0b_captured_menu_receipt import (  # noqa: E402
    gbas_payload,
    state_byte,
)


EXPECTED_SHA256 = (
    "dca72f535850d4445fc8f27d032628e63b1a9b7dee0f8012fbfee9b69c4a1951"
)
EXPECTED_RECEIPT_SHA256 = (
    "3c677ced990956892c876d310207c4549f27016721ebf025db39990f3408f380"
)
CAPTURES = (
    ROOT / "save_states_for_claude/rc11_corrupted-walls.ss0",
    ROOT / "save_states_for_claude/rc11_low-health-degradation.ss0",
)


def digest(payload: bytes | bytearray) -> str:
    return hashlib.sha256(payload).hexdigest()


class Stage1RuntimeEpochR312Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.base = r312.BASE.read_bytes()
        cls.base_receipt = r312.BASE_RECEIPT.read_bytes()
        cls.rejected = r312.REJECTED_LIVE_RECEIPT.read_bytes()
        cls.candidate = r312.DEFAULT_OUTPUT.read_bytes()
        cls.receipt_bytes = r312.DEFAULT_RECEIPT.read_bytes()
        cls.receipt = json.loads(cls.receipt_bytes)

    def test_pinned_identity_and_deterministic_rebuild(self) -> None:
        self.assertEqual(digest(self.base), r312.BASE_SHA256)
        self.assertEqual(digest(self.base_receipt), r312.BASE_RECEIPT_SHA256)
        self.assertEqual(
            digest(self.rejected), r312.REJECTED_LIVE_RECEIPT_SHA256
        )
        self.assertEqual(digest(self.candidate), EXPECTED_SHA256)
        self.assertEqual(digest(self.receipt_bytes), EXPECTED_RECEIPT_SHA256)
        candidate, receipt = r312.build(
            self.base, self.base_receipt, self.rejected
        )
        self.assertEqual(candidate, self.candidate)
        self.assertEqual(
            r312.r305.r304.receipt_bytes(receipt), self.receipt_bytes
        )
        self.assertFalse(receipt["promotable"])
        self.assertFalse(receipt["emulator_invoked"])

    def test_exact_eight_byte_epoch_delta(self) -> None:
        functional = r312.r305.r304.delta(
            self.base, self.candidate, functional=True
        )
        self.assertEqual(functional, r312.owned_ranges())
        self.assertEqual(len(functional), 8)
        for offset in functional:
            self.assertEqual(self.base[offset], r312.OLD_EPOCH)
            self.assertEqual(self.candidate[offset], r312.NEW_EPOCH)
        for offset, (before, after) in enumerate(
            zip(self.base, self.candidate, strict=True)
        ):
            if offset in functional or offset in r312.CHECKSUM_OFFSETS:
                continue
            self.assertEqual(after, before, f"unowned r311 drift at {offset:#x}")

    def test_all_gates_and_publications_use_one_epoch(self) -> None:
        for bank in r312.BANKS:
            for address in r312.GATE_STARTS:
                start = r312.bank_offset(bank, address)
                self.assertEqual(
                    self.candidate[start:start + len(r312.NEW_GATE)],
                    r312.NEW_GATE,
                )
            start = r312.bank_offset(bank, r312.FINALIZER_ADDR)
            self.assertEqual(
                self.candidate[start:start + len(r312.NEW_FINALIZER)],
                r312.NEW_FINALIZER,
            )

    def test_operator_states_prove_stale_runtime_false_ready(self) -> None:
        for capture in CAPTURES:
            state = gbas_payload(capture)
            resident = bytes(
                state_byte(state, r312.r305.RUNTIME_RELOCATED_ADDR + index)
                for index in range(r312.r305.RUNTIME_LENGTH)
            )
            self.assertEqual(resident, r312.CAPTURED_STALE_DAD7)
            self.assertEqual(state_byte(state, 0xDF51), r312.OLD_EPOCH)
            self.assertNotEqual(
                resident, r312.desired_dad7(self.candidate, r312.BANKS[0])
            )

    def test_installer_replaces_stale_gateway_then_skips(self) -> None:
        contract = r312.epoch_contract(self.candidate)
        self.assertEqual(contract["values_exhausted"], 256)
        self.assertEqual(contract["installing_values"], 255)
        self.assertTrue(contract["legacy_A8_first_gate_installs"])
        self.assertTrue(contract["second_gate_skips"])
        desired = r312.desired_dad7(self.candidate, r312.BANKS[0])
        self.assertEqual(desired[7:10], bytes.fromhex("C4 13 00"))
        self.assertEqual(
            contract["installed_DAD7_sha256"], hashlib.sha256(desired).hexdigest()
        )

    def test_mutated_gate_or_publication_is_rejected(self) -> None:
        for address in (
            r312.GATE_STARTS[0] + r312.GATE_EPOCH_INDEX,
            r312.FINALIZER_ADDR + r312.FINALIZER_EPOCH_INDEX,
        ):
            mutant = bytearray(self.candidate)
            mutant[r312.bank_offset(r312.BANKS[0], address)] ^= 1
            with self.assertRaises(AssertionError):
                r312.validate_candidate(self.base, bytes(mutant))

    def test_checksums_are_exact(self) -> None:
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


if __name__ == "__main__":
    unittest.main()
