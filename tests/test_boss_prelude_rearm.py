import hashlib
import importlib.util
from pathlib import Path
import unittest
from unittest.mock import patch

spec=importlib.util.spec_from_file_location('rearm',Path(__file__).resolve().parents[1]/'scripts/diagnostics/build_boss_prelude_rearm.py')
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)

class RearmTest(unittest.TestCase):
 def setUp(self):
  self.parent=bytearray([255])*0x100000
  self.parent[m.HOOK:m.HOOK+6]=m.OLD
  self.parent[m.HELPER:m.HELPER+9]=m.HEADER
  self.parent[0x7B91:0x7BB3]=m.COMMON_HEADER
  self.parent[0xFC201:0xFC203]=bytes.fromhex('A049')
  for start,text in ((0x28,'C39A09'),(0x99A,'F53E01CD6100F1C9'),(0x61,'EA09DCC3BE09'),(0x9BE,'E099EA0021C9')):
   data=bytes.fromhex(text);self.parent[start:start+len(data)]=data
 def build(self):
  with patch.object(m,'PARENT',hashlib.sha256(self.parent).hexdigest()):return m.build(bytes(self.parent))
 def test_scoped_patch(self):
  result=self.build();allowed=set(range(m.HOOK,m.HOOK+6))|set(range(m.HELPER,m.HELPER+9))|{0x14e,0x14f}
  self.assertTrue({i for i,(a,b) in enumerate(zip(self.parent,result)) if a!=b}<=allowed)
  self.assertEqual(result[m.HELPER:m.HELPER+9],bytes.fromhex('3E01E091E0DAE0E4C9'))
 def test_relocated_table_untouched(self):
  result=self.build()
  self.assertEqual(result[0xFC800:0xFC905],self.parent[0xFC800:0xFC905])
  self.assertEqual(result[0x7BB3:0x7C7E],self.parent[0x7BB3:0x7C7E])
  self.assertEqual(result[0x7C91:0x7C9A],self.parent[0x7C91:0x7C9A])
  self.assertEqual(result[0x7CAE:0x7CB7],self.parent[0x7CAE:0x7CB7])
 def test_checksum(self):
  r=self.build();self.assertEqual(int.from_bytes(r[0x14e:0x150],'big'),(sum(r[:0x14e])+sum(r[0x150:]))&65535)
 def test_live_reference_rejected(self):
  self.parent[0x5000:0x5002]=bytes.fromhex('A17B')
  with self.assertRaisesRegex(ValueError,'referenced'):self.build()
 def test_unrelocated_loader_rejected(self):
  self.parent[0x7b91]=0
  with self.assertRaisesRegex(ValueError,'relocation'):self.build()
 def test_wrong_parent_rejected(self):
  with self.assertRaisesRegex(ValueError,'exact'):m.build(bytes(self.parent))
 def test_entry_instruction_contract_and_cost(self):
  # Execute the actual old/new instruction streams, including CALL/RET and
  # stack writes. Reject unknown opcodes rather than approximating them.
  def execute(rom,flags):
   memory=bytearray(65536);memory[:0x8000]=rom[:0x8000]
   registers=dict(a=0x6d,f=flags,b=0x12,c=0x34,d=0x56,e=0x78,h=0x9a,l=0xbc)
   pc,sp,cycles=m.HOOK,0xdfe0,0
   for _ in range(50):
    if pc==m.HOOK+6:return registers,sp,cycles,memory
    op=memory[pc];pc+=1
    if op==0x3e:
     registers['a']=memory[pc];pc+=1;cycles+=8
    elif op==0xe0:
     memory[0xff00+memory[pc]]=registers['a'];pc+=1;cycles+=12
    elif op==0xcd:
     target=int.from_bytes(memory[pc:pc+2],'little');pc+=2
     sp-=2;memory[sp:sp+2]=pc.to_bytes(2,'little');pc=target;cycles+=24
    elif op==0xc9:
     pc=int.from_bytes(memory[sp:sp+2],'little');sp+=2;cycles+=16
    elif op==0xef:
     sp-=2;memory[sp:sp+2]=pc.to_bytes(2,'little');pc=0x28;cycles+=16
    elif op==0xf5:
     sp-=2;memory[sp:sp+2]=(registers['a']<<8|registers['f']).to_bytes(2,'little');cycles+=16
    elif op==0xf1:
     af=int.from_bytes(memory[sp:sp+2],'little');sp+=2;registers['a']=af>>8;registers['f']=af&0xf0;cycles+=12
    elif op==0xc3:
     pc=int.from_bytes(memory[pc:pc+2],'little');cycles+=16
    elif op==0xea:
     address=int.from_bytes(memory[pc:pc+2],'little');pc+=2;memory[address]=registers['a'];cycles+=16
    elif op==0:cycles+=4
    else:self.fail(f'unexpected opcode {op:02x}')
   self.fail('entry did not return')
  candidate=self.build()
  for flags in range(0,256,16):
   old=execute(self.parent,flags);new=execute(candidate,flags)
   self.assertEqual(old[:2],new[:2])
   self.assertEqual(new[2]-old[2],244)
   self.assertEqual(new[3][0xff91],1)
   self.assertEqual(new[3][0xffda],old[3][0xffda])
   self.assertEqual(new[3][0xffe4],old[3][0xffe4])

if __name__=='__main__':unittest.main()
