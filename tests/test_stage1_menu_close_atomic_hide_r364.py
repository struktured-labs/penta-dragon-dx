from __future__ import annotations

import hashlib
from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
DIAGNOSTICS = ROOT / "scripts" / "diagnostics"
sys.path.insert(0, str(DIAGNOSTICS))

import build_stage1_menu_close_atomic_hide_r364 as r364  # noqa: E402
import verify_menu_window_order as window_verifier  # noqa: E402


WINDOW_ENABLE = 0x20


def interrupt_admission_points(instructions: list[tuple[str, str]]) -> list[str]:
    """Model instruction boundaries at which r363/r364 can accept VBlank."""
    ime = False
    delayed_enable = False
    points: list[str] = []
    for phase, opcode in instructions:
        if ime:
            points.append(phase)
        if opcode == "DI":
            ime = False
            delayed_enable = False
        elif opcode == "EI":  # enabled after the following instruction
            delayed_enable = True
        elif delayed_enable:
            ime = True
            delayed_enable = False
    return points


class AtomicMenuCloseTests(unittest.TestCase):
    def test_exact_builder_is_deterministic_and_hash_bound(self) -> None:
        source = r364.BASE.read_bytes()
        receipt = r364.BASE_RECEIPT.read_bytes()
        first, first_receipt = r364.build(source, receipt)
        second, second_receipt = r364.build(source, receipt)

        self.assertEqual(first, second)
        self.assertEqual(first_receipt, second_receipt)
        self.assertEqual(
            hashlib.sha256(first).hexdigest(),
            r364.EXPECTED_CANDIDATE_SHA256,
        )

    def test_r363_has_pre_clear_interrupt_window_and_r364_does_not(self) -> None:
        # The relevant r363 order is DI ... EI; JP $6CE2; POP HL; POP AF;
        # XOR A; LDH [$FFE4],A.  EI becomes live on entry to $6CE2, before
        # the first ownership-clearing store.
        r363_order = [
            ("wrapper", "DI"), ("wrapper", "EI"), ("wrapper", "JP"),
            ("exit-before-clear", "POP HL"),
            ("exit-before-clear", "POP AF"),
            ("exit-before-clear", "XOR A"),
            ("exit-before-clear", "FFE4=0"),
        ]
        self.assertIn("exit-before-clear",
                      interrupt_admission_points(r363_order))

        # r364 removes the early EI.  Its helper relinquishes FFE4, hides the
        # Window, restores native A/Z, and only then executes EI + JP.
        r364_order = [
            ("wrapper", "DI"), ("wrapper", "NOP"), ("wrapper", "JP"),
            ("exit-before-clear", "POP HL"),
            ("exit-before-clear", "POP AF"),
            ("exit-before-clear", "JP"),
            ("exit-before-clear", "XOR A"),
            ("exit-before-clear", "FFE4=0"),
            ("exit-after-clear", "READ LCDC"),
            ("exit-after-clear", "CLEAR LCDC.5"),
            ("exit-after-clear", "WRITE LCDC"),
            ("exit-after-clear", "XOR A"),
            ("exit-after-clear", "EI"),
            ("return-after-clear", "JP"),
            ("return-after-clear", "bank1 thunk"),
        ]
        points = interrupt_admission_points(r364_order)
        self.assertNotIn("exit-before-clear", points)
        self.assertNotIn("exit-after-clear", points)
        self.assertEqual(points, ["return-after-clear"])

    def test_window_harness_rejects_r363_and_authenticates_r364(self) -> None:
        source = r364.BASE.read_bytes()
        candidate, _ = r364.build(source, r364.BASE_RECEIPT.read_bytes())
        self.assertEqual(
            window_verifier.menu_close_atomicity(source),
            "unsafe-ei-before-owner-clear",
        )
        self.assertEqual(
            window_verifier.menu_close_atomicity(candidate),
            "atomic-owner-clear-window-hide-before-ei",
        )

    def test_atomic_helper_hides_window_for_every_lcdc_value(self) -> None:
        for lcdc in range(0x100):
            hidden = lcdc & ~WINDOW_ENABLE
            self.assertEqual(hidden & WINDOW_ENABLE, 0)
            self.assertEqual(hidden & ~WINDOW_ENABLE,
                             lcdc & ~WINDOW_ENABLE)

        clear_owner = r364.ATOMIC_EXIT.index(bytes.fromhex("AF E0 E4"))
        hide = r364.ATOMIC_EXIT.index(bytes.fromhex("F0 40 CB AF E0 40"))
        enable = r364.ATOMIC_EXIT.index(bytes.fromhex("FB C3 9A 09"))
        self.assertLess(clear_owner, hide)
        self.assertLess(hide, enable)
        self.assertEqual(r364.ATOMIC_EXIT.count(0xFB), 1)

    def test_patch_is_menu_close_only_and_keeps_r363_vblank_code(self) -> None:
        source = r364.BASE.read_bytes()
        candidate, _ = r364.build(source, r364.BASE_RECEIPT.read_bytes())
        changed = {
            index for index, pair in enumerate(zip(source, candidate, strict=True))
            if pair[0] != pair[1]
        }
        expected = (
            set(range(r364.bank_offset(r364.MENU_EXIT_ADDR),
                      r364.bank_offset(r364.MENU_EXIT_ADDR)
                      + len(r364.MENU_EXIT_PATCH)))
            | set(range(r364.bank_offset(r364.WRAPPER_TAIL_ADDR),
                        r364.bank_offset(r364.WRAPPER_TAIL_ADDR)
                        + len(r364.WRAPPER_TAIL_PATCH)))
            | set(range(r364.bank_offset(r364.ATOMIC_EXIT_ADDR),
                        r364.bank_offset(r364.ATOMIC_EXIT_ADDR)
                        + len(r364.ATOMIC_EXIT)))
            | set(r364.CHECKSUM_OFFSETS)
        )
        self.assertLessEqual(changed, expected)


if __name__ == "__main__":
    unittest.main()
