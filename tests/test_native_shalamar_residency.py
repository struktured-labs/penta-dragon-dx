"""#47 native counterexample to raw-scene-only arena residency."""
import csv
import hashlib
import json
from pathlib import Path
import sys
import unittest
import zlib

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts/diagnostics'))
from verify_pickup_class_palettes import serialized_state
from check_boss_menu_fades import scene_route_failures


class NativeShalamarResidency(unittest.TestCase):
    def test_native_damage_produces_sound_alias_without_canonical_exit(self):
        folder=ROOT/'tmp/shalamar-native-lowhealth-01'
        if not (folder/'receipt.json').exists(): self.skipTest('local native replay unavailable')
        receipt=json.loads((folder/'receipt.json').read_text())
        self.assertEqual(receipt['status'],0)
        self.assertFalse(receipt['observer_memory_writes'])
        self.assertEqual(receipt['keys'],'0')
        rom=(folder/'candidate.gb').read_bytes()
        self.assertEqual(hashlib.sha256(rom).hexdigest(),
                         '2f32570cff62b8664bfa06b939988c3fd6a7efabf870a990a5fa65bab37eac30')
        trace=folder/'trace.tsv'
        self.assertEqual(hashlib.sha256(trace.read_bytes()).hexdigest(),
                         '85c52b570ab6e7c16157f9f8df8a8f6e0fdd491e9a12fcae98036e9dd35b02a8')
        with trace.open() as f: rows=list(csv.DictReader(f,delimiter='\t'))
        self.assertEqual(len(rows),6000)
        self.assertEqual([r['scene'] for r in rows],['0C']*1536+['0B']*4464)
        self.assertEqual(rows[1536]['hp'],'109')
        observations=[]
        for path in sorted(folder.glob('frame-*.ss0')):
            state=serialized_state(path)
            self.assertEqual(int.from_bytes(state[4:8],'little'),zlib.crc32(rom)&0xffffffff)
            self.assertEqual(state[0x3b7],12)
            observations.append(dict(frame=int(path.stem.split('-')[1]),scene=state[0x5c80]))
        self.assertEqual(len(observations),51)
        # Record the current false rejection; no checker relaxation in this test.
        self.assertEqual(len(scene_route_failures(observations,12)),38)


if __name__=='__main__': unittest.main()
