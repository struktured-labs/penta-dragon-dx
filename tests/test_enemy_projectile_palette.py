import hashlib
import importlib.util
from pathlib import Path
import unittest
from unittest.mock import patch

spec=importlib.util.spec_from_file_location('bullet_palette',Path(__file__).resolve().parents[1]/'scripts/diagnostics/build_enemy_projectile_palette.py')
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)

class EnemyBulletPaletteTest(unittest.TestCase):
 def setUp(self):
  self.parent=bytearray([255])*0x100000
  for bank in m.BANKS:self.parent[m.offset(bank):m.offset(bank)+len(m.OLD)]=m.OLD
 def build(self):
  with patch.object(m,'PARENT',hashlib.sha256(self.parent).hexdigest()):return m.build(bytes(self.parent))
 def test_only_initializers_and_checksum_change(self):
  result=self.build()
  allowed={0x14e,0x14f}
  for bank in m.BANKS:allowed.update(range(m.offset(bank),m.offset(bank)+len(m.OLD)))
  self.assertTrue({i for i,(a,b) in enumerate(zip(self.parent,result)) if a!=b}<=allowed)
 def test_player_and_other_entities_preserved(self):
  def decode(code):
   self.assertEqual(code[:3],bytes.fromhex('2100D9'));i=3;out=[]
   while code[i]!=201:
    if code[i]==245:
     self.assertEqual(code[i:i+2],bytes.fromhex('F5F1'));i+=2;continue
    if code[i]==6:
     n=code[i+1];v=code[i+3];self.assertEqual(code[i+4:i+8],bytes.fromhex('220520FC'));i+=8
    else:
     self.assertEqual(code[i],62);self.assertEqual(code[i+2],34);n=1;v=code[i+1];i+=3
    out.extend([v]*n)
   return out
  old=decode(m.OLD);new=decode(m.payload());self.assertEqual(len(new),256)
  self.assertEqual([i for i,(a,b) in enumerate(zip(old,new)) if a!=b],[15]);self.assertEqual(new[15],3)
  result=self.build()
  for bank in m.BANKS:self.assertEqual(result[m.offset(bank):m.offset(bank)+len(m.OLD)],m.payload())
 def test_global_checksum(self):
  result=self.build();self.assertEqual(int.from_bytes(result[0x14e:0x150],'big'),(sum(result[:0x14e])+sum(result[0x150:]))&65535)
 def test_altered_lookup_rejected(self):
  self.parent[m.offset(16)+5]=4
  with self.assertRaisesRegex(ValueError,'preimage'):self.build()
 def test_wrong_parent_rejected(self):
  with self.assertRaisesRegex(ValueError,'exact'):m.build(bytes(self.parent))
 def test_initializer_registers_and_cycles_match(self):
  # Independent interpreter for exactly the initializer's instruction subset.
  def execute(code,carry):
   pc=0;a=85;b=153;hl=0;f=carry;cycles=0;memory={};stack=[]
   for step in range(5000):
    op=code[pc];pc+=1
    if op==0x21:hl=int.from_bytes(code[pc:pc+2],'little');pc+=2;cycles+=12
    elif op==0x06:b=code[pc];pc+=1;cycles+=8
    elif op==0x3e:a=code[pc];pc+=1;cycles+=8
    elif op==0x22:memory[hl]=a;hl+=1;cycles+=8
    elif op==0x05:
     old=b;b=(b-1)&255;f=(f&16)|64|(128 if b==0 else 0)|(32 if old&15==0 else 0);cycles+=4
    elif op==0x20:
     jump=code[pc];pc+=1
     if not f&128:pc+=jump-256 if jump>=128 else jump;cycles+=12
     else:cycles+=8
    elif op==0xf5:stack.append((a,f));cycles+=16
    elif op==0xf1:a,f=stack.pop();cycles+=12
    elif op==0xc9:return a,b,hl,f,cycles,memory,stack
    else:raise AssertionError(hex(op))
   raise AssertionError('initializer did not return')
  for carry in (0,16):
   before=execute(m.OLD,carry);after=execute(m.payload(),carry)
   self.assertEqual(before[:5],after[:5]);self.assertEqual(after[-1],[])
   self.assertEqual([addr for addr in before[5] if before[5][addr]!=after[5][addr]],[0xD90F])

if __name__=='__main__':unittest.main()
