#!/usr/bin/env python3
"""Normal-speed Stage1: 5/5/5/5/4 tiles per row in fresh HBlank intervals.

Source rows start even. INC E is safe after even source offsets (never FF);
odd offsets retain INC DE. Worst five-byte group costs112T. C=$41 makes
the final STAT poll28T/iteration, plus16T after the observed read: <=156dots
including writes, below the165dot conservative mode0+mode2 minimum.
"""
import hashlib
import json
from build_later_hdma_overlap import Asm
import build_eight_tile_groups_r401 as prior

BASE=prior.BASE
OUT=prior.ROOT/'tmp/five-tile-groups-r402'


def service():
    a=Asm(0x6C80)
    a.db(0xFA,0x80,0xD8,0xFE,2);a.jp(0xC2,'fallback')
    a.db(0xF0,0xBA,0xB7);a.jp(0xC2,'fallback')
    a.db(0xF0,0x4D,0xCB,0x7F);a.jp(0xC2,'fallback')
    a.db(0xC5,0x11,0xA0,0xC1,0x06,24,0x0E,0x41)
    a.label('row')
    index=0
    for group,count in enumerate((5,5,5,5,4)):
        tag=str(group)
        a.db(0xF3,0xF0,0x40,0xCB,0x7F);a.jr(0x28,'copy'+tag)
        a.db(0xF0,0x44,0xE6,0xF8,0xFE,0x90);a.jr(0x28,'copy'+tag)
        a.label('mode3'+tag);a.db(0xF2,0xE6,3,0xFE,3);a.jr(0x20,'mode3'+tag)
        a.label('mode0'+tag);a.db(0xF2,0xE6,3);a.jr(0x20,'mode0'+tag)
        a.label('copy'+tag)
        for _ in range(count):
            a.db(0x1A,0x1C if index%2==0 else 0x13,0x22)
            index+=1
        a.db(0xFB)
    a.db(0x7D,0xC6,8,0x6F);a.jr(0x30,'nextrow')
    a.db(0x24)
    a.label('nextrow');a.db(0x05);a.jp(0xC2,'row')
    a.db(0xC1,0x0E,0,0xAF,0x3C,0xC9)
    a.label('fallback');a.db(0xAF,0x3E,1,0xC9)
    return a.finish()


def build(source):return prior.build(source,service())


if __name__=='__main__':
    rom=build(BASE.read_bytes());OUT.mkdir(parents=True,exist_ok=True)
    target=OUT/'candidate.gb'
    if target.exists() and target.read_bytes()!=rom:raise SystemExit('candidate collision')
    target.write_bytes(rom)
    receipt=dict(experimental=True,promotable=False,base_sha256=prior.SHA,
                 candidate_sha256=hashlib.sha256(rom).hexdigest())
    (OUT/'build-receipt.json').write_text(json.dumps(receipt,indent=2)+'\n')
    print(receipt)
