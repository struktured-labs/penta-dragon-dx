"""Issue #33 experimental quartet builder preserves exact source bounds."""
import hashlib
import csv
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts/diagnostics'))
from build_menu_quartet_trial import build, payload, staged_payload
from check_secret_timer_spacing import check


class MenuQuartetTests(unittest.TestCase):
    def test_composition_preserves_other_fix_banks(self):
        path = ROOT / 'tmp/ceiling-secret-composition-01/candidate.gb'
        if not path.exists():
            self.skipTest('local composition unavailable')
        parent = path.read_bytes()
        rom, _ = build(parent, stage_row=True, fast_compile=True)
        changes = [i for i, (a, b) in enumerate(zip(parent, rom)) if a != b]
        length = len(staged_payload(True)[0])
        self.assertTrue(changes)
        self.assertTrue(all(i in (0x14e, 0x14f) or 0x5004a <= i < 0x5004d
                            or 0x53c00 <= i < 0x53c00 + length for i in changes))
        for bank in (13, 16, 28, 33, 34, 36):
            self.assertEqual(rom[bank*0x4000:(bank+1)*0x4000],
                             parent[bank*0x4000:(bank+1)*0x4000])

    def test_fast_compile_pin_and_observed_timer_regression(self):
        p = ROOT / 'tmp/stream-regressions-source-07/candidate.gb'
        if not p.exists():
            self.skipTest('local source07 unavailable')
        rom, _ = build(p.read_bytes(), stage_row=True, fast_compile=True)
        self.assertEqual(hashlib.sha256(rom).hexdigest(),
                         '32bd961cd7a5eb70f65d5a47820ffcba11cd82856ff0c6ce18260e55bc29e628')
        for suffix, sha, late in (
            ('01', '4f43eaf4569e607aef3b14e9c838b193dbff9c75aef7186dce270e9bef212749', 2),
            ('02', '3749bd0ec8b7810dac6b636c85e1231cfa5d1048ca877c3d414ac22684c0e0bd', 0),
        ):
            path = ROOT / f'tmp/secret-menu-row-staged-safety-{suffix}/sound-timing.tsv'
            if not path.exists():
                self.skipTest('local timer evidence unavailable')
            self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), sha)
            with path.open() as f:
                result = check(csv.DictReader(f, delimiter='\t'))
            self.assertEqual(len(result['late_intervals']), late)
            self.assertEqual(bool(result['errors']), bool(late))

    def test_staged_row_has_five_balanced_write_groups(self):
        code, labels = staged_payload()
        for group in range(5):
            start = labels[f'before_{group}']-0x7c00
            end = labels[f'after_{group}']-0x7c00
            self.assertEqual(code[start:end], bytes.fromhex('783279327A327B32'))
            self.assertEqual(code[end:end+2], bytes.fromhex('E808'))
        p = ROOT / 'tmp/stream-regressions-source-07/candidate.gb'
        if not p.exists():
            self.skipTest('local source07 unavailable')
        rom, _ = build(p.read_bytes(), stage_row=True)
        self.assertEqual(hashlib.sha256(rom).hexdigest(),
                         'ef44aeb52511c76e2d42b1a81566114341ac2ffe912d2a714025fd955ddf7118')

    def test_unknown_parent_rejected(self):
        with self.assertRaises(ValueError):
            build(bytes(1024))

    def test_write_span_and_stack_balance_instructions(self):
        for direct in (False, True):
            code, labels = payload(direct)
            before, after = labels['before']-0x7e00, labels['after']-0x7e00
            self.assertEqual(code[before:after], bytes.fromhex('7B227A2279227822'))
            self.assertEqual(code[after:after+9], bytes.fromhex('E80AD113131313C10D'))
            self.assertEqual(code[-3:], bytes.fromhex('C36F40'))

    def test_exact_variants(self):
        p = ROOT / 'tmp/stream-regressions-source-07/candidate.gb'
        if not p.exists():
            self.skipTest('local source07 unavailable')
        parent = p.read_bytes()
        for direct, sha in (
            (False, 'c5b3e60e794b4df4dd7d399bc0b3b0b32a5090a1d978f80ecdde660de26da1b9'),
            (True, '0d1264f9127be15310ac2651a1c4443251aa54b87e50fde711e39a039062c24e'),
        ):
            rom, labels = build(parent, direct)
            self.assertEqual(hashlib.sha256(rom).hexdigest(), sha)
            changes = [i for i, (a,b) in enumerate(zip(parent,rom)) if a != b]
            self.assertTrue(all(i in (0x14e,0x14f) or 0x5004a <= i < 0x5004d
                                or 0x53e00 <= i < 0x53e00+len(payload(direct)[0])
                                for i in changes))
