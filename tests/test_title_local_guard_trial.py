"""#35 retain access safety, mapper preservation, and unqualified timing deltas."""
import csv
import hashlib
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'scripts/diagnostics'))
from build_title_local_guard_trial import build, offset, payload, ENTRY, DATA, PARENT, OFFSET
from check_cram_timing import check

TRIAL = '8ff1c98d98f6949d39628c0c9fc86a53aae805f25cb8936484f2a00893af5c3c'


class TitleLocalGuardTests(unittest.TestCase):
    def test_retained_two_cycle_hazard_restart(self):
        path = ROOT/'tmp/title-local-guard-hazard-restart-01'
        if not (path/'receipt.json').exists():
            self.skipTest('retained restart evidence unavailable')
        self.assertEqual(hashlib.sha256((path/'runtime/candidate.gb').read_bytes()).hexdigest(), TRIAL)
        # Re-run the image/data oracles, not the receipt's cached pass flag.
        from verify_gameover_restart import validate, validate_stage_cards
        from gameover_sequence import validate_sequence
        validate(path)
        validate_stage_cards(path, saved_game=True)
        self.assertEqual(validate_sequence(path),
                         {'title_frame_pairs': 482, 'gameover_frames': 102})

    def test_unknown_parent_rejected(self):
        with self.assertRaisesRegex(ValueError, 'exact'):
            build(bytes(1024))

    def test_patch_scope_and_return(self):
        path = ROOT/'tmp/handheld-palette-trial-01/candidate.gb'
        if not path.exists():
            self.skipTest('experimental parent unavailable')
        parent = path.read_bytes()
        result = build(parent)
        self.assertEqual(hashlib.sha256(parent).hexdigest(), PARENT)
        self.assertEqual(hashlib.sha256(result).hexdigest(), TRIAL)
        allowed = {0x14e, 0x14f} | set(range(OFFSET, OFFSET+9))
        for address, length in ((0x6A59, 6), (ENTRY, len(payload())), (DATA, 8)):
            allowed.update(range(offset(address), offset(address)+length))
        self.assertEqual(len(result), len(parent))
        self.assertFalse([i for i,(a,b) in enumerate(zip(parent,result)) if a != b and i not in allowed])
        self.assertEqual(result[OFFSET:OFFSET+9], bytes.fromhex('3E14 CDBE09 F1 E0FF C9'))
        self.assertEqual(result[offset(DATA):offset(DATA)+8], parent[0x36838:0x36840])

    def test_retained_mapper_contract_and_safety(self):
        path = ROOT/'tmp/title-helper-local-cold-01'
        if not (path/'frame-0600.ss0').exists():
            self.skipTest('retained emulator evidence unavailable')
        self.assertEqual(hashlib.sha256((path/'candidate.gb').read_bytes()).hexdigest(), TRIAL)
        with (path/'cram-timing.tsv').open() as stream:
            result = check(csv.DictReader(stream, delimiter='\t'))
        self.assertEqual(result['writes'], 3248)
        self.assertEqual(result['status'], 'PASS_OBSERVED_WRITES')
        with (path/'title-helper.tsv').open() as stream:
            rows = list(csv.DictReader(stream, delimiter='\t'))
        self.assertEqual(len(rows), 732)
        for a,b in zip(rows[::2], rows[1::2]):
            self.assertEqual(a['event'], 'enter')
            self.assertIn(b['event'], ('return0', 'return7'))
            self.assertEqual(a['dc09'], b['dc09'])
            self.assertEqual(a['de'], b['de'])
            self.assertEqual(int(b['bc'],16), int(a['bc'],16)&0xff00)
            self.assertEqual(int(b['hl'],16), int(a['hl'],16)+8)
            self.assertEqual(int(b['sp'],16), int(a['sp'],16)+2)
        with (path/'trace.tsv').open() as stream:
            rows = list(csv.DictReader(stream, delimiter='\t'))
        # Still one frame different from parent499: no cadence qualification.
        self.assertEqual(next(int(r['frame']) for r in rows if r['scene']=='02'), 498)
