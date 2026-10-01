#!/usr/bin/env python3
"""Issue #23: prevent secret-stage BG0 lookup from reading injected code.

FFBA=7 indexed a six-entry Stage2..7 source table at $7BAC and read the next
routine's PUSH BC opcode ($C5), copying unaligned $68C5 into BG0. Relocate the
lookup into the eight reserved bytes following the two retired-posmap leaves
at $7FE0. Preserve six normal-stage choices and use the base Dungeon row for
secret/final stage indices 7/8. Same instructions and cycle counts.
"""
import argparse
import json
from pathlib import Path
from build_secret_chr_restore import digest

PARENT_SHA='22b3909b5ef3653abb1a40d227c2f9f0d6d6a276010ca08299af1c688eb15e6c'
TABLE=0x37FEA
SELECTOR=0x369B8
OLD=bytes.fromhex('5F FA4CDF FE0C C0 7B C6AB 6F 267B 5E 3E80 E068 6B 2668 C3E07F')


def build(parent):
    if digest(parent)!=PARENT_SHA:raise ValueError('requires exact geometry-restored parent')
    if parent[SELECTOR:SELECTOR+len(OLD)]!=OLD:raise ValueError('selector differs')
    # Source builder explicitly owns 18 retired-pointer bytes at $7FE0.
    # Seven-byte CRAM-copy leaf + three-byte arm leaf leave exactly eight.
    if parent[0x37FE0:TABLE]!=bytes.fromhex('CDDB71 CDDB71 C9 C38454'):
        raise ValueError('retired-pointer leaf ownership differs')
    if parent[TABLE:TABLE+8]!=bytes(8):raise ValueError('reserved table slot occupied')
    rows=parent[0x37BAC:0x37BB2]
    if rows!=bytes.fromhex('200030001800'):raise ValueError('normal-stage sources differ')
    result=bytearray(parent)
    result[TABLE:TABLE+8]=rows+bytes(2)
    result[SELECTOR+9]=0xE9
    result[SELECTOR+12]=0x7F
    result[0x14E:0x150]=((sum(result[:0x14E])+sum(result[0x150:]))&65535).to_bytes(2,'big')
    allowed=set(range(TABLE,TABLE+8))|{SELECTOR+9,SELECTOR+12,0x14E,0x14F}
    if any(a!=b and i not in allowed for i,(a,b) in enumerate(zip(parent,result))):
        raise ValueError('patch escaped owned bytes')
    return bytes(result)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('parent',type=Path);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();root=Path(__file__).resolve().parents[2]
    if a.output.exists() or (root/'tmp').resolve() not in a.output.resolve().parents:
        p.error('output must be fresh beneath repository tmp/')
    result=build(a.parent.read_bytes());a.output.mkdir(parents=True)
    (a.output/'candidate.gb').write_bytes(result)
    receipt=dict(issue=23,parent_sha256=PARENT_SHA,candidate_sha256=digest(result),
      builder_sha256=digest(Path(__file__).read_bytes()),release_qualified=False,
      normal_stage_rows_preserved=True,runtime_instructions_unchanged=True,
      palette_policy='FFBA7/8 use existing Dungeon BG0; scene material attributes not repaired')
    (a.output/'build-receipt.json').write_text(json.dumps(receipt,indent=2)+'\n')
    print(json.dumps(receipt))
