"""#45 bounded placement observation; not an all-game allocation proof."""
import csv
import hashlib
import json
from pathlib import Path
import unittest
import importlib.util

ROOT = Path(__file__).resolve().parents[1]


class AllocationObservation(unittest.TestCase):
    def test_demo_trampoline_is_occupied_not_a_relocation_cave(self):
        # A historical constant comment says "retired attract-delay service";
        # the exact candidate instead has a live dirty-publication service.
        parent = (ROOT/'tmp/initial-map-fastpath-trial-01/candidate.gb').read_bytes()
        self.assertEqual(hashlib.sha256(parent).hexdigest(),
                         'ec8be28897810fac01a8918a0403900780015bf6703531f0f82ae259f209f21b')
        self.assertEqual(parent[0x10E7:0x10EE], bytes.fromhex('3E01B70605C900'))
        self.assertEqual(parent[0x3494:0x3497], bytes.fromhex('C3E710'))
        # The caller tests DCFD and branches to this JP when it is zero.
        # Preserve the actual source predicate, not merely a byte-shaped call.
        self.assertEqual(parent[0x3489:0x3497],
                         bytes.fromhex('FAFDDCB72805F0BD47DFC9C3E710'))

    def test_repeating_cpu_read_control(self):
        builder = ROOT/'scripts/diagnostics/build_fixed_fade_read_control.py'
        spec = importlib.util.spec_from_file_location('read_control', builder)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        parent = (ROOT/'tmp/initial-map-fastpath-trial-01/candidate.gb').read_bytes()
        rom = module.build(parent, repeat=True)
        self.assertEqual(hashlib.sha256(rom).hexdigest(),
                         '2ab49f3d4638756f2d155148b6c518a67b59af2b48491068c48479bf5335691c')
        self.assertEqual(rom[0xCF:0xE1], parent[0xCF:0xE1])
        self.assertEqual(rom[0x100:0x104], parent[0x100:0x104])
        self.assertEqual(rom[0x150:0x155], bytes.fromhex('FACF0018FB'))
        self.assertTrue(all(a == b or i in {0x14E, 0x14F, *range(0x150, 0x155)}
                            for i, (a, b) in enumerate(zip(parent, rom))))
        with self.assertRaises(ValueError):
            module.build(bytes([parent[0] ^ 1]) + parent[1:], repeat=True)
        folder = ROOT/'tmp/fixed-fade-read-loop-positive-01'
        receipt = json.loads((folder/'receipt.json').read_text())
        self.assertEqual(receipt['status'], 0)
        self.assertEqual((folder/'candidate.gb').read_bytes(), rom)
        self.assertEqual(receipt['rom_sha256'], hashlib.sha256(rom).hexdigest())
        self.assertFalse(receipt['observer_memory_writes'])
        for field, source in (
            ('probe_sha256', ROOT/'scripts/diagnostics/probe_secret_entry.lua'),
            ('runner_sha256', ROOT/'scripts/diagnostics/run_secret_entry_probe.py'),
            ('guard_sha256', ROOT/'scripts/mgba-qt-singleflight'),
        ):
            self.assertEqual(receipt[field], hashlib.sha256(source.read_bytes()).hexdigest())
        with (folder/'fixed-fade-allocation.tsv').open() as f:
            rows = list(csv.DictReader(f, delimiter='\t'))
        self.assertEqual(len(rows), 4452)
        self.assertTrue(all((r['kind'], r['address'], r['pc']) ==
                            ('read', '00CF', '0153') for r in rows))
        cycles = [int(r['cycle']) for r in rows]
        self.assertTrue(all(b - a == 56 for a, b in zip(cycles, cycles[1:])))
        # Earlier one-shot controls are retained as inconclusive, not negatives.
        for name in ('fixed-fade-read-positive-01', 'fixed-fade-read-positive-02'):
            with (ROOT/'tmp'/name/'fixed-fade-allocation.tsv').open() as f:
                self.assertEqual(list(csv.DictReader(f, delimiter='\t')), [])

    def test_parent_no_observed_access_and_execution_positive_control(self):
        for name in ('fixed-fade-allocation-on-01',
                     'fixed-fade-allocation-return-on-01'):
            folder = ROOT/'tmp'/name
            receipt = json.loads((folder/'receipt.json').read_text())
            self.assertEqual(receipt['status'], 0)
            self.assertEqual(receipt['rom_sha256'],
                             'ec8be28897810fac01a8918a0403900780015bf6703531f0f82ae259f209f21b')
            with (folder/'fixed-fade-allocation.tsv').open() as f:
                self.assertEqual(list(csv.DictReader(f, delimiter='\t')), [])
        folder = ROOT/'tmp/fixed-fade-allocation-positive-01'
        receipt = json.loads((folder/'receipt.json').read_text())
        self.assertEqual(receipt['status'], 0)
        self.assertEqual(receipt['rom_sha256'],
                         '46eb95a0c0f770fb3cf8c3211b8030a9e881f59077e558b93703ba08da71d3fb')
        with (folder/'fixed-fade-allocation.tsv').open() as f:
            rows = list(csv.DictReader(f, delimiter='\t'))
        self.assertEqual([r['address'] for r in rows],
                         ['00CF','00D1','00D2','00D5','00D8','00DA','00DB','00DE'])
        self.assertTrue(all(r['kind']=='execute' for r in rows))
        # Positive control covers instruction entry, not data-read detection.

    def test_return_observer_full_primary_neutrality(self):
        receipts = []
        for side in ('on','off'):
            folder = ROOT/'tmp'/f'fixed-fade-allocation-return-{side}-01'
            r = json.loads((folder/'receipt.json').read_text())
            self.assertEqual(r['status'], 0)
            self.assertEqual(r['native_capture']['metadata']['frames'], 6000)
            self.assertEqual(r['native_capture']['restored_replay_epoch']['status'], 'PASS')
            for name, digest in r['native_capture']['hashes'].items():
                with (Path(r['native_capture_directory'])/name).open('rb') as f:
                    self.assertEqual(hashlib.file_digest(f,'sha256').hexdigest(), digest)
            receipts.append(r)
        for key in ('rom_sha256','source_state_sha256','probe_sha256',
                    'runner_sha256','guard_sha256','native_tap_sha256','audio_options'):
            self.assertEqual(receipts[0][key], receipts[1][key])
        self.assertEqual(receipts[0]['native_capture']['hashes'],
                         receipts[1]['native_capture']['hashes'])


if __name__ == '__main__':
    unittest.main()
