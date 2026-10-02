from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts/diagnostics"))
import build_stage1_menu_close_trial_r535 as trial


class MenuCloseTrialTests(unittest.TestCase):
    def test_visible_repair_is_room01_lcd_on_only_and_reveal_wait_is_explicit(self):
        self.assertTrue(trial.visible_map_repair().startswith(bytes.fromhex("F0 BD FE 01 C0 F0 40 CB 7F C8")))
        plain = trial.visible_map_repair(False)
        atomic = trial.visible_map_repair(True)
        self.assertEqual(len(atomic) - len(plain), 12)
        self.assertIn(bytes.fromhex("F0 44 FE 90 30 FA F0 44 FE 90 38 FA"), atomic)
        # Stack restore remains after the reveal barrier, not before it.
        self.assertTrue(atomic.endswith(bytes.fromhex("F1 E0 4F E1 D1 C1 C9")))

    def test_every_scene_and_stage_branch_preserves_other_paths(self):
        # Execute the actual bounded helper, not a separate semantic model.
        for scene in range(256):
            for stage in range(256):
                pc, a, zero, disabled = 0, 0, False, False
                writes = {}
                for _ in range(15):
                    opcode = trial.HELPER[pc]
                    if opcode == 0xFA:
                        self.assertEqual(trial.HELPER[pc+1:pc+3], b"\x80\xd8")
                        a, pc = scene, pc+3
                    elif opcode == 0xF0:
                        self.assertEqual(trial.HELPER[pc+1], 0xB7)
                        a, pc = stage, pc+2
                    elif opcode == 0xFE:
                        zero, pc = a == trial.HELPER[pc+1], pc+2
                    elif opcode == 0x20:
                        pc += 2 + (0 if zero else trial.HELPER[pc+1])
                    elif opcode == 0xF3:
                        disabled, pc = True, pc+1
                    elif opcode == 0x3E:
                        a, pc = trial.HELPER[pc+1], pc+2
                    elif opcode == 0xEA:
                        self.assertTrue(disabled)
                        writes[int.from_bytes(trial.HELPER[pc+1:pc+3], "little")] = a
                        pc += 3
                    elif opcode == 0xC3:
                        destination = int.from_bytes(trial.HELPER[pc+1:pc+3], "little")
                        break
                    else:
                        self.fail(f"unexpected opcode {opcode:02X}")
                else:
                    self.fail("helper did not terminate")
                if scene != 2:
                    self.assertEqual((destination,a,writes,disabled), (0x6CD0,scene,{},False))
                elif stage != 2:
                    self.assertEqual((destination,writes,disabled), (0x6CE2,{},False))
                else:
                    self.assertEqual((destination,writes,disabled), (0x6CE2,{0xDF53:255,0xDF57:255},True))

    def test_wrong_source_fails_closed(self):
        with self.assertRaises(ValueError):
            trial.build(bytes(0x80000))


if __name__ == "__main__":
    unittest.main()
