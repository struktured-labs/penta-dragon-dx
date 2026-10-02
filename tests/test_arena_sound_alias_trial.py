"""Issue #27 bytecode policy checks; not emulator/visual qualification."""
import hashlib
from pathlib import Path
import sys
import unittest
import zlib

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'scripts/diagnostics'))
import build_arena_sound_alias_trial as trial
from verify_pickup_class_palettes import serialized_state


def resolve_emitted(raw_scene, canonical_scene):
    """Execute the emitted resolver prefix up to its cache comparison.

Only this short instruction subset is modeled; mapper/IRQ/cycle behavior
requires the independent guarded mGBA replay.
"""
    code = trial.payload()
    pc = 0
    a = 0
    zero = carry = False
    for _ in range(20):
        op = code[pc]
        pc += 1
        if op == 0xFA:
            assert code[pc:pc+2] == bytes.fromhex('80D8')
            pc += 2
            a = raw_scene
        elif op == 0xF0:
            assert code[pc] == 0xB7
            pc += 1
            a = canonical_scene
        elif op in (0xFE, 0xD6, 0xC6, 0x3E):
            value = code[pc]
            pc += 1
            if op == 0x3E:
                a = value
                continue
            total = a + value if op == 0xC6 else a - value
            zero = (total & 255) == 0
            carry = total < 0 or total > 255
            if op != 0xFE:
                a = total & 255
        elif op in (0x18, 0x20, 0x38):
            displacement = code[pc]
            pc += 1
            if op == 0x18 or (op == 0x20 and not zero) or (op == 0x38 and carry):
                pc += displacement if displacement < 128 else displacement-256
        elif op == 0x21:
            assert code[pc:] == bytes.fromhex('0DDF BE F5 3E0D C3926F')
            return a
        else:
            raise AssertionError(f'unmodeled opcode {op:02x}')
    raise AssertionError('resolver did not terminate')


class ArenaSoundAlias(unittest.TestCase):
    def test_retained_trial_preserves_table_across_sound_alias(self):
        folder = ROOT/'tmp/arena-sound-alias-shalamar-phase721-01'
        rom_path = ROOT/'tmp/arena-sound-alias-trial-01/candidate.gb'
        if not (folder/'frame-1080.ss0').exists():
            self.skipTest('local experimental replay unavailable')
        rom = rom_path.read_bytes()
        self.assertEqual(hashlib.sha256(rom).hexdigest(),
                         '4eff32d4aa5519486371835690730bba26d2c282f3b3481199e34125d88588db')
        observed = 0
        for frame in range(1, 1081):
            raw = serialized_state(folder/f'frame-{frame:04d}.ss0')
            self.assertEqual(int.from_bytes(raw[4:8], 'little'), zlib.crc32(rom)&0xffffffff)
            if raw[0x5c80] == 11 and raw[0x3b7] == 12:
                observed += 1
                self.assertEqual(raw[0x630d], 12)
                self.assertEqual(raw[0x4a00:0x4b00], bytes([0,0]+[4]*253+[0]))
        self.assertEqual(observed, 156)
        # This table invariant does not erase the failed full replay verdict.
        import json
        verdict = json.loads((folder/'verification.json').read_text())
        self.assertTrue(verdict['failures'])

    def test_all_raw_and_canonical_scene_values(self):
        for raw in range(256):
            for canonical in range(256):
                expected = canonical if raw == 11 and 12 <= canonical <= 20 else raw
                self.assertEqual(resolve_emitted(raw, canonical), expected, (raw, canonical))

    def test_exact_parent_and_patch_boundary(self):
        path = ROOT/'tmp/stream-presentation-source-01/candidate.gb'
        if not path.exists():
            self.skipTest('local exact parent unavailable')
        parent = path.read_bytes()
        self.assertEqual(hashlib.sha256(parent).hexdigest(), trial.PARENT)
        result = trial.build(parent)
        permitted = set(range(0x14E, 0x150))
        for bank, addr, length in ((13, 0x6F90, 8), (20, 0x6F92, 6),
                                   (20, trial.ENTRY, len(trial.payload()))):
            pos = trial.offset(bank, addr)
            permitted.update(range(pos, pos+length))
        self.assertEqual(len(result), len(parent))
        self.assertTrue(all(i in permitted for i, (a, b) in enumerate(zip(parent, result)) if a != b))
        self.assertEqual(result[0x36F90:0x36F98], bytes.fromhex('3E14 CDBE09 F1 C8 00'))
        with self.assertRaises(ValueError):
            trial.build(parent[:0x200]+bytes([parent[0x200]^1])+parent[0x201:])


if __name__ == '__main__':
    unittest.main()
