import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import build_v302_title_fix as b


class SceneBG5Tests(unittest.TestCase):
    def test_opt_in_fits_existing_allocations(self):
        base = b.build_phased_palette_loader()
        row = bytes.fromhex('ff7fff031f000000')
        trial = b.build_phased_palette_loader(stage1_bg5=row)
        self.assertEqual(len(trial[1]), 96)
        self.assertLessEqual(len(trial[0]), b.SHADOW_MAIN_ADDR-b.PALETTE_LOADER_ADDR)
        self.assertEqual(trial[0][:len(base[0])], base[0])
        self.assertEqual(trial[0][-8:], row)
        self.assertEqual(trial[2:], base[2:])

    def test_defaults_remain_disabled(self):
        self.assertIsNone(b.load_stage1_bg5_experiment(b.PALETTE_YAML))

    def test_invalid_row_rejected(self):
        with self.assertRaises(ValueError):
            b.build_phased_palette_loader(stage1_bg5=bytes(7))

    def test_selector_only_changes_stage1_bg5(self):
        # Execute the actual small selector; verify every scene/slot pair.
        original = b.build_phased_palette_loader()[0]
        code = b.build_phased_palette_loader(stage1_bg5=bytes(8))[0]
        start = len(original)
        for scene in range(256):
            for slot in range(7):
                pc, a, hl, zero = start, 0, 0x6800+slot*8, False
                while True:
                    op = code[pc]; pc += 1
                    if op == 0x7B: a = slot
                    elif op == 0xFE: zero = a == code[pc]; pc += 1
                    elif op == 0x20:
                        delta = code[pc]; pc += 1
                        if not zero: pc += delta if delta < 128 else delta-256
                    elif op == 0xFA: a = scene; pc += 2
                    elif op == 0xE6: a &= code[pc]; pc += 1
                    elif op == 0x21: hl = int.from_bytes(code[pc:pc+2], 'little'); pc += 2
                    elif op == 0xC3: break
                    else: self.fail(hex(op))
                selected = slot == 5 and scene in (2,10)
                self.assertEqual(hl != 0x6800+slot*8, selected, (scene,slot))


if __name__ == '__main__': unittest.main()
