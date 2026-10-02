"""#26 chunk-yield code structure; emulator qualification remains separate."""
import importlib.util
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
with patch.object(sys, 'path', [str(ROOT / 'scripts/diagnostics'), *sys.path]):
    spec = importlib.util.spec_from_file_location('chunk_yield', ROOT / 'scripts/diagnostics/build_secret_chunk_yield_trial.py')
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)


class ChunkYieldTests(unittest.TestCase):
    def test_only_insert_safe_windows_between_complete_tile_groups(self):
        old, new = mod.code(6, True), mod.body()
        rebuilt = bytearray(new[:16])
        cursor = 16
        for row in range(24):
            for chunk in range(3):
                group = new[cursor:cursor + 80]
                self.assertEqual(group, bytes.fromhex('1a134fcbd477cb940a22') * 8)
                rebuilt.extend(group)
                cursor += 80
                if chunk < 2:
                    self.assertEqual(new[cursor:cursor + 11], mod.YIELD)
                    cursor += 11
            size = 49 + (11 if row < 23 else 0)
            rebuilt.extend(new[cursor:cursor + size])
            cursor += size
        rebuilt.extend(new[cursor:])
        self.assertEqual(bytes(rebuilt), old)
        self.assertEqual(len(new) - len(old), 48 * 11)
        self.assertEqual(mod.YIELD, bytes.fromhex('3e01e070fb00f33e06e070'))

    def test_exact_parent_patch_boundary_and_unknown_rejection(self):
        path = ROOT / 'tmp/secret-sound-alias-fast-trial-01/candidate.gb'
        if not path.exists():
            self.skipTest('local parent ROM unavailable')
        original = path.read_bytes()
        result = mod.build(original)
        allowed = set(range(mod.BASE, mod.BASE + len(mod.body()))) | {0x14e, 0x14f}
        self.assertEqual(len(result), len(original))
        self.assertTrue(all(a == b or i in allowed for i, (a, b) in enumerate(zip(original, result))))
        with self.assertRaises(ValueError):
            mod.build(original[:-1] + bytes([original[-1] ^ 1]))


if __name__ == '__main__':
    unittest.main()
