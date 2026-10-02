"""#45 shortened dispatch is a retained failed timing experiment."""
import csv
import hashlib
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts/diagnostics'))
import build_native_fade_dispatch_trial as builder


class NativeFadeDispatch(unittest.TestCase):
    def test_patch_does_not_change_menu_fallthrough_or_fixed_code(self):
        p = ROOT/'tmp/initial-map-fastpath-trial-01/candidate.gb'
        if not p.exists(): self.skipTest('local parent unavailable')
        old = p.read_bytes(); new = builder.build(old)
        self.assertEqual(hashlib.sha256(new).hexdigest(),
                         '32f85ef6b4d0799c852a749ac55f99df9d44c57ef713f1ec9c6ba1a7b417e41f')
        allowed = {0x14e,0x14f,builder.BASE+0x4707,builder.BASE+0x4708}
        allowed.update(range(builder.BASE+0x5d00,builder.BASE+0x5d40))
        self.assertTrue(all(i in allowed for i,(a,b) in enumerate(zip(old,new)) if a!=b))
        self.assertEqual(old[builder.BASE+0x4709:builder.BASE+0x4800],
                         new[builder.BASE+0x4709:builder.BASE+0x4800])
        with self.assertRaises(ValueError): builder.build(new)

    def test_shorter_dispatch_still_fails_native_fade_timing(self):
        p=ROOT/'tmp/native-fade-dispatch-entry-01/secret-fade-timing.tsv'
        if not p.exists(): self.skipTest('local replay unavailable')
        with p.open() as f: rows={r['pc']:r for r in csv.DictReader(f,delimiter='\t')}
        self.assertEqual(int(rows['0F7A']['cycle'])-int(rows['15DA']['cycle']),1104)
        self.assertEqual(rows['15DD']['frame'],'2649')
        self.assertNotEqual(rows['15DD']['frame'],'2652')


if __name__ == '__main__': unittest.main()
