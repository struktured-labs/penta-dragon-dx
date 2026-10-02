"""#45: retain the first divergent wait and exact observer-neutrality evidence."""
import csv
import hashlib
import json
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]


class ReturnWaitCounterEvidence(unittest.TestCase):
    def test_native_chain_still_loses_third_wait_before_custom_fade(self):
        receipt = self.receipt('return-chain-wait-trace-01')
        self.assertEqual(receipt['rom_sha256'],
                         '62ed16109187ea84b7cade8e2c36fcb128d4ffa020cf49ce750f720d605117b3')
        path = ROOT/'tmp/return-chain-wait-trace-01/return-loader-timing.tsv'
        with path.open() as f:
            rows = list(csv.DictReader(f, delimiter='\t'))
        waits = {}
        for row in rows:
            if row['pc']=='4068' and row['sp']=='DFE5' and 56<=int(row['frame'])<=190:
                waits.setdefault(int(row['b'],16),row)
        self.assertEqual(list(waits),list(range(100,0,-1)))
        self.assertEqual([waits[b]['frame'] for b in (100,99,98,97)],
                         ['56','57','58','60'])
        self.assertEqual(waits[100]['cycle'],'1137428776')
        self.assertEqual(next(r for r in rows if r['pc']=='5C22')['frame'],'190')

    def test_poll_phase_preserves_pre_interrupt_status(self):
        traces = []
        for variant in ('control', 'trial'):
            on = self.receipt(f'return-poll-phase-{variant}-01')
            off = self.receipt(f'return-wait-counter-{variant}-off-01')
            for key in ('rom_sha256', 'source_state_sha256', 'runner_sha256',
                        'guard_sha256', 'native_tap_sha256', 'audio_options'):
                self.assertEqual(on[key], off[key])
            self.assertEqual(on['native_capture']['hashes'], off['native_capture']['hashes'])
            for receipt in (on, off):
                for name, digest in receipt['native_capture']['hashes'].items():
                    with (Path(receipt['native_capture_directory']) / name).open('rb') as f:
                        self.assertEqual(hashlib.file_digest(f, 'sha256').hexdigest(), digest)
            path = ROOT / 'tmp' / f'return-poll-phase-{variant}-01' / 'return-poll-phase.tsv'
            with path.open() as f:
                traces.append(list(csv.DictReader(f, delimiter='\t')))
        control, trial = traces
        c_irq = next(r for r in control if r['pc'] == '0040')
        t_irq = next(r for r in trial if r['pc'] == '0040')
        self.assertEqual((c_irq['stack'], c_irq['af']), ('4088', 'C160'))
        self.assertEqual((t_irq['stack'], t_irq['af']), ('63FA', 'FF60'))
        # Control returns from the mode wait using its previously read mode1;
        # trial branches back to poll while the live STAT is already mode0/2.
        self.assertTrue(any(r['pc'] == '408D' and r['bc'] == '620C' for r in control))
        self.assertFalse(any(r['pc'] == '63FC' for r in trial))
        self.assertTrue(any(r['pc'] == '63F5' and int(r['cycle']) > 1137860072 for r in trial))

    def receipt(self, name):
        path = ROOT / 'tmp' / name / 'receipt.json'
        if not path.exists():
            self.skipTest('local diagnostic capture unavailable')
        return json.loads(path.read_text())

    def test_observers_do_not_change_primary_capture(self):
        for variant in ('control', 'trial'):
            on = self.receipt(f'return-wait-counter-{variant}-01')
            off = self.receipt(f'return-wait-counter-{variant}-off-01')
            for key in ('rom_sha256', 'source_state_sha256', 'runner_sha256',
                        'guard_sha256', 'native_tap_sha256', 'audio_options'):
                self.assertEqual(on[key], off[key])
            for receipt in (on, off):
                self.assertEqual(receipt['status'], 0)
                capture = receipt['native_capture']
                self.assertEqual(capture['metadata']['frames'], 240)
                self.assertEqual(capture['restored_replay_epoch']['status'], 'PASS')
                for name, digest in capture['hashes'].items():
                    with (Path(receipt['native_capture_directory']) / name).open('rb') as f:
                        self.assertEqual(hashlib.file_digest(f, 'sha256').hexdigest(), digest)
            self.assertEqual(on['native_capture']['hashes'], off['native_capture']['hashes'])

    def test_third_wait_is_first_large_divergence_not_extra_iterations(self):
        loops = []
        for variant, pc in (('control', '4068'), ('trial', '63E6')):
            self.receipt(f'return-wait-counter-{variant}-01')
            path = ROOT / 'tmp' / f'return-wait-counter-{variant}-01' / 'return-loader-timing.tsv'
            with path.open() as f:
                rows = list(csv.DictReader(f, delimiter='\t'))
            unique = {}
            for row in rows:
                if row['pc'] == pc and row['sp'] == 'DFE7' and 56 <= int(row['frame']) <= 190:
                    unique.setdefault(int(row['b'], 16), row)
            self.assertEqual(list(unique), list(range(100, 0, -1)))
            loops.append(unique)
        control, trial = loops
        deltas = [int(trial[b]['cycle']) - int(control[b]['cycle']) for b in (100, 99, 98, 97)]
        self.assertEqual(deltas, [32, 32, -40, 129968])
        self.assertEqual((control[97]['frame'], trial[97]['frame']), ('59', '60'))


if __name__ == '__main__':
    unittest.main()
