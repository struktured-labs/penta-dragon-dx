"""Execute the actual restore instructions with a nested CALL stack."""
import sys
from pathlib import Path
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts/diagnostics'))
import build_stage1_title_stack_r367 as patch


def execute_tail(code, lcdc):
    # SP points at CALL $6C80's return word. Next is CALL $0847's return,
    # saved AF containing LCDC, and saved AF containing VBK.
    stack = [0x084D, 0x6E53, lcdc << 8 | 0x80, 0x01B0]
    registers = {'AF': 0, 'HL': 0x6270, 'DE': 0x1234}
    hardware = {}
    pc = 0
    while pc < len(code):
        op = code[pc]
        pc += 1
        if op == 0xAF:
            registers['AF'] = 0x80
        elif op == 0xE0:
            hardware[0xFF00 | code[pc]] = registers['AF'] >> 8
            pc += 1
        elif op in (0xE1, 0xD1, 0xF1):
            name = {0xE1: 'HL', 0xD1: 'DE', 0xF1: 'AF'}[op]
            registers[name] = stack.pop(0)
            if name == 'AF':
                registers[name] &= 0xFFF0
        elif op in (0xE5, 0xD5):
            stack.insert(0, registers[{0xE5: 'HL', 0xD5: 'DE'}[op]])
        elif op == 0x3E:
            registers['AF'] = code[pc] << 8 | (registers['AF'] & 255)
            pc += 1
        elif op == 0xC9:
            return stack.pop(0), stack, hardware, registers['AF'] >> 8
        else:
            raise AssertionError(f'unsupported opcode {op:02x}')
    raise AssertionError('tail did not return')


class StackContract(unittest.TestCase):
    def test_old_candidate_reproduces_wrong_lcdc_and_return(self):
        target, stack, hw, bank = execute_tail(patch.OLD_TAIL, 0x83)
        self.assertEqual(hw[0xFF40], 0x08)
        self.assertEqual(target, 0x6E53)  # skipped bank-restoring trampoline
        self.assertEqual(stack[0], 0x8380)  # saved LCDC still stranded

    def test_fixed_tail_preserves_both_return_addresses_for_all_lcdc(self):
        for lcdc in range(256):
            with self.subTest(lcdc=lcdc):
                target, stack, hw, bank = execute_tail(patch.NEW_TAIL, lcdc)
                self.assertEqual(target, 0x084D)
                self.assertEqual(stack, [0x6E53, 0x01B0])
                self.assertEqual(hw, {0xFF4F: 0, 0xFF40: lcdc})
                self.assertEqual(bank, 13)

    def test_built_rom_contains_executed_tail_and_preserves_sara_fix(self):
        rom, offset = patch.build()
        self.assertEqual(rom[offset:offset + len(patch.NEW_TAIL)], patch.NEW_TAIL)
        self.assertEqual(rom[0x1199:0x119B], bytes.fromhex('CB BF'))


if __name__ == '__main__':
    unittest.main()
