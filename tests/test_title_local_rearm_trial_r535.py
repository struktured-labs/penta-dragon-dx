from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts/diagnostics"))
import build_menu_title_trial_r535 as combined
import build_title_local_rearm_trial_r535 as local


class LocalTitleRearmTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.base = (ROOT / "tmp/stage4-cache-key-r534/candidate.gb").read_bytes()
        cls.source = combined.build(cls.base)
        cls.rom = local.build(cls.source)

    def test_preserves_non_title_path_and_live_cleaner_pad(self):
        w = local.WRAPPER
        self.assertEqual(self.rom[w:w+3], self.base[w:w+3])
        self.assertEqual(self.rom[w+5:w+14], self.base[w+5:w+14])
        pad = local.BANK13 + 0x6E60
        self.assertEqual(self.rom[pad:pad+15], self.base[pad:pad+15])
        self.assertEqual(self.rom[0x3B42:0x3B56], self.source[0x3B42:0x3B56])

    def test_rearm_marker_and_scene_semantics_execute_actual_bytes(self):
        # Every old scene/marker pair, plus title/non-title new scene edges.
        for old in range(256):
            for marker in range(256):
                for new in (0, 1, 2, 255):
                    pc, a, z, writes, stack = 0x76D7, 0, False, [], []
                    for _ in range(24):
                        op = self.rom[local.BANK13 + pc]
                        arg = self.rom[local.BANK13 + pc+1:local.BANK13 + pc+3]
                        target = int.from_bytes(arg, "little")
                        if op == 0x7E: a, pc = old, pc+1
                        elif op == 0x78: a, pc = new, pc+1
                        elif op == 0x3D: a = (a-1)&255; z, pc = a == 0, pc+1
                        elif op == 0xCC:
                            if z: stack.append(pc+3); pc = target
                            else: pc += 3
                        elif op == 0xFA:
                            self.assertEqual(target, 0xDF4C)
                            a, pc = marker, pc+3
                        elif op == 0xFE: z, pc = a == arg[0], pc+2
                        elif op == 0xC8: pc = stack.pop() if z else pc+1
                        elif op == 0xC3:
                            if target == 0x6BDF: break
                            pc = target
                        elif op == 0xAF: a, z, pc = 0, True, pc+1
                        elif op == 0xEA: writes.append((target, a)); pc += 3
                        elif op == 0xC9: pc = stack.pop()
                        else: self.fail(f"unexpected opcode {op:02X}")
                    else: self.fail("title wrapper did not terminate")
                    expected = int(old == 1 and marker != 0xA0) + int(new == 1)
                    self.assertEqual(writes, [(0xDF08, 0)] * expected)
                    self.assertEqual((a, stack), (new, []))

    def test_unknown_source_is_rejected(self):
        changed = bytearray(self.source)
        changed[local.LEAF] ^= 1
        with self.assertRaises(ValueError):
            local.build(changed)
