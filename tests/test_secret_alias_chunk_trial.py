"""#26 alias-only chunking: routing and independently generated state guards."""
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts/diagnostics'))
import build_secret_alias_chunk_trial as trial
from verify_pickup_class_palettes import serialized_state


def bank(code, stage, raw, canonical):
    pc, a, zero = 0, 0, False
    for _ in range(24):
        op = code[pc]
        if op == 0xf0:
            a = {0xba: stage, 0xb7: canonical}[code[pc + 1]]; pc += 2
        elif op == 0xfa:
            a = raw; pc += 3
        elif op == 0xfe:
            zero = a == code[pc + 1]; pc += 2
        elif op in (0x20, 0x28):
            delta = int.from_bytes(code[pc + 1:pc + 2], 'little', signed=True)
            pc += 2
            if zero == (op == 0x28): pc += delta
        elif op == 0x3e:
            return code[pc + 1]
        elif op == 0x11:
            return 28
        else:
            raise AssertionError(hex(op))
    raise AssertionError('unterminated gate')


class AliasChunkTests(unittest.TestCase):
    def test_exhaustive_alias_routing_and_unchanged_healthy_prefix(self):
        code = trial.gate()
        self.assertEqual(code[:43], trial.old_gate()[:43])
        for raw in range(256):
            for canonical in range(256):
                expected = 36 if raw in (9, 10) else 38 if raw == 11 and canonical in (9, 10) else 28
                self.assertEqual(bank(code, 7, raw, canonical), expected)
        for stage in range(256):
            if stage != 7:
                for raw in (9, 10, 11):
                    self.assertEqual(bank(code, stage, raw, 9), 28)

    def test_own_cold_machine_state_matches_except_rom_identity(self):
        paths = [ROOT / 'tmp' / name / 'frame-3600.ss0' for name in
                 ('secret-sound-alias-fast-own-entry-01', 'secret-alias-chunk-own-entry-01')]
        if not all(p.exists() for p in paths):
            self.skipTest('local independently generated states unavailable')
        a, b = map(serialized_state, paths)
        self.assertEqual(a[32:], b[32:])
        self.assertEqual(a[8:16], b[8:16])


if __name__ == '__main__':
    unittest.main()
