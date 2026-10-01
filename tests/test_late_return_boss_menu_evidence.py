"""#27/#36/#45 bounded repeated-menu acceptance, not whole-game readiness."""
import hashlib
import json
from pathlib import Path
import sys
import unittest
import zlib

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'scripts/diagnostics'))
from check_boss_menu_fades import inspect_roundtrips
from verify_pickup_class_palettes import serialized_state


class LateReturnBossMenus(unittest.TestCase):
    def test_both_bosses_three_standard_timing_roundtrips(self):
        for boss, scene in (('ted', 0x10), ('shalamar', 0x0C)):
            with self.subTest(boss=boss):
                folder = ROOT/'tmp'/f'late-return-{boss}-menus-01'
                r = json.loads((folder/'completion.json').read_text())
                self.assertEqual(r['rom']['sha256'],
                                 '46eb95a0c0f770fb3cf8c3211b8030a9e881f59077e558b93703ba08da71d3fb')
                for key in ('rom','state','probe','runner','native_tap'):
                    p = Path(r[key]['path'])
                    self.assertEqual(hashlib.sha256(p.read_bytes()).hexdigest(),r[key]['sha256'])
                state = serialized_state(Path(r['state']['path']))
                self.assertEqual(int.from_bytes(state[4:8],'little'),
                                 zlib.crc32(Path(r['rom']['path']).read_bytes()))
                self.assertEqual(r['select_presses'], [120,240,420,540,720,840])
                self.assertEqual(r['held_frames'], 6)
                self.assertEqual(r['third_entry_hold'], 6)
                self.assertTrue(r['completed'])
                self.assertEqual(r['native_capture']['restored_replay_epoch']['status'], 'PASS')
                self.assertEqual(r['native_capture']['metadata']['frames'], 1080)
                for name, digest in r['native_capture']['hashes'].items():
                    with (Path(r['av_output'])/name).open('rb') as f:
                        self.assertEqual(hashlib.file_digest(f,'sha256').hexdigest(),digest)
                result = inspect_roundtrips(folder, scene)
                self.assertEqual(result['status'], 'PASS', result['failures'])
                self.assertEqual([c['status'] for c in result['cycles']], ['PASS']*3)

    def test_retained_broken_ted_is_still_rejected(self):
        result = inspect_roundtrips(ROOT/'tmp/ted-menu-broken-roundtrips-gated-01', 0x10)
        self.assertEqual(result['status'], 'FAIL')


if __name__ == '__main__':
    unittest.main()
