#!/usr/bin/env python3
"""Offline root-cause, emitted-DMA, ownership, and mutation tests for r315."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
DIAGNOSTICS = ROOT / "scripts" / "diagnostics"
sys.path.insert(0, str(DIAGNOSTICS))

import build_stage1_scene0b_chr_restore_r315 as r315  # noqa: E402


EXPECTED_SHA256 = (
    "3af4b5bdf352a43622a01093e225e431109c61b1f7e216b8a732d2248f15bd4c"
)
EXPECTED_RECEIPT_SHA256 = (
    "78255b7823310486ae39aff47ad836b0874f2581966c5c184f5b5ecae8285348"
)


def digest(payload: bytes | bytearray) -> str:
    return hashlib.sha256(payload).hexdigest()


class Stage1Scene0BChrRestoreR315Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.base = r315.BASE.read_bytes()
        cls.base_receipt = r315.BASE_RECEIPT.read_bytes()
        cls.rejected_receipt = r315.REJECTED_LIVE_RECEIPT.read_bytes()
        cls.rejected_chr = r315.REJECTED_CHR_DUMP.read_bytes()
        cls.rejected_planes = r315.REJECTED_PLANE_DUMP.read_bytes()
        cls.rejected_metadata = r315.REJECTED_PLANE_METADATA.read_bytes()
        cls.candidate = r315.DEFAULT_OUTPUT.read_bytes()
        cls.receipt_bytes = r315.DEFAULT_RECEIPT.read_bytes()
        cls.receipt = json.loads(cls.receipt_bytes)

    def test_pinned_identity_and_deterministic_rebuild(self) -> None:
        self.assertEqual(digest(self.base), r315.BASE_SHA256)
        self.assertEqual(digest(self.base_receipt), r315.BASE_RECEIPT_SHA256)
        self.assertEqual(
            digest(self.rejected_receipt), r315.REJECTED_LIVE_RECEIPT_SHA256
        )
        self.assertEqual(
            digest(self.rejected_chr), r315.REJECTED_CHR_DUMP_SHA256
        )
        if EXPECTED_SHA256 != "TO_BE_PINNED":
            self.assertEqual(digest(self.candidate), EXPECTED_SHA256)
        if EXPECTED_RECEIPT_SHA256 != "TO_BE_PINNED":
            self.assertEqual(digest(self.receipt_bytes), EXPECTED_RECEIPT_SHA256)
        rebuilt, receipt = r315.build(
            self.base, self.base_receipt,
            self.rejected_receipt, self.rejected_chr,
            self.rejected_planes, self.rejected_metadata,
        )
        self.assertEqual(rebuilt, self.candidate)
        # The reconstructed ROM is exact. The current receipt additionally
        # authenticates the corrupt page's ROM source; keep the immutable old
        # receipt intact and require exactly these two evidence additions.
        expected_receipt = json.loads(self.receipt_bytes)
        expected_receipt["preimage_contract"]["captured_failure"].update(
            physical_corrupt_page_sha256=r315.CORRUPT_SOURCE_SHA256,
            physical_corrupt_page_source="file:$1C000-$1C0FF = bank7:$4000-$40FF",
        )
        self.assertEqual(receipt, expected_receipt)
        self.assertFalse(receipt["promotable"])
        self.assertFalse(receipt["emulator_invoked"])

    def test_capture_proves_the_exact_signed_restore_domain(self) -> None:
        contract = r315.rejected_chr_contract(
            self.base, self.rejected_chr,
            self.rejected_planes, self.rejected_metadata,
        )
        self.assertEqual(contract["LCDC"], "83")
        self.assertEqual(contract["mismatch_tile_range"], "$10-$1F")
        self.assertEqual(contract["mismatch_tiles"], 16)
        self.assertEqual(contract["mismatch_bytes"], 248)
        self.assertEqual(
            contract["referenced_mismatch_tiles"],
            ["10", "11", "13", "14", "15", "16", "17", "1D", "1E"],
        )
        self.assertEqual(contract["referenced_mismatch_bytes"], 138)
        self.assertTrue(contract["tile_0F_boundary_exact"])
        self.assertTrue(contract["tile_20_boundary_exact"])

        canonical = r315.canonical_bg_art(self.base)
        actual = bytearray(self.rejected_chr[:0x2000])
        destination = r315.VRAM_DESTINATION - 0x8000
        actual[destination:destination + r315.ART_BYTES] = self.candidate[
            r315.bank_offset(r315.ART_PAYLOAD_ADDR):
            r315.bank_offset(r315.ART_PAYLOAD_ADDR) + r315.ART_BYTES
        ]
        for tile in range(0x100):
            address = tile * 16 + (0x1000 if tile < 0x80 else 0)
            self.assertEqual(
                actual[address:address + 16],
                canonical[tile * 16:(tile + 1) * 16],
                f"signed physical tile {tile:02X}",
            )

    def test_art_mirror_is_hash_pinned_and_exact(self) -> None:
        offset = r315.bank_offset(r315.ART_PAYLOAD_ADDR)
        payload = self.candidate[offset:offset + r315.ART_BYTES]
        self.assertEqual(len(payload), 0x100)
        self.assertEqual(digest(payload), r315.ART_PAYLOAD_SHA256)
        self.assertEqual(payload, self.base[0x1D100:0x1D200])
        self.assertEqual(r315.ART_PAYLOAD_ADDR, 0x7000)
        self.assertEqual(r315.ART_PAYLOAD_END, 0x70FF)

    def test_unsigned_destination_is_a_decisive_negative_control(self) -> None:
        """ID $10 is physical $9100 under the captured LCDC=$83."""
        offset = r315.bank_offset(r315.ART_PAYLOAD_ADDR)
        payload = self.candidate[offset:offset + r315.ART_BYTES]
        canonical = r315.canonical_bg_art(self.base)
        wrong = bytearray(self.rejected_chr[:0x2000])
        wrong[0x100:0x200] = payload  # Incorrect physical $8100-$81FF.
        self.assertNotEqual(wrong[0x1100:0x1200], canonical[0x100:0x200])
        correct = bytearray(self.rejected_chr[:0x2000])
        correct[0x1100:0x1200] = payload  # Physical $9100-$91FF.
        self.assertEqual(correct[0x1100:0x1200], canonical[0x100:0x200])
        # Neighboring signed IDs and the unsigned high half were already exact.
        self.assertEqual(correct[0x10F0:0x1100], canonical[0x0F0:0x100])
        self.assertEqual(correct[0x1200:0x1210], canonical[0x200:0x210])
        self.assertEqual(correct[0x0800:0x1000], canonical[0x800:0x1000])

    def test_one_atomic_gdma_has_exact_source_destination_and_width(self) -> None:
        self.assertEqual(
            r315.ART_HELPER,
            bytes.fromhex(
                "F055E680FE8020F8F040CB7F280C"
                "F044FE9030FAF044FE9038FA"
                "C5F04F47AFE04F3E70E051AFE0523E11E053AFE0543E0FE055"
                "F055FEFFF578E04FF1C1C9"
            ),
        )
        self.assertEqual(r315.GDMA_BLOCKS, 16)
        self.assertEqual(r315.GDMA_COMMAND, 0x0F)
        self.assertEqual(r315.VRAM_DESTINATION, 0x9100)
        self.assertEqual(r315.ART_BYTES, 16 * 16)
        self.assertEqual(r315.ART_HELPER.count(bytes.fromhex("E0 55")), 1)
        self.assertEqual(r315.ART_HELPER.count(bytes.fromhex("F0 55")), 2)
        self.assertLess(
            r315.ART_HELPER.index(bytes.fromhex("F0 55 E6 80 FE 80 20 F8")),
            r315.ART_HELPER.index(bytes.fromhex("E0 55")),
        )
        self.assertLess(
            r315.ART_HELPER.index(bytes.fromhex("E0 55")),
            r315.ART_HELPER.rindex(bytes.fromhex("F0 55 FE FF")),
        )
        self.assertNotIn(
            bytes.fromhex("F0 55 FE FF"),
            r315.ART_HELPER[:r315.ART_HELPER.index(bytes.fromhex("E0 55"))],
        )
        self.assertIn(bytes.fromhex("C5 F0 4F 47 AF E0 4F"), r315.ART_HELPER)
        self.assertTrue(
            r315.ART_HELPER.endswith(bytes.fromhex("F5 78 E0 4F F1 C1 C9"))
        )
        self.assertEqual(r315.ART_HELPER.count(0xC5), 1)  # PUSH BC
        self.assertEqual(r315.ART_HELPER.count(0xC1), 1)  # POP BC

    def test_repair_restores_art_before_arm_display_and_commit(self) -> None:
        self.assertEqual(r315.REPAIR_HOOK_ADDR, 0x6D4D)
        self.assertEqual(
            r315.NEW_REPAIR_HOOK,
            bytes((0xC3, r315.REPAIR_WRAPPER_ADDR & 0xFF,
                   r315.REPAIR_WRAPPER_ADDR >> 8)),
        )
        self.assertEqual(r315.REPAIR_WRAPPER[:3], bytes.fromhex("CD 80 6E"))
        self.assertEqual(r315.REPAIR_WRAPPER[3:6], bytes.fromhex("C2 CE 6D"))
        self.assertEqual(r315.REPAIR_WRAPPER[6:], bytes.fromhex("C3 6D 6D"))
        self.assertEqual(r315.r314.HANDLER_LABELS["transaction_armed_effect"],
                         0x6DCB)
        self.assertEqual(r315.r314.HANDLER_LABELS["display_flip_effect"],
                         0x6E25)
        self.assertEqual(r315.r314.HANDLER_LABELS["commit_effect"], 0x6E2A)

    def test_menu_entry_and_hold_are_untouched_but_exact_close_restores(self) -> None:
        # The complete mux through the exact predicate is unchanged.  Only the
        # body reached after D880=0B/FFB7=02 is redirected.
        prefix_start = r315.bank_offset(0x6C80)
        hook = r315.bank_offset(r315.MENU_HOOK_ADDR)
        self.assertEqual(
            self.candidate[prefix_start:hook], self.base[prefix_start:hook]
        )
        self.assertEqual(r315.MENU_HOOK_ADDR, 0x6CDA)
        self.assertEqual(r315.MENU_EXIT_ADDR, 0x6CE2)
        self.assertEqual(
            self.candidate[hook:hook + len(r315.NEW_MENU_HOOK)],
            r315.NEW_MENU_HOOK,
        )
        self.assertEqual(r315.MENU_WRAPPER[0], 0xF3)  # DI
        self.assertIn(bytes.fromhex("3E FF EA 53 DF EA 57 DF"),
                      r315.MENU_WRAPPER)
        self.assertIn(bytes.fromhex("CD 80 6E 20 FB F1"), r315.MENU_WRAPPER)
        self.assertTrue(r315.MENU_WRAPPER.endswith(bytes.fromhex("C3 E2 6C")))

    def test_busy_menu_dma_retries_until_idle_then_starts_once(self) -> None:
        self.assertEqual(
            r315.MENU_WRAPPER,
            bytes.fromhex(
                "F3F040F5CBEFE0403EFFEA53DFEA57DFCD806E20FB"
                "F1CBAFE040FBC3E26C"
            ),
        )
        call_index = r315.MENU_WRAPPER.index(bytes.fromhex("CD 80 6E"))
        branch_index = r315.MENU_WRAPPER.index(bytes.fromhex("20 FB"))
        branch_target = (
            r315.MENU_WRAPPER_ADDR + branch_index + 2
            + int.from_bytes(bytes([0xFB]), signed=True)
        )
        self.assertEqual(branch_target,
                         r315.MENU_WRAPPER_ADDR + call_index)
        self.assertEqual(branch_target, 0x6E70)
        self.assertGreater(r315.MENU_WRAPPER.index(bytes.fromhex("FB C3")),
                           branch_index)
        self.assertEqual(
            r315.menu_retry_model((0x00, 0x03, 0x85, 0xFF)),
            {"helper_calls": 1, "FF55_reads": 4,
             "FF55_writes": 1, "GDMA_starts": 1},
        )
        self.assertEqual(
            r315.menu_retry_model((0x85, 0xFF)),
            {"helper_calls": 1, "FF55_reads": 2,
             "FF55_writes": 1, "GDMA_starts": 1},
        )
        self.assertEqual(
            r315.menu_retry_model((0x85, 0x85, 0x85, 0xFF)),
            {"helper_calls": 2, "FF55_reads": 4,
             "FF55_writes": 2, "GDMA_starts": 2},
        )
        with self.assertRaises(AssertionError):
            r315.menu_retry_model((0x85, 0x85))
        with self.assertRaises(AssertionError):
            r315.menu_retry_model((0x00, 0x03))

    def test_gdma_uses_lcd_off_or_a_fresh_vblank_safe_window(self) -> None:
        inactive = r315.ART_HELPER.index(
            bytes.fromhex("F0 55 E6 80 FE 80 20 F8")
        )
        lcd_branch = r315.ART_HELPER.index(bytes.fromhex("F0 40 CB 7F 28 0C"))
        leave_vblank = r315.ART_HELPER.index(bytes.fromhex("F0 44 FE 90 30 FA"))
        enter_vblank = r315.ART_HELPER.index(bytes.fromhex("F0 44 FE 90 38 FA"))
        start = r315.ART_HELPER.index(bytes.fromhex("E0 55"))
        self.assertLess(inactive, lcd_branch)
        self.assertLess(lcd_branch, leave_vblank)
        self.assertLess(leave_vblank, enter_vblank)
        self.assertLess(enter_vblank, start)
        branch_index = r315.ART_HELPER.index(bytes.fromhex("28 0C"))
        setup_index = r315.ART_HELPER.index(
            bytes.fromhex("C5 F0 4F 47 AF E0 4F")
        )
        self.assertEqual(
            r315.ART_HELPER_ADDR + branch_index + 2 + 0x0C,
            r315.ART_HELPER_ADDR + setup_index,
        )

        self.assertEqual(
            r315.safe_window_model(0x03, ()),
            {"LCDC": "03", "mode": "LCD-off direct GDMA",
             "LY_reads": 0, "VRAM_safe": True},
        )
        self.assertEqual(
            r315.safe_window_model(0x83, (80, 143, 144)),
            {"LCDC": "83", "mode": "LCD-on fresh-VBlank GDMA",
             "LY_reads": 3, "visible_sample": 80,
             "VBlank_edge_sample": 144, "VRAM_safe": True},
        )
        self.assertEqual(
            r315.safe_window_model(0x83, (150, 153, 0, 80, 143, 144)),
            {"LCDC": "83", "mode": "LCD-on fresh-VBlank GDMA",
             "LY_reads": 6, "visible_sample": 0,
             "VBlank_edge_sample": 144, "VRAM_safe": True},
        )
        with self.assertRaises(AssertionError):
            r315.safe_window_model(0x03, (0,))
        with self.assertRaises(AssertionError):
            r315.safe_window_model(0x83, (150, 153))

    def test_window_cover_brackets_the_menu_wait_and_restores_lcdc(self) -> None:
        show = r315.MENU_WRAPPER.index(bytes.fromhex("F0 40 F5 CB EF E0 40"))
        helper = r315.MENU_WRAPPER.index(bytes.fromhex("CD 80 6E"))
        hide = r315.MENU_WRAPPER.index(bytes.fromhex("F1 CB AF E0 40"))
        enable_ime = r315.MENU_WRAPPER.index(bytes.fromhex("FB C3 E2 6C"))
        self.assertLess(show, helper)
        self.assertLess(helper, hide)
        self.assertLess(hide, enable_ime)
        self.assertEqual(r315.MENU_WRAPPER.count(0xF5), 1)  # PUSH AF
        self.assertEqual(r315.MENU_WRAPPER.count(0xF1), 1)  # POP AF
        for callsite in (0x1B69, 0x1DC2):
            self.assertEqual(
                self.base[callsite:callsite + 9],
                bytes.fromhex("F0 40 CB AF E0 40 CD 98 77"),
            )

        visual = r315.helper_contract(self.base)["visual_boundary"]
        self.assertIn("direct native close has LCDC.5=0",
                      visual["entry_precondition"])
        self.assertEqual(
            visual["direct_close_proof"],
            "fixed:$1B69/$1DC2 exact F040CBAFE040CD9877",
        )
        self.assertFalse(visual["corrupted_gameplay_CHR_visible_during_wait"])

    def test_direct_close_routes_have_exact_enabled_ime_provenance(self) -> None:
        contract = r315.menu_entry_ime_contract(self.base)
        self.assertEqual(
            contract["close_callsites"], ["fixed:$1B69", "fixed:$1DC2"]
        )
        self.assertEqual(
            contract["native_IME_owner"],
            "bank20:$4000/$4017 -> sole EI $4082; RET $4083",
        )
        self.assertEqual(
            contract["entry_IME"],
            "enabled at both scoped direct close sites",
        )
        self.assertEqual(contract["shared_tail_transfers"], 19)
        self.assertEqual(contract["all_targeted_menu_completions_IME"],
                         "enabled")
        self.assertFalse(contract["unknown_IME_assumption"])

        menu_offset = r315._banked_offset(
            r315.NATIVE_MENU_BANK, r315.NATIVE_MENU_ADDR
        )
        native = self.base[
            menu_offset:menu_offset
            + r315.NATIVE_MENU_END - r315.NATIVE_MENU_ADDR
        ]
        self.assertEqual(native[0x82:], bytes.fromhex("FB C9"))
        self.assertEqual(native[:-2].count(0xC9), 0)
        self.assertEqual(
            r315._absolute_transfer_sites(self.base, 0x1B35),
            frozenset({0x1B04}),
        )
        self.assertEqual(
            r315._absolute_transfer_sites(self.base, 0x1D5D),
            frozenset({0x0A97}),
        )

        no_ei = bytearray(self.base)
        no_ei[menu_offset + 0x82] = 0x00
        with self.assertRaises(AssertionError):
            r315.menu_entry_ime_contract(bytes(no_ei))

    def test_busy_retry_liveness_is_bound_to_lcd_on(self) -> None:
        helper = r315.helper_contract(self.base)
        liveness = helper["HBlank_busy_liveness"]
        self.assertEqual(liveness["precondition"],
                         "LCDC.7=1 at both scoped close routes")
        self.assertEqual(liveness["static_owner"],
                         "fixed:$12E0 chooses $83/$8B")
        self.assertEqual(liveness["captured_control"],
                         "rejected live metadata LCDC=$83")
        self.assertTrue(liveness["bounded_without_IME"])
        safe = helper["VRAM_safe_window"]
        self.assertEqual(safe["transfer_time_us"], 128)
        self.assertEqual(safe["VBlank_capacity_bytes"], 2280)
        self.assertEqual(safe["nominal_VBlank_time_us"], 1087)
        self.assertEqual(safe["payload_bytes"], 256)
        self.assertEqual(safe["LCD_off_repair_model"]["LY_reads"], 0)

    def test_current_hot_paths_never_reach_the_repair_hook(self) -> None:
        for scene in (0x02, 0x0B):
            state = r315.r314.execute_handler(
                scene=scene, gateway=r315.r314.CURRENT_GATEWAY
            )
            pcs = [row[0] for row in state["trace"]]
            self.assertNotIn(r315.REPAIR_HOOK_ADDR, pcs)
            self.assertNotIn(r315.r314.HANDLER_LABELS["repair"], pcs)
            self.assertEqual(r315.r314._owned_writes(state), [])

    def test_exact_owned_delta_and_r314_transaction_addresses(self) -> None:
        functional = r315.r305.r304.delta(
            self.base, self.candidate, functional=True
        )
        expected = {
            offset for offset in r315.owned_ranges()
            if self.base[offset] != self.candidate[offset]
        }
        self.assertEqual(functional, expected)
        self.assertEqual(len(functional), self.receipt["ownership"][
            "functional_changed_bytes"
        ])
        self.assertEqual(
            self.receipt["ownership"]["r314_observation_addresses_preserved"],
            {"start": "$6D4D", "armed": "$6DCB",
             "display": "$6E25", "commit": "$6E2A"},
        )
        for offset, (before, after) in enumerate(
            zip(self.base, self.candidate, strict=True)
        ):
            if offset in functional or offset in r315.CHECKSUM_OFFSETS:
                continue
            self.assertEqual(before, after, f"unowned r314 drift at {offset:#x}")

    def test_r293_is_bank_one_only_and_cannot_restore_this_failure(self) -> None:
        lineage = r315.lineage_contract(self.base)
        self.assertTrue(lineage["r293_private_bank_one_loader_chain_byte_exact"])
        self.assertEqual(lineage["r293_total_bytes"], 256)
        self.assertTrue(all(item.startswith("VBK1:")
                            for item in lineage["r293_targets"]))
        self.assertEqual(
            lineage["missing_owner"],
            "bank-zero CHR $9100-$91FF after menu completion",
        )

    def test_mutated_inputs_and_candidate_regions_are_rejected(self) -> None:
        for label, payload_index in (
            ("base receipt", 0), ("rejected receipt", 1), ("CHR dump", 2),
            ("plane dump", 3), ("plane metadata", 4),
        ):
            inputs = [bytearray(self.base_receipt),
                      bytearray(self.rejected_receipt),
                      bytearray(self.rejected_chr),
                      bytearray(self.rejected_planes),
                      bytearray(self.rejected_metadata)]
            inputs[payload_index][-1] ^= 1
            with self.subTest(label=label), self.assertRaises(AssertionError):
                r315.build(
                    self.base, bytes(inputs[0]), bytes(inputs[1]),
                    bytes(inputs[2]), bytes(inputs[3]), bytes(inputs[4]),
                )

        for address, relative, label in (
            (r315.REPAIR_HOOK_ADDR, 1, "repair hook"),
            (r315.MENU_HOOK_ADDR, 1, "menu hook"),
            (r315.REPAIR_WRAPPER_ADDR, 0, "repair wrapper"),
            (r315.MENU_WRAPPER_ADDR, 0, "menu wrapper"),
            (r315.ART_HELPER_ADDR, 0, "art helper"),
            (r315.ART_PAYLOAD_ADDR, 0x10, "art payload"),
        ):
            mutant = bytearray(self.candidate)
            mutant[r315.bank_offset(address) + relative] ^= 1
            with self.subTest(label=label), self.assertRaises(AssertionError):
                r315.validate_candidate(self.base, bytes(mutant))

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
