#!/usr/bin/env python3
"""Offline identity, branch, ownership, and mutation tests for r317."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
DIAGNOSTICS = ROOT / "scripts" / "diagnostics"
sys.path.insert(0, str(DIAGNOSTICS))

import build_stage1_selector_latch_cold_init_r317 as r317  # noqa: E402


EXPECTED_SHA256 = (
    "77e491aa7e34711a245f0586c2434461fc6c8d3e5fad1bca0b3b27fbcfb43da0"
)
EXPECTED_RECEIPT_SHA256 = (
    "e72a095a207fdc1bb86e30b7361ea046484c8acfbb75064faedaca039646706c"
)


def digest(payload: bytes | bytearray) -> str:
    return hashlib.sha256(payload).hexdigest()


def jr_target(address: int, operand: int) -> int:
    displacement = operand if operand < 0x80 else operand - 0x100
    return (address + 2 + displacement) & 0xFFFF


ABSOLUTE_TRANSFER_OPCODES = frozenset({
    0xC2, 0xC3, 0xC4, 0xCA, 0xCC, 0xCD,
    0xD2, 0xD4, 0xDA, 0xDC,
})


def bank_transfer_sites(
    payload: bytes, bank: int, target: int,
) -> list[tuple[int, int]]:
    image = payload[bank * 0x4000:(bank + 1) * 0x4000]
    return [
        (0x4000 + index, image[index])
        for index in range(len(image) - 2)
        if image[index] in ABSOLUTE_TRANSFER_OPCODES
        and image[index + 1] == (target & 0xFF)
        and image[index + 2] == (target >> 8)
    ]


class Stage1SelectorLatchColdInitR317Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.base = r317.BASE.read_bytes()
        cls.base_receipt = r317.BASE_RECEIPT.read_bytes()
        cls.candidate = r317.DEFAULT_OUTPUT.read_bytes()
        cls.receipt_bytes = r317.DEFAULT_RECEIPT.read_bytes()
        cls.receipt = json.loads(cls.receipt_bytes)
        cls.relocated, _ = r317.r316.build(
            cls.base, cls.base_receipt
        )

    def test_pinned_identity_and_deterministic_rebuild(self) -> None:
        self.assertEqual(digest(self.base), r317.BASE_SHA256)
        self.assertEqual(
            digest(self.base_receipt), r317.BASE_RECEIPT_SHA256
        )
        self.assertEqual(digest(self.relocated), r317.RELOCATION_SHA256)
        self.assertEqual(digest(self.candidate), EXPECTED_SHA256)
        self.assertEqual(r317.EXPECTED_CANDIDATE_SHA256, EXPECTED_SHA256)
        self.assertEqual(digest(self.receipt_bytes), EXPECTED_RECEIPT_SHA256)
        rebuilt, receipt = r317.build(self.base, self.base_receipt)
        self.assertEqual(rebuilt, self.candidate)
        self.assertEqual(
            r317.r305.r304.receipt_bytes(receipt), self.receipt_bytes
        )
        self.assertFalse(receipt["promotable"])
        self.assertFalse(receipt["emulator_invoked"])

    def test_dispatcher_consumes_only_its_exact_three_byte_pad(self) -> None:
        start = r317.DISPATCH_OFFSET
        stop = start + len(r317.DISPATCH_REPLACEMENT)
        self.assertEqual(
            self.relocated[start:stop], r317.DISPATCH_PREIMAGE
        )
        self.assertEqual(
            self.candidate[start:stop], r317.DISPATCH_REPLACEMENT
        )
        self.assertEqual(len(r317.DISPATCH_PREIMAGE), 36)
        self.assertEqual(len(r317.DISPATCH_REPLACEMENT), 36)
        self.assertEqual(r317.DISPATCH_PREIMAGE[-3:], bytes(3))
        self.assertEqual(
            self.candidate[stop:stop + 32], self.relocated[stop:stop + 32]
        )
        self.assertEqual(
            self.receipt["ownership"]["trailing_pad_consumed_bytes"], 3
        )
        self.assertEqual(
            self.receipt["ownership"]["rom_size_delta_bytes"], 0
        )

    def test_dispatcher_targets_and_cold_only_write_are_exact(self) -> None:
        code = r317.DISPATCH_REPLACEMENT
        self.assertEqual(code[7:9], bytes.fromhex("38 18"))
        self.assertEqual(
            jr_target(r317.DISPATCH_ADDR + 7, code[8]), 0x5D8B
        )
        self.assertEqual(code[22:24], bytes.fromhex("28 06"))
        self.assertEqual(
            jr_target(r317.DISPATCH_ADDR + 22, code[23]), 0x5D88
        )
        self.assertEqual(
            code[24:30], bytes.fromhex("AF E0 72 C3 40 59")
        )
        self.assertEqual(code[30:33], bytes.fromhex("C3 FC C4"))
        self.assertEqual(code[33:36], bytes.fromhex("3E 01 C9"))

    def test_exhaustive_dispatch_model_partitions_and_preserves_live_state(self) -> None:
        contract = r317.dispatcher_contract()
        self.assertEqual(contract["input_tuples"], 2304)
        self.assertTrue(all(contract["route_counts"].values()))
        for scene in range(0x100):
            for c602 in (0x00, 0x04, 0xFF):
                for c5ff in (0x00, 0xC9, 0xFF):
                    result = r317.dispatch_route(scene, c602, c5ff)
                    if result["route"] == "not-installed":
                        self.assertEqual(result["token_write"], 0)
                        self.assertEqual(result["target"], 0x5940)
                    else:
                        self.assertIsNone(result["token_write"])
        self.assertEqual(
            r317.dispatch_route(0x0B, 0x00, 0xC9),
            {
                "route": "installed-hot",
                "target": 0xC4FC,
                "token_write": None,
            },
        )
        self.assertEqual(
            r317.dispatch_route(0x0B, 0x00, 0x00),
            {
                "route": "not-installed",
                "target": 0x5940,
                "token_write": 0,
            },
        )
        for incoming in (0x53, 0x57):
            with self.subTest(incoming=incoming):
                self.assertEqual(
                    r317.dispatched_token_after(
                        0x0B, 0x00, 0x00, incoming
                    ),
                    0,
                )
                self.assertEqual(
                    r317.dispatched_token_after(
                        0x0B, 0x00, 0xC9, incoming
                    ),
                    incoming,
                )

    def test_only_audited_relocation_header_and_dispatcher_bytes_change(self) -> None:
        overlay = {
            offset for offset, (before, after) in
            enumerate(zip(self.relocated, self.candidate, strict=True))
            if before != after and offset not in r317.r316.CHECKSUM_OFFSETS
        }
        expected_overlay = {
            r317.DISPATCH_OFFSET + relative
            for relative in r317.DISPATCH_CHANGED_RELATIVE_OFFSETS
        }
        self.assertEqual(overlay, expected_overlay)
        self.assertEqual(len(overlay), 13)

        total = {
            offset for offset, (before, after) in
            enumerate(zip(self.base, self.candidate, strict=True))
            if before != after and offset not in r317.r316.CHECKSUM_OFFSETS
        }
        relocated_operands = {
            r317.r316.site_offset(site) + 1
            for site in r317.r316.OPERAND_SITES
        }
        self.assertEqual(
            total,
            relocated_operands
            | {r317.r316.CGB_FLAG_OFFSET}
            | expected_overlay,
        )
        self.assertEqual(len(total), 68)
        self.assertEqual(self.receipt["ownership"]["escaped_bytes"], 0)

    def test_first_read_and_other_local_initializers_remain_exact(self) -> None:
        first_read = r317.r316.bank_offset(
            r317.DISPATCH_BANK, r317.TOKEN_FIRST_READ_ADDR
        )
        self.assertEqual(
            self.candidate[
                first_read:first_read + len(r317.TOKEN_FIRST_READ)
            ],
            r317.TOKEN_FIRST_READ,
        )
        local_init = r317.r316.bank_offset(
            r317.DISPATCH_BANK, r317.LOCAL_LATCH_INIT_ADDR
        )
        self.assertEqual(
            self.candidate[
                local_init:local_init + len(r317.LOCAL_LATCH_INIT)
            ],
            r317.LOCAL_LATCH_INIT,
        )
        contract = self.receipt["first_use_contract"]
        self.assertIn(
            "installed $C52B",
            contract["sole_missing_definition_before_r317"],
        )
        self.assertIn("no active map anchor",
                      contract["intended_initial_semantics"])
        installer = r317.r316.bank_offset(
            r317.DISPATCH_BANK, r317.INSTALLER_ADDR
        )
        self.assertEqual(
            self.candidate[
                installer:installer + len(r317.INSTALLER)
            ],
            r317.INSTALLER,
        )
        self.assertIn(
            "C4F3/C4F5",
            contract["discarded_deferred_token_semantics"],
        )

    def test_bank13_and_bank16_installed_runtime_dominance_is_exact(self) -> None:
        bank13_final = r317.r316.bank_offset(
            r317.DISPATCH_BANK, r317.BANK13_INSTALL_FINAL_ADDR
        )
        self.assertEqual(
            self.candidate[
                bank13_final:
                bank13_final + len(r317.BANK13_INSTALL_FINAL)
            ],
            r317.BANK13_INSTALL_FINAL,
        )
        self.assertEqual(0xC520 + (0x57C7 - 0x57BC), 0xC52B)
        self.assertEqual(
            bank_transfer_sites(self.candidate, 13, 0x5940),
            [(0x5D85, 0xC3)],
        )
        self.assertEqual(
            bank_transfer_sites(self.candidate, 13, 0xC4FC),
            [(0x5D88, 0xC3), (0x5E7C, 0xC3)],
        )
        for target in (0x578C, 0x57BC, 0x57C7, 0xC52B):
            with self.subTest(bank=13, target=target):
                self.assertEqual(
                    bank_transfer_sites(self.candidate, 13, target), []
                )

        self.assertEqual(
            self.candidate[
                r317.BANK16_PRIVATE_CALL_ADDR:
                r317.BANK16_PRIVATE_CALL_ADDR
                + len(r317.BANK16_PRIVATE_CALL)
            ],
            r317.BANK16_PRIVATE_CALL,
        )
        for address, expected in (
            (r317.BANK16_PRIVATE_ENTRY_ADDR,
             r317.BANK16_PRIVATE_ENTRY),
            (r317.BANK16_CACHED_DISPATCH_ADDR,
             r317.BANK16_CACHED_DISPATCH),
            (r317.BANK16_CACHED_FIRST_READ_ADDR,
             r317.BANK16_CACHED_FIRST_READ),
            (r317.BANK16_CACHED_INSTALL_FINAL_ADDR,
             r317.BANK16_CACHED_INSTALL_FINAL),
        ):
            with self.subTest(bank=16, address=address):
                offset = r317.r316.bank_offset(16, address)
                self.assertEqual(
                    self.candidate[offset:offset + len(expected)], expected
                )
        self.assertEqual(0xC53D + (0x58F3 - 0x58E0), 0xC550)
        self.assertEqual(
            bank_transfer_sites(self.candidate, 16, 0x5940),
            [(0x5CE2, 0xC3), (0x5D79, 0xC3)],
        )
        self.assertEqual(
            bank_transfer_sites(self.candidate, 16, 0xC4F5),
            [(0x5CDF, 0xCA), (0x7008, 0xC3)],
        )

    def test_every_dispatcher_changed_byte_has_a_mutation_control(self) -> None:
        for relative in sorted(r317.DISPATCH_CHANGED_RELATIVE_OFFSETS):
            with self.subTest(relative=relative):
                mutant = bytearray(self.candidate)
                mutant[r317.DISPATCH_OFFSET + relative] ^= 0x01
                with self.assertRaises(AssertionError):
                    r317.validate_candidate(
                        self.base, self.relocated, bytes(mutant)
                    )

    def test_four_latch_relocation_and_collision_control_survive(self) -> None:
        self.assertEqual(len(r317.r316.OPERAND_SITES), 54)
        for site in r317.r316.OPERAND_SITES:
            offset = r317.r316.site_offset(site)
            self.assertEqual(
                self.candidate[offset:offset + 2],
                bytes((site.opcode, site.new_operand)),
            )
        collision = self.receipt["relocation"][
            "native_selector_collision_control"
        ]
        self.assertEqual(
            collision["r314_negative_control"]["mismatch_page_indices"],
            [1, 3, 4, 5],
        )
        self.assertEqual(collision["r316"]["selector_hex"],
                         "1011121314151617")
        self.assertEqual(collision["r316"]["mismatch_page_indices"], [])

    def test_serial_vector_ie_init_and_dynamic_gates_are_explicit(self) -> None:
        self.assertEqual(
            self.candidate[
                r317.SERIAL_VECTOR_ADDR:
                r317.SERIAL_VECTOR_ADDR + len(r317.SERIAL_VECTOR)
            ],
            r317.SERIAL_VECTOR,
        )
        ie_init = r317.r316.bank_offset(
            r317.IE_INIT_BANK, r317.IE_INIT_ADDR
        )
        self.assertEqual(
            self.candidate[ie_init:ie_init + len(r317.IE_INIT)],
            r317.IE_INIT,
        )
        gates = self.receipt["required_live_gates"]
        self.assertIn(
            "every executed E2/F2 has C outside {01,02,72,73,74}",
            gates,
        )
        self.assertIn(
            "every live CPU access to FF01/FF72/FF73/FF74 matches an audited relocated owner, installed mirror, or bank13:$5D83 init; FF02 has zero live accesses",
            gates,
        )
        self.assertIn(
            "SC.bit7 and IE.bit3 remain zero while FF01 is live", gates
        )
        self.assertNotIn(
            "no SC access", self.receipt["hardware_contract"]["FF01"]
        )

    def test_runtime_install_gates_reject_stale_savestate_code(self) -> None:
        gates = self.receipt["required_live_gates"]
        self.assertIn(
            "fresh Stage1 install exercises FF01 core/row owners", gates
        )
        self.assertIn(
            "fresh Stage2 install byte-audits and exercises D400 FF01 owners",
            gates,
        )
        self.assertIn(
            "fresh Stage7 install byte-audits and exercises DA13/dual-plane FF01 owners",
            gates,
        )
        self.assertIn(
            "fresh Ted install byte-audits and exercises C4F5/C4FC FF72/FF73/FF74 owners",
            gates,
        )
        self.assertIn(
            "fresh bank13 install byte-audits source $57BC:$57C7 -> installed $C520:$C52B and observes bank13:$5D83 FF72=00 before $C52B",
            gates,
        )
        self.assertIn(
            "fresh bank16 install byte-audits source $58E0:$58F3 -> installed $C53D:$C550 and observes bank16:$7003 FF72=00 before $7008->$C4F5/$C550",
            gates,
        )

    def test_cgb_header_timing_and_checksums_are_exact(self) -> None:
        self.assertEqual(self.base[0x0143], 0x80)
        self.assertEqual(self.candidate[0x0143], 0xC0)
        timing = self.receipt["timing"]
        self.assertEqual(timing["not_installed_delta_t"], 16)
        self.assertEqual(timing["installed_hot_delta_t"], 0)
        self.assertEqual(timing["later_dungeon_delta_t"], 0)

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
        self.assertEqual(self.candidate[0x014D], 0xB9)
        self.assertEqual(
            int.from_bytes(self.candidate[0x014E:0x0150], "big"), 0x0DE4
        )


if __name__ == "__main__":
    unittest.main()
