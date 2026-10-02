"""#27: native spawn evidence is not a workload-matched speed qualification."""
import csv
import hashlib
import json
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
CASES = (
    ('arena-stage1-spawn-trace-01', 'arena-completion-safe-trial-01',
     'd901357a105036469b8debbff138fb63e87afb3a0cfbe5a24eeaafa91353910a', 9, 2),
    ('arena-parent-stage1-spawn-trace-01', 'stream-presentation-source-01',
     'd744124d3d161247e0584bb39e8db1243ade4e428cbc15f82a85c10d0a4ac4d5', 4, 0),
)


def matches_captured_selection(rom, row):
    """Consistency only: an intervening timer tick could change the sampled index."""
    index = int(row['rng_index'])
    choices = [int(row[f'choice{i}']) for i in range(5)]
    return (0 <= index < 100 and
            int(row['a']) == choices[rom[0xD85 + index] % 5])


class NativeSpawnEvidence(unittest.TestCase):
    def test_both_replays_and_mutated_type_negative_control(self):
        for run, build, digest, count, count_2a in CASES:
            with self.subTest(run=run):
                base = ROOT / 'tmp' / run
                rom_path = ROOT / 'tmp' / build / 'candidate.gb'
                if not (base / 'manifest.json').exists() or not rom_path.exists():
                    self.skipTest('local ROM-bound spawn evidence unavailable')
                rom = rom_path.read_bytes()
                self.assertEqual(hashlib.sha256(rom).hexdigest(), digest)
                manifest = json.loads((base / 'manifest.json').read_text())
                self.assertEqual(manifest['status'], 'fail')
                self.assertTrue(manifest['rows'][0]['deterministic_replay'])
                # Actual timer vector/call and selector, not an inference from docs.
                self.assertEqual(rom[0x50:0x53], bytes.fromhex('c3b306'))
                self.assertEqual(rom[0x6C4:0x6C7], bytes.fromhex('cd790d'))
                self.assertEqual(rom[0xD79:0xD85],
                                 bytes.fromhex('f0d13cfe6438023e00e0d1c9'))
                for replay in ('a', 'b'):
                    path = base / f'stage1-dx-{replay}-loop-patrol/result.json.copies.tsv'
                    with path.open() as stream:
                        rows = [r for r in csv.DictReader(stream, delimiter='\t')
                                if r['event'] == 'native-spawn']
                    self.assertEqual(len(rows), count)
                    self.assertEqual(sum(int(r['a']) == 42 for r in rows), count_2a)
                    self.assertEqual(rows[0]['phase'], 'loading')
                    for row in rows:
                        self.assertTrue(matches_captured_selection(rom, row))
                        mutated = dict(row, a=str(int(row['a']) ^ 1))
                        self.assertFalse(matches_captured_selection(rom, mutated))


if __name__ == '__main__':
    unittest.main()
