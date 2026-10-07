import hashlib
import sys
from pathlib import Path
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'scripts/diagnostics'))
import playtest_successor_lineage as m

class SuccessorLineageTest(unittest.TestCase):
    def setUp(self):
        self.parent=bytearray(0x100000)
        self.child=bytearray(self.parent)
        for offset,before,after in m.RUNS:
            self.parent[offset:offset+len(bytes.fromhex(before))]=bytes.fromhex(before)
            self.child[offset:offset+len(bytes.fromhex(after))]=bytes.fromhex(after)
        self.a=patch.object(m,'PARENT_SHA',hashlib.sha256(self.parent).hexdigest())
        self.b=patch.object(m,'CANDIDATE_SHA',hashlib.sha256(self.child).hexdigest())
        self.a.start();self.b.start();self.addCleanup(self.a.stop);self.addCleanup(self.b.stop)

    def test_complete_parent_reconstruction(self):
        self.assertEqual(m.authenticated_parent(self.child,(0x42a7,0x436e)),self.parent)

    def test_every_changed_run_rejected_as_unchanged_component(self):
        for offset,before,after in m.RUNS:
            with self.assertRaisesRegex(ValueError,'intersects'):
                m.authenticated_parent(self.child,(offset,offset+1))

    def test_mutated_child_rejected_inside_and_outside_delta(self):
        for offset in (0x1a43,0x42a7,0xffba1,0x148):
            rom=bytearray(self.child);rom[offset]^=1
            self.assertFalse(m.is_candidate(rom))
            with self.assertRaisesRegex(ValueError,'exact'):
                m.authenticated_parent(rom,(0x42a7,0x436e))

    def test_ranges_required_and_bounded(self):
        for ranges in ((),((0,0),),((-1,2),),((0,0x100001),)):
            with self.assertRaises(ValueError):m.authenticated_parent(self.child,*ranges)

    def test_delta_mutation_rejected_even_with_repin(self):
        rom=bytearray(self.child);rom[0x1a43]^=1
        with patch.object(m,'CANDIDATE_SHA',hashlib.sha256(rom).hexdigest()):
            with self.assertRaisesRegex(ValueError,'delta bytes'):
                m.authenticated_parent(rom,(0x42a7,0x436e))

    def test_unlisted_mutation_rejected_even_with_repin(self):
        rom=bytearray(self.child);rom[0x500]^=1
        with patch.object(m,'CANDIDATE_SHA',hashlib.sha256(rom).hexdigest()):
            with self.assertRaisesRegex(ValueError,'reconstruction'):
                m.authenticated_parent(rom,(0x42a7,0x436e))

if __name__=='__main__':unittest.main()
