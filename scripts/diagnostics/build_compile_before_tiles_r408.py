#!/usr/bin/env python3
"""Stage1 synchronous compile-before-copy using the existing SVBK3 plane."""
import hashlib
import json
import build_stage1_pointer_r407 as prior
import build_six_tile_groups_r405 as copy
from build_later_hdma_overlap import Asm
ROOT=prior.ROOT
BASE=ROOT/'tmp/stage1-pointer-r407/candidate.gb'
SHA='1438d4d852d802921baa3f5c1e4d51aaa0dd6e000013d295b3d96371d0224c0a'
OUT=ROOT/'tmp/compile-before-tiles-r408'
HELPER=0x7C00
OFFSET=26*0x4000+HELPER-0x4000
CONTEXT=bytes.fromhex('F0 B7 FE 02 20 1E FA 80 D8 E6 F6 FE 02 20 15 F0 E5 3D 3E 00 20 02 3E 06 EA 24 C6 EA 27 C6 EA 30 C6 EA 33 C6')
def helper(bulk_bank=None):
    a=Asm(HELPER)
    a.db(0xF0,1,0xE6,1,0xC8,0xF0,0xE0,0xFE,3,0xC8)
    a.db(0xF3,0xC5,0xE5,*CONTEXT)
    # No preexisting stack data is accessed while bank3 is mapped. Only
    # the fresh D400 CALL/RET pair uses its scratch stack; IRQs remain off.
    a.db(0x3E,3,0xE0,0x70,0x11,0xA0,0xC1,0x21,0,0xD0,0x06,0xC6,
         0x3E,24,0xE0,0xE0)
    if bulk_bank is None:
        a.label('row');a.db(0xCD,0,0xD4,0x7D,0xC6,8,0x6F);a.jr(0x30,'next')
        a.db(0x24);a.label('next');a.db(0xF0,0xE0,0x3D,0xE0,0xE0);a.jr(0x20,'row')
    else:
        a.db(0x3E,bulk_bank,0xCD,0x47,0x08)
    a.db(0x3E,1,0xE0,0x70,0xE1,0xC1,0x3E,3,0xE0,0xE0,0xC9)
    return a.finish()
def build(source):
    if hashlib.sha256(source).hexdigest()!=SHA:raise ValueError('wrong r407')
    assert source[0x7AC83:0x7ACA7]==CONTEXT
    old=copy.service();new=copy.service(HELPER);code=helper()
    assert copy.OFFSET+len(new)<=OFFSET
    assert source[copy.OFFSET:copy.OFFSET+len(old)]==old
    assert source[copy.OFFSET+len(old):copy.OFFSET+len(new)]==b'\xff'*(len(new)-len(old))
    assert source[OFFSET:OFFSET+len(code)]==b'\xff'*len(code)
    rom=bytearray(source);rom[copy.OFFSET:copy.OFFSET+len(new)]=new;rom[OFFSET:OFFSET+len(code)]=code
    copy.old.prior.update_checksums(rom)
    return bytes(rom)
if __name__=='__main__':
    rom=build(BASE.read_bytes());OUT.mkdir(parents=True,exist_ok=True)
    target=OUT/'candidate.gb'
    if target.exists() and target.read_bytes()!=rom:raise SystemExit('candidate collision')
    target.write_bytes(rom)
    receipt=dict(experimental=True,promotable=False,base_sha256=SHA,
                 candidate_sha256=hashlib.sha256(rom).hexdigest())
    (OUT/'build-receipt.json').write_text(json.dumps(receipt,indent=2)+'\n')
    print(receipt)
