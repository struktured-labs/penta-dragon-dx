"""Execute the emitted packer bytes against the raw-H marker contract."""
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts/diagnostics'))
import build_later_stage_deferred_dma_r443 as builder


def execute(code, raw, scroll):
    memory = {0xFFC4: raw, 0xDC00: 0x72, 0xDC02: scroll}
    pc = a = b = 0
    zero = False
    for _ in range(100):
        op = code[pc]
        pc += 1
        if op in (0xF0, 0xE0):
            address = 0xFF00 + code[pc]
            pc += 1
            if op == 0xF0:
                a = memory[address]
            else:
                memory[address] = a
        elif op in (0xFA, 0xEA):
            address = int.from_bytes(code[pc:pc+2], 'little')
            pc += 2
            if op == 0xFA:
                a = memory[address]
            else:
                memory[address] = a
        elif op in (0xE6, 0xF6, 0x3E):
            value = code[pc]
            pc += 1
            if op == 0x3E:
                a = value
            else:
                a = a & value if op == 0xE6 else a | value
                zero = a == 0
        elif op in (0x28, 0x20, 0x18):
            displacement = int.from_bytes(code[pc:pc+1], 'little', signed=True)
            pc += 1
            if op == 0x18 or (op == 0x28 and zero) or (op == 0x20 and not zero):
                pc += displacement
        elif op == 0x07:
            a = ((a << 1) | (a >> 7)) & 255
            zero = False
        elif op == 0x47:
            b = a
        elif op in (0xB7, 0xB0):
            a |= a if op == 0xB7 else b
            zero = a == 0
        elif op == 0xCB:
            assert code[pc] == 0x5F
            pc += 1
            zero = not (a & 8)
        elif op == 0xC9 or (op == 0xC0 and not zero):
            return memory[0xFFC4]
        elif op != 0xC0:
            raise AssertionError(f'unsupported opcode {op:02X}')
    raise AssertionError('packer did not return')


class DmaMarkerTests(unittest.TestCase):
    def test_every_legal_raw_address_and_scroll(self):
        code = builder.packer()
        for raw in range(0x98, 0xA0):
            for scroll in range(16):
                page = 0x80 | ((raw & 4) << 2) | scroll
                self.assertEqual(execute(code, raw, scroll), page | builder.READY)
                self.assertEqual(execute(code, raw & 0xF7, scroll), page | builder.DMA_PENDING)

    def test_relative_request_never_requests_dma(self):
        for scroll in range(16):
            self.assertEqual(execute(builder.packer(), 0, scroll), builder.READY | scroll)

    def test_pending_and_ready_requests_are_not_overwritten(self):
        for raw in range(256):
            if raw & 0x60:
                self.assertEqual(execute(builder.packer(), raw, 7), raw)


if __name__ == '__main__':
    unittest.main()
