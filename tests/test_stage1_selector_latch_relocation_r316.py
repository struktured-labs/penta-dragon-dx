#!/usr/bin/env python3
"""Offline identity, ownership, collision, and mutation tests for r316."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
DIAGNOSTICS = ROOT / "scripts" / "diagnostics"
sys.path.insert(0, str(DIAGNOSTICS))

import build_stage1_selector_latch_relocation_r316 as r316  # noqa: E402


EXPECTED_SHA256 = (
    "1373479e5a63c1adfa958ae1e278d99d32032b1d3d08386fc3a4d7641496dc2e"
)
EXPECTED_RECEIPT_SHA256 = (
    "2490bb53189b2460ee114b2be5e085d93513747a7fba1ef6e32b2a347aa0e386"
)


def digest(payload: bytes | bytearray) -> str:
    return hashlib.sha256(payload).hexdigest()


class Stage1SelectorLatchRelocationR316Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.base = r316.BASE.read_bytes()
        cls.base_receipt = r316.BASE_RECEIPT.read_bytes()
        cls.candidate = r316.DEFAULT_OUTPUT.read_bytes()
        cls.receipt_bytes = r316.DEFAULT_RECEIPT.read_bytes()
        cls.receipt = json.loads(cls.receipt_bytes)

    def test_pinned_identity_and_deterministic_rebuild(self) -> None:
        self.assertEqual(digest(self.base), r316.BASE_SHA256)
        self.assertEqual(digest(self.base_receipt), r316.BASE_RECEIPT_SHA256)
        self.assertEqual(digest(self.candidate), EXPECTED_SHA256)
        self.assertEqual(r316.EXPECTED_CANDIDATE_SHA256, EXPECTED_SHA256)
        self.assertEqual(digest(self.receipt_bytes), EXPECTED_RECEIPT_SHA256)
        rebuilt, receipt = r316.build(self.base, self.base_receipt)
        self.assertEqual(rebuilt, self.candidate)
        self.assertEqual(
            r316.r305.r304.receipt_bytes(receipt), self.receipt_bytes
        )
        self.assertFalse(receipt["promotable"])
        self.assertFalse(receipt["emulator_invoked"])

    def test_complete_four_latch_executable_inventory(self) -> None:
        self.assertEqual(len(r316.OPERAND_SITES), 54)
        self.assertEqual(
            len({(site.bank, site.address) for site in r316.OPERAND_SITES}),
            54,
        )
        for old_operand, expected in r316.EXPECTED_SITE_COUNTS.items():
            sites = [site for site in r316.OPERAND_SITES
                     if site.old_operand == old_operand]
            self.assertEqual(len(sites), expected)
            self.assertEqual(
                {
                    access: sum(site.access == access for site in sites)
                    for access in ("read", "write")
                },
                r316.EXPECTED_ACCESS_COUNTS[old_operand],
            )
            self.assertGreater(
                sum(site.access == "read" for site in sites), 0
            )
            self.assertGreater(
                sum(site.access == "write" for site in sites), 0
            )

    def test_only_operand_bytes_change_and_every_opcode_is_exact(self) -> None:
        functional = {
            offset for offset, (before, after) in
            enumerate(zip(self.base, self.candidate, strict=True))
            if before != after and offset not in r316.CHECKSUM_OFFSETS
        }
        operand_offsets = {
            r316.site_offset(site) + 1 for site in r316.OPERAND_SITES
        }
        expected = operand_offsets | {r316.CGB_FLAG_OFFSET}
        self.assertEqual(functional, expected)
        for site in r316.OPERAND_SITES:
            offset = r316.site_offset(site)
            self.assertEqual(
                self.base[offset:offset + 2],
                bytes((site.opcode, site.old_operand)),
            )
            self.assertEqual(
                self.candidate[offset:offset + 2],
                bytes((site.opcode, site.new_operand)),
            )
        self.assertEqual(self.receipt["ownership"]["opcode_changes"], 0)
        self.assertEqual(
            self.receipt["ownership"]["instruction_width_delta_bytes"], 0
        )
        self.assertEqual(
            self.receipt["ownership"]["instruction_cycle_delta_t"], 0
        )

    def test_native_indirect_owner_and_continue_route_remain_exact(self) -> None:
        self.assertEqual(
            self.candidate[
                r316.STOCK_READER_ADDR:
                r316.STOCK_READER_ADDR + len(r316.STOCK_READER)
            ],
            r316.STOCK_READER,
        )
        self.assertEqual(
            self.candidate[
                r316.STOCK_WRITER_ADDR:
                r316.STOCK_WRITER_ADDR + len(r316.STOCK_WRITER)
            ],
            r316.STOCK_WRITER,
        )
        route = r316.bank_offset(1, r316.CONTINUE_RELOAD_ADDR)
        self.assertEqual(
            self.candidate[route:route + len(r316.CONTINUE_RELOAD)],
            r316.CONTINUE_RELOAD,
        )
        self.assertIn(bytes.fromhex("CD 9C 0C"), r316.CONTINUE_RELOAD)

    def test_negative_control_corrupts_four_pages_and_r316_corrupts_none(self) -> None:
        contract = r316.collision_contract(self.base)
        old = contract["r314_negative_control"]
        fixed = contract["r316"]
        self.assertEqual(old["selector_hex"], "1000120003011617")
        self.assertEqual(old["mismatch_page_indices"], [1, 3, 4, 5])
        self.assertEqual(
            old["mismatch_vram_pages"],
            ["$9100", "$9300", "$9400", "$9500"],
        )
        self.assertEqual(fixed["selector_hex"], "1011121314151617")
        self.assertEqual(fixed["mismatch_page_indices"], [])
        self.assertEqual(fixed["page_sha256"],
                         fixed["canonical_page_sha256"])
        self.assertEqual(
            fixed["io_state"],
            {"FF01": 0, "FF72": 1, "FF73": 0, "FF74": 3},
        )

    def test_each_selector_slot_has_an_independent_missing_relocation_control(self) -> None:
        for old_operand in sorted(r316.LATCH_RELOCATIONS):
            with self.subTest(selector=f"FF{old_operand:02X}"):
                writer = next(
                    site for site in r316.OPERAND_SITES
                    if site.old_operand == old_operand and site.access == "write"
                )
                mutant = bytearray(self.candidate)
                mutant[r316.site_offset(writer) + 1] = old_operand
                with self.assertRaises(AssertionError):
                    r316.validate_candidate(self.base, bytes(mutant))

    def test_each_replacement_destination_has_an_independent_mutation_control(self) -> None:
        for old_operand in sorted(r316.LATCH_RELOCATIONS):
            with self.subTest(selector=f"FF{old_operand:02X}"):
                site = next(
                    item for item in r316.OPERAND_SITES
                    if item.old_operand == old_operand
                )
                mutant = bytearray(self.candidate)
                mutant[r316.site_offset(site) + 1] ^= 0x01
                with self.assertRaises(AssertionError):
                    r316.validate_candidate(self.base, bytes(mutant))

    def test_serial_control_pairs_are_unchanged_and_not_introduced(self) -> None:
        # Static decoding found the raw FF02 pairs in tables/art rather than
        # executable code.  r316 must neither touch nor add any of them.
        for opcode in (0xE0, 0xF0):
            pattern = bytes((opcode, 0x02))
            before = [index for index in range(len(self.base) - 1)
                      if self.base[index:index + 2] == pattern]
            after = [index for index in range(len(self.candidate) - 1)
                     if self.candidate[index:index + 2] == pattern]
            self.assertEqual(after, before)
        self.assertNotIn(0x02, r316.LATCH_RELOCATIONS.values())
        for c_value in (0x01, 0x02):
            for indirect_opcode in (0xE2, 0xF2):
                self.assertNotIn(
                    bytes((0x0E, c_value, indirect_opcode)), self.candidate,
                    "immediate C must not feed serial E2/F2 access",
                )
        self.assertIn("SC.bit7 and IE.bit3 remain zero while FF01 is live",
                      self.receipt["required_live_gates"])

    def test_release_contract_is_explicitly_cgb_and_pocket_gated(self) -> None:
        hardware = self.receipt["hardware_contract"]
        self.assertEqual(self.base[0x0143], 0x80)
        self.assertEqual(self.candidate[0x0143], 0xC0)
        self.assertIn("Game Boy Color", hardware["release_mode"])
        self.assertIn("rejected", hardware["DMG"])
        self.assertIn("Pocket/core round-trip", hardware["FF72_FF73_FF74"])
        self.assertIn(
            "Analogue Pocket hardware pass before promotion",
            self.receipt["required_live_gates"],
        )

    def test_checksums_are_exact(self) -> None:
        header = 0
        for value in self.candidate[0x0134:0x014D]:
            header = (header - value - 1) & 0xFF
        self.assertEqual(self.candidate[0x014D], header)
        total = (
            sum(self.candidate[:0x014E]) + sum(self.candidate[0x0150:])
        ) & 0xFFFF
        self.assertEqual(
            int.from_bytes(self.candidate[0x014E:0x0150], "big"), total
        )


if __name__ == "__main__":
    unittest.main()
