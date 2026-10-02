#!/usr/bin/env python3
"""Focused static controls for r307's bank-16 installer mirror."""

from __future__ import annotations

import hashlib
from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
DIAGNOSTICS = ROOT / "scripts" / "diagnostics"
sys.path.insert(0, str(DIAGNOSTICS))

import build_stage1_bank16_installer_mirror_r307 as r307  # noqa: E402


EXPECTED_SHA256 = (
    "77722cf7abfff564de72caf0cdd06dbb774bf0614c071933247178817b3bea84"
)
EXPECTED_RECEIPT_SHA256 = (
    "a36bc024705b9df3388b83e008f6add576a590db35a92e36110d2935a8b50bc5"
)


def sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


class Stage1Bank16InstallerMirrorR307Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.base = r307.BASE.read_bytes()
        cls.base_receipt = r307.BASE_RECEIPT.read_bytes()
        cls.candidate, cls.receipt = r307.build(
            cls.base, cls.base_receipt
        )

    def test_identity_receipts_and_checksums_are_pinned(self) -> None:
        self.assertEqual(sha256(self.candidate), EXPECTED_SHA256)
        self.assertEqual(self.receipt["candidate_sha256"], EXPECTED_SHA256)
        self.assertEqual(
            sha256(r307.r305.r304.receipt_bytes(self.receipt)),
            EXPECTED_RECEIPT_SHA256,
        )
        self.assertEqual(self.candidate, r307.DEFAULT_OUTPUT.read_bytes())
        self.assertEqual(
            sha256(r307.DEFAULT_RECEIPT.read_bytes()),
            EXPECTED_RECEIPT_SHA256,
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

    def test_both_installer_banks_emit_one_canonical_image(self) -> None:
        canonical = r307.simulate_installer(
            self.candidate, r307.CANONICAL_BANK
        )
        mirror = r307.simulate_installer(
            self.candidate, r307.MIRROR_BANK
        )
        self.assertEqual(canonical, mirror)
        self.assertEqual(
            list(canonical),
            [region[0] for region in r307.COPY_REGIONS]
            + [r307.EXTENSION_REGION[0]],
        )
        self.assertIn(
            r307.R305_FIXED_PREDICATE_GATEWAY,
            canonical["DA8E-DAFF"],
        )
        self.assertEqual(
            self.receipt["installer_contract"]["predicate_pointer_exceptions"],
            [],
        )

    def test_installer_inventory_and_entry_scans_are_exact(self) -> None:
        for bank in (r307.CANONICAL_BANK, r307.MIRROR_BANK):
            self.assertEqual(
                r307.absolute_transfers_to(
                    self.candidate,
                    bank,
                    r307.INSTALLER_ADDR,
                    r307.INSTALLER_ADDR + 1,
                ),
                [
                    (address, 0xC4, r307.INSTALLER_ADDR)
                    for address in r307.INSTALLER_CALL_SITES
                ],
            )
        self.assertEqual(
            r307.absolute_transfers_to(
                self.candidate,
                r307.MIRROR_BANK,
                r307.CONTINUATION_ADDR,
                r307.CONTINUATION_END,
            ),
            [(0x577A, 0xC3, r307.CONTINUATION_ADDR)],
        )
        inventory = self.receipt["installer_contract"][
            "copy_region_inventory"
        ]
        self.assertEqual(len(inventory), 8)
        self.assertEqual(
            [row["range"] for row in inventory],
            [region[0] for region in r307.COPY_REGIONS]
            + [r307.EXTENSION_REGION[0]],
        )

    def test_overlay_changes_only_the_reviewed_bank16_regions(self) -> None:
        functional = r307.r305.r304.delta(
            self.base, self.candidate, functional=True
        )
        expected = {
            offset
            for offset in r307.owned_ranges()
            if self.base[offset] != self.candidate[offset]
        }
        self.assertEqual(functional, expected)
        bank13 = slice(13 * 0x4000, 14 * 0x4000)
        self.assertEqual(self.candidate[bank13], self.base[bank13])
        self.assertEqual(self.receipt["ownership"]["escaped_bytes"], 0)

    def test_structural_mutations_fail_closed(self) -> None:
        mutants: list[tuple[str, bytearray]] = []
        for label, bank, address in (
            ("atomic source", 16, r307.ATOMIC_SOURCE_ADDR),
            ("runtime source B", 16, r307.RUNTIME_SOURCE_B_ADDR),
            ("continuation cave", 16, r307.CONTINUATION_ADDR + 20),
            ("canonical extension", 13, r307.CANONICAL_EXTENSION_SOURCE_ADDR),
            ("fixed predicate gateway", 16, r307.R305_FIXED_PREDICATE_GATEWAY_ADDR),
            ("installer call", 16, r307.INSTALLER_CALL_SITES[0]),
        ):
            mutant = bytearray(self.base)
            offset = r307.bank_offset(bank, address)
            mutant[offset] ^= 0x01
            mutants.append((label, mutant))
        for label, mutant in mutants:
            with self.subTest(label=label):
                with self.assertRaises(AssertionError):
                    r307.validate_structural_preimages(bytes(mutant))

    def test_installer_output_mutations_fail_closed(self) -> None:
        for label, address in (
            ("DA13 odd tag", r307.ATOMIC_SOURCE_ADDR + 1),
            ("DBDF compiler", r307.RUNTIME_SOURCE_B_ADDR),
            ("DBF1 extension", r307.EXTENSION_SOURCE_ADDR),
        ):
            mutant = bytearray(self.candidate)
            mutant[r307.bank_offset(r307.MIRROR_BANK, address)] ^= 0x01
            with self.subTest(label=label):
                with self.assertRaises(AssertionError):
                    r307.installer_contract(bytes(mutant))


if __name__ == "__main__":
    unittest.main()
