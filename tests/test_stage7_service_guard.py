from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import stage7_service_guard as guard


class Stage7ServiceGuardTest(unittest.TestCase):
    def test_guards_skip_only_exact_stage7_scene(self):
        for code in (guard.DEATH_GUARD, guard.ART_GUARD):
            skipped = [
                scene for scene in range(256)
                if guard.modeled_service(code, scene=scene) == "skip"
            ]
            self.assertEqual(skipped, [0x08])
        self.assertEqual(
            guard.modeled_service(guard.DEATH_GUARD, scene=0x17),
            "death_story",
        )
        self.assertEqual(
            guard.modeled_service(guard.ART_GUARD, scene=0x02),
            "stage1_art",
        )

    def test_guard_bodies_are_receipt_exact(self):
        self.assertEqual(
            guard.DEATH_GUARD,
            bytes.fromhex("FA 80 D8 FE 08 C8 C3 00 71"),
        )
        self.assertEqual(
            guard.ART_GUARD,
            bytes.fromhex("FA 80 D8 FE 08 C8 C3 0E 6A"),
        )

    def test_menu_fallthrough_is_register_and_cycle_exact(self):
        code = guard.build_menu_delay_region()
        self.assertEqual(len(code), len(guard.MENU_DELAY_PREIMAGE))
        self.assertEqual(code[:2], bytes.fromhex("18 09"))
        self.assertEqual(code[2:11], guard.ART_GUARD)
        self.assertEqual(guard.menu_delay_cycles(code), 48)

    def test_install_is_preimage_locked_and_scoped(self):
        rom = bytearray([0xA5]) * (32 * guard.BANK_SIZE)

        def put(address, payload):
            offset = guard.bank_offset(address)
            rom[offset:offset + len(payload)] = payload

        put(guard.DEATH_GUARD_ADDR, guard.DEATH_GUARD_SLOT_PREIMAGE)
        put(
            guard.DEATH_GUARD_ADDR + len(guard.DEATH_GUARD_SLOT_PREIMAGE),
            guard.DEATH_GUARD_BOUNDARY,
        )
        put(guard.PAIR_CALL_ADDR, guard.PAIR_CALL_PREIMAGE)
        put(guard.ART_CALL_ADDR, guard.ART_CALL_PREIMAGE)
        put(
            guard.MENU_DELAY_START - len(guard.MENU_OWNER_PREIMAGE),
            guard.MENU_OWNER_PREIMAGE,
        )
        put(guard.MENU_DELAY_START, guard.MENU_DELAY_PREIMAGE)
        put(guard.MENU_DELAY_END, guard.MENU_DELAY_BOUNDARY)
        before = bytes(rom)
        report = guard.install(rom)
        self.assertEqual(report.death_guard, 0x570E)
        self.assertEqual(report.art_guard, 0x6EC6)
        self.assertEqual(report.original_menu_delay_cycles, 48)
        self.assertEqual(report.guarded_menu_delay_cycles, 48)
        self.assertEqual(
            rom[
                guard.bank_offset(guard.PAIR_CALL_ADDR):
                guard.bank_offset(guard.PAIR_CALL_ADDR) + 6
            ],
            bytes.fromhex("CD 0E 57 CD 60 6A"),
        )
        self.assertEqual(
            rom[
                guard.bank_offset(guard.ART_CALL_ADDR):
                guard.bank_offset(guard.ART_CALL_ADDR) + 3
            ],
            bytes.fromhex("C4 C6 6E"),
        )

        allowed = set()
        for address, size in (
            (guard.DEATH_GUARD_ADDR, len(guard.DEATH_GUARD)),
            (guard.PAIR_CALL_ADDR, 3),
            (guard.ART_CALL_ADDR, 3),
            (guard.MENU_DELAY_START, len(guard.MENU_DELAY_PREIMAGE)),
        ):
            offset = guard.bank_offset(address)
            allowed.update(range(offset, offset + size))
        changed = {
            index for index, (old, new) in enumerate(zip(before, rom))
            if old != new
        }
        self.assertTrue(changed <= allowed)


if __name__ == "__main__":
    unittest.main()
