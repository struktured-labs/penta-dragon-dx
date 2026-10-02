"""#26 explicit experimental source construction; audio failure is not waived."""
import hashlib
import inspect
import json
from pathlib import Path
import sys
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
from build_stream_regression_candidate import build


class SecretAliasSource(unittest.TestCase):
    def test_requires_explicit_dependencies_and_defaults_off(self):
        self.assertIs(inspect.signature(build).parameters['secret_sound_alias'].default,False)
        with self.assertRaisesRegex(ValueError,'requires explicit completion-safe'):
            build(ROOT/'tmp/not-created-secret-source-test',secret_sound_alias=True)

    def test_source_result_matches_trial_and_binds_helpers(self):
        base=ROOT/'tmp/secret-sound-alias-fast-source-01'
        if not (base/'build-receipt.json').exists(): self.skipTest('local source build unavailable')
        receipt=json.loads((base/'build-receipt.json').read_text())
        pin='665a33b6b26d0a8ec1622a7c897d4fc10bdf7c8c5e0e5a2edaae98df0dafe0e7'
        self.assertEqual(receipt['candidate_sha256'],pin)
        self.assertEqual(hashlib.sha256((base/'candidate.gb').read_bytes()).hexdigest(),pin)
        self.assertFalse(receipt['release_qualified'])
        self.assertFalse(receipt['retained_candidate_inputs'])
        self.assertTrue(receipt['experimental_secret_sound_alias_chain'])
        self.assertIn('audio comparison fails',receipt['qualification_warning'])
        self.assertEqual(receipt['stages'][-1]['name'],'secret-sound-alias-fast')
        sources=receipt['loaded_project_python_sources']
        self.assertIn('scripts/diagnostics/build_secret_sound_alias_fast_trial.py',sources)
        for path,digest in sources.items():
            self.assertEqual(hashlib.sha256((ROOT/path).read_bytes()).hexdigest(),digest,path)
        self.assertEqual(receipt['entrypoint_sha256'],
                         hashlib.sha256((ROOT/'scripts/build_stream_regression_candidate.py').read_bytes()).hexdigest())
