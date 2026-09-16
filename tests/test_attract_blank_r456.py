"""Execute the emitted blanking service and prove its bounded write/ABI contract."""
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'scripts'), str(ROOT / 'scripts/diagnostics')]
import compose_attract_blank_r456 as build
import compose_attract_blank_r456c as bounded
import compose_attract_blank_r456d as scoped
from verify_stage1_spike_palettes import publication_boundary


def execute(scene, stage, lcdc=0x83, composer=build, caller=0x01AA):
    code = composer.service()
    ime = True
    pc, a, flags = 0, 18, 0
    regs = {0xC5: 0x1234, 0xE5: 0x5678}
    stack, writes = [], []
    memory = {0xD880: scene, 0xFFBA: stage, 0xFF40: lcdc, 0xFF44: 144, 0xFF68: 0xBC}
    memory.update({0xDFFB: caller & 255, 0xDFFC: caller >> 8})
    for _ in range(100):
        op = code[pc]; pc += 1
        if op in (0xF3, 0xFB):
            ime = op == 0xFB
        elif op == 0xCD:
            assert code[pc:pc+2] == bytes.fromhex('0E0A')
            pc += 2; a, flags = 0, 0x80
            writes.extend((address, 0) for address in (0xFF47, 0xFF48, 0xFF49))
        elif op in (0xC5, 0xE5, 0xF5):
            stack.append((a << 8 | flags) if op == 0xF5 else regs[op])
        elif op in (0xC1, 0xE1, 0xF1):
            value = stack.pop()
            if op == 0xF1: a, flags = value >> 8, value & 255
            else: regs[op+4] = value
        elif op == 0xF8:
            regs[0xE5] = 0xDFF7 - 2*len(stack) + code[pc]
            pc += 1
            flags = 0
        elif op in (0x2A, 0x7E):
            a = memory[regs[0xE5]]
            if op == 0x2A: regs[0xE5] += 1
        elif op == 0xFA:
            address = int.from_bytes(code[pc:pc+2], 'little'); pc += 2
            a = memory[address]
        elif op == 0xF0:
            a = memory[0xFF00 + code[pc]]; pc += 1
        elif op in (0xFE, 0xD6):
            value = code[pc]; pc += 1
            flags = 0x40 | (0x80 if a == value else 0) | (0x10 if a < value else 0)
            if op == 0xD6: a = (a - value) & 255
        elif op == 0xB7:
            flags = 0x80 if a == 0 else 0
        elif op == 0xAF:
            a, flags = 0, 0x80
        elif op == 0xCB:
            assert code[pc] == 0x7F; pc += 1
            flags = (flags & 0x10) | 0x20 | (0 if a & 128 else 0x80)
        elif op in (0x20, 0x28, 0x30):
            delta = int.from_bytes(code[pc:pc+1], 'little', signed=True); pc += 1
            take = {0x20: not flags & 0x80, 0x28: bool(flags & 0x80), 0x30: not flags & 0x10}[op]
            if take: pc += delta
        elif op == 0x3E:
            a = code[pc]; pc += 1
        elif op in (0xE0, 0xEA):
            width = 1 if op == 0xE0 else 2
            address = int.from_bytes(code[pc:pc+width], 'little') + (0xFF00 if width == 1 else 0)
            pc += width; memory[address] = a; writes.append((address, a))
            if composer in (bounded, scoped) and address == 0xFF69:
                assert not ime, 'palette transaction must not be interrupted'
        elif op == 0xC9:
            assert not stack and regs == {0xC5: 0x1234, 0xE5: 0x5678}
            assert a == 1 and flags == 0x80
            assert ime, 'native caller resumes with interrupts enabled'
            return writes, memory
        else:
            raise AssertionError(f'unmodeled opcode {op:02X}')
    raise AssertionError('service did not return')


class AttractBlank(unittest.TestCase):
    def test_native_caller_scope(self):
        for caller in (0x01AA, 0x0165, 0x1AC1, 0x7445, 0x40A3, 0x40AC, 0x4126, 0x00AA, 0x01AB):
            for scene in range(256):
                for stage in (0, 1, 6, 255):
                    writes, memory = execute(scene, stage, composer=scoped, caller=caller)
                    self.assertEqual([v for a,v in writes if a == 0xFF69],
                                     [255,127]*4 if (caller,scene,stage) == (0x01AA,2,0) else [])
                    self.assertEqual(memory[0xFF68],0xBC)

    def test_bounded_transaction_scope_and_abi(self):
        for scene in range(256):
            for stage in (0, 1, 6, 255):
                writes, memory = execute(scene, stage, composer=bounded)
                self.assertEqual([v for a,v in writes if a == 0xFF69],
                                 [255,127]*4 if scene == 2 and stage == 0 else [])
                self.assertEqual(memory[0xFF68], 0xBC)
                self.assertTrue(all(a in (0xFF47,0xFF48,0xFF49,0xFF68,0xFF69,0xDD09,0xFFF4)
                                    for a,_ in writes))
        self.assertEqual([v for a,v in execute(2,0,0,composer=bounded)[0] if a==0xFF69], [255,127]*4)

    def test_bounded_composition_exact_scope(self):
        if not bounded.BASE.exists(): self.skipTest('local base unavailable')
        source = bounded.BASE.read_bytes(); rom = bounded.build(source)
        changed = {i for i,(a,b) in enumerate(zip(source,rom)) if a != b}
        allowed = set(range(0x416C,0x4176)) | {0x14D,0x14E,0x14F}
        allowed |= set(range(18*0x4000+0x2C80,18*0x4000+0x2C80+len(bounded.service())))
        self.assertLessEqual(changed, allowed)
        self.assertEqual(publication_boundary(rom)['variant'], 'r456c-attract-white-8234bd84')
        mutated = bytearray(rom); mutated[0x416C] ^= 1
        with self.assertRaises(RuntimeError): publication_boundary(mutated)

    def test_scene_and_stage_scope_and_register_preservation(self):
        for scene in range(256):
            for stage in (0, 1, 6, 255):
                writes, memory = execute(scene, stage)
                cram = [value for address, value in writes if address == 0xFF69]
                self.assertEqual(cram, [255, 127]*4 if scene == 2 and stage == 0 else [])
                self.assertEqual(memory[0xFF68], 0xBC)
                self.assertEqual(memory[0xDD09], 1)
                self.assertEqual(memory[0xFFF4], 1)
                self.assertTrue(all(address in (0xFF47,0xFF48,0xFF49,0xFF68,0xFF69,0xDD09,0xFFF4)
                                    for address, _ in writes))
        self.assertEqual([v for a,v in execute(2,0,0)[0] if a==0xFF69], [255,127]*4)

    def test_exact_composition_preserves_publication_and_gameplay(self):
        if not build.BASE.exists(): self.skipTest('local base unavailable')
        source = build.BASE.read_bytes(); rom = build.build(source)
        changed = {i for i,(a,b) in enumerate(zip(source,rom)) if a != b}
        allowed = set(range(0x416C,0x4176)) | {0x14D,0x14E,0x14F}
        allowed |= set(range(18*0x4000+0x2C80,18*0x4000+0x2C80+len(build.service())))
        self.assertLessEqual(changed, allowed)
        self.assertEqual(publication_boundary(rom)['variant'], 'r456a-attract-white-44dbde77')
        mutated = bytearray(rom); mutated[0x416C] ^= 1
        with self.assertRaises(RuntimeError): publication_boundary(mutated)


if __name__ == '__main__': unittest.main()
