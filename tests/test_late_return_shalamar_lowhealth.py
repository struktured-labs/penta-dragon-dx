"""#27/#45 one-HP-write fixture followed by controller-only menu replay."""
import copy
import hashlib
import json
from pathlib import Path
import sys
import unittest
import zlib

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'scripts/diagnostics'))
from check_boss_menu_fades import inspect_roundtrips, scene_observation, scene_route_failures
from verify_pickup_class_palettes import serialized_state


class ShalamarLowHealth(unittest.TestCase):
    def test_low_health_fixture_and_full_replay_bindings(self):
        entry = ROOT/'tmp/late-return-shalamar-lowhealth-entry-01'
        r = json.loads((entry/'receipt.json').read_text())
        self.assertEqual(r['status'], 0)
        self.assertTrue(r['observer_memory_writes'])
        self.assertEqual(r['diagnostic_environment']['ENTRY_ONCE_HP'], '109')
        state = serialized_state(entry/'frame-0001.ss0')
        self.assertEqual((state[0x60BB],state[0x5C80],state[0x3B7]), (109,12,12))
        folder = ROOT/'tmp/late-return-shalamar-lowhealth-menus-01'
        replay = json.loads((folder/'completion.json').read_text())
        self.assertEqual(replay['rom']['sha256'],
                         '46eb95a0c0f770fb3cf8c3211b8030a9e881f59077e558b93703ba08da71d3fb')
        self.assertEqual(replay['state']['sha256'],
                         hashlib.sha256((entry/'frame-0001.ss0').read_bytes()).hexdigest())
        for key in ('rom','state','probe','runner','native_tap'):
            self.assertEqual(hashlib.sha256(Path(replay[key]['path']).read_bytes()).hexdigest(),
                             replay[key]['sha256'])
        self.assertEqual(int.from_bytes(state[4:8], 'little'),
                         zlib.crc32(Path(replay['rom']['path']).read_bytes()))
        self.assertEqual(replay['native_capture']['restored_replay_epoch']['status'], 'PASS')
        self.assertEqual(replay['native_capture']['metadata']['frames'],1080)
        for name,digest in replay['native_capture']['hashes'].items():
            with (Path(replay['av_output'])/name).open('rb') as f:
                self.assertEqual(hashlib.file_digest(f,'sha256').hexdigest(),digest)

    def test_alias_palettes_three_cycles_and_negative_owner_control(self):
        folder = ROOT/'tmp/late-return-shalamar-lowhealth-menus-01'
        result = inspect_roundtrips(folder, 0x0C)
        self.assertEqual(result['status'],'PASS',result['failures'])
        self.assertEqual([c['status'] for c in result['cycles']],['PASS']*3)
        self.assertEqual(result['sound_alias_frames'],list(range(7,1081)))
        rows = [scene_observation(i, serialized_state(folder/f'frame-{i:04d}.ss0'))
                for i in range(1,1081)]
        self.assertEqual(scene_route_failures(rows,0x0C),[])
        # Canonical identity cannot excuse the original wrong-palette symptom.
        changed = copy.deepcopy(rows)
        changed[6]['shalamar_palette_valid'] = False
        failures = scene_route_failures(changed,0x0C)
        self.assertEqual(len(failures),1)
        self.assertEqual(failures[0]['frame'],7)


if __name__ == '__main__':
    unittest.main()
