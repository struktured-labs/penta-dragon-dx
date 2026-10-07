"""#68: publication must require the same candidate-specific gate roster."""
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'scripts/diagnostics'))
import verify_release_candidate as matrix
import lowhealth_candidate_lineage as low
import playtest_successor_lineage as successor
import run_deterministic_suite as runner


class GateInventoryIdentity(unittest.TestCase):
    def setUp(self):
        self.scratch = tempfile.TemporaryDirectory(dir=ROOT/'tmp', prefix='gate-inventory-test-')
        self.addCleanup(self.scratch.cleanup)
        self.root = Path(self.scratch.name)

    def names(self, path, pin):
        return [gate.name for gate in matrix.build_gates(
            path, self.root/'output', expanded_candidate_override=True,
            menu_icon_candidate_override=True, candidate_sha256=pin)]

    def test_supported_hash_only_candidates_require_both_playtest_gates(self):
        for pin in (successor.CANDIDATE_SHA, low.CANDIDATE_SHA, *sorted(low.TITLE_SHAS)):
            with self.subTest(pin=pin):
                names = self.names(self.root/'absent.gb', pin)
                self.assertEqual(len(names), 97)
                self.assertEqual(names[3:5], ['playtest_header_data_and_timing',
                                             'playtest_secret_boss_handoff'])
                self.assertEqual(len(names), len(set(names)))

    def test_unknown_hash_does_not_gain_candidate_specific_gates(self):
        names = self.names(self.root/'absent.gb', '0'*64)
        self.assertEqual(len(names), 95)
        self.assertNotIn('playtest_secret_boss_handoff', names)
        self.assertNotIn('playtest_header_data_and_timing', names)

    def test_actual_rom_rejects_conflicting_hash(self):
        path = self.root/'candidate.gb'
        path.write_bytes(bytes(0x100000))
        with self.assertRaisesRegex(ValueError, 'candidate identity differs'):
            self.names(path, low.TITLE_RETRY_SHA)

    def test_actual_and_hash_only_generic_rosters_agree(self):
        path = self.root/'candidate.gb'
        rom = bytes(0x100000)
        path.write_bytes(rom)
        pin = hashlib.sha256(rom).hexdigest()
        self.assertEqual(self.names(path, pin), self.names(self.root/'absent.gb', pin))

    def test_preflight_rejects_roster_drift(self):
        path = self.root/'candidate.gb'
        path.write_bytes(bytes(0x100000))
        gate = matrix.Gate('one', (), 1)
        with patch.object(matrix, 'build_gates', side_effect=([gate], [])):
            with self.assertRaisesRegex(ValueError, 'inventories differ'):
                runner.check_gate_inventory(path, dict(expanded_ted=True, menu_icon_colors=True))

    def test_evidence_failure_marks_run_terminal_and_withholds_success(self):
        run = dict(status='matrix-running')
        path = self.root/'run.json'
        def fail():
            raise SystemExit('rejected evidence')
        with patch('builtins.print'):
            self.assertFalse(runner.check_source_evidence(run, path, 'matrix-evidence-failed', fail))
        result = json.loads(path.read_text())
        self.assertEqual(result['status'], 'matrix-evidence-failed')
        self.assertEqual(result['error'], 'rejected evidence')
        self.assertIn('finished_at', result)

    def test_success_does_not_emit_a_receipt_or_relabel_run(self):
        run = dict(status='matrix-running')
        path = self.root/'run.json'
        self.assertTrue(runner.check_source_evidence(run, path, 'failed', lambda: None))
        self.assertEqual(run, dict(status='matrix-running'))
        self.assertFalse(path.exists())


if __name__ == '__main__':
    unittest.main()
