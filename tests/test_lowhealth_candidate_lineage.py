"""#59: unchanged-component inheritance must reject every changed region."""
import hashlib
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts/diagnostics'))
import lowhealth_candidate_lineage as lineage


class LowHealthLineage(unittest.TestCase):
    def setUp(self):
        self.parent = bytearray(0x100000)
        self.child = bytearray(self.parent)
        for offset, before, after in lineage.RUNS:
            self.parent[offset:offset + len(bytes.fromhex(before))] = bytes.fromhex(before)
            self.child[offset:offset + len(bytes.fromhex(after))] = bytes.fromhex(after)
        for name, data in (('PARENT_SHA', self.parent), ('CANDIDATE_SHA', self.child)):
            context = patch.object(lineage, name, hashlib.sha256(data).hexdigest())
            context.start()
            self.addCleanup(context.stop)

    def test_exact_ancestor_reconstruction(self):
        self.assertEqual(lineage.authenticated_parent(self.child, (0x42a7, 0x436e)), self.parent)

    def test_all_changed_regions_rejected(self):
        for offset, before, after in lineage.RUNS:
            with self.assertRaisesRegex(ValueError, 'intersects'):
                lineage.authenticated_parent(self.child, (offset, offset + len(bytes.fromhex(after))))

    def test_unknown_rom_fails_even_outside_delta(self):
        changed = bytearray(self.child)
        changed[0x500] ^= 1
        self.assertFalse(lineage.is_candidate(changed))
        with self.assertRaisesRegex(ValueError, 'exact'):
            lineage.authenticated_parent(changed, (0x42a7, 0x436e))

    def test_repin_cannot_hide_unlisted_change(self):
        changed = bytearray(self.child)
        changed[0x500] ^= 1
        with patch.object(lineage, 'CANDIDATE_SHA', hashlib.sha256(changed).hexdigest()):
            with self.assertRaisesRegex(ValueError, 'reconstruction'):
                lineage.authenticated_parent(changed, (0x42a7, 0x436e))

    def test_repin_cannot_hide_wrong_delta(self):
        changed = bytearray(self.child)
        changed[0x7b8a0] ^= 1
        with patch.object(lineage, 'CANDIDATE_SHA', hashlib.sha256(changed).hexdigest()):
            with self.assertRaisesRegex(ValueError, 'delta bytes'):
                lineage.authenticated_parent(changed, (0x42a7, 0x436e))

    def test_explicit_valid_ranges_required(self):
        for ranges in ((), ((0, 0),), ((-1, 2),), ((0, 0x100001),)):
            with self.assertRaises(ValueError):
                lineage.authenticated_parent(self.child, *ranges)

    def test_dispatcher_overlay_owns_only_four_immediates(self):
        for start, end in ((0x356ca, 0x356ee), (0x356fa, 0x356ff)):
            self.assertEqual(lineage.dispatcher_overlay(self.child, start, self.parent[start:end]),
                             self.child[start:end])
        with self.assertRaisesRegex(ValueError, 'unowned'):
            lineage.dispatcher_overlay(self.child, 0x7b8a0, self.parent[0x7b8a0:0x7b8a9])

    def test_dispatcher_wrong_oracle_is_not_overwritten(self):
        payload = bytearray(self.parent[0x356ca:0x356ee])
        payload[0x356ea - 0x356ca] ^= 1
        with self.assertRaisesRegex(ValueError, 'preimage'):
            lineage.dispatcher_overlay(self.child, 0x356ca, payload)


class ActualCandidate(unittest.TestCase):
    def test_retains_full_roster_and_exact_broken_control(self):
        path = ROOT / 'tmp/later-lowhealth-camera-source-01/candidate.gb'
        if not path.is_file():
            self.skipTest('local source candidate absent')
        import verify_release_candidate
        import verify_playtest_boss_handoff
        import build_boss_prelude_inline_rearm as layout
        rom = path.read_bytes()
        self.assertTrue(lineage.is_candidate(rom))
        parent, rebuilt = lineage.source_replay(rom)
        self.assertEqual(hashlib.sha256(parent).hexdigest(), lineage.PARENT_SHA)
        self.assertEqual(rebuilt, rom)
        gates = verify_release_candidate.build_gates(path, ROOT / 'tmp/unused-lowhealth-roster')
        names = [gate.name for gate in gates]
        self.assertEqual(len(names), 97)
        for name in ('playtest_header_data_and_timing', 'playtest_secret_boss_handoff',
                     'low_health_flicker', 'gameplay_movement_stress'):
            self.assertIn(name, names)
        broken = verify_playtest_boss_handoff.broken_control(rom)
        self.assertEqual(hashlib.sha256(broken).hexdigest(),
                         'a73288eb3ae486f8c431cde5ba69ba59d6932ccb3d579848926ef8bba01888fd')
        allowed = set(range(layout.HOOK, layout.HOOK + len(layout.OLD))) | {0x14e, 0x14f}
        self.assertTrue({i for i, (a, b) in enumerate(zip(rom, broken)) if a != b} <= allowed)


if __name__ == '__main__':
    unittest.main()
