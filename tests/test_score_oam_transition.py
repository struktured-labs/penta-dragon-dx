import importlib.util
from pathlib import Path
import unittest

spec=importlib.util.spec_from_file_location('card_check',Path(__file__).resolve().parents[1]/'scripts/diagnostics/check_score_oam_transition.py')
check=importlib.util.module_from_spec(spec);spec.loader.exec_module(check)

class CardEvidenceTest(unittest.TestCase):
 def rows(self,dirty=False):
  return [dict(frame=str(i),scene='18' if i<200 else '03',stage='01',
     visible_oam='4' if dirty else '0',shadow_oam='0',score_poll='1' if 50<=i<150 else '0') for i in range(1,2401)]
 def test_clean_card_and_gameplay_coverage(self):
  r=check.assess(self.rows());self.assertTrue(r['complete'])
  self.assertEqual(r['card_dirty_frames'],0);self.assertEqual(r['first_gameplay'],200)
 def test_lingering_sprites_detected(self):
  self.assertEqual(check.assess(self.rows(True))['card_dirty_frames'],199)
  self.assertEqual(check.assess(self.rows(True))['score_dirty_frames'],100)
 def test_truncated_route_not_complete(self):
  self.assertFalse(check.assess(self.rows()[:-1])['complete'])
 def test_other_stage_does_not_supply_coverage(self):
  rows=self.rows()
  for r in rows:r['stage']='02'
  self.assertEqual(check.assess(rows)['card_frames'],0)
 def test_dirty_shadow_detected(self):
  rows=self.rows();rows[99]['shadow_oam']='1'
  self.assertEqual(check.assess(rows)['card_shadow_dirty_frames'],1)
 def test_nonzero_attribute_mutation_detected(self):
  raw=bytearray(71680);self.assertEqual(check.attribute_errors(raw),[])
  raw[0x3C87]=4;self.assertEqual(check.attribute_errors(raw),[0x87])
 def test_wrong_map_rejected(self):
  raw=bytearray(71680);raw[0x340]=8
  with self.assertRaisesRegex(ValueError,'tilemap'):check.attribute_errors(raw)
 def test_wrong_state_layout_rejected(self):
  with self.assertRaisesRegex(ValueError,'layout'):check.attribute_errors(bytes(70000))

if __name__=='__main__':unittest.main()
