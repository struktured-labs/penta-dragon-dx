"""Execute the wait bytecode, including the VBlank-disabled escape."""
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts/diagnostics'))
import build_publication_backpressure_r382 as builder


def execute(ie, clear_after):
    code = builder.WAIT
    pc, a, flags, pending, polls = 0, 1, 0x10, 0, 0
    stack = []
    enabled = False
    for _ in range(1000):
        op = code[pc]; pc += 1
        if op == 0x3E:
            a = code[pc]; pc += 1
        elif op == 0xEA:
            assert code[pc:pc+2] == b'\x5c\xdf'
            pending = a; pc += 2
        elif op == 0xF5:
            stack.append((a, flags))
        elif op == 0xFB:
            enabled = True
        elif op == 0xF0:
            assert code[pc] == 0xFF
            a = ie; pc += 1
        elif op == 0x0F:
            flags = (a & 1) << 4
            a = (a >> 1) | ((a & 1) << 7)
        elif op in (0x30, 0x20):
            delta = code[pc]; pc += 1
            take = not (flags & (0x10 if op == 0x30 else 0x80))
            if take:
                pc += delta if delta < 128 else delta - 256
        elif op == 0xFA:
            assert code[pc:pc+2] == b'\x5c\xdf'
            polls += 1
            if enabled and ie & 1 and polls >= clear_after:
                pending = 0
            a = pending; pc += 2
        elif op == 0xB7:
            flags = 0x80 if a == 0 else 0
        elif op == 0xF1:
            a, flags = stack.pop()
        elif op == 0xC9:
            return a, flags, pending, polls, enabled, stack
        else:
            raise AssertionError(hex(op))
    raise AssertionError('wait did not return')


class WaitTests(unittest.TestCase):
    def test_all_ie_values_and_delayed_commit_preserve_af(self):
        for ie in range(256):
            for delay in (1, 2, 17):
                a, flags, pending, polls, enabled, stack = execute(ie, delay)
                self.assertEqual((a, flags, enabled, stack), (1, 0x10, True, []))
                self.assertEqual((pending, polls), (0, delay) if ie & 1 else (1, 0))

    def test_owned_bytes_and_lcd_off_tail(self):
        source = builder.BASE.read_bytes()
        candidate = builder.build(source)
        owned = set(range(0x118B, 0x118B+len(builder.WAIT)))
        owned.update(range(0x12FC, 0x1303))
        owned.update(range(builder.DONE_OFFSET, builder.DONE_OFFSET+11))
        owned.update((0x14D, 0x14E, 0x14F))
        self.assertTrue(all(i in owned for i, (a, b) in enumerate(zip(source, candidate)) if a != b))
        self.assertEqual(candidate[0x12FA:0x12FC], bytes.fromhex('18 05'))
        self.assertEqual(candidate[0x1301:0x1303], bytes.fromhex('FB C9'))


if __name__ == '__main__':
    unittest.main()
