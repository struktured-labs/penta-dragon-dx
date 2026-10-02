"""The native priority writer must not erase a pending physical map."""
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts/diagnostics'))
import build_native_priority_collision_r381 as builder


def execute(code, *, a, flags, target):
    # Execute the actual two-byte replacement for each native store.
    pc = 0
    while pc < len(code):
        opcode = code[pc]
        pc += 1
        if opcode == 0:
            continue
        if opcode == 0xE0:
            if code[pc] != 0xC4:
                raise AssertionError('unexpected destination')
            pc += 1
            target = a
        else:
            raise AssertionError(f'unexpected opcode {opcode:02x}')
    return a, flags, target


class CollisionTests(unittest.TestCase):
    def test_actual_bytes_preserve_pending_target_and_registers(self):
        source = builder.BASE.read_bytes()
        candidate = builder.build(source)
        for address in builder.STORES:
            for target in (0, 0x98, 0x9B, 0x9C, 0x9F):
                for a in (0, 1):
                    for flags in range(0, 256, 16):
                        self.assertEqual(execute(candidate[address:address+2],
                            a=a, flags=flags, target=target), (a, flags, target))
            # Exact observed r380 failure: native clear loses 9B, selecting
            # relative fallback instead of the completed absolute map.
            self.assertEqual(execute(source[address:address+2],
                a=0, flags=0x80, target=0x9B)[2], 0)

    def test_only_two_stores_and_checksums_change(self):
        source = builder.BASE.read_bytes()
        candidate = builder.build(source)
        changed = {i for i, (a, b) in enumerate(zip(source, candidate)) if a != b}
        self.assertEqual(changed - {0x14D, 0x14E, 0x14F},
                         {0x50C5, 0x50C6, 0x50CA, 0x50CB})
        with self.assertRaises(ValueError):
            builder.build(bytes(len(source)))


if __name__ == '__main__':
    unittest.main()
