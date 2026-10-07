"""Issue #8: footer ownership and failed-precondition regression controls."""
import hashlib
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts' / 'diagnostics'))
import build_title_glyph_read_window as fix


class TitleGlyphReadWindowTests(unittest.TestCase):
    def test_exact_candidate_and_owned_delta(self):
        parent = (ROOT / 'tmp/later-lowhealth-camera-source-01/candidate.gb').read_bytes()
        child = fix.build(parent)
        self.assertEqual(hashlib.sha256(child).hexdigest(),
                         'a1ff1f90018122d84a378d0150a9fcbd0b5da6ffb228462b4f16c8bcd74e6d6d')
        pos = fix.previous.offset(fix.previous.ENTRY)
        changed = {i for i, (a, b) in enumerate(zip(parent, child)) if a != b}
        self.assertTrue(changed)
        self.assertLessEqual(changed, {0x14e, 0x14f} | set(range(pos, pos + fix.previous.SLOT)))
        damaged = bytearray(parent)
        damaged[0x356ea] ^= 1
        with self.assertRaisesRegex(ValueError, 'exact'):
            fix.build(bytes(damaged))

    def test_both_predicates_follow_read_wait_and_copy_has_own_wait(self):
        code = fix.helper()
        self.assertEqual(len(code), fix.previous.SLOT)
        wait = bytes.fromhex('F041 E602 20FA')
        self.assertEqual(code.count(wait), 2)
        first = code.index(wait)
        for predicate in ('FA459AFE79', 'FAFC97FE18'):
            self.assertGreater(code.index(bytes.fromhex(predicate)), first)
        self.assertLess(code.rindex(wait), code.index(bytes.fromhex('AFE055')))
        # Ordinary gameplay keeps the same early return, before touching VBK.
        self.assertEqual(code[:5], bytes.fromhex('FA80D8FE02'))
        self.assertEqual(code[7:10], bytes.fromhex('FE15D8'))
        self.assertIn(bytes.fromhex('F1C3606B'), code)

    def test_lineage_replays_extension_and_rejects_changed_component(self):
        import lowhealth_candidate_lineage as lineage
        parent = (ROOT / 'tmp/later-lowhealth-camera-source-01/candidate.gb').read_bytes()
        child = fix.build(parent)
        self.assertTrue(lineage.is_candidate(child))
        ancestor, rebuilt = lineage.source_replay(child)
        self.assertEqual(rebuilt, child)
        self.assertEqual(hashlib.sha256(ancestor).hexdigest(), lineage.PARENT_SHA)
        with self.assertRaisesRegex(ValueError, 'title-read delta'):
            lineage.authenticated_parent(child, (0x36da7, 0x36e00))
        with self.assertRaisesRegex(ValueError, 'unowned title-read'):
            lineage.dispatcher_overlay(child, 0x36da7, ancestor[0x36da7:0x36e00])


if __name__ == '__main__':
    unittest.main()
