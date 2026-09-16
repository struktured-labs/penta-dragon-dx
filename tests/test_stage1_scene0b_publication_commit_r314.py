#!/usr/bin/env python3
"""Static emitted-code, transaction, ABI, and ownership controls for r314."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
DIAGNOSTICS = ROOT / "scripts" / "diagnostics"
sys.path.insert(0, str(DIAGNOSTICS))

import build_stage1_scene0b_publication_commit_r314 as r314  # noqa: E402


EXPECTED_SHA256 = (
    "010f9b78e5294f436d4a6735e799f12546a26827637db5ce1d6646eeff06c303"
)
EXPECTED_RECEIPT_SHA256 = (
    "730ddfb4acc6a71dadf7404ad0e000378fe62972ff87d3a5dd0f315357819bf1"
)


def digest(payload: bytes | bytearray) -> str:
    return hashlib.sha256(payload).hexdigest()


class Stage1Scene0BPublicationCommitR314Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.base = r314.BASE.read_bytes()
        cls.base_receipt = r314.BASE_RECEIPT.read_bytes()
        cls.rejected = r314.REJECTED_LIVE_RECEIPT.read_bytes()
        cls.candidate = r314.DEFAULT_OUTPUT.read_bytes()
        cls.receipt_bytes = r314.DEFAULT_RECEIPT.read_bytes()
        cls.receipt = json.loads(cls.receipt_bytes)

    def test_pinned_identity_and_deterministic_rebuild(self) -> None:
        self.assertEqual(digest(self.base), r314.BASE_SHA256)
        self.assertEqual(digest(self.base_receipt), r314.BASE_RECEIPT_SHA256)
        self.assertEqual(
            digest(self.rejected), r314.REJECTED_LIVE_RECEIPT_SHA256
        )
        self.assertEqual(digest(self.candidate), EXPECTED_SHA256)
        if EXPECTED_RECEIPT_SHA256 != "TO_BE_PINNED":
            self.assertEqual(digest(self.receipt_bytes), EXPECTED_RECEIPT_SHA256)
        rebuilt, receipt = r314.build(
            self.base, self.base_receipt, self.rejected
        )
        self.assertEqual(rebuilt, self.candidate)
        self.assertEqual(
            r314.r305.r304.receipt_bytes(receipt), self.receipt_bytes
        )
        self.assertFalse(receipt["promotable"])
        self.assertFalse(receipt["emulator_invoked"])

    def test_exact_handler_only_delta_and_native_publisher(self) -> None:
        functional = r314.r305.r304.delta(
            self.base, self.candidate, functional=True
        )
        expected = {
            offset for offset in r314.owned_ranges()
            if self.base[offset] != self.candidate[offset]
        }
        self.assertEqual(functional, expected)
        self.assertEqual(len(functional), 262)
        handler = r314.bank_offset(r314.MUX_BANK, r314.HANDLER_ADDR)
        self.assertEqual(
            self.candidate[handler:handler + len(r314.HANDLER)], r314.HANDLER
        )
        self.assertEqual(
            self.candidate[r314.MAIN_PUBLISH_CALL_ADDR:
                           r314.MAIN_PUBLISH_CALL_ADDR
                           + len(r314.MAIN_PUBLISHER)],
            r314.MAIN_PUBLISHER,
        )
        self.assertEqual(self.candidate[0x12EC:0x12EE], bytes.fromhex("E0 40"))
        for offset, (before, after) in enumerate(
            zip(self.base, self.candidate, strict=True)
        ):
            if offset in functional or offset in r314.CHECKSUM_OFFSETS:
                continue
            self.assertEqual(after, before, f"unowned r313 drift at {offset:#x}")

    def test_old_start_marker_and_new_commit_markers_are_exact(self) -> None:
        labels = r314.HANDLER_LABELS
        self.assertEqual(labels["repair_effect"], 0x6D4D)
        self.assertEqual(
            labels["repair_effect"],
            r314.r313.HANDLER_LABELS["repair_effect"],
        )
        self.assertEqual(labels["display_flip_effect"], 0x6E25)
        self.assertEqual(labels["commit_effect"], 0x6E2A)
        handler = r314.bank_offset(r314.MUX_BANK, r314.HANDLER_ADDR)

        def emitted(address: int, before: int, after: int = 0) -> bytes:
            offset = handler + address - r314.HANDLER_ADDR
            return self.candidate[offset - before:offset + after]

        self.assertEqual(
            emitted(labels["repair_effect"], 0, 3),
            bytes((0xC3, labels["arm_transaction"] & 0xFF,
                   labels["arm_transaction"] >> 8)),
        )
        self.assertEqual(
            emitted(labels["display_flip_effect"], 2), bytes.fromhex("E0 40")
        )
        self.assertEqual(
            emitted(labels["commit_effect"], 5), bytes.fromhex("3E C4 EA DE DA")
        )

    def test_transaction_inserts_and_removes_only_private_word(self) -> None:
        contract = r314.transaction_contract()
        self.assertEqual(
            contract["armed_chain"], "[DAD7,3493,42B1,0013,A314,caller]"
        )
        self.assertEqual(contract["completion_chain"], "[12EE,caller]")
        self.assertTrue(contract["older_stack_bytes_exact"])
        self.assertTrue(contract["all_transaction_start_writes_IME_disabled"])
        self.assertEqual(
            contract["commit_order"],
            "completed-map LCDC owner -> DADE CD-to-C4 acknowledgment",
        )
        self.assertEqual(contract["commit_selectors"]["0"]["LCDC"], "83")
        self.assertEqual(contract["commit_selectors"]["1"]["LCDC"], "8B")

    def test_emitted_repair_stack_and_canaries_are_exact(self) -> None:
        state = r314.execute_handler()
        sp = state["initial_sp"]
        self.assertEqual(state["pc"], 0x0061)
        self.assertEqual(state["sp"], sp)
        self.assertEqual(
            [r314._read16(state["mem"], sp + offset)
             for offset in range(0, 12, 2)],
            [0xDAD7, 0x3493, 0x42B1, 0x0013, 0xA314, 0x1357],
        )
        self.assertEqual(bytes(state["mem"][sp + 12:sp + 16]), state["canary"])
        self.assertEqual((state["h"] << 8) | state["l"], state["saved_hl"])

    def test_commit_publishes_before_current_ack_and_preserves_caller(self) -> None:
        for selector, lcdc in ((0, 0x83), (1, 0x8B)):
            state = r314.execute_handler(
                gateway=r314.PENDING_GATEWAY,
                outer_return=r314.TRANSACTION_SENTINEL,
                layout="commit", dc0b=selector,
            )
            sp = state["initial_sp"]
            self.assertEqual(
                r314._owned_writes(state),
                [(0xFF40, lcdc, True), (0xDADE, 0xC4, True)],
            )
            self.assertEqual(state["sp"], sp + 4)
            self.assertEqual(r314._read16(state["mem"], sp + 4), 0x12EE)
            self.assertEqual(r314._read16(state["mem"], sp + 6), 0x1357)
            self.assertEqual(
                bytes(state["mem"][sp + 8:sp + 12]), state["canary"]
            )

    def test_commit_scope_failure_collapses_to_native_selector(self) -> None:
        mutations = (
            {"gateway": r314.STALE_GATEWAY},
            {"scene": 0x02, "gateway": r314.PENDING_GATEWAY},
            {"svbk": 0x02, "gateway": r314.PENDING_GATEWAY},
            {"ffb7": 0x03, "gateway": r314.PENDING_GATEWAY},
        )
        for mutation in mutations:
            state = r314.execute_handler(
                outer_return=r314.TRANSACTION_SENTINEL,
                layout="commit", **mutation,
            )
            sp = state["initial_sp"]
            self.assertEqual(r314._owned_writes(state), [])
            self.assertEqual(state["sp"], sp + 4)
            self.assertEqual(r314._read16(state["mem"], sp + 4), 0x12E0)
            self.assertEqual(r314._read16(state["mem"], sp + 6), 0x1357)

    def test_transaction_arm_is_exclusive_to_exact_primary_stack(self) -> None:
        for key, value in (
            ("dirty_return", 0x42B2),
            ("map_return", 0x0AB8),
        ):
            state = r314.execute_handler(**{key: value})
            sp = state["initial_sp"]
            self.assertEqual(
                r314._owned_writes(state)[:5],
                [
                    (0xDADE, 0xCD, False), (0xDADF, 0x13, False),
                    (0xDAE0, 0x00, False), (0xDF53, 0xFF, False),
                    (0xDF57, 0xFF, False),
                ],
            )
            self.assertEqual(state["sp"], sp + 2)
            self.assertEqual(r314._read16(state["mem"], sp + 2), 0xDAD7)
            self.assertTrue(state["ime"])

    def test_current_hot_paths_keep_r313_handler_cycle_counts(self) -> None:
        for scene in (0x02, 0x0B):
            old = r314.r313.execute_route(
                self.base, scene=scene, svbk=0xF9, ffb7=0x02,
                gateway=r314.CURRENT_GATEWAY,
            )
            old_cycles = sum(
                row[2] for row in old["trace"]
                if r314.r313.HANDLER_ADDR
                <= row[0] < r314.r313.HANDLER_ADDR + len(r314.r313.HANDLER)
            )
            new = r314.execute_handler(
                scene=scene, gateway=r314.CURRENT_GATEWAY
            )
            new_cycles = sum(row[2] for row in new["trace"])
            self.assertEqual(new_cycles, old_cycles)

    def test_semantic_exhaustion_has_no_current_or_pending_writes(self) -> None:
        contract = r314.semantic_contract()
        self.assertEqual(contract["emitted_opcode_executions"], 2053)
        self.assertEqual(contract["scene_values_exhausted"], 256)
        self.assertEqual(contract["raw_SVBK_values_exhausted"], 256)
        self.assertEqual(contract["FFB7_values_exhausted"], 256)
        self.assertEqual(contract["single_gateway_byte_mutations_exhausted"], 768)
        self.assertEqual(contract["outer_low_high_values_exhausted"], 512)
        self.assertEqual(contract["current_gateway_writes"], 0)
        self.assertEqual(contract["pending_gateway_writes"], 0)

    def test_handler_and_candidate_mutations_are_rejected(self) -> None:
        patterns = {
            "pending": (bytes.fromhex("3E CD EA DE DA"), 1),
            "arm-map-return": (bytes.fromhex("F8 08 7E FE E0"), 4),
            "sentinel": (bytes.fromhex("F8 08 36 14 23 36 A3"), 3),
            "continuation": (bytes.fromhex("F8 04 36 EE 23 36 12"), 3),
            "display": (bytes.fromhex("E0 40 3E C4 EA DE DA"), 1),
            "finalize": (bytes.fromhex("3E C4 EA DE DA"), 1),
        }
        original = r314.HANDLER
        try:
            for name, (pattern, relative) in patterns.items():
                offset = original.index(pattern) + relative
                mutant = bytearray(original)
                mutant[offset] ^= 1
                r314.HANDLER = bytes(mutant)
                caught = False
                for contract in (r314.transaction_contract,
                                 r314.semantic_contract):
                    try:
                        contract()
                    except AssertionError:
                        caught = True
                        break
                self.assertTrue(caught, f"{name} mutation survived")
                r314.HANDLER = original
        finally:
            r314.HANDLER = original

        mutant = bytearray(self.candidate)
        mutant[r314.bank_offset(r314.MUX_BANK, r314.HANDLER_ADDR)] ^= 1
        with self.assertRaises(AssertionError):
            r314.validate_candidate(self.base, bytes(mutant))

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
