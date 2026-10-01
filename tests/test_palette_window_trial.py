"""Issue #24: retain the failing restart control and bounded patch contract."""
import sys
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'scripts/diagnostics'))
import build_palette_window_trial as trial
from restart_terrain import compare_terrain


class PaletteWindowTests(unittest.TestCase):
    def test_unknown_parent_rejected(self):
        with self.assertRaisesRegex(ValueError, 'exact combined'):
            trial.build(bytes(0x100000))

    def test_ly_window_rejects_last_lines_and_ly_zero(self):
        self.assertIn(bytes.fromhex('F044 FE90'), trial.router())
        self.assertIn(bytes.fromhex('FE98'), trial.router())
        self.assertTrue(trial.router().endswith(bytes.fromhex('7AE5 21E371 E5 C36100')))

    def test_retained_replay_rejects_parent_and_accepts_trial(self):
        paths = [ROOT/'tmp'/name for name in (
            'stream-presentation-combined-hazard-gameover-01',
            'stream-palette-window-hazard-01')]
        if not all((p/'stage-after-2.ss0').exists() for p in paths):
            self.skipTest('local retained emulator corpus unavailable')
        with self.assertRaisesRegex(ValueError, 'terrain/colour/priority changed'):
            compare_terrain(paths[0]/'stage-before.ss0', paths[0]/'stage-after-2.ss0')
        for cycle in (1, 2):
            compare_terrain(paths[1]/'stage-before.ss0', paths[1]/f'stage-after-{cycle}.ss0')

    def test_exact_rebuild_changes_only_router_and_checksum(self):
        path = ROOT/'tmp/stream-presentation-combined-01/candidate.gb'
        if not path.exists():
            self.skipTest('local pinned parent unavailable')
        parent = path.read_bytes()
        result = trial.build(parent)
        allowed = {0x14E, 0x14F} | set(range(trial.OFFSET, trial.OFFSET+len(trial.router())))
        self.assertTrue(all(a == b or i in allowed for i,(a,b) in enumerate(zip(parent,result))))
        self.assertEqual(len(parent), len(result))


if __name__ == '__main__':
    unittest.main()
