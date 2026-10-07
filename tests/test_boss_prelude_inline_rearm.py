"""#27: execute old/new fixed-bank preludes and compare all native effects."""
import hashlib
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts/diagnostics'))
import build_boss_prelude_inline_rearm as build


def execute(code, flags, bank):
    registers = dict(a=0x73, b=0x6A, c=0x8E, d=0x23, e=0xC1,
                     h=0xAA, l=0x55, f=flags, sp=0xDFF1, bank=bank)
    writes = []
    pc = cycles = 0
    while pc < len(code):
        op = code[pc]
        pc += 1
        if op == 0x21:
            registers['l'], registers['h'] = code[pc:pc+2]
            pc += 2; cycles += 12
        elif op == 0xAF:
            registers['a'], registers['f'] = 0, 0x80
            cycles += 4
        elif op in (0x06, 0x2E, 0x3E):
            registers[{0x06:'b', 0x2E:'l', 0x3E:'a'}[op]] = code[pc]
            pc += 1; cycles += 8
        elif op == 0x22:
            hl = registers['h'] * 256 + registers['l']
            writes.append((hl, registers['a']))
            hl = (hl + 1) & 65535
            registers['h'], registers['l'] = hl >> 8, hl & 255
            cycles += 8
        elif op == 0x05:
            old = registers['b']; value = (old - 1) & 255
            registers['b'] = value
            registers['f'] = ((registers['f'] & 0x10) | 0x40
                              | (0x80 if value == 0 else 0)
                              | (0x20 if old & 15 == 0 else 0))
            cycles += 4
        elif op == 0x20:
            delta = code[pc]; pc += 1
            if registers['f'] & 0x80:
                cycles += 8
            else:
                pc += delta - 256 if delta >= 128 else delta
                cycles += 12
        elif op == 0xE0:
            writes.append((0xFF00 + code[pc], registers['a']))
            pc += 1; cycles += 12
        else:
            raise AssertionError(f'unexpected opcode {op:02X}')
    return registers, writes, cycles, pc


class InlineRearmTests(unittest.TestCase):
    def test_native_effects_and_bank_preserved_for_all_flags(self):
        for bank in (1, 3, 13, 16, 63):
            for flags in range(0, 256, 16):
                before, old_writes, old_cycles, old_pc = execute(build.OLD, flags, bank)
                after, new_writes, new_cycles, new_pc = execute(build.NEW, flags, bank)
                self.assertEqual(before, after)
                self.assertEqual([pair for pair in new_writes if pair[0] != 0xFF91], old_writes)
                self.assertEqual([pair for pair in new_writes if pair[0] == 0xFF91], [(0xFF91, 1)])
                self.assertEqual(new_cycles - old_cycles, 4)
                self.assertEqual((old_pc, new_pc), (26, 26))
                self.assertEqual(after['bank'], bank)
                self.assertEqual(old_writes, [(address, 0) for address in (*range(0xFFC2, 0xFFC6), *range(0xFFB2, 0xFFB7))] + [(0xFFDA, 1), (0xFFE4, 1)])

    def test_patches_only_prelude_and_checksum(self):
        parent = bytearray(0x100000)
        parent[build.HOOK:build.HOOK+26] = build.OLD
        with patch.object(build, 'PARENT', hashlib.sha256(parent).hexdigest()):
            result = build.build(parent)
        changed = {i for i, (a, b) in enumerate(zip(parent, result)) if a != b}
        self.assertTrue(changed <= set(range(build.HOOK, build.HOOK+26)) | {0x14E, 0x14F})
        self.assertEqual(result[build.HOOK:build.HOOK+26], build.NEW)

    def test_wrong_identity_and_re_pinned_wrong_preimage_rejected(self):
        with self.assertRaisesRegex(ValueError, 'exact'):
            build.build(bytes(0x100000))
        parent = bytes(0x100000)
        with patch.object(build, 'PARENT', hashlib.sha256(parent).hexdigest()):
            with self.assertRaisesRegex(ValueError, 'preimage'):
                build.build(parent)


if __name__ == '__main__':
    unittest.main()
