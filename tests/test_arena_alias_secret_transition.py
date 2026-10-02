"""#26/#27 transition coverage and a retained cache-freshness counterexample.

These assertions explicitly do not qualify using DF0D as universal identity.
"""
import csv
import hashlib
import json
from pathlib import Path
import sys
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts/diagnostics'))
from verify_pickup_class_palettes import serialized_state
from check_secret_pickup_attributes import inspect_planes


class SecretTransition(unittest.TestCase):
    def folder(self):
        path=ROOT/'tmp/arena-alias-late-pause-return-01'
        if not (path/'receipt.json').exists():self.skipTest('local route unavailable')
        return path

    def test_pause_timer_crosses_return(self):
        path=self.folder()
        receipt=json.loads((path/'receipt.json').read_text())
        self.assertEqual(receipt['status'],0)
        self.assertTrue(receipt['observer_memory_writes'])  # assistance not hidden
        self.assertEqual(receipt['rom_sha256'],'585f5830daa32e59c000f5ddd6b57aab545e55375b46574286702db9fc28e4db')
        self.assertEqual(hashlib.sha256((path/'candidate.gb').read_bytes()).hexdigest(),receipt['rom_sha256'])
        with (path/'trace.tsv').open() as f:rows=list(csv.DictReader(f,delimiter='\t'))
        with (path/'item-action.tsv').open() as f:items=list(csv.DictReader(f,delimiter='\t'))
        self.assertEqual(len(rows),12000)
        self.assertEqual(len(items),12000)
        returned=next(r for r in rows[7500:] if (r['scene'],r['stage'])==('02','00'))
        self.assertEqual(returned['frame'],'8436')
        self.assertEqual(items[8435]['pause_timer'],'44')
        self.assertEqual(items[-1]['pause_timer'],'0')

    def test_cache_is_not_universal_scene_identity(self):
        path=self.folder()
        rom=(path/'candidate.gb').read_bytes()
        for frame,scene in ((7080,9),(7440,9),(9000,2)):
            raw=serialized_state(path/f'frame-{frame:04d}.ss0')
            self.assertEqual(raw[0x5c80],scene)
            self.assertEqual(raw[0x3b7],scene)
            self.assertEqual(raw[0x630d],10)
            self.assertNotEqual(raw[0x630d],raw[0x5c80])
            if scene==9:
                self.assertEqual(inspect_planes(raw,rom)['mismatches'],[])
        # Correct sampled palette policy does not erase the stale-owner finding.


if __name__=='__main__':unittest.main()
