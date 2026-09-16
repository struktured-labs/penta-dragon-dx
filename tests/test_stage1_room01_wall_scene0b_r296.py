#!/usr/bin/env python3
"""Independent static controls for the r296 Stage-1 visual repair."""

from __future__ import annotations

import hashlib
from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
DIAGNOSTICS = ROOT / "scripts" / "diagnostics"
sys.path.insert(0, str(DIAGNOSTICS))

import build_stage1_room01_wall_scene0b_r296 as r296  # noqa: E402


EXPECTED_SHA256 = (
    "eb0bc7aa90260d37991f4a36a7428c4acebd72d19311489e77ef5f6371ea769e"
)
EXPECTED_HELPER = bytes.fromhex(
    "79 E0 E0 F0 B7 FE 02 20 1E FA 80 D8 E6 F6 FE 02 20 15 "
    "F0 BD 3D 3E 00 20 02 3E 06 "
    "EA 24 C6 EA 27 C6 EA 30 C6 EA 33 C6 "
    "3E 01 EA 09 DC C1 D1 3E 03 E0 70 D5 C5 "
    "11 A0 C1 06 C6 F0 E0 4F 3E 01 C9"
)


def sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


class Stage1Room01WallScene0BR296Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.base = r296.BASE.read_bytes()
        cls.base_receipt = r296.BASE_RECEIPT.read_bytes()
        cls.candidate, cls.receipt = r296.build(cls.base, cls.base_receipt)

    def test_candidate_identity_checksums_and_native_isolation(self) -> None:
        self.assertEqual(sha256(self.candidate), EXPECTED_SHA256)
        self.assertEqual(self.candidate, r296.DEFAULT_OUTPUT.read_bytes())
        self.assertEqual(self.receipt["candidate_sha256"], EXPECTED_SHA256)
        self.assertFalse(self.receipt["promotable"])
        self.assertEqual(
            self.candidate[14 * r296.BANK_SIZE:15 * r296.BANK_SIZE],
            self.base[14 * r296.BANK_SIZE:15 * r296.BANK_SIZE],
        )
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

    def test_reviewed_target_ids_are_exactly_the_35_wall_companions(self) -> None:
        packed = r296.ROOM01_CAPTURE.read_bytes()
        expected = {
            row * 24 + column for row, column in r296.ROOM01_TARGET_CELLS
        }
        actual = {
            index
            for index, tile in enumerate(packed)
            if tile in r296.TARGET_TILES
        }
        self.assertEqual(len(expected), 35)
        self.assertEqual(actual, expected)
        self.assertEqual({packed[index] for index in actual}, {0x24, 0x27, 0x30, 0x33})

    def test_wall_helper_has_exact_machine_abi(self) -> None:
        helper = r296.build_wall_helper()
        self.assertEqual(helper, EXPECTED_HELPER)
        helper_offset = r296.bank_offset(
            r296.EXPANSION_BANK, r296.WALL_HELPER_ADDR
        )
        self.assertEqual(
            self.candidate[helper_offset:helper_offset + len(EXPECTED_HELPER)],
            EXPECTED_HELPER,
        )
        # The direct $0847 entry maps A=$15, and the native compiler restores
        # SVBK1 before making any call whose return belongs to the deep frame.
        self.assertEqual(self.candidate[0x4309:0x430F], bytes.fromhex(
            "3E 15 CD 47 08 00"
        ))
        self.assertEqual(self.base[0x0847:0x0850], bytes.fromhex(
            "CD 61 00 CD 80 6C C3 61 00"
        ))
        self.assertEqual(self.base[0x434E:0x4357], bytes.fromhex(
            "AF E0 4F 3C E0 70 CD F1 DB"
        ))
        self.assertEqual(
            self.receipt["offline_contract"]["transient_mapper_frames_migrated"],
            ["084D", "430E"],
        )

    def test_room_context_model_is_scoped_and_full_byte_exact(self) -> None:
        initial = {tile: 0x80 + index for index, tile in enumerate(r296.TARGET_TILES)}
        room01 = r296.apply_wall_model(initial, scene=0x0B, ffb7=0x02, room=1)
        room05 = r296.apply_wall_model(initial, scene=0x02, ffb7=0x02, room=5)
        splash = r296.apply_wall_model(initial, scene=0x18, ffb7=0x02, room=1)
        stage2 = r296.apply_wall_model(initial, scene=0x03, ffb7=0x03, room=1)
        self.assertEqual(room01, {tile: 0x06 for tile in r296.TARGET_TILES})
        self.assertEqual(room05, {tile: 0x00 for tile in r296.TARGET_TILES})
        self.assertEqual(splash, initial)
        self.assertEqual(stage2, initial)

    def test_reachable_publisher_predicate_is_exhaustive(self) -> None:
        observed = set()
        for ffb7 in range(256):
            for dd06 in range(4):
                for ffbf in range(4):
                    scene = r296.reachable_scene(ffb7, dd06=dd06, ffbf=ffbf)
                    accepted = r296.predicate_accepts(scene, ffb7)
                    self.assertEqual(accepted, ffb7 == 0x02)
                    if accepted:
                        observed.add(scene)
        self.assertEqual(observed, {0x02, 0x0A, 0x0B})
        self.assertFalse(r296.predicate_accepts(0x18, 0x02))
        self.assertFalse(r296.predicate_accepts(0x03, 0x03))

    def test_all_scene_gate_encodings_and_targets_are_exact(self) -> None:
        for bank, predicate in r296.PREDICATE_BY_BANK.items():
            call = bytes((0xCD, predicate & 0xFF, predicate >> 8))
            gateway = r296.bank_offset(bank, r296.ATTR_GATEWAY_ADDR)
            art = r296.bank_offset(bank, r296.ART_LOADER_GATE_ADDR)
            bg7 = r296.bank_offset(bank, r296.BG7_SELECTOR_GATE_ADDR)
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
            # JR NZ at $71B9 still lands at $71C1, immediately after LD L,$C8.
            self.assertEqual(0x71BB + self.candidate[bg7 + 4], 0x71C1)

    def test_row_helper_realigns_before_unchanged_body(self) -> None:
        row = r296.bank_offset(r296.ROW_HELPER_BANK, r296.ROW_HELPER_START)
        align = r296.bank_offset(r296.ROW_HELPER_BANK, 0x6BBE)
        self.assertEqual(
            self.candidate[row:align],
            bytes.fromhex(
                "C1 FA 80 D8 E6 F6 FE 02 C2 50 6C "
                "FA FD DC B7 CA 50 6C F0 BF B7 20 0C"
            ),
        )
        end = r296.bank_offset(r296.ROW_HELPER_BANK, r296.ROW_HELPER_END)
        self.assertEqual(self.candidate[align:end], self.base[align:end])
        transition = r296.bank_offset(
            r296.ROW_HELPER_BANK, r296.TRANSITION_GATE_ADDR
        )
        self.assertEqual(
            self.candidate[transition:transition + 8],
            bytes.fromhex("FA 80 D8 E6 F6 FE 02 C0"),
        )

    def test_changed_bytes_cannot_escape_owned_ranges(self) -> None:
        allowed = {0x014D, 0x014E, 0x014F}
        allowed.update(range(0x4309, 0x430F))
        helper = r296.bank_offset(r296.EXPANSION_BANK, r296.WALL_HELPER_ADDR)
        allowed.update(range(helper, helper + len(EXPECTED_HELPER)))
        for bank in r296.MIRROR_BANKS:
            for address, size in (
                (r296.ATTR_GATEWAY_ADDR, 10),
                (r296.ART_LOADER_GATE_ADDR, 8),
                (r296.BG7_SELECTOR_GATE_ADDR, 9),
            ):
                offset = r296.bank_offset(bank, address)
                allowed.update(range(offset, offset + size))
        allowed.update(range(r296.bank_offset(13, 0x5D4C), r296.bank_offset(13, 0x5D59)))
        allowed.update(range(r296.bank_offset(16, 0x6180), r296.bank_offset(16, 0x6188)))
        allowed.update(range(r296.bank_offset(16, 0x6268), r296.bank_offset(16, 0x6270)))
        allowed.update(range(
            r296.bank_offset(19, r296.ROW_HELPER_START),
            r296.bank_offset(19, r296.ROW_HELPER_END),
        ))
        transition = r296.bank_offset(19, r296.TRANSITION_GATE_ADDR)
        allowed.update(range(transition, transition + 8))
        changed = {
            index
            for index, (old, new) in enumerate(zip(self.base, self.candidate, strict=True))
            if old != new
        }
        self.assertTrue(changed)
        self.assertLessEqual(changed, allowed)


if __name__ == "__main__":
    unittest.main()
