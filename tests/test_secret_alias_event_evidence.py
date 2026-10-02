"""#26 validate observer neutrality and retain timing/route differences."""
import csv
import hashlib
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]


class EventEvidence(unittest.TestCase):
    def test_complete_capture_observer_neutrality(self):
        for name in ('secret-sound-alias-parent', 'secret-sound-alias-fast'):
            for ext in ('s16le', 'video', 'states', 'timeline.tsv'):
                paths = [Path('/mnt/data/tmp')/f'penta-{name}-{suffix}-01-av'/f'native.{ext}'
                         for suffix in ('audio','events')]
                if not all(p.exists() for p in paths): self.skipTest('local AV evidence unavailable')
                self.assertEqual(*(hashlib.sha256(p.read_bytes()).digest() for p in paths))

    def test_command_timing_and_unpaired_tail_remain_visible(self):
        sequences = []
        for name in ('secret-sound-alias-parent', 'secret-sound-alias-fast'):
            path = ROOT/'tmp'/f'{name}-events-01'/'sound-commands.tsv'
            if not path.exists(): self.skipTest('local trace unavailable')
            with path.open() as stream:
                sequences.append(list(csv.DictReader(stream, delimiter='\t')))
        parent, candidate = sequences
        self.assertEqual([len(s) for s in sequences], [20,27])
        self.assertEqual(parent[:3], candidate[:3])
        self.assertEqual((parent[3]['frame'], candidate[3]['frame']), ('74','73'))
        for a,b in zip(parent, candidate):
            self.assertEqual((a['event'],a['command'],a['caller']),
                             (b['event'],b['command'],b['caller']))
        # Matching zipped events is NOT full route equality: seven remain unpaired.
        self.assertEqual(len(candidate[len(parent):]), 7)


if __name__ == '__main__': unittest.main()
