import importlib.util
from pathlib import Path
import unittest

spec=importlib.util.spec_from_file_location('handoff',Path(__file__).resolve().parents[1]/'scripts/diagnostics/check_boss_prelude_handoff.py')
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)

class HandoffTest(unittest.TestCase):
 def fixture(self,scene):
  rom=bytearray(0x100000);rom[0x37200:0x37300]=bytes([4])*256
  rom[0x36820:0x36828]=bytes(range(8));raw=bytearray(71680)
  resolver=bytes.fromhex('FA80D8FE0B200EF0B7D60CFE0938043E0B1802C60C210DDFBEF53E0DC39A6F')
  rom[0x52de0:0x52de0+len(resolver)]=resolver
  raw[0x3ba]=1 if scene==3 else 0
  raw[0x5c80]=raw[0x3b7]=raw[0x630d]=scene;raw[0x391]=1
  if scene==12:raw[0x4a00:0x4b00]=rom[0x37200:0x37300]
  else:
   for i in (0xae,0xaf,0xbe,0xbf,0xc6,0xc7,0xd6,0xd7):raw[0x4a00+i]=2
   raw[0xd4:0xdc]=rom[0x36820:0x36828]
  return raw,rom
 def test_both_scenes_and_low_health(self):
  for scene in (12,3):
   raw,rom=self.fixture(scene);m.assess(raw,rom,scene);raw[0x5c80]=11
   if scene==3:raw[0x630d]=11
   m.assess(raw,rom,scene)
 def test_dungeon_alias_requires_exact_resolver(self):
  raw,rom=self.fixture(3);raw[0x5c80]=raw[0x630d]=11;rom[0x52de7]^=1
  with self.assertRaisesRegex(ValueError,'resolver'):m.assess(raw,rom,3)
 def test_dungeon_alias_requires_stage2_selector(self):
  raw,rom=self.fixture(3);raw[0x5c80]=raw[0x630d]=11;raw[0x3ba]=0
  with self.assertRaisesRegex(ValueError,'selector'):m.assess(raw,rom,3)
 def test_dungeon_alias_rejects_stale_miniboss(self):
  raw,rom=self.fixture(3);raw[0x5c80]=11;raw[0x630d]=10
  with self.assertRaisesRegex(ValueError,'stale'):m.assess(raw,rom,3)
 def test_dungeon_alias_still_checks_colors(self):
  raw,rom=self.fixture(3);raw[0x5c80]=raw[0x630d]=11;raw[0xd5]^=1
  with self.assertRaisesRegex(ValueError,'CRAM'):m.assess(raw,rom,3)
 def test_disarmed_setup_rejected(self):
  raw,rom=self.fixture(12);raw[0x391]=0
  with self.assertRaisesRegex(ValueError,'stale'):m.assess(raw,rom,12)
 def test_stale_owner_rejected(self):
  raw,rom=self.fixture(12);raw[0x630d]=10
  with self.assertRaisesRegex(ValueError,'stale'):m.assess(raw,rom,12)
 def test_wrong_material_rejected(self):
  raw,rom=self.fixture(12);raw[0x4a11]=0
  with self.assertRaisesRegex(ValueError,'material'):m.assess(raw,rom,12)
 def test_stale_stage2_cram_rejected(self):
  raw,rom=self.fixture(3);raw[0xd5]^=1
  with self.assertRaisesRegex(ValueError,'CRAM'):m.assess(raw,rom,3)
 def test_wrong_checkpoint_rejected(self):
  raw,rom=self.fixture(12);raw[0x3b7]=10
  with self.assertRaisesRegex(ValueError,'checkpoint'):m.assess(raw,rom,12)

if __name__=='__main__':unittest.main()
