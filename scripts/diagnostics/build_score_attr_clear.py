"""#60 experimental: clear stale arena attributes before publishing score text."""
import argparse
import hashlib
import json
from pathlib import Path

PARENT='f340103bab9e9fcb948712807703cde40d31bb961d70dd2f3b3b78d40befdd7c'
def offset(a):return 63*0x4000+a-0x4000

def payload():
    code=bytearray.fromhex('F5C5D5E5 F04FF5 3E01E04F 210098 111000 0640')
    loop=len(code)
    # Configure under DI, then check STAT immediately before triggering DMA.
    # Checking before the register setup allowed mode3 to begin in that gap.
    code.extend(bytes.fromhex('F3 3E44E051 AFE052 7CE053 7DE054'))
    wait=len(code)
    code.extend(bytes.fromhex('F041 E602 20'))
    code.append((wait-(len(code)+1))&255)
    code.extend(bytes.fromhex('AFE055 FB 19 05 20'))
    code.append((loop-(len(code)+1))&255)
    code.extend(bytes.fromhex('F1E04F E1D1C1F1C9'))
    return bytes(code)

def build(parent):
    if hashlib.sha256(parent).hexdigest()!=PARENT:raise ValueError('exact score-OAM parent required')
    result=bytearray(parent)
    # Enter a private copy of the native score fade/input wait, reusing its
    # first four-tick idle interval for attribute publication. The previous
    # trial did this before font loading and shifted transition frame timing.
    old=bytes.fromhex('CD470FCDA800E60128F9AFE095E094')
    if parent[0x7589:0x7598]!=old:raise ValueError('score fade entry changed')
    result[0x7589:0x7598]=bytes.fromhex('3E3FCD6100')+bytes(10)
    # Fixed fade0F47 calls bank-local406F. Mirror that wait, adding the clear
    # only when HL points at its first shade0FD4, after resetting FFD4.
    delay=bytes.fromhex('F5AFE0D4 7DFED4 2003 CD0045 F0D4FE0420FA AFE0D4F1C9')
    route=bytes.fromhex('CD470F CDA800E60128F9 AFE095E094 3E01C39575')
    for address,code in [(0x4400,bytes(16)),(0x4500,payload()),
                         (0x406F,delay),(0x4600,route),
                         (0x758E,bytes.fromhex('C30046')),(0x7595,bytes.fromhex('CD6100'))]:
        pos=offset(address)
        if parent[pos:pos+len(code)]!=b'\xff'*len(code):raise ValueError('attribute helper cave occupied')
        result[pos:pos+len(code)]=code
    result[0x14e:0x150]=((sum(result[:0x14e])+sum(result[0x150:]))&65535).to_bytes(2,'big')
    return bytes(result)

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('parent',type=Path);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();root=Path(__file__).resolve().parents[2]
    if a.output.exists() or (root/'tmp').resolve() not in a.output.resolve().parents:p.error('fresh worktree tmp output required')
    rom=build(a.parent.read_bytes());a.output.mkdir(parents=True);(a.output/'candidate.gb').write_bytes(rom)
    receipt=dict(issue=60,experimental=True,release_qualified=False,parent_sha256=PARENT,
      candidate_sha256=hashlib.sha256(rom).hexdigest(),builder_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest())
    (a.output/'receipt.json').write_text(json.dumps(receipt,indent=2)+'\n');print(json.dumps(receipt))
