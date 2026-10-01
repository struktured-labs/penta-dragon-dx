"""Structural guards for rejected #23 diagnostic candidates, not readiness."""
import hashlib
from pathlib import Path
import sys
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts/diagnostics'))
import build_secret_attributes_trial as trial


class SecretAttributeTrialTests(unittest.TestCase):
    def test_helper_fits_before_lookup(self):
        for chunked in (False,True):
            self.assertLessEqual(0x6c80+len(trial.helper(chunked)),trial.TABLE)

    def test_wrong_parent_rejected(self):
        with self.assertRaisesRegex(ValueError,'exact source07'):
            trial.build(bytes(0x100000))

    def test_parent_and_trial_contract(self):
        path=ROOT/'tmp/stream-regressions-source-07/candidate.gb'
        if not path.exists():self.skipTest('local exact ROM not available')
        parent=path.read_bytes()
        self.assertEqual(hashlib.sha256(parent).hexdigest(),trial.PARENT)
        for chunked,expected in (
            (False,'4b00c3134d0f1f6f2508a7e3ed9c129381a0d5d862f361266b348b6430fa3c54'),
            (True,'c29265219f9ef5b288ce0e1a0e18efba8b1352a3c81a8bf3ec04f7dc86b23ad7'),
        ):
            rom=trial.build(parent,chunked)
            self.assertEqual(hashlib.sha256(rom).hexdigest(),expected)
            allowed=set(range(trial.HOOK,trial.HOOK+5))|{0x14e,0x14f}
            allowed.update(range(trial.BASE+0x2c80,trial.BASE+0x2c80+len(trial.helper(chunked))))
            allowed.update(range(trial.BASE+trial.TABLE-0x4000,trial.BASE+trial.TABLE-0x4000+256))
            self.assertTrue(all(i in allowed for i,(a,b) in enumerate(zip(parent,rom)) if a!=b))
            self.assertEqual(int.from_bytes(rom[0x14e:0x150],'big'),(sum(rom[:0x14e])+sum(rom[0x150:]))&65535)


if __name__=='__main__':unittest.main()
