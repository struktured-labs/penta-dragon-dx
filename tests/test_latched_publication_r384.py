"""Execute snapshot packing: page, scroll, readiness, repeated requests."""
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts/diagnostics'))
from build_idempotent_latched_publication_r384 import PACK


def pack(target, x, y, previous_x=0):
    pc, a, b, zero, carry = 0, 0, 0, False, False
    latched_x = previous_x
    while pc < len(PACK):
        op = PACK[pc]; pc += 1
        if op == 0xF0:
            assert PACK[pc] == 0xC4
            a = target; pc += 1
        elif op == 0xCB:
            assert PACK[pc] == 0x77
            zero = not (a & 0x40); pc += 1
        elif op == 0xC0:
            if not zero: return target, latched_x
        elif op == 0xFA:
            address = int.from_bytes(PACK[pc:pc+2], 'little'); pc += 2
            a = {0xDC00: x, 0xDC02: y}[address]
        elif op == 0xEA:
            assert PACK[pc:pc+2] == b'\x5c\xdf'
            latched_x = a; pc += 2
        elif op == 0xB7:
            zero = a == 0; carry = False
        elif op == 0x28:
            delta = PACK[pc]; pc += 1
            if zero: pc += delta
        elif op == 0xE6:
            a &= PACK[pc]; pc += 1
            zero = a == 0; carry = False
        elif op == 0x07:
            carry = bool(a & 0x80)
            a = ((a << 1) & 255) | int(carry); zero = False
        elif op == 0xF6:
            a |= PACK[pc]; pc += 1
            zero = a == 0; carry = False
        elif op == 0x47:
            b = a
        elif op == 0xB0:
            a |= b; zero = a == 0; carry = False
        elif op == 0xE0:
            assert PACK[pc] == 0xC4
            target = a; pc += 1
        elif op == 0xC9:
            return target, latched_x
        else:
            raise AssertionError(hex(op))
    raise AssertionError('missing return')


class SnapshotTests(unittest.TestCase):
    def test_all_coordinate_bytes_and_pages(self):
        for x in range(256):
            for y in range(256):
                for raw in (0, 0x9B, 0x9F):
                    target, saved_x = pack(raw, x, y)
                    self.assertEqual(saved_x, x)
                    self.assertEqual(target & 15, y & 15)
                    self.assertTrue(target & 0x40)
                    self.assertEqual(bool(target & 0x80), bool(raw))
                    self.assertEqual((target & 0x10) >> 1, (raw & 4) << 1)

    def test_repeated_requests_keep_the_completed_snapshot(self):
        for x in range(16):
            for y in range(16):
                for page in (0, 0x9B, 0x9F):
                    target, saved_x = pack(page, x, y)
                    self.assertEqual(pack(target, x ^ 15, y ^ 15, saved_x),
                                     (target, saved_x))


if __name__ == '__main__':
    unittest.main()
