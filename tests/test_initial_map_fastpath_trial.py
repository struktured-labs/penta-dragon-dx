"""#14/#45 bounded fast-path trial; full return/audio qualification pending."""
import hashlib
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'scripts/diagnostics'))
import build_initial_map_fastpath_trial as builder


class FastpathTrial(unittest.TestCase):
    def test_native_fade_control_requires_explicit_exact_parent(self):
        p = ROOT/'tmp/return-initial-map-trial-01/candidate.gb'
        if not p.exists(): self.skipTest('native fade parent unavailable')
        parent = p.read_bytes()
        with self.assertRaises(ValueError): builder.build(parent)
        result = builder.build(parent, native_fade_control=True)
        self.assertEqual(hashlib.sha256(result).hexdigest(),
                         'd7ea4f6bbb1e63a29ac5aba42e8c260bb6d246dd9207d65e6d8326bba7382004')
        self.assertEqual(result[0x15da:0x15dd], bytes.fromhex('CD7A0F'))
        self.assertEqual(result[0x75f0:0x75f3], bytes.fromhex('C3330F'))
        self.assertEqual(result[builder.OFFSET:builder.OFFSET+len(builder.body())], builder.body())

    def test_dispatch_preserves_zero_ce_path_and_inactive_return(self):
        code = builder.body()
        self.assertEqual(code[:5], builder.OLD[:5])
        self.assertEqual(code[14:17], bytes.fromhex('3E01C9'))
        self.assertEqual(code[5:8], bytes.fromhex('C3916C'))
        self.assertEqual(code[17:22], bytes.fromhex('F0C1B728F8'))
        self.assertEqual(22 - 8, 14)  # inactive JR Z lands on bank1/Z return
        self.assertEqual(code[22:], builder.OLD[5:])

    def test_exact_parent_and_change_scope(self):
        p = ROOT/'tmp/return-cgb-fade-trial-16/candidate.gb'
        if not p.exists(): self.skipTest('pinned parent unavailable')
        parent = p.read_bytes()
        trial = builder.build(parent)
        self.assertEqual(hashlib.sha256(trial).hexdigest(),
                         'ec8be28897810fac01a8918a0403900780015bf6703531f0f82ae259f209f21b')
        allowed = {0x14e, 0x14f} | set(range(builder.OFFSET, builder.OFFSET+len(builder.body())))
        self.assertTrue(all(i in allowed for i,(a,b) in enumerate(zip(parent,trial)) if a!=b))
        with self.assertRaises(ValueError): builder.build(trial)

    def test_fresh_doorway_matches_parent_without_retiming(self):
        from verify_doorway_occlusion import verify
        trial = ROOT/'tmp/doorway-gate-fastpath-01'
        parent = ROOT/'tmp/doorway-bisect-chunks-01'
        if not trial.exists(): self.skipTest('emulator capture unavailable')
        self.assertTrue(verify(ROOT/'tmp/ceiling-stock-doorway-03', trial)['passed'])
        for name in ('trace.tsv', 'loops.tsv', 'frame-1216.png'):
            self.assertEqual((trial/name).read_bytes(), (parent/name).read_bytes())
        with self.assertRaisesRegex(ValueError, 'position/scene'):
            verify(ROOT/'tmp/ceiling-stock-doorway-03', ROOT/'tmp/return-fade16-doorway-01')


if __name__ == '__main__': unittest.main()
