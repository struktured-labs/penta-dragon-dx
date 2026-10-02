"""#23 experimental copier bindings; these are not gameplay acceptance tests."""
import hashlib
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts/diagnostics'))
import build_secret_combined_copy_trial as trial


class CombinedCopyTrialTests(unittest.TestCase):
    def test_ceiling_composition_preserves_existing_repairs(self):
        import build_sara_doorway_priority as ceiling
        path = ROOT / 'tmp/stream-regressions-source-07/candidate.gb'
        if not path.exists():
            self.skipTest('local exact parent ROM unavailable')
        parent = ceiling.build(path.read_bytes(), combined=True)
        self.assertEqual(hashlib.sha256(parent).hexdigest(), trial.CEILING_SOURCE07)
        result = trial.build(parent, 6, True)
        allowed = {0x14e, 0x14f, *range(trial.HOOK, trial.HOOK+5),
                   *range(28*0x4000, 28*0x4000+len(trial.gate())),
                   *range(trial.BASE, trial.BASE+0x4000)}
        self.assertTrue(all(a == b or i in allowed
                            for i, (a, b) in enumerate(zip(parent, result))))
        self.assertEqual(result[32*0x4000:36*0x4000], parent[32*0x4000:36*0x4000])

    def test_row_yields_restore_stack_bank_before_interrupts(self):
        old, new = trial.code(6), trial.code(6, True)
        sequence = bytes.fromhex('3e01e070fb00f33e06e070')
        self.assertEqual(new.count(sequence), 23)
        self.assertEqual(len(new) - len(old), 23 * len(sequence))
        self.assertLess(0x4000 + len(new), 0x6c80)

    def test_body_does_not_overlap_entry_or_table(self):
        for bank in (3, 6):
            self.assertLess(0x4000 + len(trial.code(bank)), 0x6c80)

    def test_invalid_inputs_rejected(self):
        with self.assertRaisesRegex(ValueError, 'exact source07'):
            trial.build(bytes(0x100000))
        with self.assertRaisesRegex(ValueError, 'unsupported diagnostic scratch bank'):
            trial.build(b'', 1)

    def test_bank_change_only_changes_three_scratch_selectors(self):
        old, new = trial.code(3), trial.code(6)
        differences = [i for i, pair in enumerate(zip(old, new)) if pair[0] != pair[1]]
        self.assertEqual(len(old), len(new))
        self.assertEqual(len(differences), 3)
        for i in differences:
            self.assertEqual(old[i-1:i+3], bytes.fromhex('3e03e070'))
            self.assertEqual(new[i-1:i+3], bytes.fromhex('3e06e070'))

    def test_exact_experimental_roms_and_checksum(self):
        path = ROOT / 'tmp/stream-regressions-source-07/candidate.gb'
        if not path.exists():
            self.skipTest('local exact parent ROM unavailable')
        parent = path.read_bytes()
        for bank, expected in (
            (3, '91f45fd07be958c6e95e87664c07d71010a3e60a9d2550aa224fc94ff40cd607'),
            (6, '7c149ac86c0163dc1c60b607e852e3b145c07965a78515f7c7019a621ec93c79'),
        ):
            rom = trial.build(parent, bank)
            self.assertEqual(hashlib.sha256(rom).hexdigest(), expected)
            self.assertEqual(len(rom), len(parent))
            self.assertEqual(int.from_bytes(rom[0x14e:0x150], 'big'),
                             (sum(rom[:0x14e]) + sum(rom[0x150:])) & 65535)


if __name__ == '__main__':
    unittest.main()
