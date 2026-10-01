import sys
from pathlib import Path
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts/diagnostics'))
from check_boss_menu_fades import scene_observation, scene_route_failures, SHALAMAR_PALETTE_POLICY
from verify_pickup_class_palettes import serialized_state


class ShalamarAliasGate(unittest.TestCase):
    def row(self):
        s=bytearray(71680);s[8]=0x80;s[0x5c80]=11;s[0x3b7]=12
        s[0x4a00:0x4b00]=SHALAMAR_PALETTE_POLICY
        return scene_observation(1,s)

    def test_alias_requires_model_owner_and_correct_dx_policy(self):
        row=self.row()
        self.assertEqual(scene_route_failures([row],12),[])
        for key,value in [('scene',0x17),('canonical_scene',2),
                          ('cgb',None),('shalamar_palette_valid',False)]:
            with self.subTest(key=key):
                self.assertTrue(scene_route_failures([dict(row,**{key:value})],12))
        self.assertTrue(scene_route_failures([dict(row,scene=12,shalamar_palette_valid=False)],12))
        self.assertTrue(scene_route_failures([dict(row,canonical_scene=16)],16))
        self.assertEqual(scene_route_failures([dict(row,cgb=False,shalamar_palette_valid=False)],12),[])

    def test_native_alias_accepted_but_retained_corrupt_dx_rejected(self):
        cases=[('shalamar-native-lowhealth-01',1680,False),
               ('return-fade16-shalamar-phase721-01',999,False),
               ('star-shalamar-native-inventory-phase721-01',999,True)]
        for directory,frame,failed in cases:
            path=ROOT/'tmp'/directory/f'frame-{frame:04d}.ss0'
            if not path.exists(): self.skipTest('local replay unavailable')
            row=scene_observation(frame,serialized_state(path))
            self.assertEqual((row['scene'],row['canonical_scene']),(11,12))
            self.assertEqual(bool(scene_route_failures([row],12)),failed,directory)


if __name__=='__main__': unittest.main()
