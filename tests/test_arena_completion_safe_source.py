"""#27 reproducible source construction, not a release-readiness gate."""
import hashlib
import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from build_stream_regression_candidate import arena_alias_chain, build

PIN = 'd901357a105036469b8debbff138fb63e87afb3a0cfbe5a24eeaafa91353910a'
OLD_PIN = '585f5830daa32e59c000f5ddd6b57aab545e55375b46574286702db9fc28e4db'


class CompletionSafeSource(unittest.TestCase):
    def test_explicit_dependencies_before_any_output(self):
        with self.assertRaisesRegex(ValueError, 'requires explicit arena alias'):
            build(ROOT / 'tmp/not-created-completion-test', arena_completion_safe=True)
        with self.assertRaisesRegex(ValueError, 'requires explicit presentation'):
            build(ROOT / 'tmp/not-created-completion-test', arena_alias=True,
                  arena_completion_safe=True)
        with self.assertRaises(ValueError):
            arena_alias_chain(bytes(0x100000), completion_safe=True)

    def test_old_and_new_chain_pins_remain_distinct(self):
        path = ROOT / 'tmp/stream-presentation-source-01/candidate.gb'
        if not path.exists():
            self.skipTest('local presentation fixture unavailable')
        for safe, pin, length in ((False, OLD_PIN, 3), (True, PIN, 4)):
            rom, records = arena_alias_chain(path.read_bytes(), completion_safe=safe)
            self.assertEqual(hashlib.sha256(rom).hexdigest(), pin)
            self.assertEqual(len(records), length)
            for before, after in zip(records, records[1:]):
                self.assertEqual(before['candidate_sha256'], after['parent_sha256'])

    def test_fresh_source_build_is_bound_and_not_promoted(self):
        base = ROOT / 'tmp/arena-completion-safe-source-02'
        if not (base / 'build-receipt.json').exists():
            self.skipTest('fresh source receipt unavailable')
        receipt = json.loads((base / 'build-receipt.json').read_text())
        self.assertEqual(receipt['candidate_sha256'], PIN)
        self.assertEqual(hashlib.sha256((base / 'candidate.gb').read_bytes()).hexdigest(), PIN)
        self.assertFalse(receipt['release_qualified'])
        self.assertFalse(receipt['retained_candidate_inputs'])
        for flag in ('presentation', 'arena_alias', 'arena_completion_safe'):
            self.assertTrue(receipt[f'experimental_{flag}_chain'])
        self.assertEqual(receipt['stages'][-1]['name'], 'arena-completion-safe')
        sources = receipt['loaded_project_python_sources']
        self.assertIn('scripts/diagnostics/build_arena_completion_safe_trial.py', sources)
        self.assertIn('scripts/diagnostics/build_arena_direct_scene_trial.py', sources)
        for path, digest in sources.items():
            self.assertEqual(hashlib.sha256((ROOT / path).read_bytes()).hexdigest(), digest, path)


if __name__ == '__main__':
    unittest.main()
