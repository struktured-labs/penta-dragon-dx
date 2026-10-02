#!/usr/bin/env python3
"""Exhaustive static gates for the exact r310+r307 r311 composition."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
DIAGNOSTICS = ROOT / "scripts" / "diagnostics"
sys.path.insert(0, str(DIAGNOSTICS))

import build_stage1_final_scene0b_r311 as r311  # noqa: E402


EXPECTED_SHA256 = (
    "be8e78761470b811111e74d47c1cbb9923e34d136c420ccb76314a6be22ab84d"
)
EXPECTED_RECEIPT_SHA256 = (
    "5db65ed067ed1bda36e933c466e77f88aba51a6212b8baa7c96938f800587130"
)


def digest(payload: bytes | bytearray) -> str:
    return hashlib.sha256(payload).hexdigest()


class Stage1FinalScene0BR311Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.base = r311.BASE.read_bytes()
        cls.base_receipt = r311.BASE_RECEIPT.read_bytes()
        cls.r307_candidate = r311.R307_CANDIDATE.read_bytes()
        cls.r307_receipt = r311.R307_RECEIPT.read_bytes()
        cls.live_receipt = r311.R310_LIVE_RECEIPT.read_bytes()
        cls.candidate = r311.DEFAULT_OUTPUT.read_bytes()
        cls.receipt_bytes = r311.DEFAULT_RECEIPT.read_bytes()
        cls.receipt = json.loads(cls.receipt_bytes)

    def rebuild(self) -> tuple[bytes, dict[str, object]]:
        return r311.build(
            self.base,
            self.base_receipt,
            self.r307_candidate,
            self.r307_receipt,
            self.live_receipt,
        )

    def test_pinned_identity_receipt_and_deterministic_rebuild(self) -> None:
        self.assertEqual(digest(self.base), r311.BASE_SHA256)
        self.assertEqual(digest(self.base_receipt), r311.BASE_RECEIPT_SHA256)
        self.assertEqual(digest(self.candidate), EXPECTED_SHA256)
        self.assertEqual(digest(self.receipt_bytes), EXPECTED_RECEIPT_SHA256)
        candidate, receipt = self.rebuild()
        self.assertEqual(candidate, self.candidate)
        self.assertEqual(
            r311.r305.r304.receipt_bytes(receipt), self.receipt_bytes
        )
        self.assertEqual(receipt["candidate_sha256"], EXPECTED_SHA256)
        self.assertFalse(receipt["promotable"])
        self.assertFalse(receipt["emulator_invoked"])

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

    def test_exact_union_has_disjoint_r310_and_r307_ownership(self) -> None:
        r305_base = r311.r310.BASE.read_bytes()
        r310_delta = r311.r305.r304.delta(
            r305_base, self.base, functional=True
        )
        r307_delta = r311.r305.r304.delta(
            r305_base, self.r307_candidate, functional=True
        )
        final_from_r310 = r311.r305.r304.delta(
            self.base, self.candidate, functional=True
        )
        self.assertFalse(r310_delta & r307_delta)
        self.assertEqual(final_from_r310, r307_delta)
        self.assertEqual(len(r310_delta), 68)
        self.assertEqual(len(r307_delta), 54)
        self.assertEqual(
            self.receipt["composition_contract"]["r310_r307_overlap_bytes"],
            0,
        )
        self.assertTrue(
            self.receipt["composition_contract"]["r311_union_exact"]
        )

    def test_every_nonoverlay_r310_byte_is_exact(self) -> None:
        overlay = r311.r305.r304.delta(
            self.base, self.candidate, functional=True
        )
        self.assertEqual(
            overlay,
            {
                offset for offset in r311.owned_ranges()
                if self.base[offset] != self.candidate[offset]
            },
        )
        for offset, (before, after) in enumerate(
            zip(self.base, self.candidate, strict=True)
        ):
            if offset in overlay or offset in r311.CHECKSUM_OFFSETS:
                continue
            self.assertEqual(after, before, f"r310 drift at {offset:#x}")
        self.assertTrue(
            self.receipt["composition_contract"]
            ["r310_bytes_exact_outside_r307_and_checksums"]
        )

    def test_overlay_is_exact_pinned_r307_bank16_data(self) -> None:
        self.assertTrue(r311.owned_ranges())
        self.assertTrue(
            all(
                offset // r311.r305.r304.BANK_SIZE == r311.MIRROR_BANK
                for offset in r311.owned_ranges()
            )
        )
        for offset in r311.owned_ranges():
            self.assertEqual(self.candidate[offset], self.r307_candidate[offset])
        self.assertEqual(
            self.receipt["ownership"]["functional_changed_bytes_from_r310"],
            54,
        )
        self.assertEqual(self.receipt["ownership"]["escaped_bytes"], 0)

    def test_r310_behavioral_components_remain_exact(self) -> None:
        precompile = r311.r310.PRECOMPILE_SITE
        helper = r311.r310.bank_offset(
            r311.r310.HELPER_BANK, r311.r310.HELPER_ADDR
        )
        wall = r311.r310.bank_offset(
            r311.r305.WALL_BANK, r311.r305.WALL_ADDR
        )
        mux = r311.r310.bank_offset(r311.r305.BANK31, r311.r305.MUX_ADDR)
        self.assertEqual(
            self.candidate[
                precompile:precompile + len(r311.r310.NEW_PRECOMPILE)
            ],
            r311.r310.NEW_PRECOMPILE,
        )
        self.assertEqual(
            self.candidate[helper:helper + len(r311.r310.NEW_HELPER)],
            r311.r310.NEW_HELPER,
        )
        self.assertEqual(
            self.candidate[wall:wall + len(r311.r305.NEW_WALL_HELPER)],
            r311.r305.NEW_WALL_HELPER,
        )
        self.assertEqual(
            self.candidate[mux:mux + len(r311.r305.MUX)], r311.r305.MUX
        )
        for key in (
            "r310_precompile_route_exact",
            "r310_effective_room_helper_exact",
            "r310_room_lifecycle_helper_exact",
            "r310_bank31_mux_exact",
        ):
            self.assertTrue(self.receipt["ownership"][key])

    def test_both_cold_installers_emit_one_canonical_wram_image(self) -> None:
        canonical = r311.r307.simulate_installer(
            self.candidate, r311.r307.CANONICAL_BANK
        )
        mirror = r311.r307.simulate_installer(
            self.candidate, r311.r307.MIRROR_BANK
        )
        self.assertEqual(canonical, mirror)
        self.assertEqual(
            list(canonical),
            [region[0] for region in r311.r307.COPY_REGIONS]
            + [r311.r307.EXTENSION_REGION[0]],
        )
        self.assertEqual(
            canonical["DBF1-DBFC"], r311.r307.CANONICAL_EXTENSION
        )
        self.assertIn(
            r311.r307.R305_FIXED_PREDICATE_GATEWAY,
            canonical["DA8E-DAFF"],
        )
        self.assertEqual(
            self.receipt["installer_contract"]["mismatched_ranges"], []
        )
        self.assertEqual(
            self.receipt["installer_contract"]
            ["predicate_pointer_exceptions"],
            [],
        )

    def test_installer_entries_and_continuation_order_are_exact(self) -> None:
        for bank in (r311.r307.CANONICAL_BANK, r311.r307.MIRROR_BANK):
            self.assertEqual(
                r311.r307.absolute_transfers_to(
                    self.candidate,
                    bank,
                    r311.r307.INSTALLER_ADDR,
                    r311.r307.INSTALLER_ADDR + 1,
                ),
                [
                    (address, 0xC4, r311.r307.INSTALLER_ADDR)
                    for address in r311.r307.INSTALLER_CALL_SITES
                ],
            )
        self.assertEqual(
            r311.r307.absolute_transfers_to(
                self.candidate,
                r311.r307.MIRROR_BANK,
                r311.r307.CONTINUATION_ADDR,
                r311.r307.CONTINUATION_END,
            ),
            [(0x577A, 0xC3, r311.r307.CONTINUATION_ADDR)],
        )
        blob = r311.r307.NEW_MIRROR_CONTINUATION
        prefix_end = len(r311.r307.MIRROR_EXTENSION_PREFIX)
        final = blob.index(r311.r307.FINAL_INSTALLER)
        sentinel = blob.index(bytes.fromhex("EA 51 DF"))
        extension = blob.index(r311.r307.CANONICAL_EXTENSION)
        self.assertEqual(prefix_end, final)
        self.assertLess(final, sentinel)
        self.assertGreaterEqual(extension, sentinel + 3)

    def test_timing_delta_is_cold_only_and_exact(self) -> None:
        self.assertEqual(r311.COLD_COPY_T, 664)
        self.assertEqual(r311.COLD_INSTALLER_DELTA_T, 720)
        timing = self.receipt["timing_t_cycles"]
        self.assertEqual(timing["renderer_delta_from_r310"], 0)
        self.assertEqual(timing["ordinary_frame_delta_from_r310"], 0)
        self.assertEqual(timing["scene0b_hot_path_delta_from_r310"], 0)
        self.assertEqual(timing["bank13_installer_delta_from_r310"], 0)
        self.assertEqual(
            timing["bank16_cold_installer_delta_from_r310"], 720
        )

    def test_inherited_ffe0_scratch_lifetime_is_explicit_and_pinned(self) -> None:
        helper = r311.r310.bank_offset(
            r311.r310.HELPER_BANK, r311.r310.HELPER_ADDR
        )
        blob = self.candidate[helper:helper + len(r311.r310.NEW_HELPER)]
        self.assertTrue(blob.startswith(r311.FFE0_SCRATCH_ENTRY))
        self.assertIn(r311.FFE0_SCRATCH_RESTORE, blob)
        self.assertEqual(self.candidate[r311.PRECOMPILE_DI_ADDR], 0xF3)
        self.assertEqual(
            self.candidate[
                r311.NATIVE_FFE0_REINIT_ADDR:
                r311.NATIVE_FFE0_REINIT_ADDR + len(r311.NATIVE_FFE0_REINIT)
            ],
            r311.NATIVE_FFE0_REINIT,
        )
        note = self.receipt["reviewed_release_caveats"]["FFE0_shared_scratch"]
        self.assertIn("shared-HRAM lifetime dependency", note["classification"])
        self.assertIn("$4302 DI", note["bounded_atomic_window"])
        self.assertIn("dedicated scratch", note["fragility"])

    def test_global_bg6_policy_is_rejected_by_contextual_corpus(self) -> None:
        packed = r311.r310.r296.ROOM01_CAPTURE.read_bytes()
        positions = {
            index for index, tile in enumerate(packed)
            if tile in r311.r310.TARGET_TILES
        }
        reviewed = {
            row * 24 + column
            for row, column in r311.r310.r296.ROOM01_TARGET_CELLS
        }
        self.assertEqual(len(positions), 35)
        self.assertEqual(positions, reviewed)
        table = r311.r310.bank_offset(13, 0x7000)
        self.assertTrue(all(
            self.candidate[table + tile] == 0
            for tile in r311.r310.TARGET_TILES
        ))
        note = self.receipt["reviewed_release_caveats"][
            "global_BG6_policy_rejected"
        ]
        self.assertIn("exactly 35", note["room01_corpus"])
        self.assertIn(
            "same-ID oracle accepts BG0", note["default_and_room05_controls"]
        )
        self.assertIn("publication", note["publication_epoch_correction"])
        self.assertIn("FFE5==01", note["decision"])

    def test_r310_corrected_live_evidence_is_exact_and_passed(self) -> None:
        self.assertEqual(digest(self.live_receipt), r311.R310_LIVE_RECEIPT_SHA256)
        live = json.loads(self.live_receipt)
        self.assertTrue(live["passed"])
        self.assertEqual(live["rom_sha256"], r311.BASE_SHA256)
        self.assertTrue(all(live["checks"].values()))
        self.assertEqual(live["maximum_unexpected_lut_mismatches"], 0)
        counters = live["hazard_publication_counters"]
        self.assertEqual(counters["expected_plane_promotions"], 40)
        self.assertEqual(counters["expected_plane_invalid_promotions"], 0)
        self.assertEqual(counters["expected_plane_pending"], 0)

    def test_identity_and_installer_mutations_fail_closed(self) -> None:
        mutations = []
        bad_base = bytearray(self.base)
        bad_base[0x4309] ^= 1
        mutations.append(("r310 base", bytes(bad_base), self.base_receipt,
                          self.r307_candidate, self.r307_receipt,
                          self.live_receipt))
        bad_r307 = bytearray(self.r307_candidate)
        bad_r307[r311.r307.bank_offset(16, r311.r307.ATOMIC_SOURCE_ADDR)] ^= 1
        mutations.append(("r307 candidate", self.base, self.base_receipt,
                          bytes(bad_r307), self.r307_receipt,
                          self.live_receipt))
        bad_live = bytearray(self.live_receipt)
        bad_live[-2] ^= 1
        mutations.append(("live receipt", self.base, self.base_receipt,
                          self.r307_candidate, self.r307_receipt,
                          bytes(bad_live)))
        for label, base, base_receipt, r307_candidate, r307_receipt, live in mutations:
            with self.subTest(label=label):
                with self.assertRaises(AssertionError):
                    r311.build(
                        base, base_receipt, r307_candidate,
                        r307_receipt, live,
                    )

        mirror_mutant = bytearray(self.candidate)
        mirror_mutant[
            r311.r307.bank_offset(
                r311.r307.MIRROR_BANK, r311.r307.EXTENSION_SOURCE_ADDR
            )
        ] ^= 1
        with self.assertRaises(AssertionError):
            r311.r307.installer_contract(bytes(mirror_mutant))


if __name__ == "__main__":
    unittest.main()
