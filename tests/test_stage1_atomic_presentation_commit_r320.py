#!/usr/bin/env python3
"""Offline identity, atomicity, ABI, timing, and mutation gates for r320."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
DIAGNOSTICS = ROOT / "scripts" / "diagnostics"
sys.path.insert(0, str(DIAGNOSTICS))

import build_stage1_atomic_presentation_commit_r320 as r320  # noqa: E402


EXPECTED_SHA256 = (
    "1bbe2d1d3950b1a6f1a194de42fbf5b5e31b26671b037635c42cbd3013d35ae7"
)
EXPECTED_RECEIPT_SHA256 = (
    "9ed345f166f16eae4d94fc69d06ddef51fdbdf195dad4ca50b106aa110c2018b"
)


def digest(payload: bytes | bytearray) -> str:
    return hashlib.sha256(payload).hexdigest()


class Stage1AtomicPresentationCommitR320Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.base = r320.BASE.read_bytes()
        cls.base_receipt = r320.BASE_RECEIPT.read_bytes()
        cls.candidate = r320.DEFAULT_OUTPUT.read_bytes()
        cls.receipt_bytes = r320.DEFAULT_RECEIPT.read_bytes()
        cls.receipt = json.loads(cls.receipt_bytes)

    def test_pinned_identity_receipt_and_deterministic_rebuild(self) -> None:
        self.assertEqual(digest(self.base), r320.BASE_SHA256)
        self.assertEqual(r320.BASE_SHA256,
                         r320.r319.EXPECTED_CANDIDATE_SHA256)
        self.assertEqual(digest(self.base_receipt),
                         r320.BASE_RECEIPT_SHA256)
        self.assertEqual(digest(self.candidate), EXPECTED_SHA256)
        self.assertEqual(r320.EXPECTED_CANDIDATE_SHA256, EXPECTED_SHA256)
        self.assertEqual(digest(self.receipt_bytes),
                         EXPECTED_RECEIPT_SHA256)
        self.assertEqual(self.receipt["candidate_sha256"], EXPECTED_SHA256)
        rebuilt, receipt = r320.build(self.base, self.base_receipt)
        self.assertEqual(rebuilt, self.candidate)
        self.assertEqual(
            r320.r319.r318.r317.r305.r304.receipt_bytes(receipt),
            self.receipt_bytes,
        )
        self.assertFalse(receipt["promotable"])
        self.assertFalse(receipt["emulator_invoked"])

    def test_exact_functional_delta_and_canonical_checksums(self) -> None:
        changed = {
            offset
            for offset, (before, after) in enumerate(
                zip(self.base, self.candidate, strict=True)
            )
            if before != after
        }
        functional = changed - r320.CHECKSUM_OFFSETS
        self.assertEqual(functional, r320.owned_ranges())
        self.assertEqual(len(functional), 35)
        self.assertEqual(len(r320.primary_changed_offsets()), 32)
        self.assertEqual(len(r320.scene0b_changed_offsets()), 3)
        self.assertLessEqual(
            changed, r320.owned_ranges() | r320.CHECKSUM_OFFSETS
        )
        self.assertEqual(changed & r320.CHECKSUM_OFFSETS,
                         {0x014E, 0x014F})
        checksummed = bytearray(self.candidate)
        r320.r319.r318.r317.r305.r304.update_checksums(checksummed)
        self.assertEqual(bytes(checksummed), self.candidate)
        ownership = self.receipt["ownership"]
        self.assertEqual(ownership["functional_changed_bytes_from_r319"], 35)
        self.assertEqual(ownership["escaped_bytes"], 0)
        self.assertEqual(ownership["rom_size_delta_bytes"], 0)

    def test_primary_leaf_is_exact_width_scroll_first_atomic_commit(self) -> None:
        self.assertEqual(len(r320.OLD_PRIMARY), 35)
        self.assertEqual(len(r320.NEW_PRIMARY), 35)
        self.assertEqual(r320.PRIMARY_END - r320.PRIMARY_ADDR, 35)
        self.assertEqual(
            self.base[r320.PRIMARY_ADDR:r320.PRIMARY_END],
            r320.OLD_PRIMARY,
        )
        self.assertEqual(
            self.candidate[r320.PRIMARY_ADDR:r320.PRIMARY_END],
            r320.NEW_PRIMARY,
        )
        contract = r320.primary_static_contract()
        self.assertEqual(contract["DI"], "$12E0")
        self.assertEqual(contract["SCX_write"], "$12EC")
        self.assertEqual(contract["SCY_write"], "$12F3")
        self.assertEqual(contract["LCDC_write"], "$12FF")
        self.assertEqual(contract["EI"], "$1301")
        self.assertEqual(contract["RET"], "$1302")
        self.assertEqual(
            contract["write_order"], ["FF43 optional", "FF42", "FF40"]
        )
        self.assertEqual(
            r320.jr_target(0x12E5, r320.NEW_PRIMARY[6]), 0x12EE
        )
        self.assertEqual(
            r320.jr_target(0x12FB, r320.NEW_PRIMARY[28]), 0x12FF
        )
        self.assertLess(
            r320.OLD_PRIMARY.index(bytes.fromhex("E0 40")),
            r320.OLD_PRIMARY.index(bytes.fromhex("E0 42")),
        )
        self.assertGreater(
            r320.NEW_PRIMARY.index(bytes.fromhex("E0 40")),
            r320.NEW_PRIMARY.index(bytes.fromhex("E0 42")),
        )

    def test_zero_nonzero_selector_semantics_are_exhaustive(self) -> None:
        counts = {0x83: 0, 0x8B: 0}
        for dc0b in range(0x100):
            expected = 0x83 if dc0b == 0 else 0x8B
            self.assertEqual(r320.lcdc_from_dc0b(dc0b), expected)
            for ff97 in (0x00, 0x02, 0xFF):
                result = r320.primary_publisher_model(
                    ff97=ff97, dc00=0xAC, dc02=0x5E,
                    dc0b=dc0b, incoming_scx=0x77,
                )
                self.assertEqual(result["lcdc"], expected)
                self.assertEqual(result["writes"][-1],
                                 ("FF40", expected, False))
                self.assertTrue(result["final_ime"])
                self.assertEqual(result["return"], 0x01F0)
                counts[expected] += 1
        self.assertEqual(counts, {0x83: 3, 0x8B: 765})
        self.assertEqual(
            self.receipt["offline_contract"]["exhaustive"]
            ["selector_cases_exhausted"],
            768,
        )

    def test_ff97_scx_and_dc02_scy_domains_are_exhaustive(self) -> None:
        scx_cases = 0
        for ff97 in range(0x100):
            for dc00 in range(0x100):
                result = r320.primary_publisher_model(
                    ff97=ff97, dc00=dc00, dc02=0xAE,
                    dc0b=0, incoming_scx=0x5C,
                )
                self.assertEqual(
                    result["scx"], 0x5C if ff97 == 2 else dc00 & 0x0F
                )
                self.assertEqual(result["scy"], 0x0E)
                self.assertEqual(result["writes"][-1][0], "FF40")
                self.assertTrue(all(not write[2]
                                    for write in result["writes"]))
                scx_cases += 1
        self.assertEqual(scx_cases, 65536)

        scy_cases = 0
        for dc02 in range(0x100):
            for dc0b in (0x00, 0x01, 0x80, 0xFF):
                result = r320.primary_publisher_model(
                    ff97=2, dc00=0, dc02=dc02,
                    dc0b=dc0b, incoming_scx=0x0C,
                )
                self.assertEqual(result["writes"][0],
                                 ("FF42", dc02 & 0x0F, False))
                scy_cases += 1
        self.assertEqual(scy_cases, 1024)

    def test_cycle_model_and_exact_caller_return_abi(self) -> None:
        expected = {
            (2, 0): 144,
            (2, 1): 148,
            (0, 0): 176,
            (0, 1): 180,
        }
        for (ff97, dc0b), cycles in expected.items():
            with self.subTest(ff97=ff97, dc0b=dc0b):
                result = r320.primary_publisher_model(
                    ff97=ff97, dc00=0, dc02=0,
                    dc0b=dc0b, incoming_scx=0,
                )
                self.assertEqual(result["t_cycles"], cycles)
        self.assertEqual(
            self.base[
                r320.PUBLISHER_ENTRY_ADDR:
                r320.PUBLISHER_ENTRY_ADDR + len(r320.PUBLISHER_ENTRY_PREFIX)
            ],
            bytes.fromhex(
                "B7 CA 03 13 4F CD 3F 42 CD 50 42 D5 E5 45 4B C5 CD 22 13"
            ),
        )
        self.assertEqual(
            self.candidate[
                r320.PUBLISHER_CALL_ADDR:
                r320.PUBLISHER_CALL_ADDR + len(r320.PUBLISHER_CALL)
            ],
            bytes.fromhex("CD A0 12"),
        )
        self.assertEqual(
            r320.fixed_target_census(
                self.candidate, r320.PUBLISHER_ENTRY_ADDR
            ),
            [(0x01ED, 0xCD)],
        )
        self.assertEqual(
            self.candidate[
                r320.PUBLISHER_RETURN_ADDR:
                r320.PUBLISHER_RETURN_ADDR
                + len(r320.PUBLISHER_RETURN_CONTINUATION)
            ],
            bytes.fromhex(
                "F0 CC 3C E6 01 E0 CC C8 F0 CD 3C E6 03 E0 CD C3 78 0B"
            ),
        )
        self.assertEqual(
            self.receipt["offline_contract"]["ABI"]["post_publish_PC"],
            "$01F0",
        )
        self.assertEqual(
            self.receipt["offline_contract"]["ABI"]
            ["publisher_target_census"],
            ["fixed:$01ED CALL $12A0"],
        )

    def test_scene0b_success_and_abort_converge_on_atomic_leaf(self) -> None:
        continuation = r320.bank_offset(
            r320.SCENE0B_BANK, r320.SCENE0B_CONTINUATION_ADDR
        )
        flip = r320.bank_offset(
            r320.SCENE0B_BANK, r320.SCENE0B_FLIP_ADDR
        )
        ack = r320.bank_offset(
            r320.SCENE0B_BANK, r320.SCENE0B_ACK_ADDR
        )
        abort = r320.bank_offset(
            r320.SCENE0B_BANK, r320.SCENE0B_ABORT_ADDR
        )
        self.assertEqual(self.base[continuation], 0xEE)
        self.assertEqual(self.candidate[continuation], 0xE0)
        self.assertEqual(self.base[flip:flip + 2], bytes.fromhex("E0 40"))
        self.assertEqual(self.candidate[flip:flip + 2],
                         bytes.fromhex("F3 00"))
        self.assertEqual(self.candidate[ack:ack + 5],
                         bytes.fromhex("3E C4 EA DE DA"))
        self.assertEqual(
            self.candidate[abort:abort + len(r320.SCENE0B_ABORT_CONTINUATION)],
            r320.SCENE0B_ABORT_CONTINUATION,
        )
        self.assertNotIn(
            bytes.fromhex("E0 40"),
            self.candidate[flip:ack],
        )
        self.assertEqual(
            self.receipt["patch"]["scene0B"]["continuation"],
            "bank31:$6E11 EE->E0 ($12EE->$12E0)",
        )
        contract = r320.scene0b_static_contract(self.candidate)
        self.assertEqual(contract["private_FF40_writes"], 0)
        self.assertEqual(contract["success_stack_continuation"], "$12E0")
        self.assertEqual(contract["abort_stack_continuation"], "$12E0")
        self.assertTrue(contract["success_ack_interrupt_closed"])
        self.assertTrue(
            contract["all_presentation_paths_reach_fixed_EI_1301"]
        )
        self.assertTrue(
            contract["no_interrupt_visible_write_before_path_DI"]
        )
        self.assertEqual(
            contract["success_order"],
            [
                "DI bank31:$6E23",
                "DADE=$C4 bank31:$6E25",
                "mapper fixed:$0061->$09BE RET",
                "continuation fixed:$12E0 DI",
                "SCX fixed:$12EC (optional)",
                "SCY fixed:$12F3",
                "LCDC fixed:$12FF",
                "matching EI fixed:$1301",
                "RET fixed:$1302 -> caller:$01F0",
            ],
        )
        self.assertEqual(contract["ordinary_order"][-2],
                         "matching EI fixed:$1301")
        self.assertEqual(contract["abort_order"][-2],
                         "matching EI fixed:$1301")

    def test_whole_rom_selector_clone_census_eliminates_unsafe_copies(self) -> None:
        self.assertEqual(
            r320.sequence_census(
                self.base, r320.LCDC_SELECTOR_ZERO_BRANCH
            ),
            list(r320.BASE_SELECTOR_OFFSETS),
        )
        self.assertEqual(
            r320.unsafe_selector_census(self.base),
            list(r320.UNSAFE_SELECTOR_OFFSETS),
        )
        self.assertEqual(
            r320.sequence_census(
                self.candidate, r320.LCDC_SELECTOR_ZERO_BRANCH
            ),
            list(r320.SAFE_SELECTOR_OFFSETS),
        )
        self.assertEqual(r320.unsafe_selector_census(self.candidate), [])
        self.assertEqual(
            r320.sequence_census(self.candidate, r320.NO_SCROLL_SELECTOR),
            list(r320.NO_SCROLL_SELECTOR_OFFSETS),
        )
        census = self.receipt["offline_contract"]["selector_clone_census"]
        self.assertEqual(
            census["r319_unsafe_LCDC_first_offsets"],
            ["0x0012E0", "0x07EE17"],
        )
        self.assertEqual(census["r320_unsafe_LCDC_first_offsets"], [])

    def test_r319_semantic_and_cgb_fixes_survive_byte_exact(self) -> None:
        for address in r320.r319.TRAMPOLINE_ADDRS:
            offset = r320.r319.bank_offset(r320.r319.BANK, address)
            self.assertEqual(
                self.base[offset:offset + len(r320.r319.NEW_TRAMPOLINE)],
                r320.r319.NEW_TRAMPOLINE,
            )
            self.assertEqual(
                self.candidate[offset:offset + len(r320.r319.NEW_TRAMPOLINE)],
                r320.r319.NEW_TRAMPOLINE,
            )
        cgb = r320.r319.r318.r317.r316.CGB_FLAG_OFFSET
        self.assertEqual(
            self.candidate[cgb],
            r320.r319.r318.r317.r316.CGB_ONLY_FLAG,
        )

    def test_every_primary_and_scene0b_target_mutation_fails_closed(self) -> None:
        targets = set(range(r320.PRIMARY_ADDR, r320.PRIMARY_END))
        for address, payload in (
            (r320.PUBLISHER_ENTRY_ADDR, r320.PUBLISHER_ENTRY_PREFIX),
            (r320.PUBLISHER_CALL_ADDR, r320.PUBLISHER_CALL),
            (r320.PUBLISHER_RETURN_ADDR,
             r320.PUBLISHER_RETURN_CONTINUATION),
            (r320.MAPPER_ENTRY_ADDR, r320.MAPPER_ENTRY),
            (r320.MAPPER_BODY_ADDR, r320.MAPPER_BODY),
        ):
            targets.update(range(address, address + len(payload)))
        for address in (*r320.SAFE_SELECTOR_OFFSETS,
                        *r320.NO_SCROLL_SELECTOR_OFFSETS):
            payload = (
                r320.LCDC_SELECTOR_ZERO_BRANCH
                if address in r320.SAFE_SELECTOR_OFFSETS
                else r320.NO_SCROLL_SELECTOR
            )
            targets.update(range(address, address + len(payload)))
        for address, payload in (
            (r320.SCENE0B_CONTINUATION_ADDR,
             bytes((r320.SCENE0B_CONTINUATION_NEW,))),
            (r320.SCENE0B_FLIP_ADDR, r320.SCENE0B_FLIP_NEW),
            (r320.SCENE0B_ACK_ADDR, r320.SCENE0B_ACK),
            (r320.SCENE0B_TAIL_ADDR, r320.SCENE0B_TAIL),
            (r320.SCENE0B_ABORT_ADDR, r320.SCENE0B_ABORT_CONTINUATION),
        ):
            offset = r320.bank_offset(r320.SCENE0B_BANK, address)
            targets.update(range(offset, offset + len(payload)))
        for offset in sorted(targets):
            with self.subTest(offset=f"0x{offset:06X}"):
                mutant = bytearray(self.candidate)
                mutant[offset] ^= 0x01
                with self.assertRaises(AssertionError):
                    r320.validate_candidate(self.base, bytes(mutant))

        mutations = self.receipt["offline_contract"]["mutation"]
        self.assertEqual(mutations["owned_byte_mutations"], 35)
        self.assertEqual(mutations["owned_byte_mutations_rejected"], 35)
        self.assertEqual(mutations["boundary_mutations"], 6)
        self.assertEqual(mutations["boundary_mutations_rejected"], 6)

    def test_wrong_base_and_receipt_fail_closed(self) -> None:
        bad_base = bytearray(self.base)
        bad_base[r320.PRIMARY_ADDR] ^= 0x01
        with self.assertRaises(AssertionError):
            r320.build(bytes(bad_base), self.base_receipt)
        bad_handler_base = bytearray(self.base)
        bad_handler_base[r320.bank_offset(
            r320.SCENE0B_BANK, r320.SCENE0B_FLIP_ADDR
        )] ^= 0x01
        with self.assertRaises(AssertionError):
            r320.build(bytes(bad_handler_base), self.base_receipt)
        bad_receipt = bytearray(self.base_receipt)
        bad_receipt[-2] ^= 0x01
        with self.assertRaises(AssertionError):
            r320.build(self.base, bytes(bad_receipt))


if __name__ == "__main__":
    unittest.main()
