#!/usr/bin/env python3
"""Synchronous six-tile groups; explicit source-page crossings, no new RAM."""
import hashlib
import json
import build_relative_commit_consume_r404 as prior
import build_five_tile_groups_r402 as old
from build_later_hdma_overlap import Asm
ROOT=prior.ROOT
BASE=ROOT/'tmp/relative-commit-consume-r404/candidate.gb'
SHA='607dd53618c59e94dfb4b20cbac149549ca48ef7840cd39cdcb16ea60800f177'
OUT=ROOT/'tmp/six-tile-groups-r405'
OFFSET=26*0x4000+0x2C80

def service(precompile=None, native_cached=False, static_rows=False):
    a=Asm(0x6C80)
    a.db(0xFA,0x80,0xD8,0xFE,2);a.jp(0xC2,'fallback')
    a.db(0xF0,0xBA,0xB7);a.jp(0xC2,'fallback')
    a.db(0xF0,0x4D,0xCB,0x7F);a.jp(0xC2,'fallback')
    a.db(0xF0,0x40,0xCB,0x7F);a.jp(0xCA,'fallback')
    if native_cached:
        a.db(0xF0,0xE0,0xFE,3);a.jp(0xCA,'fallback')
    if precompile is not None:a.db(0xCD,precompile&255,precompile>>8)
    a.db(0xC5,0x11,0xA0,0xC1,0x0E,0x41)
    for row in range(24):
        for group in range(4):
            tag=f'{row}_{group}'
            a.db(0xF3,0xF0,0x44,0xE6,0xF8,0xFE,0x90);a.jr(0x28,'copy'+tag)
            a.label('mode3'+tag);a.db(0xF2,0xE6,3,0xFE,3);a.jr(0x20,'mode3'+tag)
            a.label('mode0'+tag);a.db(0xF2,0x0F);a.jr(0x38,'mode0'+tag)
            a.label('copy'+tag)
            for i in range(6):
                source=0xC1A0+row*24+group*6+i
                a.db(0x1A,0x13 if source&255==255 else 0x1C,0x22)
            a.db(0xFB)
        if static_rows:
            # Entry L=0; every row advances exactly 32 cells. This unrolled
            # routine knows the low byte and all three page crossings.
            a.db(0x2E, ((row+1)*32)&255)
            if row%8 == 7:a.db(0x24)
        else:
            a.db(0x7D,0xC6,8,0x6F);a.jr(0x30,'next'+str(row))
            a.db(0x24);a.label('next'+str(row))
    a.db(0xC1,0x0E,0,0xAF,0x3C,0xC9)
    a.label('fallback');a.db(0xAF,0x3E,1,0xC9)
    return a.finish()

def build(source):
    if hashlib.sha256(source).hexdigest()!=SHA:raise ValueError('wrong r404')
    code=service();previous=old.service()
    assert 0x6C80+len(code)<=0x8000
    assert source[OFFSET:OFFSET+len(previous)]==previous
    assert source[OFFSET+len(previous):OFFSET+len(code)]==b'\xff'*(len(code)-len(previous))
    rom=bytearray(source);rom[OFFSET:OFFSET+len(code)]=code
    old.prior.update_checksums(rom)
    return bytes(rom)

if __name__=='__main__':
    rom=build(BASE.read_bytes());OUT.mkdir(parents=True,exist_ok=True)
    target=OUT/'candidate.gb'
    if target.exists() and target.read_bytes()!=rom:raise SystemExit('candidate collision')
    target.write_bytes(rom)
    receipt=dict(experimental=True,promotable=False,base_sha256=SHA,
                 candidate_sha256=hashlib.sha256(rom).hexdigest(),service_size=len(service()))
    (OUT/'build-receipt.json').write_text(json.dumps(receipt,indent=2)+'\n')
    print(receipt)
