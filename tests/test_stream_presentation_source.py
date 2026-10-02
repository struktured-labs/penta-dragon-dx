"""Construction checks, not gameplay qualification or deployment authority."""
import hashlib
import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'scripts'))
from build_stream_regression_candidate import presentation_chain

PIN = 'd744124d3d161247e0584bb39e8db1243ade4e428cbc15f82a85c10d0a4ac4d5'


class PresentationSource(unittest.TestCase):
    def test_rejects_unpinned_inputs(self):
        with self.assertRaisesRegex(ValueError, 'exact source07'):
            presentation_chain(bytes(0x100000), bytes(0x80000))

    def test_chain_matches_tested_candidate(self):
        source = ROOT/'tmp/stream-regressions-source-07/candidate.gb'
        reported = ROOT/'tmp/sara-atomic-pose-source-16/candidate.gb'
        if not source.exists() or not reported.exists():
            self.skipTest('local immutable chain fixtures unavailable')
        result, records = presentation_chain(source.read_bytes(), reported.read_bytes())
        self.assertEqual(hashlib.sha256(result).hexdigest(), PIN)
        self.assertEqual(len(records), 7)
        for previous, current in zip(records, records[1:]):
            self.assertEqual(previous['candidate_sha256'], current['parent_sha256'])

    def test_fresh_source_build_receipt(self):
        # Fresh receipt after adding secret-alias opt-in; preserve older receipts
        # as historical evidence rather than rewriting its bound tool hashes.
        base = ROOT/'tmp/stream-presentation-source-04'
        if not (base/'build-receipt.json').exists():
            self.skipTest('fresh source construction unavailable')
        receipt = json.loads((base/'build-receipt.json').read_text())
        self.assertFalse(receipt['release_qualified'])
        self.assertFalse(receipt['retained_candidate_inputs'])
        self.assertTrue(receipt['experimental_presentation_chain'])
        self.assertFalse(receipt['experimental_arena_alias_chain'])
        self.assertFalse(receipt['experimental_arena_completion_safe_chain'])
        self.assertEqual(receipt['candidate_sha256'], PIN)
        self.assertEqual(hashlib.sha256((base/'candidate.gb').read_bytes()).hexdigest(), PIN)
        sources = receipt['loaded_project_python_sources']
        for required in ('scripts/diagnostics/build_five_point_star_trial.py',
                         'scripts/diagnostics/build_title_local_guard_trial.py',
                         'scripts/diagnostics/build_later_hdma_overlap.py'):
            self.assertIn(required, sources)
        for name, digest in sources.items():
            self.assertEqual(hashlib.sha256((ROOT/name).read_bytes()).hexdigest(), digest, name)


if __name__ == '__main__':
    unittest.main()
