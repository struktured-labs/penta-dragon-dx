"""#27: keep bank-dependent work out of the pre-initialization path."""
import hashlib
import importlib.util
from pathlib import Path
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('late_rearm', Path(__file__).resolve().parents[1]/'scripts/diagnostics/build_boss_prelude_late_rearm.py')
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


class LateRearmTests(unittest.TestCase):
    def setUp(self):
        self.parent = bytearray(0x100000)
        self.parent[m.EARLY:m.EARLY+6] = m.OLD_EARLY
        self.parent[0x1A49:m.HOOK+3] = bytes.fromhex('CDFD16CD4E17CD9B75')
        self.parent[m.HELPER:m.HELPER+9] = m.OLD_HELPER

    def build(self):
        with patch.object(m, 'PARENT', hashlib.sha256(self.parent).hexdigest()):
            return m.build(self.parent)

    def test_no_banked_call_before_native_initialization(self):
        rom = self.build()
        self.assertEqual(rom[m.EARLY:m.EARLY+6], m.NATIVE_EARLY)
        self.assertEqual(rom[0x1A49:m.HOOK], bytes.fromhex('CDFD16CD4E17'))
        self.assertEqual(rom[m.HOOK:m.HOOK+3], bytes.fromhex('CD9A7C'))

    def test_wrapper_preserves_af_stack_and_tail_target(self):
        rom = self.build()
        for af in range(0, 65536, 16):
            memory = bytearray(65536)
            memory[:0x8000] = rom[:0x8000]
            pc, sp, value, cycles = m.HELPER, 0xDFDE, af, 0
            while pc != 0x759B:
                op = memory[pc]
                pc += 1
                if op == 0xF5:
                    sp -= 2
                    memory[sp:sp+2] = value.to_bytes(2, 'little')
                    cycles += 16
                elif op == 0x3E:
                    value = memory[pc] << 8 | (value & 255)
                    pc += 1
                    cycles += 8
                elif op == 0xE0:
                    memory[0xFF00+memory[pc]] = value >> 8
                    pc += 1
                    cycles += 12
                elif op == 0xF1:
                    value = int.from_bytes(memory[sp:sp+2], 'little') & 0xFFF0
                    sp += 2
                    cycles += 12
                elif op == 0xC3:
                    pc = int.from_bytes(memory[pc:pc+2], 'little')
                    cycles += 16
                else:
                    self.fail(f'unexpected opcode {op:02x}')
            self.assertEqual((value, sp, cycles, memory[0xFF91]), (af, 0xDFDE, 64, 1))

    def test_only_named_sites_and_checksum_change(self):
        rom = self.build()
        allowed = {0x14e, 0x14f} | set(range(m.EARLY, m.EARLY+6)) | set(range(m.HOOK, m.HOOK+3)) | set(range(m.HELPER, m.HELPER+9))
        self.assertTrue({i for i, (a, b) in enumerate(zip(rom, self.parent)) if a != b} <= allowed)
        self.assertEqual(int.from_bytes(rom[0x14e:0x150], 'big'), (sum(rom[:0x14e])+sum(rom[0x150:])) & 65535)

    def test_changed_entry_rejected_even_with_repin(self):
        for address in (m.EARLY, 0x1A49, m.HOOK, m.HELPER):
            self.parent[address] ^= 1
            with self.assertRaisesRegex(ValueError, 'preimage'):
                self.build()
            self.parent[address] ^= 1

    def test_unknown_parent_rejected(self):
        with self.assertRaisesRegex(ValueError, 'exact'):
            m.build(self.parent)


if __name__ == '__main__':
    unittest.main()
