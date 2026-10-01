"""Issue #33: bounded experimental patch and actual timer negative control."""
import csv
import hashlib
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts/diagnostics'))
from build_menu_timer_yield_trial import build
from check_secret_timer_spacing import check


class MenuTimerYieldTests(unittest.TestCase):
    def test_fast_row_midpoint_composition(self):
        path = ROOT / 'tmp/menu-row-staged-trial-02/candidate.gb'
        if not path.exists():
            self.skipTest('local fast-row candidate unavailable')
        parent = path.read_bytes()
        result = build(parent, per_row=True, pending_only=True, midpoint_only=True)
        self.assertEqual(hashlib.sha256(result).hexdigest(),
                         'c55a4f55c79d7705dedf5cebe8c01483b3d9d7ce1bb9de1472a6690fca704109')
        # The unrolled compiler and every HBlank write group remain intact.
        self.assertEqual(result[0x53c00:0x53e00], parent[0x53c00:0x53e00])
        with self.assertRaises(ValueError):
            build(parent)

    def test_retained_category_inputs_are_consumed_in_requested_frames(self):
        # Native category writes, not map selector/DC0B or copy-entry counts.
        # Does not claim rendered response latency or other menu controls.
        for name, sha in (
            ('secret-original-menu-input-02',
             'f19fa1895c3d363afbb70531105243b72e0250c4a1008c0636618a0a63c13a31'),
            ('secret-midpoint-menu-input-02',
             '410340e5a9380e019a0ac1fd293d86fa28d4cfa51f5e91bd0a1125ecf3550cc7'),
        ):
            path = ROOT / 'tmp' / name / 'menu-input.tsv'
            if not path.exists():
                self.skipTest('local menu input trace unavailable')
            self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), sha)
            with path.open() as stream:
                rows = list(csv.DictReader(stream, delimiter='\t'))
            changes = [(int(r['frame']), r['selector']) for r in rows
                       if r['pc'] == '1EB5' and 2400 <= int(r['frame']) < 2520]
            self.assertEqual(changes, [(2420, '01'), (2460, '00')])

    def test_wrong_parent_rejected(self):
        with self.assertRaises(ValueError):
            build(bytes(1024))

    def test_composition_preserves_other_repair_banks(self):
        path = ROOT / 'tmp/ceiling-secret-composition-01/candidate.gb'
        if not path.exists():
            self.skipTest('local combined parent unavailable')
        parent = path.read_bytes()
        result = build(parent, True, True, True)
        self.assertEqual(hashlib.sha256(result).hexdigest(),
                         '0847fb0fda65b365a65a816f06b5a6ebd970613c3ff5acc09b297f8c7e20b853')
        changed = [i for i, (a, b) in enumerate(zip(parent, result)) if a != b]
        self.assertTrue(all(i in (0x14e, 0x14f) or
                            20*0x4000 <= i < 21*0x4000 for i in changed))
        self.assertEqual(result[32*0x4000:37*0x4000], parent[32*0x4000:37*0x4000])

    def test_exact_candidate_and_bounded_changes(self):
        path = ROOT / 'tmp/stream-regressions-source-07/candidate.gb'
        if not path.exists():
            self.skipTest('local source07 unavailable')
        parent = path.read_bytes()
        result = build(parent)
        self.assertEqual(hashlib.sha256(result).hexdigest(),
                         '18e34994fed287d66af648c8756ce78c5c28c1943e1ac154446df59e3643df68')
        self.assertEqual(len(result), len(parent))
        changed = [i for i, (a, b) in enumerate(zip(parent, result)) if a != b]
        self.assertTrue(changed)
        self.assertTrue(all(i in (0x14e, 0x14f) or
                            20*0x4000 <= i < 21*0x4000 for i in changed))

    def test_retained_parent_fails_trial_passes(self):
        for name, sha, late in (
            ('secret-source07-menu-timing-01',
             '33293c8b5788cecc4e93716564aa03b144ed9738c0f5381efdafb39f1f0f0923', 5),
            ('secret-menu-yield-timing-01',
             'c44f6fdd73037012f5fe6296ab994d763a63f4d8db4c0af275142f6b8862f29e', 0),
        ):
            with self.subTest(name=name):
                path = ROOT / 'tmp' / name / 'sound-timing.tsv'
                if not path.exists():
                    self.skipTest('local timer evidence unavailable')
                self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), sha)
                with path.open() as stream:
                    rows = list(csv.DictReader(stream, delimiter='\t'))
                # Same complete prefix through menu close, not a selected
                # passing subset of the actual menu exposure.
                result = check([r for r in rows if int(r['frame']) <= 2600])
                self.assertEqual(len(result['late_intervals']), late)
                self.assertEqual(bool(result['errors']), bool(late))

    def test_row_trial_preserves_inner_loop_target(self):
        path = ROOT / 'tmp/stream-regressions-source-07/candidate.gb'
        if not path.exists():
            self.skipTest('local source07 unavailable')
        parent = path.read_bytes()
        result = build(parent, per_row=True)
        self.assertEqual(hashlib.sha256(result).hexdigest(),
                         'b6f637e8fdf55b816834b670386cb1d1c39fc42f0de69ae17f3e2b9ec1b1ff9b')
        base = 20 * 0x4000
        pair = parent.index(bytes.fromhex('0E0AC51A13CD844047'), base, base+0x4000)
        self.assertEqual(result[pair:pair+9], parent[pair:pair+9])
        tail = parent.index(bytes.fromhex('7806000E0C094705'), base, base+0x4000)
        self.assertEqual(result[tail:tail+3], bytes.fromhex('C3007E'))

    def test_pending_and_midpoint_branches_restore_flags(self):
        path = ROOT / 'tmp/stream-regressions-source-07/candidate.gb'
        if not path.exists():
            self.skipTest('local source07 unavailable')
        for midpoint, expected in (
            (False, 'ddccb54e26681485a8f8008ff4d439b5f5bb45db2b561ae71166cb94ab6cbdfd'),
            (True, 'cf5f517c29978cb119725d1ee4c0aeefcf51299e245bf2943d758f6aa744e8ad'),
        ):
            result = build(path.read_bytes(), True, True, midpoint)
            self.assertEqual(hashlib.sha256(result).hexdigest(), expected)
            helper = result[20*0x4000+0x3e00:20*0x4000+0x3e40]
            # Both conditional exits land on the common POP AF, not a
            # displaced instruction or an operand byte.
            branches = (4, 10) if midpoint else (5,)
            for pc in branches:
                self.assertIn(helper[pc], (0x20, 0x28))
                self.assertEqual(helper[pc+2+helper[pc+1]], 0xf1)
