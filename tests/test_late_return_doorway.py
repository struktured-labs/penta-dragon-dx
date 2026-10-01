"""#14 exact doorway occlusion and separate floor-priority control."""
import csv
import hashlib
import json
from pathlib import Path
import sys
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts/diagnostics'))
from verify_doorway_occlusion import verify
from build_sara_doorway_priority import helper


class LateReturnDoorway(unittest.TestCase):
    def test_exact_occlusion_and_known_broken_control(self):
        stock=ROOT/'tmp/ceiling-stock-doorway-03'
        current=ROOT/'tmp/late-return-doorway-01'
        result=verify(stock,current)
        self.assertEqual(result['candidate']['bindings']['candidate.gb'],
                         '46eb95a0c0f770fb3cf8c3211b8030a9e881f59077e558b93703ba08da71d3fb')
        self.assertTrue(result['passed'])
        self.assertEqual(result['candidate']['world'],(1240,1356))
        self.assertEqual(result['candidate']['nonblack'],0)
        self.assertEqual(result['candidate']['priority'],[True]*4)
        broken=verify(stock,ROOT/'tmp/ceiling-source07-negative-01')
        self.assertFalse(broken['passed'])
        self.assertEqual(broken['candidate']['nonblack'],192)
        # Keep the prior non-position-matched experiment rejected too.
        with self.assertRaisesRegex(ValueError,'position/scene'):
            verify(stock,ROOT/'tmp/return-fade16-doorway-01')

    def test_floor_priority_stays_clear_for_600_moving_frames(self):
        folder=ROOT/'tmp/late-return-floor-01'
        r=json.loads((folder/'receipt.json').read_text())
        self.assertEqual(r['status'],0)
        self.assertEqual(r['rom_sha256'],
                         '46eb95a0c0f770fb3cf8c3211b8030a9e881f59077e558b93703ba08da71d3fb')
        self.assertEqual(hashlib.sha256((folder/'candidate.gb').read_bytes()).hexdigest(),r['rom_sha256'])
        self.assertEqual(hashlib.sha256((folder/'probe.lua').read_bytes()).hexdigest(),r['probe_sha256'])
        with (folder/'priority.tsv').open() as f:
            rows=[r for r in csv.DictReader(f,delimiter='\t') if int(r['frame'])>1200]
        self.assertEqual([int(r['frame']) for r in rows],list(range(1201,1801)))
        expected=helper(combined=True).hex().upper()
        for row in rows:
            self.assertFalse(any(int(row[f'a{i}'],16)&128 for i in range(4)),row['frame'])
            self.assertTrue(row['helper'].startswith(expected),row['frame'])


if __name__=='__main__':unittest.main()
