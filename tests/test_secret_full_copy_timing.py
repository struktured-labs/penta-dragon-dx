"""#26 full copier boundaries and observer neutrality, not speed parity."""
import csv
import hashlib
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]


def calls(path):
    with path.open() as stream:
        rows = list(csv.DictReader(stream, delimiter='\t'))
    pending = None
    result = []
    entries = 0
    for row in rows:
        if row['event'] == 'entry_observed':
            entries += 1
        elif row['event'] == 'begin':
            if pending is not None:
                raise ValueError('nested entry')
            pending = row
        elif row['event'] == 'end':
            if pending is None or row['return_pc'] != pending['return_pc']:
                raise ValueError('unmatched return')
            if int(row['sp'], 16) != (int(pending['sp'], 16) + 2) & 65535:
                raise ValueError('return stack mismatch')
            result.append((pending, row, int(row['cycle']) - int(pending['cycle'])))
            pending = None
        else:
            raise ValueError('unknown event')
    if not result or entries != len(result) + (pending is not None):
        raise ValueError('missing measured calls')
    return result, pending


class FullCopyTiming(unittest.TestCase):
    def test_complete_boundaries_and_neutrality(self):
        for name, control, count, first_low in (
            ('secret-stock-full-copy-02', 'secret-stock-startup-gated-off-01', 134, 144944),
            ('secret-fast-full-copy-02', 'secret-fast-gated-audio-01', 130, 150608)):
            trace = ROOT / 'tmp' / name / 'full-copy-timing.tsv'
            if not trace.exists(): self.skipTest('local timing evidence unavailable')
            with self.subTest(name=name):
                measured, pending = calls(trace)
                self.assertEqual(len(measured), count)
                self.assertIsNone(pending)
                self.assertEqual(next(c[2] for c in measured if c[0]['scene'] == '0B'), first_low)
                for suffix in ('s16le', 'video', 'states', 'timeline.tsv', 'wav'):
                    hashes = []
                    for run in (name, control):
                        path = Path('/mnt/data/tmp') / f'penta-{run}-av' / f'native.{suffix}'
                        with path.open('rb') as stream:
                            hashes.append(hashlib.file_digest(stream, 'sha256').hexdigest())
                    self.assertEqual(*hashes)

    def test_rejected_empty_first_attempt(self):
        path = ROOT / 'tmp/secret-stock-full-copy-01/full-copy-timing.tsv'
        if not path.exists(): self.skipTest('retained failed trace unavailable')
        with self.assertRaisesRegex(ValueError, 'missing measured calls'):
            calls(path)


if __name__ == '__main__':
    unittest.main()
