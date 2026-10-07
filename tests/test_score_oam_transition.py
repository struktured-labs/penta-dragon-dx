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
 def test_extended_route_requires_exact_ordered_requested_frames(self):
  rows=self.rows()
  rows.extend(dict(rows[-1],frame=str(i)) for i in range(2401,3301))
  self.assertTrue(check.assess(rows,3300)['complete'])
  self.assertFalse(check.assess(rows)['complete'])
  rows[500]=dict(rows[499])
  self.assertFalse(check.assess(rows,3300)['complete'])
 def test_empty_and_reordered_routes_fail_closed(self):
  self.assertFalse(check.assess([])['complete'])
  self.assertFalse(check.assess(list(reversed(self.rows())))['complete'])
 def test_lowhealth_requires_native_dungeon_owner(self):
  rows=self.rows()
  for r in rows:
   if r['scene']=='03':r.update(scene='0B',native_scene='03')
  self.assertEqual(check.assess(rows)['first_gameplay'],200)
  for r in rows:r['native_scene']='0C'
  self.assertIsNone(check.assess(rows)['first_gameplay'])
  for r in rows:r.pop('native_scene')
  self.assertIsNone(check.assess(rows)['first_gameplay'])
 def test_invalid_frame_contract_rejected(self):
  for frames in (0,-1,'3300'):
   with self.assertRaises(ValueError):check.assess([],frames)
 def test_recipe_normalizes_only_owned_output_paths(self):
  a=Path(__file__).resolve().parents[1]/'tmp/recipe-a'
  b=a.with_name('recipe-b')
  def receipt(folder):
   return {'inputs_environment':{'ENTRY_OUT':str(folder),
     'ENTRY_NATIVE_START_GATE':str(folder/'native-runtime/ready'),
     'ENTRY_NATIVE_DEFER_START':'1','ENTRY_FRAMES':'3300','ENTRY_KEYS':'1'}}
  x,y=receipt(a),receipt(b)
  self.assertEqual(check.input_recipe(x,a),check.input_recipe(y,b))
  y['inputs_environment']['ENTRY_KEYS']='0'
  self.assertNotEqual(check.input_recipe(x,a),check.input_recipe(y,b))
  y['inputs_environment']['ENTRY_NATIVE_START_GATE']=str(a/'native-runtime/ready')
  with self.assertRaises(ValueError):check.input_recipe(y,b)
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
