#!/usr/bin/env python3
"""Static controls for r302's five-gate Stage-1 composition."""

from __future__ import annotations

import hashlib
from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
DIAGNOSTICS = ROOT / "scripts" / "diagnostics"
sys.path.insert(0, str(DIAGNOSTICS))

import build_stage1_lowhealth_all_gates_r302 as r302  # noqa: E402


EXPECTED_SHA256 = (
    "4c0824ea1884602fb5ddfb3c13efbee15e6886d9a381a95d1a9e39fb9f499154"
)
EXPECTED_RECEIPT_SHA256 = (
    "5820e385e4e251a2e13e720a1ff1ef0ccf13864d7957a433d27554b63a43619f"
)


def sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


class Stage1LowHealthAllGatesR302Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.base = r302.BASE.read_bytes()
        cls.base_receipt = r302.BASE_RECEIPT.read_bytes()
        cls.r297_full, cls.r297_receipt = r302.r297.build(
            cls.base, cls.base_receipt, variant="full"
        )
        cls.r300_candidate, cls.r300_receipt = r302.r300.build(
            cls.base, cls.base_receipt
        )
        cls.candidate, cls.receipt = r302.build(
            cls.base, cls.base_receipt
        )

    def test_identity_checksums_and_source_receipts_are_pinned(self) -> None:
        self.assertEqual(sha256(self.candidate), EXPECTED_SHA256)
        self.assertEqual(self.receipt["candidate_sha256"], EXPECTED_SHA256)
        self.assertEqual(
            sha256(r302.receipt_bytes(self.receipt)), EXPECTED_RECEIPT_SHA256
        )
        self.assertEqual(self.candidate, r302.DEFAULT_OUTPUT.read_bytes())
        self.assertEqual(
            sha256(r302.DEFAULT_RECEIPT.read_bytes()), EXPECTED_RECEIPT_SHA256
        )
        self.assertEqual(
            sha256(self.r297_full), r302.R297_FULL_SHA256
        )
        self.assertEqual(
            sha256(r302.receipt_bytes(self.r297_receipt)),
            r302.R297_RECEIPT_SHA256,
        )
        self.assertEqual(sha256(self.r300_candidate), r302.R300_SHA256)
        self.assertEqual(
            sha256(r302.receipt_bytes(self.r300_receipt)),
            r302.R300_RECEIPT_SHA256,
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

    def test_shared_predicate_exhausts_reachable_states_for_all_callers(self) -> None:
        accepted_scenes = set()
        cases = 0
        for ffb7 in range(256):
            for dd06 in range(4):
                for ffbf in range(4):
                    scene = r302.r296.reachable_scene(
                        ffb7, dd06=dd06, ffbf=ffbf
                    )
                    accepted = r302.r296.predicate_accepts(scene, ffb7)
                    self.assertEqual(accepted, ffb7 == 0x02)
                    for component in r302.LOW_HEALTH_COMPONENTS:
                        self.assertEqual(
                            r302.r296.predicate_accepts(scene, ffb7), accepted,
                            component,
                        )
                    if accepted:
                        accepted_scenes.add(scene)
                    cases += 1
        self.assertEqual(cases, 4096)
        self.assertEqual(accepted_scenes, {0x02, 0x0A, 0x0B})
        self.assertFalse(r302.r296.predicate_accepts(0x18, 0x02))
        for stage in range(3, 256):
            for scene in (stage, 0x0A, 0x0B):
                self.assertFalse(
                    r302.r296.predicate_accepts(scene, stage),
                    (stage, scene),
                )

    def test_attr_art_bg7_encodings_use_only_r296_shared_predicate(self) -> None:
        for bank, predicate in r302.r296.PREDICATE_BY_BANK.items():
            call = bytes((0xCD, predicate & 0xFF, predicate >> 8))
            gateway = r302.r297.bank_offset(
                bank, r302.r296.ATTR_GATEWAY_ADDR
            )
            art = r302.r297.bank_offset(
                bank, r302.r296.ART_LOADER_GATE_ADDR
            )
            bg7 = r302.r297.bank_offset(
                bank, r302.r296.BG7_SELECTOR_GATE_ADDR
            )
            self.assertEqual(
                self.candidate[gateway:gateway + 10],
                call + bytes.fromhex("C2 B9 DA") + bytes(4),
            )
            self.assertEqual(
                self.candidate[art:art + 8], call + b"\xC0" + bytes(4)
            )
            self.assertEqual(
                self.candidate[bg7:bg7 + 9],
                call + bytes.fromhex("20 06") + bytes(4),
            )
            # The BG7 relative branch still lands immediately after LD L,$C8.
            self.assertEqual(0x71BB + self.candidate[bg7 + 4], 0x71C1)

        pred13 = r302.r297.bank_offset(13, 0x5D4C)
        front16 = r302.r297.bank_offset(16, 0x6180)
        tail16 = r302.r297.bank_offset(
            16, r302.r296.BANK16_PREDICATE_TAIL_ADDR
        )
        self.assertEqual(
            self.candidate[pred13:pred13 + len(r302.r296.BANK13_PREDICATE)],
            r302.r296.BANK13_PREDICATE,
        )
        self.assertEqual(
            self.candidate[
                front16:front16 + len(r302.r296.BANK16_PREDICATE_FRONT)
            ],
            r302.r296.BANK16_PREDICATE_FRONT,
        )
        self.assertEqual(
            self.candidate[
                tail16:tail16 + len(r302.r296.BANK16_PREDICATE_TAIL)
            ],
            r302.r296.BANK16_PREDICATE_TAIL,
        )

    def test_r297_attr_only_implementation_is_fully_replaced(self) -> None:
        for bank, helper in r302.r297.ATTR_HELPER_BY_BANK.items():
            gateway = r302.r297.bank_offset(
                bank, r302.r297.ATTR_GATEWAY_ADDR
            )
            old_r297 = (
                r302.r297.OLD_ATTR_GATEWAY[:7]
                + bytes((0xC4, helper & 0xFF, helper >> 8))
            )
            self.assertEqual(
                self.r300_candidate[gateway:gateway + len(old_r297)],
                old_r297,
            )
            self.assertNotEqual(
                self.candidate[gateway:gateway + len(old_r297)], old_r297
            )
        attr_owned = r302.r297_attr_ranges()
        scene_delta = r302.delta(
            self.r300_candidate, self.candidate, functional=True
        )
        # Every r297 attr byte that remains different is now part of an r296
        # predicate/gateway encoding, never an orphaned r297 helper tail.
        self.assertTrue(scene_delta & attr_owned)
        self.assertTrue(
            self.receipt["components"]["r297_retained"]
            ["attr_only_gateway"] == "replaced"
        )

    def test_native_renderer_row_and_transition_abi_are_exact(self) -> None:
        self.assertEqual(
            self.candidate[0x4303:0x4319], self.base[0x4303:0x4319]
        )
        row = r302.r297.bank_offset(r302.r297.ROW_BANK, 0x6BA7)
        end = r302.r297.bank_offset(r302.r297.ROW_BANK, 0x6BEB)
        changes = {
            index
            for index, pair in enumerate(
                zip(self.base[row:end], self.candidate[row:end], strict=True)
            )
            if pair[0] != pair[1]
        }
        self.assertEqual(
            changes, {r302.r297.ROW_MASK_ADDR - 0x6BA7}
        )
        self.assertEqual(self.candidate[row], 0xC1)       # POP BC
        self.assertEqual(self.candidate[row + 4], 0x47)   # LD B,A
        miniboss = r302.r297.bank_offset(r302.r297.ROW_BANK, 0x6BBA)
        self.assertEqual(
            self.candidate[miniboss:miniboss + 4],
            bytes.fromhex("CB 58 20 0C"),
        )
        transition = r302.r297.bank_offset(r302.r297.ROW_BANK, 0x55C3)
        transition_end = transition + len(r302.r296.OLD_TRANSITION_GATE)
        transition_changes = {
            index
            for index, pair in enumerate(zip(
                self.base[transition:transition_end],
                self.candidate[transition:transition_end],
                strict=True,
            ))
            if pair[0] != pair[1]
        }
        self.assertEqual(
            transition_changes,
            {r302.r297.TRANSITION_MASK_ADDR - 0x55C3},
        )

    def test_r297_wall_route_and_r300_semantic_bank_are_byte_exact(self) -> None:
        for start, width in (
            (r302.r297.RST0_ADDR, len(r302.r297.NEW_RST0)),
            (r302.r297.ROOM_STUB_ADDR, len(r302.r297.NEW_ROOM_STUB)),
            (
                r302.r297.bank_offset(
                    r302.r297.EXPANSION_BANK, r302.r297.WALL_HELPER_ADDR
                ),
                len(r302.r297.WALL_HELPER),
            ),
        ):
            self.assertEqual(
                self.candidate[start:start + width],
                self.r297_full[start:start + width],
            )
        for offset in r302.r297.ROOM_HOOK_SITES:
            self.assertEqual(self.candidate[offset:offset + 2], b"\xC7\x00")
        bank20 = slice(
            r302.r300.SEMANTIC_BANK * r302.r297.BANK_SIZE,
            (r302.r300.SEMANTIC_BANK + 1) * r302.r297.BANK_SIZE,
        )
        self.assertEqual(
            self.candidate[bank20], self.r300_candidate[bank20]
        )
        primary = r302.r300.semantic.bank_offset(
            r302.r300.SEMANTIC_BANK, r302.r300.PRIMARY_LUT_ADDR
        )
        room01 = r302.r300.semantic.bank_offset(
            r302.r300.SEMANTIC_BANK, r302.r300.ROOM01_LUT_ADDR
        )
        for tile in r302.r300.TARGET_TILES:
            self.assertEqual(self.candidate[primary + tile], 0x00)
            self.assertEqual(self.candidate[room01 + tile], 0x06)
        for tile in r302.r300.semantic.TOOTH_TILES:
            self.assertEqual(self.candidate[primary + tile], 0x0F)
            self.assertEqual(self.candidate[room01 + tile], 0x0F)

    def test_rejected_r301_is_absent_not_claimed_as_effective(self) -> None:
        menu = r302.r297.bank_offset(13, r302.r301.MENU_HELPER_ADDR)
        ingress = r302.r297.bank_offset(21, r302.r301.INGRESS_ADDR)
        helper = r302.r297.bank_offset(21, r302.r301.CONTEXT_HELPER_ADDR)
        self.assertEqual(
            self.candidate[menu:menu + len(r302.r301.OLD_MENU_HELPER)],
            r302.r301.OLD_MENU_HELPER,
        )
        self.assertEqual(
            self.candidate[ingress:ingress + len(r302.r301.INGRESS)],
            b"\xFF" * len(r302.r301.INGRESS),
        )
        self.assertEqual(
            self.candidate[helper:helper + len(r302.r301.CONTEXT_HELPER)],
            b"\xFF" * len(r302.r301.CONTEXT_HELPER),
        )
        rejected = self.receipt["components"]["r301_rejected"]
        self.assertFalse(rejected["included"])
        self.assertIn("no bank21 ingress", rejected["reason"])
        self.assertEqual(
            r302.delta(self.base, self.candidate, functional=True)
            & r302.r301_owned_ranges(),
            set(),
        )

    def test_component_ownership_is_pairwise_disjoint(self) -> None:
        retained = (
            r302.delta(self.base, self.r297_full, functional=True)
            - r302.r297_attr_ranges()
        )
        semantic = r302.delta(
            self.r297_full, self.r300_candidate, functional=True
        )
        scene = r302.delta(
            self.r300_candidate, self.candidate, functional=True
        )
        rejected = r302.r301_owned_ranges()
        self.assertTrue(retained)
        self.assertTrue(semantic)
        self.assertTrue(scene)
        self.assertTrue(retained.isdisjoint(semantic))
        self.assertTrue(retained.isdisjoint(scene))
        self.assertTrue(semantic.isdisjoint(scene))
        self.assertTrue(retained.isdisjoint(rejected))
        self.assertTrue(semantic.isdisjoint(rejected))
        self.assertTrue(scene.isdisjoint(rejected))
        final = r302.delta(self.base, self.candidate, functional=True)
        self.assertLessEqual(final, retained | semantic | scene)
        self.assertEqual(
            self.receipt["ownership"]["rejected_r301_overlap_bytes"], 0
        )

    def test_timing_contract_is_exact_for_accept_and_reject_paths(self) -> None:
        accepted = {
            13: {"art": 108, "attr": 112, "bg7": 108},
            16: {"art": 124, "attr": 128, "bg7": 124},
        }
        for scene in (0x02, 0x0A, 0x0B):
            for bank, components in accepted.items():
                for component, expected in components.items():
                    self.assertEqual(
                        r302.gate_cycles(
                            component, bank=bank, scene=scene, ffb7=0x02
                        ),
                        expected,
                    )
        splash = {
            13: {"art": 120, "attr": 116, "bg7": 112},
            16: {"art": 136, "attr": 132, "bg7": 128},
        }
        for bank, components in splash.items():
            for component, expected in components.items():
                self.assertEqual(
                    r302.gate_cycles(
                        component, bank=bank, scene=0x18, ffb7=0x02
                    ),
                    expected,
                )
        later = {"art": 84, "attr": 80, "bg7": 76}
        for bank in r302.r296.MIRROR_BANKS:
            for component, expected in later.items():
                self.assertEqual(
                    r302.gate_cycles(
                        component, bank=bank, scene=0x03, ffb7=0x03
                    ),
                    expected,
                )
        self.assertEqual(
            self.receipt["offline_contract"]["timing"]
            ["stage1_scene02"]["bank13"]["attr"]["delta"],
            68,
        )
        self.assertEqual(
            self.receipt["offline_contract"]["timing"]
            ["stage1_scene02"]["bank16"]["attr"]["delta"],
            84,
        )
        self.assertEqual(
            self.receipt["offline_contract"]["timing"]
            ["stage1_scene0B"]["bank13"]["attr"],
            {"r300_t_cycles": 100, "r302_t_cycles": 112, "delta": 12},
        )

    def test_component_preimage_and_omission_controls_fail_closed(self) -> None:
        bad_gateway = bytearray(self.r300_candidate)
        gateway = r302.r297.bank_offset(13, r302.r297.ATTR_GATEWAY_ADDR)
        bad_gateway[gateway] ^= 0x01
        with self.assertRaises(AssertionError):
            r302.validate_replacement_preimages(
                self.base, bytes(bad_gateway)
            )

        bad_row = bytearray(self.candidate)
        row_body = r302.r297.bank_offset(r302.r297.ROW_BANK, 0x6BC0)
        bad_row[row_body] ^= 0x01
        with self.assertRaises(AssertionError):
            r302.validate_native_and_omission(
                self.base, bytes(bad_row), self.r297_full,
                self.r300_candidate,
            )

        leaked_r301 = bytearray(self.candidate)
        ingress = r302.r297.bank_offset(21, r302.r301.INGRESS_ADDR)
        leaked_r301[ingress:ingress + len(r302.r301.INGRESS)] = (
            r302.r301.INGRESS
        )
        with self.assertRaises(AssertionError):
            r302.validate_native_and_omission(
                self.base, bytes(leaked_r301), self.r297_full,
                self.r300_candidate,
            )


if __name__ == "__main__":
    unittest.main()
