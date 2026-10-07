import hashlib
import importlib.util
from pathlib import Path
import unittest
from unittest.mock import patch

spec=importlib.util.spec_from_file_location('score',Path(__file__).resolve().parents[1]/'scripts/diagnostics/build_score_oam_publish.py')
score=importlib.util.module_from_spec(spec);spec.loader.exec_module(score)

class ScoreOamTest(unittest.TestCase):
 def setUp(self):
  self.parent=bytearray([255])*0x100000
  self.parent[0x7569:0x756F]=bytes.fromhex('CD7E00CD2B49')
  self.parent[0x492B:0x4944]=score.CLEAR
 def build(self):
  with patch.object(score,'PARENT',hashlib.sha256(self.parent).hexdigest()):return score.build(bytes(self.parent))
 def test_only_declared_spans_changed(self):
  result=self.build()
  spans=[(0x14E,2),(0x7569,6),(score.offset(0x756B),6),(score.offset(0x4300),16),(score.offset(0x4320),25)]
  allowed={i for start,size in spans for i in range(start,start+size)}
  self.assertTrue({i for i,(a,b) in enumerate(zip(self.parent,result)) if a!=b}<=allowed)
 def test_native_clear_preserved_and_mirrored(self):
  result=self.build();self.assertEqual(result[0x492B:0x4944],score.CLEAR)
  self.assertEqual(result[score.offset(0x4320):score.offset(0x4320)+25],score.CLEAR)
 def test_dma_masked_and_return_bank_one(self):
  result=self.build();self.assertEqual(result[score.offset(0x4306):score.offset(0x4310)],bytes.fromhex('F3CD80FFFB3E01C36B75'))
 def test_occupied_cave_rejected(self):
  self.parent[score.offset(0x4300)]=0
  with self.assertRaisesRegex(ValueError,'occupied'):self.build()
 def test_modified_native_clear_rejected(self):
  self.parent[0x492B]=0
  with self.assertRaisesRegex(ValueError,'native score'):self.build()
 def test_unknown_parent_rejected(self):
  with self.assertRaisesRegex(ValueError,'exact clean-header'):score.build(bytes(self.parent))

if __name__=='__main__':unittest.main()
