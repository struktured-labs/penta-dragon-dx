from __future__ import annotations

import hashlib
from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
DIAGNOSTICS = ROOT / "scripts" / "diagnostics"
sys.path.insert(0, str(DIAGNOSTICS))

import build_stage1_sara_priority_clear_r365 as r365  # noqa: E402


class SaraPriorityClearTests(unittest.TestCase):
    def test_exact_builder_is_deterministic_and_hash_bound(self) -> None:
        source = r365.BASE.read_bytes()
        receipt = r365.BASE_RECEIPT.read_bytes()
        first, first_receipt = r365.build(source, receipt)
        second, second_receipt = r365.build(source, receipt)
        self.assertEqual(first, second)
        self.assertEqual(first_receipt, second_receipt)
        self.assertEqual(
            hashlib.sha256(first).hexdigest(),
            r365.EXPECTED_CANDIDATE_SHA256,
        )

    def test_patch_is_one_logic_byte_plus_checksums(self) -> None:
        source = r365.BASE.read_bytes()
        candidate, _ = r365.build(source, r365.BASE_RECEIPT.read_bytes())
        changed = {
            index
            for index, pair in enumerate(zip(source, candidate, strict=True))
            if pair[0] != pair[1]
        }
        self.assertIn(r365.PRIORITY_SET_OPCODE_OFFSET, changed)
        self.assertLessEqual(
            changed,
            {r365.PRIORITY_SET_OPCODE_OFFSET} | set(r365.CHECKSUM_OFFSETS),
        )
        self.assertEqual(
            candidate[r365.HELPER_START:r365.HELPER_START + len(r365.HELPER_POSTIMAGE)],
            r365.HELPER_POSTIMAGE,
        )

    def test_all_non_priority_attribute_bits_are_preserved(self) -> None:
        for attr in range(0x100):
            for slot in range(0x100):
                for control in (0, 1, 0x7F, 0xFF):
                    old = r365.r364_priority(attr, slot, control)
                    new = r365.r365_priority(attr, slot, control)
                    self.assertEqual((old ^ new) & 0x7F, 0)
                    self.assertEqual(new & 0x80, 0)

    def test_non_sara_slots_are_result_and_cycle_exact(self) -> None:
        for attr in range(0x100):
            for slot in range(4, 0x100):
                for control in (0, 1, 0xFF):
                    self.assertEqual(
                        r365.r365_priority(attr, slot, control),
                        r365.r364_priority(attr, slot, control),
                    )
        changed = [
            index
            for index, pair in enumerate(
                zip(r365.HELPER_PREIMAGE, r365.HELPER_POSTIMAGE, strict=True)
            )
            if pair[0] != pair[1]
        ]
        self.assertEqual(changed, [18])
        self.assertEqual(r365.HELPER_PREIMAGE[17:19], bytes.fromhex("CB FF"))
        self.assertEqual(r365.HELPER_POSTIMAGE[17:19], bytes.fromhex("CB BF"))

    def test_both_emitter_call_sites_are_unchanged(self) -> None:
        source = r365.BASE.read_bytes()
        candidate, _ = r365.build(source, r365.BASE_RECEIPT.read_bytes())
        for site in r365.CALL_SITES:
            self.assertEqual(source[site:site + 3], r365.CALL)
            self.assertEqual(candidate[site:site + 3], r365.CALL)

    def test_wrong_base_and_receipt_are_rejected(self) -> None:
        source = bytearray(r365.BASE.read_bytes())
        source[0x200] ^= 1
        with self.assertRaisesRegex(AssertionError, "wrong exact r364 base"):
            r365.build(bytes(source), r365.BASE_RECEIPT.read_bytes())
        receipt = bytearray(r365.BASE_RECEIPT.read_bytes())
        receipt[-2] ^= 1
        with self.assertRaisesRegex(AssertionError, "receipt identity drifted"):
            r365.build(r365.BASE.read_bytes(), bytes(receipt))


if __name__ == "__main__":
    unittest.main()
