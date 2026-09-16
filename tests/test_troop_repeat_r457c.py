from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts/diagnostics'))
"""Execute emitted delay bytes and verify exact experimental reconstruction."""
import hashlib
import unittest
import compose_troop_repeat_r457c as c


def execute(scene, lcdc, phases=(0, 3, 3, 0)):
    code = c.wait_code()
    pc, a, b, flags = 0, 0x57, 0xA6, 0
    stack, reads, edges = [], 0, 0
    for _ in range(100000):
        op = code[pc]; pc += 1
        if op == 0xFA:
            assert code[pc:pc+2] == bytes.fromhex('80D8')
            pc += 2; a = scene
        elif op == 0xFE:
            flags = 0x80 if a == code[pc] else 0; pc += 1
        elif op in (0x20, 0x28):
            delta = int.from_bytes(code[pc:pc+1], 'little', signed=True); pc += 1
            taken = bool(flags & 0x80) == (op == 0x28)
            if taken: pc += delta
        elif op == 0xF0:
            reg = code[pc]; pc += 1
            assert reg in (0x40, 0x41)
            if reg == 0x40: a = lcdc
            else:
                a = phases[reads % len(phases)]; reads += 1
        elif op == 0xCB:
            assert code[pc] == 0x7F; pc += 1
            flags = 0 if a & 0x80 else 0x80
        elif op == 0xC5: stack.append(b)
        elif op == 0xC1: b = stack.pop()
        elif op == 0x06: b = code[pc]; pc += 1
        elif op == 0xE6:
            a &= code[pc]; pc += 1; flags = 0x80 if not a else 0
        elif op == 0x05:
            b = (b - 1) & 255; edges += 1; flags = 0x80 if not b else 0
        elif op == 0xAF: a, flags = 0, 0x80
        elif op == 0xC9: return a, flags, b, stack, reads, edges
        else: raise AssertionError(f'unhandled opcode {op:02X} at {pc-1}')
    raise TimeoutError('STAT did not supply the required edges')


class TroopRepeat(unittest.TestCase):
    def test_scene_and_lcdc_scope(self):
        for scene in range(256):
            for lcdc in range(256):
                a, f, b, stack, reads, edges = execute(scene, lcdc)
                self.assertEqual((a, f, b, stack), (0, 0x80, 0xA6, []))
                expected = 120 if scene == 0x11 and lcdc & 0x80 else 0
                self.assertEqual(edges, expected)
                self.assertEqual(reads, expected * 4)

    def test_stat_phase_delays_do_not_change_window_count(self):
        for phases in ((3, 0), (2, 2, 3, 3, 3, 0), (1, 1, 2, 3, 0, 0)):
            self.assertEqual(execute(0x11, 0x83, phases)[-1], 120)
        with self.assertRaises(TimeoutError): execute(0x11, 0x83, (0, 1, 2))

    def test_exact_composition_and_mutation(self):
        source = (c.ROOT / 'tmp/attract-blank-r456d/candidate.gb').read_bytes()
        result = c.build(source)
        self.assertEqual(hashlib.sha256(result).hexdigest(),
                         '3e2421bcd94b747c810b42246c6da1d2019cad1e068eb0326012222dbe106306')
        self.assertEqual(result, (c.ROOT / 'tmp/troop-exact-repeat-delay-r457c/candidate.gb').read_bytes())
        allowed = {0x14D, 0x14E, 0x14F}
        for address, before, _ in c.patches():
            allowed.update(range(c.off(20, address), c.off(20, address)+len(before)))
        self.assertLessEqual({i for i, (a,b) in enumerate(zip(source,result)) if a!=b}, allowed)
        for address, _, _ in c.patches():
            mutated = bytearray(source); mutated[c.off(20,address)] ^= 1
            with self.assertRaises(ValueError): c.build(bytes(mutated))


if __name__ == '__main__': unittest.main()
