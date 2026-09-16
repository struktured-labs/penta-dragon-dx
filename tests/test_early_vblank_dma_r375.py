import sys
from pathlib import Path
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts/diagnostics'))
import build_early_vblank_dma_r375 as patch


def run(lcdc, reads):
    reads = iter(reads)
    pc, a, zero, ime = 0, 0, False, True
    seen = []
    code = patch.WAIT
    for _ in range(200):
        if pc == len(code): return ime, seen
        op = code[pc]; pc += 1
        if op == 0xF0:
            addr = code[pc]; pc += 1
            if addr == 0x40: a = lcdc
            else:
                assert addr == 0x44
                a = next(reads); seen.append((a, ime))
        elif op == 0xCB:
            assert code[pc] == 0x7F
            pc += 1; zero = not a & 128
        elif op == 0xE6:
            a &= code[pc]; pc += 1; zero = a == 0
        elif op == 0xFE:
            zero = a == code[pc]; pc += 1
        elif op in (0x18,0x20,0x28):
            delta = code[pc]; pc += 1
            if op == 0x18 or (op == 0x20 and not zero) or (op == 0x28 and zero):
                pc += delta if delta < 128 else delta-256
        elif op == 0xF3: ime = False
        elif op == 0xFB: ime = True
        else: raise AssertionError(hex(op))
    raise AssertionError('no completion')


class EarlyWindowTests(unittest.TestCase):
    def test_every_protected_scanline(self):
        for ly in range(154):
            if 144 <= ly <= 147:
                self.assertEqual(run(0x83,[ly,ly]),(False,[(ly,True),(ly,False)]))
            else:
                ime, seen = run(0x83,[144,ly,143,144,144])
                self.assertFalse(ime)
                self.assertEqual(seen[-3:],[(143,True),(144,True),(144,False)])
                self.assertIn((ly,False),seen)

    def test_lcd_off(self):
        self.assertEqual(run(0,[]),(False,[]))

    def test_only_dma_service_changes(self):
        source = patch.BASE.read_bytes(); rom = patch.build(source)
        old = patch.prior.dma.SERVICE_CODE.replace(patch.prior.OLD_WAIT,patch.prior.WAIT)
        allowed = set(range(patch.prior.dma.SERVICE,patch.prior.dma.SERVICE+len(old)))
        allowed.update((0x14D,0x14E,0x14F))
        self.assertTrue(all(a==b or i in allowed for i,(a,b) in enumerate(zip(source,rom))))


if __name__ == '__main__': unittest.main()
