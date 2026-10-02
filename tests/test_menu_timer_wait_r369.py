import sys
from pathlib import Path
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts/diagnostics'))
import build_menu_timer_wait_r369 as patch


def execute(code, a, f, bc, ie, stack):
    pc = 0
    ime = False
    while pc < len(code):
        op = code[pc]
        pc += 1
        if op in (0xC5, 0xF5):
            stack.insert(0, bc if op == 0xC5 else a << 8 | f)
        elif op in (0xC1, 0xF1):
            value = stack.pop(0)
            if op == 0xC1:
                bc = value
            else:
                a, f = value >> 8, value & 0xF0
        elif op in (0xF0, 0xE0):
            assert code[pc] == 255
            pc += 1
            if op == 0xF0:
                a = ie
            else:
                ie = a
        elif op == 0xE6:
            a &= code[pc]
            pc += 1
            f = 0x20 | (0x80 if a == 0 else 0)
        elif op == 0xFB:
            ime = True
        elif op == 0xC9:
            assert stack.pop(0) == 0x6EE3
        else:
            raise AssertionError(hex(op))
    return a, f, bc, ie, ime, stack


class TimerWaitTests(unittest.TestCase):
    def test_only_timer_enabled_then_original_ie_bc_and_result_restored(self):
        for ie in range(256):
            for bc in (0, 0x1234, 65535):
                for result_f in range(0, 256, 16):
                    a,f,b,masked,ime,stack = execute(patch.PREFIX, 0, 0, bc, ie, [0x6EE3])
                    self.assertEqual(masked, ie & 4)
                    self.assertTrue(ime)
                    # Original DMA body balances BC/VBK and returns result AF;
                    # its new leading DI closes the IRQ window before setup.
                    a,f,b,restored,ime,stack = execute(patch.SUFFIX, 255, result_f, b, masked, stack)
                    self.assertEqual((a,f,b,restored,ime,stack), (255,result_f,bc,ie,False,[]))

    def test_wait_branches_land_before_protected_dma(self):
        self.assertEqual(patch.NEW[len(patch.PREFIX):len(patch.PREFIX)+patch.DMA_START],
                         patch.OLD[:patch.DMA_START])
        self.assertEqual(patch.NEW[len(patch.PREFIX)+patch.DMA_START], 0xF3)
        # LCD-off JR Z +12 targets the inserted DI, not the instruction after it.
        branch = patch.OLD.index(bytes.fromhex('28 0C'))
        self.assertEqual(branch + 2 + 12, patch.DMA_START)

    def test_only_menu_call_is_retargeted(self):
        source = patch.BASE.read_bytes()
        rom = patch.build(source)
        self.assertEqual(rom[patch.OFFSET(0x6E50):patch.OFFSET(0x6E50)+len(patch.OLD)], patch.OLD)
        self.assertEqual(rom[patch.OFFSET(0x6EE5):patch.OFFSET(0x6EFF)],
                         source[patch.OFFSET(0x6EE5):patch.OFFSET(0x6EFF)])


if __name__ == '__main__':
    unittest.main()
