#!/usr/bin/env python3
"""Static emitted-code, ownership, ABI, and timing controls for r313."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
DIAGNOSTICS = ROOT / "scripts" / "diagnostics"
sys.path.insert(0, str(DIAGNOSTICS))

import build_stage1_scene0b_runtime_selfheal_r313 as r313  # noqa: E402


EXPECTED_SHA256 = (
    "07e12b47c1561822c7dbe2c9f7d739c418ad6fcbb1822d2fa06726c705ec82e8"
)
EXPECTED_RECEIPT_SHA256 = (
    "c4086dc2d7186d8e6b9c88829d130034b64fee83783a9314944023f44138ba96"
)


def digest(payload: bytes | bytearray) -> str:
    return hashlib.sha256(payload).hexdigest()


class Stage1Scene0BRuntimeSelfhealR313Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.base = r313.BASE.read_bytes()
        cls.base_receipt = r313.BASE_RECEIPT.read_bytes()
        cls.candidate = r313.DEFAULT_OUTPUT.read_bytes()
        cls.receipt_bytes = r313.DEFAULT_RECEIPT.read_bytes()
        cls.receipt = json.loads(cls.receipt_bytes)

    def test_pinned_identity_and_deterministic_rebuild(self) -> None:
        self.assertEqual(digest(self.base), r313.BASE_SHA256)
        self.assertEqual(digest(self.base_receipt), r313.BASE_RECEIPT_SHA256)
        self.assertEqual(digest(self.candidate), EXPECTED_SHA256)
        self.assertEqual(digest(self.receipt_bytes), EXPECTED_RECEIPT_SHA256)
        rebuilt, receipt = r313.build(self.base, self.base_receipt)
        self.assertEqual(rebuilt, self.candidate)
        self.assertEqual(
            r313.r305.r304.receipt_bytes(receipt), self.receipt_bytes
        )
        self.assertFalse(receipt["promotable"])
        self.assertFalse(receipt["emulator_invoked"])

    def test_exact_owned_delta_and_nonlive_vector_route(self) -> None:
        functional = r313.r305.r304.delta(
            self.base, self.candidate, functional=True
        )
        expected = {
            offset for offset in r313.owned_ranges()
            if self.base[offset] != self.candidate[offset]
        }
        self.assertEqual(functional, expected)
        self.assertEqual(len(functional), 119)
        self.assertEqual(functional & set(range(0x18, 0x20)), {0x1B, 0x1C})
        self.assertEqual(
            self.candidate[0x18:0x20],
            bytes.fromhex("7A 3C CA 13 00 C3 80 DB"),
        )
        # D!=$FF still falls through to the exact JP $DB80 bytes/control.
        self.assertEqual(self.candidate[0x1D:0x20], self.base[0x1D:0x20])
        for offset, (before, after) in enumerate(
            zip(self.base, self.candidate, strict=True)
        ):
            if offset in functional or offset in r313.CHECKSUM_OFFSETS:
                continue
            self.assertEqual(after, before, f"unowned r312 drift at {offset:#x}")

    def test_exact_stack_key_native_di_ei_and_dirty_tail_preimages(self) -> None:
        self.assertEqual(self.candidate[0x3492:0x3494], bytes.fromhex("DF C9"))
        self.assertEqual(
            self.candidate[r313.RST18_CALLSITE_ADDR:
                           r313.RST18_CALLSITE_ADDR + len(r313.RST18_CALLSITE)],
            r313.RST18_CALLSITE,
        )
        self.assertEqual(
            self.candidate[r313.DIRTY_RETURN_ADDR:
                           r313.DIRTY_RETURN_ADDR + len(r313.DIRTY_RETURN)],
            r313.DIRTY_RETURN,
        )
        self.assertEqual(
            self.candidate[r313.ATOMIC_COPY_DI_ADDR:
                           r313.ATOMIC_COPY_DI_ADDR + len(r313.ATOMIC_COPY_DI)],
            r313.ATOMIC_COPY_DI,
        )
        self.assertEqual(
            self.candidate[r313.ATOMIC_COPY_EI_ADDR:
                           r313.ATOMIC_COPY_EI_ADDR + len(r313.ATOMIC_COPY_EI)],
            r313.ATOMIC_COPY_EI,
        )
        tail = r313.bank_offset(r313.DIRTY_TAIL_BANK, r313.DIRTY_TAIL_ADDR)
        self.assertEqual(
            self.candidate[tail:tail + len(r313.DIRTY_TAIL)], r313.DIRTY_TAIL
        )

    def test_emitted_semantics_exhaust_all_dimensions(self) -> None:
        semantic = r313.semantic_contract(self.base)
        self.assertEqual(semantic["emitted_opcode_executions"], 2052)
        self.assertEqual(semantic["scene_values_exhausted"], 256)
        self.assertEqual(semantic["raw_SVBK_values_exhausted"], 256)
        self.assertEqual(semantic["FFB7_values_exhausted"], 256)
        self.assertEqual(semantic["single_gateway_byte_mutations_exhausted"], 768)
        self.assertEqual(semantic["outer_low_high_values_exhausted"], 512)
        self.assertTrue(semantic["all_repair_writes_IME_disabled"])
        self.assertEqual(semantic["current_gateway_cache_writes"], 0)
        self.assertEqual(semantic["unknown_gateway_writes"], 0)

    def test_emitted_timing_is_derived_and_exact(self) -> None:
        timing = r313.timing_contract(self.base)
        self.assertEqual(
            timing["paths"]["scene0B_current"],
            {
                "fixed_dispatch_mux_prefix": 220,
                "handler_through_mapper_jump": 304,
                "final_mapper": 76,
                "delta_t_cycles": 600,
            },
        )
        self.assertEqual(timing["paths"]["scene02_current"]["delta_t_cycles"], 460)
        self.assertEqual(
            timing["paths"]["scene0B_exact_legacy_repair"]["delta_t_cycles"],
            768,
        )
        self.assertEqual(timing["steady_average_t_per_frame"], "85.19")
        self.assertEqual(timing["steady_frame_budget_fraction"], "0.1213%")

    def test_repair_is_atomic_and_returns_dirty_for_both_maps(self) -> None:
        expected_writes = [
            (0xDADE, 0xC4, False), (0xDADF, 0x13, False),
            (0xDAE0, 0x00, False), (0xDF53, 0xFF, False),
            (0xDF57, 0xFF, False),
        ]
        for hl, selected, other in (
            (0x9800, 0xDF53, 0xDF57), (0x9C00, 0xDF57, 0xDF53),
        ):
            state = r313.execute_route(
                self.base, scene=0x0B, svbk=0xF9, ffb7=0x02,
                gateway=r313.STALE_GATEWAY, stop=0x42B1, original_hl=hl,
            )
            self.assertEqual(state["cycles"], 1716)
            self.assertEqual(state["pc"], 0x42B1)
            self.assertEqual(state["a"], 1)
            self.assertFalse(state["f"] & 0x80)
            self.assertFalse(state["ime"])
            self.assertEqual((state["h"] << 8) | state["l"], hl)
            self.assertEqual(state["sp"], state["initial_sp"] + 4)
            self.assertEqual(r313._watched_writes(state)[:5], expected_writes)
            self.assertEqual(state["mem"][selected], 0x00)
            self.assertEqual(state["mem"][other], 0xFF)

    def test_current_scene02_and_scene0b_abi_matches_direct_dad7(self) -> None:
        contract = r313.stack_contract(self.base)
        self.assertEqual(
            contract["current_scene_outputs_flags_BCDEHL_SP_IME_exact"],
            {"02": True, "0B": True},
        )
        self.assertTrue(contract["real_frames_and_net_SP_exact_at_DAD7"])
        self.assertEqual(contract["repair_dirty_returns"]["9800"]["Z"], False)
        self.assertEqual(contract["repair_dirty_returns"]["9C00"]["Z"], False)

    def test_handler_and_candidate_mutations_are_rejected(self) -> None:
        patterns = {
            "outer": (bytes.fromhex("FE 93"), 1),
            "scene": (bytes.fromhex("FA 80 D8 FE 0B"), 4),
            "svbk": (bytes.fromhex("F0 70 E6 07 FE 01"), 5),
            "current": (bytes.fromhex("FA DE DA FE C4"), 4),
            "ffb7": (bytes.fromhex("F0 B7 FE 02"), 3),
            "stale": (bytes.fromhex("FA DE DA FE C2"), 4),
            "di": (bytes.fromhex("F3 3E C4 EA DE DA"), 0),
            "runtime-write": (bytes.fromhex("3E C4 EA DE DA"), 3),
            "cache-write": (bytes.fromhex("EA 53 DF"), 1),
            "stack-target": (bytes.fromhex("F8 02 36 D7"), 3),
        }
        original = r313.HANDLER
        try:
            for name, (pattern, relative) in patterns.items():
                offset = original.index(pattern) + relative
                mutant = bytearray(original)
                mutant[offset] ^= 1
                r313.HANDLER = bytes(mutant)
                caught = False
                for contract in (
                    r313.semantic_contract, r313.stack_contract,
                    r313.timing_contract,
                ):
                    try:
                        contract(self.base)
                    except AssertionError:
                        caught = True
                        break
                self.assertTrue(caught, f"{name} handler mutation survived")
                r313.HANDLER = original
        finally:
            r313.HANDLER = original

        mutant = bytearray(self.candidate)
        mutant[r313.bank_offset(r313.MUX_BANK, r313.HANDLER_ADDR)] ^= 1
        with self.assertRaises(AssertionError):
            r313.validate_candidate(self.base, bytes(mutant))

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
