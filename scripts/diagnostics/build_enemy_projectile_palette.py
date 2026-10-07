"""#57: give enemy bullet tile0F a stable red palette, independent of weapons.

Reuse existing OBJ3 (red flying-enemy palette); preserve weapon OBJ0 and all
palette bytes. Only the boot/boss-exit LUT initializer changes; no per-frame
instructions or palette uploads are added. Both bank13/16 copies are patched.
"""
import argparse
import hashlib
import json
from pathlib import Path

PARENT='668a57574a211fb837f223a289858a8bba3c2dd65f479f9955a256f35870d4ab'
ADDRESS=0x7DA8
BANKS=(13,16)
RUNS=((16,0),(32,255),(16,3),(16,5),(16,4),(16,5),(16,6),(127,4),(1,0))
OLD=bytes.fromhex('2100D9')+b''.join(bytes((6,n,62,v,34,5,32,252)) for n,v in RUNS)+b'\xc9'

def payload():
 runs=((15,0),(1,3))+RUNS[1:]
 code=bytes.fromhex('2100D9')+b''.join(bytes((62,v,34)) if n==1 else bytes((6,n,62,v,34,5,32,252)) for n,v in runs)
 # Splitting tile0F and simplifying singleton FF saves28T and two bytes.
 # PUSH/POP AF costs28T, preserves the return ABI and keeps total init time
 # equal to the parent (ordinary stack, maximum extra depth two bytes).
 assert len(OLD)-len(code)-1==2
 return code+bytes.fromhex('F5F1C9')

def offset(bank):return bank*0x4000+ADDRESS-0x4000

def build(parent):
 if hashlib.sha256(parent).hexdigest()!=PARENT:raise ValueError('exact score-card parent required')
 if len(parent)!=0x100000:raise ValueError('ROM size changed')
 result=bytearray(parent)
 for bank in BANKS:
  pos=offset(bank)
  if parent[pos:pos+len(OLD)]!=OLD:raise ValueError('projectile LUT initializer preimage changed')
  result[pos:pos+len(OLD)]=payload()
 result[0x14e:0x150]=((sum(result[:0x14e])+sum(result[0x150:]))&65535).to_bytes(2,'big')
 return bytes(result)

if __name__=='__main__':
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('parent',type=Path);p.add_argument('--output',type=Path,required=True)
 a=p.parse_args();root=Path(__file__).resolve().parents[2]
 if a.output.exists() or (root/'tmp').resolve() not in a.output.resolve().parents:p.error('fresh worktree tmp output required')
 rom=build(a.parent.read_bytes());a.output.mkdir(parents=True);(a.output/'candidate.gb').write_bytes(rom)
 report=dict(issue=57,experimental=True,release_qualified=False,parent_sha256=PARENT,
  candidate_sha256=hashlib.sha256(rom).hexdigest(),builder_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
  palette_policy='enemy tile0F uses existing stable red OBJ3; player weapon OBJ0 unchanged')
 (a.output/'receipt.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report))
