"""#59 bounded scene-domain decoder and exact untouched DMA tail."""
import sys
from pathlib import Path
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts/diagnostics'))
from build_lowhealth_deferred_dma import OLD, NEW, build


def decode(code, raw, canonical):
    """Execute only LD A/CP/JR of the new nine-byte classifier prefix."""
    assert code[:5] == bytes.fromhex('FA80D8FE0B')
    a = raw
    pc = 5
    assert code[pc:pc+2] == bytes.fromhex('2002')
    pc += 4 if a != 11 else 2
    if pc == 7:
        assert code[pc:pc+2] == bytes.fromhex('F0B7')
        a=canonical
        pc+=2
    assert pc == 9 and code[pc:] == OLD[3:]
    return a


class DeferredDomain(unittest.TestCase):
    def test_exhaustive_scene_domain(self):
        for raw in range(256):
            for canonical in range(256):
                scene=decode(NEW,raw,canonical)
                self.assertEqual(scene,canonical if raw==11 else raw)
                eligible=((scene-3)&255)<6
                self.assertEqual(eligible,3 <= (canonical if raw==11 else raw) <= 8)

    def test_lcd_dma_and_latch_tail_unchanged(self):
        self.assertEqual(NEW[9:],OLD[3:])
        self.assertIn(bytes.fromhex('F040CB7FCA9E6C'),NEW)
        self.assertEqual(len(NEW)-len(OLD),6)

    def test_wrong_parent_rejected(self):
        with self.assertRaises(ValueError):build(bytes(1048576))


if __name__=='__main__':unittest.main()
