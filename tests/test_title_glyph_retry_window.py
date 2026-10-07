"""Issue #8: minimal blocked-predicate retry preserves successful paths."""
import hashlib
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts' / 'diagnostics'))
import build_title_glyph_retry_window as fix


class TitleGlyphRetryTests(unittest.TestCase):
    def test_successful_paths_unchanged(self):
        old, new = fix.old.helper(), fix.helper()
        read = old.index(bytes.fromhex('FA459AFE79'))
        operand = read + 6
        tail = len(old.rstrip(b'\0'))
        self.assertEqual(len(new), len(old))
        self.assertEqual(new[:operand], old[:operand])
        self.assertEqual(new[operand + 1:tail], old[operand + 1:tail])
        self.assertEqual(new[tail:tail + 5], bytes.fromhex('F041E60228'))
        self.assertEqual(new[tail + 6], 0x18)
        target = lambda at: at + 1 + int.from_bytes(new[at:at+1], 'little', signed=True)
        self.assertEqual(target(operand), tail)
        self.assertEqual(target(tail + 7), read)
        self.assertEqual(new[target(tail + 5):target(tail + 5) + 4], bytes.fromhex('F1C3606B'))

    def test_exact_rom_and_changed_ownership(self):
        parent = (ROOT / 'tmp/later-lowhealth-camera-source-01/candidate.gb').read_bytes()
        child = fix.build(parent)
        import lowhealth_candidate_lineage as lineage
        self.assertTrue(lineage.is_candidate(child))
        ancestor, rebuilt = lineage.source_replay(child)
        self.assertEqual(rebuilt, child)
        self.assertEqual(hashlib.sha256(ancestor).hexdigest(), lineage.PARENT_SHA)
        with self.assertRaisesRegex(ValueError, 'title-read delta'):
            lineage.authenticated_parent(child, (0x36da7, 0x36e00))
        self.assertEqual(hashlib.sha256(child).hexdigest(),
                         '126861281b75edaf8daace834ccbe41e53ed0c9eebb71e50fe3bd6823e8b6941')
        allowed = {0x14e, 0x14f, fix.old.offset(0x6dd0)} | set(range(fix.old.offset(0x6df5), fix.old.offset(0x6dfd)))
        self.assertLessEqual({i for i, (a, b) in enumerate(zip(parent, child)) if a != b}, allowed)
        damaged = bytearray(parent)
        damaged[fix.old.offset(fix.old.ENTRY)] ^= 1
        with self.assertRaisesRegex(ValueError, 'exact'):
            fix.build(bytes(damaged))


if __name__ == '__main__':
    unittest.main()
