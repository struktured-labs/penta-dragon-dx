"""#27 source reproducibility and native restart qualification, not readiness."""
import hashlib
import json
from pathlib import Path
import sys
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'scripts'),str(ROOT/'scripts/diagnostics')]
from build_stream_regression_candidate import arena_alias_chain,build
from verify_gameover_restart import validate,validate_stage_cards
from gameover_sequence import validate_sequence

PIN='585f5830daa32e59c000f5ddd6b57aab545e55375b46574286702db9fc28e4db'


class ArenaAliasSource(unittest.TestCase):
    def test_explicit_opt_in_and_exact_parent(self):
        with self.assertRaisesRegex(ValueError,'requires explicit presentation'):
            build(ROOT/'tmp/not-created-arena-alias-test',arena_alias=True)
        with self.assertRaises(ValueError):
            arena_alias_chain(bytes(0x100000))

    def test_source_receipt_and_transitive_bindings(self):
        base=ROOT/'tmp/arena-alias-source-03'
        if not (base/'build-receipt.json').exists():self.skipTest('local source build unavailable')
        receipt=json.loads((base/'build-receipt.json').read_text())
        self.assertTrue(receipt['experimental_arena_alias_chain'])
        self.assertTrue(receipt['experimental_presentation_chain'])
        self.assertFalse(receipt['experimental_arena_completion_safe_chain'])
        self.assertFalse(receipt['release_qualified'])
        self.assertFalse(receipt['retained_candidate_inputs'])
        self.assertEqual(receipt['candidate_sha256'],PIN)
        self.assertEqual(hashlib.sha256((base/'candidate.gb').read_bytes()).hexdigest(),PIN)
        for path,digest in receipt['loaded_project_python_sources'].items():
            self.assertEqual(hashlib.sha256((ROOT/path).read_bytes()).hexdigest(),digest,path)
        self.assertEqual([x['name'] for x in receipt['stages'][-3:]],
                         ['arena-sound-alias','arena-graphics-owner','arena-alias-fastpath'])

    def test_native_damage_restart(self):
        base=ROOT/'tmp/arena-alias-fastpath-natural-restart-01'
        if not (base/'receipt.json').exists():self.skipTest('local restart replay unavailable')
        receipt=json.loads((base/'receipt.json').read_text())
        self.assertEqual(receipt['rom_sha256'],PIN)
        self.assertEqual(hashlib.sha256((base/'runtime/candidate.gb').read_bytes()).hexdigest(),PIN)
        self.assertEqual(receipt['status'],'pass')
        self.assertIn('movement-driven native damage',receipt['stimulus'])
        self.assertTrue(receipt['saved_game_fixture'])
        self.assertEqual((base/'route.txt').read_text().strip(),'ok 2 2 2')
        validate(base)
        validate_stage_cards(base,saved_game=True)
        self.assertEqual(validate_sequence(base),{'title_frame_pairs':482,'gameover_frames':102})


if __name__=='__main__':unittest.main()
