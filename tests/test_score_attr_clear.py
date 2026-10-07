import hashlib
import importlib.util
from pathlib import Path
import unittest
from unittest.mock import patch

spec=importlib.util.spec_from_file_location('attrs',Path(__file__).resolve().parents[1]/'scripts/diagnostics/build_score_attr_clear.py')
attrs=importlib.util.module_from_spec(spec);spec.loader.exec_module(attrs)

class ScoreAttributePatch(unittest.TestCase):
 def setUp(self):
  self.parent=bytearray([255])*0x100000
  p=attrs.offset(0x4300);self.parent[p:p+16]=bytes.fromhex('CD7E00CD2043F3CD80FFFB3E01C36B75')
  self.parent[0x7589:0x7598]=bytes.fromhex('CD470FCDA800E60128F9AFE095E094')
 def build(self):
  with patch.object(attrs,'PARENT',hashlib.sha256(self.parent).hexdigest()):return attrs.build(bytes(self.parent))
 def test_only_expansion_helper_and_checksum_change(self):
  result=self.build();self.assertEqual(len(result),len(self.parent))
  for i,(a,b) in enumerate(zip(self.parent,result)):
   if a!=b:self.assertTrue(i in (0x14e,0x14f) or 0x7589<=i<0x7598 or i>=63*0x4000)
 def test_zero_source_and_single_block_dma(self):
  r=self.build();self.assertEqual(r[attrs.offset(0x4400):attrs.offset(0x4410)],bytes(16))
  self.assertIn(bytes.fromhex('AFE055FB'),attrs.payload())
  self.assertIn(bytes.fromhex('2100981110000640'),attrs.payload())
 def test_wait_and_loop_targets(self):
  code=attrs.payload()
  for index,expected in ((code.index(bytes.fromhex('F041E602'))+4,code.index(bytes.fromhex('F041E602'))),(code.index(bytes.fromhex('FB190520'))+3,19)):
   rel=code[index+1];rel=rel-256 if rel>127 else rel
   self.assertEqual(index+2+rel,expected)
 def test_occupied_source_rejected(self):
  self.parent[attrs.offset(0x4400)]=0
  with self.assertRaisesRegex(ValueError,'occupied'):self.build()
 def test_occupied_helper_rejected(self):
  self.parent[attrs.offset(0x4500)]=0
  with self.assertRaisesRegex(ValueError,'occupied'):self.build()
 def test_unknown_parent_rejected(self):
  with self.assertRaisesRegex(ValueError,'exact score-OAM'):attrs.build(bytes(self.parent))

if __name__=='__main__':unittest.main()
