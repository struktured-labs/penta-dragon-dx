"""Execute emitted guard bytes: only native Shalamar HP-zero bypasses cropping."""
from pathlib import Path
import sys
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts/diagnostics'))
import compose_shalamar_death_r458b as composer


def execute(scene, hp):
    code = composer.guard_code()
    pc, a, zero = 0, 0xAA, False
    reads = []
    for _ in range(20):
        op = code[pc]; pc += 1
        if op == 0x7B:
            a = scene
        elif op == 0xFE:
            zero = a == code[pc]; pc += 1
        elif op == 0x20:
            offset = int.from_bytes(code[pc:pc+1], 'little', signed=True); pc += 1
            if not zero: pc += offset
        elif op == 0xFA:
            address = int.from_bytes(code[pc:pc+2], 'little'); pc += 2
            reads.append(address)
            a = hp if address == 0xDCBB else 0x5B
        elif op == 0xB7:
            zero = a == 0
        elif op == 0x3E:
            a = code[pc]; pc += 1
        elif op == 0xC9:
            return 'death', a, reads
        elif op == 0xC3:
            assert code[pc:pc+2] == bytes.fromhex('0360')
            return 'native', a, reads
        else:
            raise AssertionError(f'Unexpected opcode {op:02X}')
    raise AssertionError('guard did not terminate')


class ShalamarDeathGuard(unittest.TestCase):
    def test_all_scene_and_hp_values(self):
        for scene in range(256):
            for hp in range(256):
                route, a, reads = execute(scene, hp)
                dying = scene == 0x0C and hp == 0
                self.assertEqual((route, a), ('death', 1) if dying else ('native', 0x5B))
                self.assertEqual(reads, ([0xDCBB] if scene == 0x0C else [])
                                 + ([] if dying else [0xC357]))

    def test_exact_composition_and_mutation_rejection(self):
        source = composer.BASE.read_bytes()
        result = composer.build(source)
        allowed = {0x14D, 0x14E, 0x14F}
        allowed.update(range(composer.off(20, 0x6000), composer.off(20, 0x6003)))
        start = composer.off(20, 0x6300)
        allowed.update(range(start, start + len(composer.guard_code())))
        self.assertLessEqual({i for i, (a, b) in enumerate(zip(source, result)) if a != b}, allowed)
        self.assertEqual(result, (composer.OUT / 'candidate.gb').read_bytes())
        changed = bytearray(source); changed[start] = 0
        with self.assertRaises(ValueError): composer.build(bytes(changed))
