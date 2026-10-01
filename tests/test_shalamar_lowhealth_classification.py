"""#27 reproducer: a native sound alias must not select dungeon palettes.

These assertions retain observed broken evidence, not a fixed-game verdict.
"""
from pathlib import Path
import sys
import unittest
import zlib
import hashlib
import json

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts/diagnostics'))
from verify_pickup_class_palettes import serialized_state


class ShalamarLowHealth(unittest.TestCase):
    def test_current_candidate_retains_boss_palette_during_sound_alias(self):
        folder=ROOT/'tmp/return-fade16-shalamar-phase721-01'
        parent=ROOT/'tmp/current-map-shalamar-phase721-01'
        if not (folder/'completion.json').exists():
            self.skipTest('current Shalamar replay unavailable')
        launch=json.loads((folder/'completion.json').read_text())
        rom=Path(launch['rom']['path']).read_bytes()
        self.assertEqual(hashlib.sha256(rom).hexdigest(),
                         '126dd0b7fff1e03eb6b224f818b85398593c7109ffb676cc538c1bd90742304b')
        self.assertEqual(hashlib.sha256(Path(launch['state']['path']).read_bytes()).hexdigest(),
                         launch['state']['sha256'])
        from check_boss_menu_fades import inspect_roundtrips
        result=inspect_roundtrips(folder,12,721)
        # #47 fixes the demonstrated native-alias false positive without
        # rewriting the historical failed receipt or ignoring graphics policy.
        historical=json.loads((folder/'verification.json').read_text())
        self.assertEqual(historical['status'],'FAIL')
        self.assertEqual(result['status'],'PASS')
        self.assertEqual([c['status'] for c in result['cycles']],['PASS']*3)
        self.assertEqual(result['scene_route_failures'],[])
        self.assertEqual(result['sound_alias_frames'],list(range(952,1081)))
        expected=bytes([0,0]+[4]*253+[0])
        for frame in range(1,1081):
            name=f'frame-{frame:04d}'
            state=serialized_state(folder/(name+'.ss0'))
            self.assertEqual(int.from_bytes(state[4:8],'little'),zlib.crc32(rom)&0xffffffff)
            self.assertEqual((folder/(name+'.png')).read_bytes(),(parent/(name+'.png')).read_bytes())
            if frame>=952:
                self.assertEqual((state[0x5c80],state[0x3b7]),(11,12))
                self.assertEqual(state[0x4a00:0x4b00],expected)
        self.assertNotEqual(expected,rom[0x37000:0x37100])

    def test_retained_scene_alias_installs_wrong_table(self):
        folder=ROOT/'tmp/star-shalamar-native-inventory-phase721-01'
        if not (folder/'frame-0999.ss0').exists():
            self.skipTest('local transition evidence unavailable')
        rom=(ROOT/'tmp/stream-presentation-source-01/candidate.gb').read_bytes()
        # Shalamar's authored uniform BG4 policy: blank IDs00/01/FF stay BG0.
        expected=bytes([0,0]+[4]*253+[0])
        snapshots=[serialized_state(folder/f'frame-{f:04d}.ss0') for f in (997,998,999)]
        for raw in snapshots:
            self.assertEqual(int.from_bytes(raw[4:8],'little'),zlib.crc32(rom)&0xffffffff)
            self.assertEqual(raw[0x3b7],12)
            self.assertEqual(raw[0x3e4],0)
        self.assertEqual([r[0x5c80] for r in snapshots],[12,11,11])
        self.assertEqual(snapshots[0][0x4a00:0x4b00],expected)
        self.assertEqual(snapshots[1][0x4a00:0x4b00],expected)
        self.assertNotEqual(snapshots[2][0x4a00:0x4b00],expected)
        self.assertEqual(snapshots[2][0x4a00:0x4b00],rom[0x37000:0x37100])


if __name__=='__main__': unittest.main()
