"""Exercise emitted source stores without granting cache/lifecycle readiness."""
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts/diagnostics'))
import build_exact_source_dirty_r385 as builder


def execute(new, old, scene, stage, advance):
    code = builder.store_helper(0x7100, advance=advance)
    a, flags, pc, bc, hl = 0, 0x10, 0, 0xA000, 0xC1A0
    stack, writes = [], {}
    while pc < len(code):
        op = code[pc]; pc += 1
        if op == 0x0A: a = new
        elif op == 0x03: bc += 1
        elif op == 0xF5: stack.append((a, flags))
        elif op == 0xBE: flags = 0x80 if a == old else 0
        elif op in (0x28, 0x20):
            delta = code[pc]; pc += 1
            if bool(flags & 0x80) == (op == 0x28): pc += delta
        elif op == 0xFA:
            assert code[pc:pc+2] == b'\x80\xd8'
            a = scene; pc += 2
        elif op == 0xFE:
            flags = 0x80 if a == code[pc] else 0; pc += 1
        elif op == 0xF0:
            assert code[pc] == 0xBA
            a = stage; pc += 1
        elif op == 0xB7: flags = 0x80 if a == 0 else 0
        elif op == 0x3E: a = code[pc]; pc += 1
        elif op == 0xEA:
            address = int.from_bytes(code[pc:pc+2], 'little'); pc += 2
            writes[address] = a
        elif op == 0xF1: a, flags = stack.pop()
        elif op in (0x22, 0x77):
            writes[hl] = a
            if op == 0x22: hl += 1
        elif op == 0xC9: return a, flags, bc, hl, writes, stack
        else: raise AssertionError(hex(op))
    raise AssertionError('missing return')


class StoreTests(unittest.TestCase):
    def test_exact_change_detection_and_native_registers(self):
        for new in range(256):
            for old in (new, new ^ 255, 0, 255):
                for scene, stage in ((2, 0), (2, 1), (10, 0)):
                    for advance in (False, True):
                        a, flags, bc, hl, writes, stack = execute(new, old, scene, stage, advance)
                        self.assertEqual((a, flags, bc, hl, stack),
                                         (new, 0x10, 0xA000+advance, 0xC1A0+advance, []))
                        expected = {0xC1A0: new}
                        if new != old and (scene, stage) == (2, 0):
                            expected.update({0xDF53: 255, 0xDF57: 255})
                        self.assertEqual(writes, expected)


if __name__ == '__main__':
    unittest.main()
