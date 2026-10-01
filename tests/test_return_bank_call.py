"""#45 isolated instruction/stack model, not emulator or timing acceptance."""
import hashlib
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts/diagnostics'))
import return_bank_call as code


class Machine:
    """Only the emitted primitive's opcodes; reject everything else."""
    def __init__(self):
        self.mem = bytearray(65536)
        self.af, self.hl, self.sp, self.bank = 0xABC0, 0x9876, 0xDFE0, 20
        self.mem[0x61:0x67] = bytes.fromhex('EA09DC C3BE09')
        self.mem[0x9BE:0x9C4] = bytes.fromhex('E099 EA0021 C9')
        self.mem[0x99D:0x9A2] = code.EPILOGUE
        self.mem[code.CALLBACK:code.CALLBACK+6] = code.callback()

    def push(self, value):
        self.sp -= 2
        self.mem[self.sp:self.sp+2] = value.to_bytes(2, 'little')

    def pop(self):
        value = int.from_bytes(self.mem[self.sp:self.sp+2], 'little')
        self.sp += 2
        return value

    def run(self, pc, stop):
        for _ in range(100):
            if pc == stop:
                return
            op = self.mem[pc]; pc += 1
            if op == 0xF5: self.push(self.af)
            elif op == 0xE5: self.push(self.hl)
            elif op == 0xF1: self.af = self.pop() & 0xFFF0
            elif op == 0xE1: self.hl = self.pop()
            elif op == 0xF8:
                self.hl = self.sp + self.mem[pc]; pc += 1
                self.af &= 0xFF00  # emitted positive offset has no H/C carry here
            elif op == 0x36:
                self.mem[self.hl] = self.mem[pc]; pc += 1
            elif op == 0x23: self.hl = (self.hl + 1) & 65535
            elif op == 0x3E:
                self.af = (self.mem[pc] << 8) | (self.af & 255); pc += 1
            elif op in (0xCD, 0xC3):
                target = int.from_bytes(self.mem[pc:pc+2], 'little'); pc += 2
                if op == 0xCD: self.push(pc)
                pc = target
            elif op == 0xC9: pc = self.pop()
            elif op == 0xE0:
                self.mem[0xFF00+self.mem[pc]] = self.af >> 8; pc += 1
            elif op == 0xEA:
                target = int.from_bytes(self.mem[pc:pc+2], 'little'); pc += 2
                self.mem[target] = self.af >> 8
                if target == 0x2100: self.bank = self.af >> 8
            else: raise AssertionError(f'unsupported opcode {op:02x}')
        raise AssertionError('primitive did not terminate')


class ReturnBankCall(unittest.TestCase):
    def test_chain_preserves_intermediate_registers_and_bank(self):
        for flags in range(0, 256, 16):
            m = Machine(); m.af = 0xAB00 | flags
            original_sp = m.sp
            m.push(0x6D00)
            body = code.native_chain((0x0F47, 0x4068))
            m.mem[0x6C80:0x6C80+len(body)] = body
            m.run(0x6C80, 0x0F47)
            self.assertEqual((m.af, m.hl, m.bank), (0xAB00 | flags, 0x9876, 1))
            self.assertEqual(m.sp, original_sp - 6)
            m.mem[0x0F47] = 0xC9
            m.af, m.hl = 0x42B0, 0x1234
            m.run(0x0F47, 0x4068)
            self.assertEqual((m.af, m.hl, m.bank), (0x42B0, 0x1234, 1))
            self.assertEqual(m.sp, original_sp - 4)
            m.mem[0x4068] = 0xC9
            m.run(0x4068, 0x6D00)
            self.assertEqual((m.af, m.hl, m.bank, m.sp),
                             (0x42B0, 0x1234, 20, original_sp))
        self.assertEqual(code.native_chain((0x169C,)), code.native_call(0x169C))
        for targets in ((), (-1,), (0x8000,), tuple(range(9))):
            with self.assertRaises(ValueError): code.native_chain(targets)

    def test_native_inputs_outputs_and_stack(self):
        for bank in (1, 13):
            for flags in range(0, 256, 16):
                m = Machine(); m.af = 0xAB00 | flags
                original = (m.af, m.hl, m.sp)
                m.push(0x6D00)  # bank20 caller CALL to the generated thunk
                body = code.native_call(0x169C, bank)
                m.mem[0x6C80:0x6C80+len(body)] = body
                m.run(0x6C80, 0x169C)
                self.assertEqual((m.af, m.hl, m.bank), (*original[:2], bank))
                self.assertEqual(m.sp, original[2]-4)  # callback + continuation
                m.af, m.hl = 0x42B0, 0x1234  # native outputs must survive callback
                m.mem[0x169C] = 0xC9
                m.run(0x169C, 0x6D00)
                self.assertEqual((m.af, m.hl, m.sp, m.bank),
                                 (0x42B0, 0x1234, original[2], 20))
                self.assertEqual(m.mem[0xFF99], 20)
                self.assertEqual(m.mem[0xDC09], 20)

    def test_candidate_preimages_and_reject_changed_abi(self):
        path = ROOT / 'tmp/initial-map-fastpath-trial-01/candidate.gb'
        if not path.exists(): self.skipTest('local candidate unavailable')
        rom = bytearray(path.read_bytes())
        self.assertEqual(hashlib.sha256(rom).hexdigest(),
                         'ec8be28897810fac01a8918a0403900780015bf6703531f0f82ae259f209f21b')
        code.check_fixed_abi(rom)
        for address in (0xC1, 0x99D, 0x61, 0x9BE):
            bad = rom.copy(); bad[address] ^= 1
            with self.assertRaises(ValueError): code.check_fixed_abi(bad)

    def test_size_and_invalid_targets(self):
        self.assertEqual(len(code.callback()), 6)
        for address, bank in ((0x8000, 1), (-1, 1), (0x169C, 0)):
            with self.assertRaises(ValueError): code.native_call(address, bank)


if __name__ == '__main__': unittest.main()
