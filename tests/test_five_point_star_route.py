"""Retained emulator integration evidence for #22; skips absent scratch corpus."""
import json
from pathlib import Path
import sys
import unittest
from PIL import Image, ImageChops

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'scripts/diagnostics'))
from verify_pickup_class_palettes import serialized_state
from verify_five_point_star_pair import inspect


class StarRoute(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not (ROOT/'tmp/five-point-star-parent-menu-return-01/frame-0180.ss0').exists():
            raise unittest.SkipTest('retained exact-ROM star route unavailable')

    def test_rendered_gold_and_broken_control(self):
        parent = ROOT/'tmp/five-point-star-live-01'
        trial = ROOT/'tmp/five-point-star-fixed-live-01'
        self.assertEqual(inspect(parent, trial)['status'], 'PASS')
        broken = inspect(parent, parent)
        self.assertEqual(broken['status'], 'FAIL')
        self.assertFalse(broken['checks']['star_center_gold'])

    def test_collection_menu_and_return_match(self):
        for stage in ('collect-01', 'menu-02', 'menu-return-01'):
            parent = ROOT/('tmp/five-point-star-parent-'+stage)
            trial = ROOT/('tmp/five-point-star-'+stage)
            with self.subTest(stage=stage):
                for folder in (parent, trial):
                    receipt = json.loads((folder/'receipt.json').read_text())
                    self.assertEqual(receipt['status'], 0)
                    self.assertFalse(receipt['observer_memory_writes'])
                    self.assertEqual(receipt['state_change'], 'none; exact ROM CRC/header checked')
                self.assertEqual((parent/'trace.tsv').read_bytes(), (trial/'trace.tsv').read_bytes())
                states = sorted(trial.glob('frame-*.ss0'))
                self.assertGreaterEqual(len(states), 4)
                for state in states:
                    a = serialized_state(parent/state.name)
                    b = serialized_state(state)
                    self.assertEqual(a[0x198:0x1A0], b[0x198:0x1A0], state.name)
                    self.assertEqual(a[0x60BD:0x60DC], b[0x60BD:0x60DC], state.name)
                    if stage == 'collect-01' and state.name == 'frame-0001.ss0':
                        continue  # Still-present star is checked by the separate color gate.
                    before = Image.open((parent/state.name).with_suffix('.png')).convert('RGB')
                    after = Image.open(state.with_suffix('.png')).convert('RGB')
                    self.assertIsNone(ImageChops.difference(before, after).getbbox(), state.name)
        menu = serialized_state(ROOT/'tmp/five-point-star-menu-02/frame-0360.ss0')
        resumed = serialized_state(ROOT/'tmp/five-point-star-menu-return-01/frame-0180.ss0')
        self.assertEqual(menu[0x3E4], 1)
        self.assertEqual(resumed[0x3E4], 0)
        self.assertEqual(resumed[0x5C80], 2)

    def test_failed_menu_attempt_not_accepted(self):
        receipt = json.loads((ROOT/'tmp/five-point-star-menu-01/receipt.json').read_text())
        self.assertNotEqual(receipt['status'], 0)

    def test_seven_stage_opening_samples_unchanged(self):
        import hashlib
        base = ROOT/'tmp/five-point-star-seven-stage-01'
        if not (base/'manifest.json').exists():
            self.skipTest('retained seven-stage paired captures unavailable')
        manifest = json.loads((base/'manifest.json').read_text())
        self.assertEqual(manifest['original_rom_sha256'],
                         '4731248ad2d28f56539197ddfa38fcb8f79713832b7997905647caf35d34f903')
        self.assertEqual(manifest['dx_rom_sha256'],
                         'd744124d3d161247e0584bb39e8db1243ade4e428cbc15f82a85c10d0a4ac4d5')
        self.assertEqual(set(manifest['stages']), {f'stage{i}' for i in range(1, 8)})
        for stage in manifest['stages']:
            with self.subTest(stage=stage):
                for side in ('og', 'dx'):
                    self.assertEqual((base/stage/side/'run.done').read_text().strip(), 'ok')
                parent = sorted((base/stage/'og').glob('run.f*.png'))
                self.assertEqual(len(parent), 4)
                for image in parent:
                    trial = base/stage/'dx'/image.name
                    self.assertEqual(hashlib.sha256(image.read_bytes()).hexdigest(),
                                     hashlib.sha256(trial.read_bytes()).hexdigest())


if __name__ == '__main__':
    unittest.main()
