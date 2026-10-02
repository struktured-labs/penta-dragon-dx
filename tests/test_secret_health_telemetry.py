"""#42 actual-state health telemetry regression, with retained broken control."""
import csv
import hashlib
import mmap
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'scripts/diagnostics'))
from verify_pickup_class_palettes import serialized_state


class HealthTelemetry(unittest.TestCase):
    def test_repository_probe_reports_every_native_health_sample(self):
        import json
        base = ROOT/'tmp/checked-secret-health-replay-03'
        if not (base/'receipt.json').exists(): self.skipTest('repository runner evidence unavailable')
        receipt = json.loads((base/'receipt.json').read_text())
        self.assertEqual(receipt['status'], 0)
        self.assertFalse(receipt['observer_memory_writes'])
        for field, path in (
            ('probe_sha256', ROOT/'scripts/diagnostics/probe_secret_entry.lua'),
            ('runner_sha256', ROOT/'scripts/diagnostics/run_secret_entry_probe.py'),
        ):
            self.assertEqual(receipt[field], hashlib.sha256(path.read_bytes()).hexdigest())
        with (base/'trace.tsv').open() as stream:
            rows = list(csv.DictReader(stream, delimiter='\t'))
        native = Path(receipt['native_capture_directory'])
        self.assertEqual(len(rows), 120)
        with (native/'native.states').open('rb') as stream, mmap.mmap(stream.fileno(),0,access=mmap.ACCESS_READ) as data:
            self.assertEqual(len(data), len(rows)*71680)
            for i,row in enumerate(rows):
                self.assertEqual(int(row['hp']), data[i*71680+0x60bb])
        control = Path('/mnt/data/tmp/penta-secret-alias-chunk-death-control-01-av')
        for ext in ('s16le','video','states','timeline.tsv'):
            self.assertEqual(hashlib.sha256((native/f'native.{ext}').read_bytes()).digest(),
                             hashlib.sha256((control/f'native.{ext}').read_bytes()).digest())

    def test_health_matches_saved_physical_dcbb_and_old_log_does_not(self):
        for name, fixed in (('secret-sound-alias-stock-health-log-01',True),
                            ('secret-sound-alias-stock-lowhealth-01',False)):
            base = ROOT/'tmp'/name
            if not (base/'receipt.json').exists(): self.skipTest('local replay unavailable')
            with (base/'trace.tsv').open() as stream:
                rows = {int(r['frame']): r for r in csv.DictReader(stream, delimiter='\t')}
            mismatches = 0
            paths = sorted(base.glob('frame-*.ss0'))
            self.assertEqual(len(paths),17)
            for path in paths:
                frame = int(path.stem.split('-')[1])
                state = serialized_state(path)
                mismatches += int(rows[frame]['hp']) != state[0x60bb]
            if fixed: self.assertEqual(mismatches,0)
            else: self.assertGreater(mismatches,0)

    def test_logging_fix_leaves_entire_replay_unchanged(self):
        for ext in ('s16le','video','states','timeline.tsv'):
            paths = [Path('/mnt/data/tmp')/f'penta-secret-sound-alias-stock-{name}-01-av'/f'native.{ext}'
                     for name in ('lowhealth','health-log')]
            if not all(p.exists() for p in paths): self.skipTest('local capture unavailable')
            self.assertEqual(*(hashlib.sha256(p.read_bytes()).digest() for p in paths))
