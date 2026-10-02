"""#45 source construction contracts, separate from emulator acceptance."""
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'scripts'))
import build_stream_regression_candidate as builder


class LateReturnFadeSource(unittest.TestCase):
    def test_explicit_opt_in_before_any_writes(self):
        with patch.object(Path, 'mkdir', side_effect=AssertionError('unexpected write')):
            with self.assertRaisesRegex(ValueError, 'requires explicit return fade'):
                builder.build(ROOT/'tmp/not-created', experimental_late_return_fade=True)

    def test_unknown_parent_rejected(self):
        with self.assertRaisesRegex(ValueError, 'exact'):
            builder.late_return_fade_chain(bytes(0x100000))

    def test_exact_chain_and_default_parent_unchanged(self):
        parent = (ROOT/'tmp/return-cgb-fade-trial-16/candidate.gb').read_bytes()
        result, records = builder.late_return_fade_chain(parent)
        self.assertEqual(builder.digest(parent),
                         '126dd0b7fff1e03eb6b224f818b85398593c7109ffb676cc538c1bd90742304b')
        self.assertEqual(result, (ROOT/'tmp/final-fade-late-window-trial-01/candidate.gb').read_bytes())
        self.assertEqual(len(records), 3)
        for a, b in zip(records, records[1:]):
            self.assertEqual(a['candidate_sha256'], b['parent_sha256'])
        for r in records:
            self.assertEqual(builder.digest(Path(r['builder']).read_bytes()), r['builder_sha256'])

    def test_fresh_original_source_receipt_remains_unqualified(self):
        folder = ROOT/'tmp/stream-late-return-source-01'
        r = json.loads((folder/'build-receipt.json').read_text())
        self.assertEqual(builder.digest((folder/'candidate.gb').read_bytes()), r['candidate_sha256'])
        self.assertEqual(r['candidate_sha256'],
                         '46eb95a0c0f770fb3cf8c3211b8030a9e881f59077e558b93703ba08da71d3fb')
        self.assertFalse(r['retained_candidate_inputs'])
        self.assertFalse(r['release_qualified'])
        self.assertFalse(r['allocation_review_complete'])
        self.assertTrue(r['experimental_late_return_fade_chain'])
        self.assertIn('414', r['qualification_warning'])
        self.assertEqual(builder.digest((ROOT/'rom/Penta Dragon (J).gb').read_bytes()), r['original_sha256'])
        for name, digest in r['loaded_project_python_sources'].items():
            self.assertEqual(builder.digest((ROOT/name).read_bytes()), digest, name)


if __name__ == '__main__':
    unittest.main()
