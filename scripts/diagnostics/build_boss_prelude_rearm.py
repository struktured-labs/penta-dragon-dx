"""REJECTED #27/#59 experiment: bank1 mapping breaks the bank3 continuation.

Retained to reproduce the failed aaac trial; the source profile uses
build_boss_prelude_inline_rearm instead. Do not deploy this variant.

Explicitly map bank1 with native AF-preserving RST28: entry may have bank3
selected. Reuse nine bytes in abandoned records7/8;
records0..6 remain live after the timing correction (#62). Preserve
the original A=1, FFDA=1, FFE4=1 and flags/registers; additionally set FF91=1.
This is a transition-only +244T change, not a per-frame polling addition.
"""
import argparse
import hashlib
import json
from pathlib import Path

PARENT='398891b62781ddceb1893103b2b8b204dc5da6eb3d95bbe3b755c36a710c18b5'
HOOK=0x1A43
HELPER=0x7C9A
OLD=bytes.fromhex('3E01E0DAE0E4')
HEADER=bytes.fromhex('09704EAC7C243F3F3F')
PAYLOAD=bytes.fromhex('3E01E091E0DAE0E4C9')
COMMON_HEADER=bytes.fromhex('FE07D27E7C5F87836F7BCB37879521B37BD7B7119BFF061D2A12130520FACD887CC9')

def build(parent):
    if hashlib.sha256(parent).hexdigest()!=PARENT:raise ValueError('exact projectile parent required')
    if parent[HOOK:HOOK+6]!=OLD or parent[HELPER:HELPER+9]!=HEADER:raise ValueError('entry/header preimage changed')
    if parent[0x7B91:0x7BB3]!=COMMON_HEADER:raise ValueError('timing-correct clean header relocation required')
    for address, expected in ((0x28,bytes.fromhex('C39A09')),
            (0x99A,bytes.fromhex('F53E01CD6100F1C9')),
            (0x61,bytes.fromhex('EA09DCC3BE09')),
            (0x9BE,bytes.fromhex('E099EA0021C9'))):
        if parent[address:address+len(expected)]!=expected:raise ValueError('native bank mapper changed')
    refs=[i for i in range(len(parent)-1) if parent[i:i+2]==bytes.fromhex('A17B')]
    if refs:raise ValueError('old stage-index helper still referenced')
    refs=[i for i in range(len(parent)-1) if parent[i:i+2]==bytes.fromhex('A049')]
    if refs!=[0xFC201]:raise ValueError('clean stage-index helper references changed')
    result=bytearray(parent)
    result[HOOK:HOOK+6]=bytes.fromhex('EFCD9A7C0000')
    result[HELPER:HELPER+9]=PAYLOAD
    result[0x14e:0x150]=((sum(result[:0x14e])+sum(result[0x150:]))&65535).to_bytes(2,'big')
    return bytes(result)

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('parent',type=Path);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();root=Path(__file__).resolve().parents[2]
    if a.output.exists() or (root/'tmp').resolve() not in a.output.resolve().parents:p.error('fresh worktree tmp output required')
    rom=build(a.parent.read_bytes());a.output.mkdir(parents=True);(a.output/'candidate.gb').write_bytes(rom)
    report=dict(issues=[27,59],experimental=True,release_qualified=False,parent_sha256=PARENT,
        candidate_sha256=hashlib.sha256(rom).hexdigest(),builder_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        added_entry_tcycles=244,scope=__doc__)
    (a.output/'receipt.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report))
