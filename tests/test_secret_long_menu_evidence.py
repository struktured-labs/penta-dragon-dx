"""#26 retain a delivered long-menu trial without claiming recorded onset."""
import csv
import hashlib
import json
import mmap
from pathlib import Path
import unittest

ROOT=Path(__file__).resolve().parents[1]


class LongMenuEvidence(unittest.TestCase):
    def test_long_hold_closes_and_native_scrolling_resumes(self):
        folder=ROOT/'tmp/reported-secret-long-medical-01'
        if not folder.exists(): self.skipTest('Local long-menu evidence unavailable')
        receipt=json.loads((folder/'receipt.json').read_text())
        self.assertEqual(receipt['rom_sha256'],'4f5a67b8a9afb178ac0760daa2357de74fd7eb7f3de4de010385c50ea4cb08f5')
        self.assertEqual(receipt['source_state_sha256'],'755ecf5d49065b3216cb8dc45c7bb9b164bfb43d0a3a88eee258ed9939db23a4')
        self.assertFalse(receipt['observer_memory_writes'])
        self.assertEqual(receipt['native_capture']['restored_replay_epoch']['status'],'PASS')
        trace=folder/'trace.tsv'
        self.assertEqual(hashlib.sha256(trace.read_bytes()).hexdigest(),
                         'b0c1026025210ac8b5261f1015be38dd2aa772e82abf81d165619908d77a5791')
        with trace.open() as stream: rows=list(csv.DictReader(stream,delimiter='\t'))
        self.assertEqual(len(rows),4200)
        self.assertTrue(all((r['world_x'],r['world_y'],r['hp'])==('72','1176','255') for r in rows[:3960]))
        self.assertEqual(rows[-1]['world_y'],'936')
        capture=Path(receipt['native_capture_directory'])/'native.states'
        with capture.open('rb') as stream, mmap.mmap(stream.fileno(),0,access=mmap.ACCESS_READ) as states:
            self.assertEqual(len(states),4200*71680)
            window=[i+1 for i in range(4200) if states[i*71680+0x340]&32]
            self.assertEqual(window,list(range(1,3961)))
