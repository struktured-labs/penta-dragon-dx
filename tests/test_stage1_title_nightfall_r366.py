from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
DIAGNOSTICS = ROOT / "scripts" / "diagnostics"
sys.path.insert(0, str(DIAGNOSTICS))

import build_stage1_title_nightfall_r366 as r366  # noqa: E402


class Stage1TitleNightfallR366Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.base = r366.BASE.read_bytes()
        cls.base_receipt = r366.BASE_RECEIPT.read_bytes()
        cls.candidate, cls.receipt = r366.build(
            cls.base, cls.base_receipt
        )

    def test_builder_is_exact_and_deterministic(self) -> None:
        rebuilt, receipt = r366.build(self.base, self.base_receipt)
        self.assertEqual(rebuilt, self.candidate)
        self.assertEqual(receipt, self.receipt)
        self.assertEqual(
            hashlib.sha256(rebuilt).hexdigest(),
            r366.EXPECTED_CANDIDATE_SHA256,
        )
        self.assertEqual(
            self.receipt["candidate_sha256"],
            r366.EXPECTED_CANDIDATE_SHA256,
        )

    def test_title_assets_are_the_reviewed_nightfall_payload(self) -> None:
        records = r366.title.parse_title_list(self.base)
        attrs, coverage = r366.title.build_attribute_image(records)
        palettes = r366.title.build_palette_block(
            r366.title.SCHEMES["Nightfall"]
        )
        attr_start = r366.bank_offset(r366.CODE_BANK, r366.ATTR_IMAGE_ADDR)
        palette_start = r366.bank_offset(r366.CODE_BANK, r366.PAL_DATA_ADDR)
        self.assertEqual(
            self.candidate[attr_start:attr_start + len(attrs)], bytes(attrs)
        )
        self.assertEqual(
            self.candidate[palette_start:palette_start + len(palettes)],
            palettes,
        )
        self.assertEqual(self.receipt["title"]["scheme"], "Nightfall")
        self.assertEqual(self.receipt["title"]["attribute_cells"], coverage)
        self.assertEqual(set(attrs), {1, 2, 3, 4, 5, 6})

    def test_service_and_transition_hooks_are_exact(self) -> None:
        service = r366.build_title_service()
        service_start = r366.bank_offset(r366.CODE_BANK, r366.SERVICE_ADDR)
        self.assertEqual(
            self.candidate[service_start:service_start + len(service)],
            service,
        )
        wrapper, clear = r366.build_rearm_pads()
        wrapper_start = r366.bank_offset(
            r366.LIVE_BANK, r366.REARM_WRAPPER_PAD_ADDR
        )
        clear_start = r366.bank_offset(
            r366.LIVE_BANK, r366.CLEAR_HELPER_PAD_ADDR
        )
        transition = r366.bank_offset(
            r366.LIVE_BANK, r366.TRANSITION_CRYSTAL_CALL_ADDR
        )
        cleaner = r366.bank_offset(r366.LIVE_BANK, r366.CLEANER_TAIL_ADDR)
        self.assertEqual(
            self.candidate[cleaner:cleaner + len(r366.CLEANER_TAIL_PATCH)],
            r366.CLEANER_TAIL_PATCH,
        )
        self.assertEqual(
            self.candidate[wrapper_start:wrapper_start + len(wrapper)], wrapper
        )
        self.assertEqual(
            self.candidate[clear_start:clear_start + len(clear)], clear
        )
        self.assertEqual(
            self.candidate[transition:transition + 3],
            bytes((
                0xCD,
                r366.REARM_WRAPPER_ADDR & 0xFF,
                r366.REARM_WRAPPER_ADDR >> 8,
            )),
        )

    def test_live_nop_pad_fallthrough_fences_land_after_each_pad(self) -> None:
        wrapper, clear = r366.build_rearm_pads()
        self.assertEqual(
            r366.REARM_WRAPPER_PAD_ADDR + 2 + wrapper[1],
            r366.REARM_WRAPPER_PAD_ADDR + r366.REARM_WRAPPER_PAD_SIZE,
        )
        self.assertEqual(
            r366.CLEAR_HELPER_PAD_ADDR + 2 + clear[1],
            r366.CLEAR_HELPER_PAD_ADDR + r366.CLEAR_HELPER_PAD_SIZE,
        )

    def test_patch_preserves_sarah_fix_and_stays_inside_owned_bytes(self) -> None:
        self.assertEqual(self.candidate[0x1199:0x119B], bytes.fromhex("CB BF"))
        attrs, _ = r366.title.build_attribute_image(
            r366.title.parse_title_list(self.base)
        )
        palettes = r366.title.build_palette_block(
            r366.title.SCHEMES["Nightfall"]
        )
        service = r366.build_title_service()
        owned: set[int] = set()

        def own(bank: int, address: int, size: int) -> None:
            start = r366.bank_offset(bank, address)
            owned.update(range(start, start + size))

        own(r366.CODE_BANK, r366.ATTR_IMAGE_ADDR, len(attrs))
        own(r366.CODE_BANK, r366.PAL_DATA_ADDR, len(palettes))
        own(r366.CODE_BANK, r366.SERVICE_ADDR, len(service))
        own(r366.LIVE_BANK, r366.CLEANER_TAIL_ADDR,
            len(r366.CLEANER_TAIL_PATCH))
        own(r366.LIVE_BANK, r366.REARM_WRAPPER_PAD_ADDR,
            r366.REARM_WRAPPER_PAD_SIZE)
        own(r366.LIVE_BANK, r366.CLEAR_HELPER_PAD_ADDR,
            r366.CLEAR_HELPER_PAD_SIZE)
        own(r366.LIVE_BANK, r366.TRANSITION_CRYSTAL_CALL_ADDR, 3)
        changed = {
            index
            for index, pair in enumerate(
                zip(self.base, self.candidate, strict=True)
            )
            if pair[0] != pair[1]
        }
        self.assertLessEqual(changed, owned | r366.CHECKSUM_OFFSETS)

    def test_rom_checksums_are_valid(self) -> None:
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

    def test_written_receipt_is_bound_to_written_candidate(self) -> None:
        written = r366.DEFAULT_OUTPUT.read_bytes()
        receipt = json.loads(r366.DEFAULT_RECEIPT.read_text())
        self.assertEqual(
            hashlib.sha256(written).hexdigest(),
            r366.EXPECTED_CANDIDATE_SHA256,
        )
        self.assertEqual(
            receipt["candidate_sha256"], r366.EXPECTED_CANDIDATE_SHA256
        )


if __name__ == "__main__":
    unittest.main()
