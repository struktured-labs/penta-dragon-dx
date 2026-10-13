"""#14: adaptive (condition-driven Down hold) doorway oracle evidence checks."""
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts/diagnostics'))
from verify_doorway_occlusion import verify  # noqa: E402

R = ROOT / 'tmp/o14'


def need(*names):
    missing = [n for n in names if not (R / n).is_dir()]
    if missing:
        raise unittest.SkipTest('local adaptive captures unavailable: ' + ', '.join(missing))


class AdaptiveDoorwayOracle(unittest.TestCase):
    def test_late_entry_build_passes_with_condition_driven_input(self):
        need('door-stock', 'door-3d581fc8', 'door-ffc29f4e')
        for build in ('3d581fc8', 'ffc29f4e'):
            result = verify(R / 'door-stock', R / f'door-{build}')
            self.assertTrue(result['passed'], build)
            self.assertEqual(result['candidate']['world'], (1240, 1356))
            self.assertEqual(result['stock']['capture']['capture_frame'], 1216)

    def test_priority_clear_build_still_fails(self):
        need('door-stock', 'door-792319cb')
        result = verify(R / 'door-stock', R / 'door-792319cb')
        self.assertFalse(result['passed'])
        self.assertFalse(any(result['candidate']['priority']))
        self.assertGreater(result['candidate']['nonblack'], 0)

    def test_frame_caps_fail_loudly(self):
        need('door-stock', 'door-holdcap2', 'door-camcap')
        for name in ('door-holdcap2', 'door-camcap'):
            with self.assertRaisesRegex(ValueError, 'adaptive capture failed'):
                verify(R / 'door-stock', R / name)

    def test_every_input_recorded(self):
        need('door-3d581fc8')
        rows = (R / 'door-3d581fc8/doorway-inputs.tsv').read_text().splitlines()[1:]
        meta = json.loads((R / 'door-3d581fc8/doorway-capture.json').read_text())
        frames = [int(r.split('\t')[0]) for r in rows]
        self.assertEqual(frames, list(range(1, frames[-1] + 1)))
        held = [int(r.split('\t')[0]) for r in rows if r.split('\t')[4] != '00' and int(r.split('\t')[0]) > 1200]
        self.assertEqual(held, list(range(1201, meta['hold_released_frame'])))


if __name__ == '__main__':
    unittest.main()
