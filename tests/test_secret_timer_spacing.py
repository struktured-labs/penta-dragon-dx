"""#23 actual delayed-interrupt negative control plus malformed-trace guards."""
import csv
import hashlib
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts/diagnostics'))
from check_secret_timer_spacing import check


class SecretTimerSpacingTests(unittest.TestCase):
    def test_lowhealth_alias_actual_traces(self):
        for name, sha, maximum in (
                ('secret-sound-alias-timing-01',
                 '21a9a1003d5bec0a66f0c84412b95430f02a4938cd1113ab98e28bf3f17f46c6',110312),
                ('secret-sound-alias-parent-timing-01',
                 'fb2ebaffc919a181629087200179b34e46ba98be95699fa2fdec38a332fe3f13',118696)):
            path = ROOT/'tmp'/name/'sound-timing.tsv'
            if not path.exists(): self.skipTest('local alias timing traces unavailable')
            self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), sha)
            with path.open() as stream:
                rows = list(csv.DictReader(stream, delimiter='\t'))
            timers = [r for r in rows if r['kind'] == 'timer']
            self.assertTrue(any(r['scene'] == '0B' for r in timers))
            result = check(rows)
            self.assertEqual(result['intervals'], len(timers)-1)
            self.assertEqual(result['intervals'], 714)
            self.assertEqual(result['maximum_cycles'], maximum)
            self.assertEqual(result['status'], 'PASS_OBSERVED_TIMER_SPACING')
            self.assertEqual(result['late_intervals'], [])

    def test_tagged_sound_alias_does_not_hide_delayed_interrupts(self):
        row = dict(kind='timer', scene='09', tma='D2', tac='FC', svbk='01',
                   frame='1', cycle='0', canonical='09', stage='07')
        alias = dict(row, scene='0B', frame='2', cycle='190000')
        result = check([row, alias])
        self.assertEqual(result['intervals'], 1)
        self.assertEqual(len(result['late_intervals']), 1)
        self.assertEqual(result['status'], 'FAIL')
        self.assertEqual(check([dict(row, scene='0A'),
                                dict(alias, cycle='94208')])['status'], 'PASS_OBSERVED_TIMER_SPACING')
        result = check([row, dict(alias, stage='00')])
        self.assertEqual(result['intervals'], 0)
        self.assertEqual(len(result['scene_boundary_intervals']), 1)

    def test_retained_parent_broken_trial_and_row_yield_trial(self):
        fixtures = (
            ('parent', 'e69d147eec34385b4173e2fc6320994e2f4ec6e0e4a107a6b797f91ea998f3ff', 118696, 0),
            ('trial02', 'e2d993571f415ffb691bf74eacdbfab82d258035270115b13a7640c475aabe7c', 190304, 286),
            ('trial03', '63fe4c360d1e9071e6f1c03fb1b32475ea2b9889a5cabbb769c26f2deb8efc35', 113208, 0),
        )
        for name, sha, maximum, late in fixtures:
            with self.subTest(name=name):
                path = ROOT / f'tmp/secret-sound-timing-{name}-01/sound-timing.tsv'
                if not path.exists():
                    self.skipTest('local diagnostic traces unavailable')
                self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), sha)
                with path.open() as stream:
                    result = check(csv.DictReader(stream, delimiter='\t'))
                self.assertEqual(result['maximum_cycles'], maximum)
                self.assertEqual(len(result['late_intervals']), late)
                self.assertEqual(bool(result['errors']), bool(late))

    def test_empty_trace_fails(self):
        self.assertTrue(check([])['errors'])

    def test_menu_exposure_remains_a_failure_with_row_yields(self):
        # #23: the ordinary combat replay passed, but opening the menu
        # exposes late interrupts. Do not exclude menu frames to make it pass.
        fixtures = (
            ('secret-row-yield-menu-timing-01',
             '777f65ad03702f721c310c7b2dd0d89874657787522e2ea7a6d9ea13d70cc6f1', 144128),
            ('ceiling-secret-composition-return-01',
             'd7efa2d19d8cc0b017ad454f866291c6a94cd94407eb8b850b7043a11d5b7753', 147120),
        )
        for name, sha, maximum in fixtures:
            with self.subTest(name=name):
                path = ROOT / 'tmp' / name / 'sound-timing.tsv'
                if not path.exists():
                    self.skipTest('local diagnostic traces unavailable')
                self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), sha)
                with path.open() as stream:
                    result = check(csv.DictReader(stream, delimiter='\t'))
                self.assertEqual(result['status'], 'FAIL')
                self.assertEqual(result['maximum_cycles'], maximum)
                self.assertEqual(len(result['late_intervals']), 3)
                self.assertTrue(all(2400 <= gap['start_frame'] < 2520
                                    for gap in result['late_intervals']))

    def test_wrong_bank_configuration_and_clock_fail(self):
        base = dict(kind='timer', scene='09', tma='D2', tac='FC',
                    svbk='01', frame='1500', cycle='100000')
        good = [base, dict(base, frame='1501', cycle='194208')]
        self.assertFalse(check(good)['errors'])
        for mutation in (dict(svbk='06'), dict(tma='00'), dict(cycle='99999')):
            with self.subTest(mutation=mutation):
                self.assertTrue(check([base, dict(good[1], **mutation)])['errors'])


if __name__ == '__main__':
    unittest.main()
