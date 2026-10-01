"""#45 exact construction, not emulator acceptance."""
from pathlib import Path
import sys
import unittest
from unittest.mock import patch
import json

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
import build_stream_regression_candidate as builder


class ReturnFadeSource(unittest.TestCase):
    def test_fresh_original_cartridge_source_build(self):
        p=ROOT/'tmp/return-fade16-source-01'
        if not (p/'build-receipt.json').exists():
            self.skipTest('fresh original-cartridge build unavailable')
        r=json.loads((p/'build-receipt.json').read_text())
        self.assertFalse(r['retained_candidate_inputs'])
        self.assertFalse(r['release_qualified'])
        self.assertTrue(r['experimental_return_fade_chain'])
        self.assertEqual(builder.digest((p/'candidate.gb').read_bytes()),r['candidate_sha256'])
        self.assertEqual(r['candidate_sha256'],
                         '126dd0b7fff1e03eb6b224f818b85398593c7109ffb676cc538c1bd90742304b')
        self.assertEqual(builder.digest((ROOT/'rom/Penta Dragon (J).gb').read_bytes()),r['original_sha256'])
        self.assertEqual(builder.digest((p/'restart-source/build-receipt.json').read_bytes()),
                         r['restart_receipt_sha256'])
        for name,digest in r['loaded_project_python_sources'].items():
            self.assertEqual(builder.digest((ROOT/name).read_bytes()),digest,name)

    def test_reject_unknown_parent(self):
        with self.assertRaisesRegex(ValueError,'exact'):
            builder.return_fade_chain(bytes(0x100000))

    def test_requires_explicit_predecessor_flags_before_writes(self):
        with patch.object(Path,'mkdir',side_effect=AssertionError('unexpected output')):
            with self.assertRaisesRegex(ValueError,'requires explicit secret'):
                builder.build(ROOT/'tmp/not-created',return_fade=True)

    def test_exact_current_candidate_rebuilt(self):
        p=ROOT/'tmp/secret-sound-alias-fast-trial-01/candidate.gb'
        target=ROOT/'tmp/return-cgb-fade-trial-16/candidate.gb'
        if not p.exists() or not target.exists():
            self.skipTest('local construction fixtures unavailable')
        result,records=builder.return_fade_chain(p.read_bytes())
        self.assertEqual(result,target.read_bytes())
        self.assertEqual(len(records),5)
        for a,b in zip(records,records[1:]):
            self.assertEqual(a['candidate_sha256'],b['parent_sha256'])
        for record in records:
            self.assertEqual(builder.digest(Path(record['builder']).read_bytes()),record['builder_sha256'])


if __name__=='__main__':unittest.main()
