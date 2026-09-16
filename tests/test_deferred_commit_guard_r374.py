"""Execute the installed guard bytes for every scanline and pending state."""
import sys
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts/diagnostics'))
import build_deferred_commit_guard_r374 as guard


def execute(ly, pending):
    code = guard.GUARD
    pc, a, zero = 0, 0, False
    reads = []
    for _ in range(8):
        op = code[pc]
        pc += 1
        if op == 0xF0:
            assert code[pc] == 0x44
            pc += 1
            a = ly
        elif op == 0xE6:
            a &= code[pc]
            pc += 1
            zero = a == 0
        elif op == 0xFE:
            zero = a == code[pc]
            pc += 1
        elif op in (0xC2, 0xC3):
            target = int.from_bytes(code[pc:pc+2], 'little')
            pc += 2
            if op == 0xC3 or not zero:
                return target, a, zero, reads
        elif op == 0xFA:
            address = int.from_bytes(code[pc:pc+2], 'little')
            pc += 2
            assert address == 0xDF5C
            reads.append(address)
            a = pending
        elif op == 0xB7:
            zero = a == 0
        else:
            raise AssertionError(f'unexpected opcode {op:02X}')
    raise AssertionError('guard did not terminate')


class GuardTests(unittest.TestCase):
    def test_all_scanlines_and_pending_values(self):
        for ly in range(154):
            for pending in (0, 1, 255):
                target, a, zero, reads = execute(ly, pending)
                if 144 <= ly <= 147:
                    self.assertEqual((target,a,zero,reads),
                                     (0x7400,pending,pending == 0,[0xDF5C]))
                else:
                    self.assertEqual((target,reads), (0x6F1D,[]))

    def test_build_changes_only_owned_regions_and_checksums(self):
        source = guard.BASE.read_bytes()
        rom = guard.build(source)
        allowed = set(range(guard.ENTRY,guard.ENTRY+4))
        allowed.update(range(guard.CAVE,guard.CAVE+len(guard.GUARD)))
        allowed.update((0x14D,0x14E,0x14F))
        self.assertTrue(all(a == b or i in allowed
                            for i,(a,b) in enumerate(zip(source,rom))))
        self.assertEqual(rom[guard.CAVE:guard.CAVE+len(guard.GUARD)],guard.GUARD)

    def test_publisher_detection_requires_exact_guard(self):
        from verify_stage1_spike_palettes import publication_boundary
        rom = bytearray(guard.build(guard.BASE.read_bytes()))
        self.assertIn('guard-r374', publication_boundary(rom)['variant'])
        rom[guard.CAVE+3] = 0xF8
        with self.assertRaises(RuntimeError):
            publication_boundary(rom)

    def test_handoff_inspection_binds_guard_and_commit(self):
        from stage_card_palette_handoff import inspect_stage_card_palette_handoff
        rom = bytearray(guard.build(guard.BASE.read_bytes()))
        receipt = inspect_stage_card_palette_handoff(rom)
        self.assertTrue(receipt['installed'])
        self.assertTrue(receipt['vblank_guarded_installed'])
        self.assertEqual(receipt['variant'],
                         'vblank-atomic-window-fast-final-guard-r374')
        rom[guard.CAVE+3] = 0xF8
        self.assertFalse(inspect_stage_card_palette_handoff(rom)['installed'])


if __name__ == '__main__':
    unittest.main()
