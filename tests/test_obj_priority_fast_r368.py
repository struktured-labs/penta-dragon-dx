"""Execute old/new helper instructions, including flags and balanced stack."""
import sys
from pathlib import Path
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts/diagnostics'))
import build_obj_priority_fast_r368 as patch


def execute(code, a, f, hl, slot, control):
    stack = [0x4567]
    pc = 0
    while True:
        op = code[pc]
        pc += 1
        if op == 0xE5:
            stack.insert(0, hl)
        elif op == 0xF5:
            stack.insert(0, a << 8 | f)
        elif op == 0xF0:
            assert code[pc] == 0xDD
            pc += 1
            a = slot
        elif op == 0xFE:
            n = code[pc]
            pc += 1
            f = (0x80 if a == n else 0) | 0x40 | (0x10 if a < n else 0)
        elif op in (0x30, 0x28, 0x18):
            n = code[pc]
            pc += 1
            if op == 0x18 or (op == 0x30 and not f & 0x10) or (op == 0x28 and f & 0x80):
                pc += n if n < 128 else n - 256
        elif op == 0x21:
            hl = int.from_bytes(code[pc:pc+2], 'little')
            pc += 2
        elif op == 0xD7:
            # RST $10's $09DE ADD A,L / JR NC / INC H / LD L,A.
            hl = (hl + a) & 0xFFFF
            a = hl & 255
        elif op == 0x7E:
            assert hl == 0xFFC2 + slot
            a = control
        elif op == 0xA7:
            f = 0x20 | (0x80 if a == 0 else 0)
        elif op == 0xF1:
            value = stack.pop(0)
            a, f = value >> 8, value & 0xF0
        elif op == 0xCB:
            assert code[pc] == 0xBF
            pc += 1
            a &= 127
        elif op == 0xE1:
            hl = stack.pop(0)
        elif op == 0xC9:
            return a, f, hl, stack.pop(0), stack
        else:
            raise AssertionError(hex(op))


class FastPriorityTests(unittest.TestCase):
    def test_executed_registers_flags_and_return_match(self):
        old = patch.HELPER_POSTIMAGE
        new = bytes.fromhex('CB BF C9')
        for a in range(256):
            for f in range(0, 256, 16):
                for slot in (0, 1, 2, 3, 4, 39, 255):
                    for control in (0, 1, 255):
                        self.assertEqual(execute(old, a, f, 0xCDEF, slot, control),
                                         execute(new, a, f, 0xCDEF, slot, control))

    def test_patch_only_entry_and_checksums(self):
        source = patch.BASE.read_bytes()
        rom = patch.build(source)
        changed = {i for i,(a,b) in enumerate(zip(source,rom)) if a != b}
        self.assertLessEqual(changed, {0x1188,0x1189,0x118A,0x14D,0x14E,0x14F})
        for p in patch.CALL_SITES:
            self.assertEqual(rom[p:p+3], patch.CALL)


if __name__ == '__main__':
    unittest.main()
