"""#61: final receipts require the exact candidate-specific gate inventory."""
import copy
import hashlib
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'scripts'), str(ROOT / 'scripts/diagnostics')]
import build_release_bundle as bundle
import playtest_successor_lineage as lineage
from verify_release_candidate import build_gates


class ReceiptInventoryTests(unittest.TestCase):
    def test_placeholder_includes_exact_candidate_gates(self):
        absent = ROOT / 'tmp/nonexistent-receipt-inventory-candidate.gb'
        self.assertFalse(absent.exists())
        def names(identity):
            return [g.name for g in build_gates(absent, ROOT / 'tmp/inventory-only',
                    expanded_candidate_override=True, menu_icon_candidate_override=True,
                    candidate_sha256=identity)]
        current = names(lineage.CANDIDATE_SHA)
        self.assertEqual(len(current), 97)
        self.assertEqual(current[3:5], ['playtest_header_data_and_timing',
                                      'playtest_secret_boss_handoff'])
        self.assertEqual([n for n in current if not n.startswith('playtest_')], names(None))
        self.assertEqual(names('0' * 64), names(None))

    def test_existing_rom_rejects_conflicting_inventory_identity(self):
        with tempfile.TemporaryDirectory(dir=ROOT / 'tmp') as directory:
            rom = Path(directory) / 'candidate.gb'
            rom.write_bytes(b'not the candidate')
            with self.assertRaisesRegex(ValueError, 'identity differs'):
                build_gates(rom, Path(directory), candidate_sha256=lineage.CANDIDATE_SHA)

    def test_bundle_uses_rom_identity_and_rejects_incomplete_or_reordered_gates(self):
        rom = b'unit-only ROM'
        sha = hashlib.sha256(rom).hexdigest()
        md5 = hashlib.md5(rom).hexdigest()
        absent = ROOT / 'tmp/nonexistent-receipt-inventory-candidate.gb'
        with patch.object(lineage, 'CANDIDATE_SHA', sha):
            names = [g.name for g in build_gates(absent, ROOT / 'tmp/inventory-only',
                     expanded_candidate_override=True, menu_icon_candidate_override=True,
                     candidate_sha256=sha)]
            manifest = dict(status='emulator-pass', scope='full', failures=0,
                rom_md5=md5, rom_size=len(rom), source_rom_md5_after=md5,
                tested_rom_md5_after=md5, rom_hashes_intact=True,
                source_inputs_intact=True, source_fingerprint='unit',
                source_fingerprint_after='unit', source_input_count=0,
                runtime_tools_intact=True, runtime_tools={'unit': True},
                runtime_tools_after={'unit': True}, selected_gates=names,
                results=[dict(name=n, status='passed', returncode=0) for n in names])
            def check(value):
                with patch.object(bundle, 'load_json', return_value=value), \
                     patch.object(bundle, 'source_snapshot', return_value=('unit', [])), \
                     patch.object(bundle, 'emulator_runtime_snapshot', return_value={'unit': True}), \
                     patch.object(bundle, 'runtime_snapshots_match', return_value=True):
                    return bundle.validate_emulator_manifest(absent, rom)
            self.assertIs(check(manifest), manifest)
            missing = copy.deepcopy(manifest)
            missing['results'].pop(3)
            with self.assertRaisesRegex(SystemExit, 'expected 97'):
                check(missing)
            reordered = copy.deepcopy(manifest)
            reordered['results'][3:5] = reversed(reordered['results'][3:5])
            reordered['selected_gates'] = [r['name'] for r in reordered['results']]
            with self.assertRaisesRegex(SystemExit, 'gate order'):
                check(reordered)
            failed = copy.deepcopy(manifest)
            failed['results'][3]['status'] = 'failed'
            with self.assertRaisesRegex(SystemExit, 'not all passed'):
                check(failed)
            extra = copy.deepcopy(manifest)
            extra['results'][3]['name'] = 'invented-pass'
            with self.assertRaisesRegex(SystemExit, 'gate set mismatch'):
                check(extra)


if __name__ == '__main__':
    unittest.main()
