"""Execute emitted wait instructions with a delayed IRQ at the critical edge."""
import sys
from pathlib import Path
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts/diagnostics'))
import build_interrupt_checked_vblank_r373 as patch


def execute_wait(lcdc, ly_reads):
    reads = iter(ly_reads)
    code = patch.WAIT
    pc = 0
    a = 0
    z = c = False
    ime = True
    observed = []
    last_ly = None
    for _ in range(200):
        if pc == len(code):
            return ime, last_ly, observed
        op = code[pc]
        pc += 1
        if op == 0xF0:
            address = code[pc]
            pc += 1
            if address == 0x40:
                a = lcdc
            else:
                assert address == 0x44
                a = next(reads)
                last_ly = a
                observed.append((a, ime))
        elif op == 0xCB:
            assert code[pc] == 0x7F
            pc += 1
            z = not a & 128
        elif op == 0xFE:
            value = code[pc]
            pc += 1
            z, c = a == value, a < value
        elif op in (0x18,0x28,0x30,0x38):
            delta = code[pc]
            pc += 1
            if op == 0x18 or (op == 0x28 and z) or (op == 0x30 and not c) or (op == 0x38 and c):
                pc += delta if delta < 128 else delta - 256
        elif op == 0xF3:
            ime = False
        elif op == 0xFB:
            ime = True
        else:
            raise AssertionError(hex(op))
    raise AssertionError('wait did not finish')


class GuardTests(unittest.TestCase):
    def test_lcd_off_does_not_wait_on_frozen_ly(self):
        self.assertEqual(execute_wait(0, []), (False, None, []))

    def test_fresh_vblank_requires_protected_read(self):
        ime, ly, observed = execute_wait(0x83, [153, 143, 144, 144])
        self.assertFalse(ime)
        self.assertEqual(ly, 144)
        self.assertEqual(observed[-1], (144, False))

    def test_irq_delayed_edge_retries_for_every_other_scanline(self):
        for delayed_ly in range(154):
            if delayed_ly == 144:
                continue
            # Old code would enter DMA after the stale unprotected 144 sample.
            ime, ly, observed = execute_wait(0x83, [143,144,delayed_ly,143,144,144])
            self.assertFalse(ime)
            self.assertEqual(ly, 144)
            self.assertIn((delayed_ly, False), observed)
            self.assertEqual(observed[-3:], [(143,True),(144,True),(144,False)])

    def test_both_services_receive_same_guard(self):
        rom = patch.build(patch.BASE.read_bytes())
        for offset, old in ((patch.dma.SERVICE, patch.dma.SERVICE_CODE),
                            (patch.menu.offset(0x7F00), patch.menu.CODE)):
            new = old.replace(patch.OLD_WAIT, patch.WAIT)
            self.assertEqual(rom[offset:offset+len(new)], new)


if __name__ == '__main__':
    unittest.main()
