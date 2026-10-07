"""#60 experimental score-card entry: publish the native cleared sprite buffers.

Only the score entry is redirected. Bank63 mirrors the native buffer clear,
then uses the existing HRAM DMA once with interrupts masked. Both C0/C1 shadows
are already zero, so either native DMA page is correct. Gameplay is untouched.
"""
import argparse
import hashlib
import json
from pathlib import Path

PARENT='2f0c44e7e204735e0c583f48a88cb079b6630b27a3372ce10365eac0944bf8f9'
CLEAR=bytes.fromhex('E5C5F5F306A02100C0CDA20906A02100C1CDA209FBF1C1E1C9')

def offset(address): return 63*0x4000+address-0x4000

def build(parent):
    if hashlib.sha256(parent).hexdigest()!=PARENT: raise ValueError('exact clean-header parent required')
    if parent[0x7569:0x756F]!=bytes.fromhex('CD7E00CD2B49') or parent[0x492B:0x4944]!=CLEAR:
        raise ValueError('native score entry/clear changed')
    result=bytearray(parent)
    def install(address,code):
        pos=offset(address)
        if parent[pos:pos+len(code)]!=b'\xff'*len(code): raise ValueError('bank63 allocation occupied')
        result[pos:pos+len(code)]=code
    # CALL0061 switches banks and returns to bank63:756E. Return to bank1
    # uses the separate CALL at bank63:756B, landing on bank1's NOP756E.
    result[0x7569:0x756F]=bytes.fromhex('3E3FCD610000')
    install(0x756B,bytes.fromhex('CD6100C30043'))
    install(0x4300,bytes.fromhex('CD7E00CD2043F3CD80FFFB3E01C36B75'))
    install(0x4320,CLEAR)
    result[0x14E:0x150]=((sum(result[:0x14E])+sum(result[0x150:]))&65535).to_bytes(2,'big')
    return bytes(result)

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('parent',type=Path);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();root=Path(__file__).resolve().parents[2]
    if a.output.exists() or (root/'tmp').resolve() not in a.output.resolve().parents: p.error('fresh worktree tmp output required')
    rom=build(a.parent.read_bytes());a.output.mkdir(parents=True)
    (a.output/'candidate.gb').write_bytes(rom)
    receipt=dict(issue=60,experimental=True,release_qualified=False,parent_sha256=PARENT,
      candidate_sha256=hashlib.sha256(rom).hexdigest(),builder_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest())
    (a.output/'receipt.json').write_text(json.dumps(receipt,indent=2)+'\n');print(json.dumps(receipt))
