"""#45 scratch-only final E4 restore; inherits unqualified fixed-route allocation.

Only the last restore may use LY144..150. Interrupts are disabled before the
LY read; all other arrivals use the existing window. The final 64-byte copy
uses LDH(C),A, preserving bytes while reducing the critical write budget.
"""
import argparse
import hashlib
import json
from pathlib import Path
from compose_ending_bgp_handoff_r518 import Asm

PARENT='988b3e07bcfd884c01f7355704a48530502cab157d01d33f2767417ffd9921b7'
BASE=0x6314


def payload():
    a=Asm(BASE)
    a.db(*bytes.fromhex('F068 F5 F3'))
    a.label('sample_ly')
    a.db(*bytes.fromhex('F044 FE90'))
    a.jr(0x38,'fallback')
    a.db(0xFE,151)
    a.jr(0x30,'fallback')
    a.jr(0x18,'upload')
    a.label('fallback')
    a.db(*bytes.fromhex('FB00 CDF85B'))
    a.label('upload')
    a.db(*bytes.fromhex('3E07 E070 3E80 E068 2100DF 0E69'))
    a.label('write_start')
    for _ in range(64): a.db(0x2A,0xE2)
    a.label('write_end')
    a.db(*bytes.fromhex('3E01 E070 F1 E068 FB00 C9'))
    return a.finish(),a.labels


def build(parent):
    if hashlib.sha256(parent).hexdigest()!=PARENT: raise ValueError('exact988b parent required')
    body,labels=payload()
    offset=20*0x4000+BASE-0x4000
    if parent[offset:offset+len(body)]!=b'\xff'*len(body): raise ValueError('occupied cave')
    if parent[0x5165D:0x51660]!=bytes.fromhex('CDC05A'): raise ValueError('final restore call differs')
    result=bytearray(parent)
    result[offset:offset+len(body)]=body
    result[0x5165D:0x51660]=bytes.fromhex('CD')+BASE.to_bytes(2,'little')
    result[0x14E:0x150]=((sum(result[:0x14E])+sum(result[0x150:]))&65535).to_bytes(2,'big')
    return bytes(result),labels


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('parent',type=Path);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();root=Path(__file__).resolve().parents[2]
    if a.output.exists() or (root/'tmp').resolve() not in a.output.resolve().parents:
        p.error('fresh repository tmp output required')
    rom,labels=build(a.parent.read_bytes());a.output.mkdir()
    (a.output/'candidate.gb').write_bytes(rom)
    r=dict(issue=45,experimental=True,release_qualified=False,allocation_review_complete=False,
           parent_sha256=PARENT,candidate_sha256=hashlib.sha256(rom).hexdigest(),labels=labels,
           builder_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest())
    (a.output/'receipt.json').write_text(json.dumps(r,indent=2)+'\n');print(json.dumps(r))
