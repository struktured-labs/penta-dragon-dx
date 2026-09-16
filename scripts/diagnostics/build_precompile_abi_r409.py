#!/usr/bin/env python3
"""Restore native post-compile state when consuming an early Stage1 plane."""
import hashlib
import json
import build_compile_before_tiles_r408 as prior
from build_later_hdma_overlap import Asm
ROOT=prior.ROOT
BASE=ROOT/'tmp/compile-before-tiles-r408/candidate.gb'
SHA='eb88d01724e3a53076f5262878bbc7786e672b03845d3b2058fd481cb12ba6ce'
OUT=ROOT/'tmp/precompile-abi-r409'
OFFSET=27*0x4000+0x2C80
def helper():
    a=Asm(0x6C80)
    a.db(0xF3,0xF0,0xE0,0xFE,3);a.jr(0x20,'return')
    a.db(0xFA,0x80,0xD8,0xFE,2);a.jr(0x20,'cached')
    a.db(0xF0,0xBA,0xB7);a.jr(0x20,'cached')
    a.db(0xFA,0xDF,0xC3,0x4F,0x06,0xC6,0x21,0,0xD3,0xAF,0xE0,0xE0)
    a.jr(0x18,'return')
    a.label('cached');a.db(0xAF)
    a.label('return');a.db(0x3E,1,0xC9)
    return a.finish()
def build(source):
    if hashlib.sha256(source).hexdigest()!=SHA:raise ValueError('wrong r408')
    assert source[0x42FC:0x4303]==bytes.fromhex('F0 E0 FE 03 28 22 F3')
    code=helper();assert source[OFFSET:OFFSET+len(code)]==b'\xff'*len(code)
    rom=bytearray(source)
    # Same conditional skip destination, but precompiled state normalized.
    rom[0x42FC:0x4303]=bytes.fromhex('3E 1B CD 47 08 28 21')
    # DI displaced by the longer mapper call is the helper's first opcode.
    # Preserve original LD DE at4303 and remaining code.
    rom[OFFSET:OFFSET+len(code)]=code
    prior.copy.old.prior.update_checksums(rom)
    return bytes(rom)
if __name__=='__main__':
    rom=build(BASE.read_bytes());OUT.mkdir(parents=True,exist_ok=True)
    target=OUT/'candidate.gb'
    if target.exists() and target.read_bytes()!=rom:raise SystemExit('candidate collision')
    target.write_bytes(rom)
    receipt=dict(experimental=True,promotable=False,base_sha256=SHA,candidate_sha256=hashlib.sha256(rom).hexdigest())
    (OUT/'build-receipt.json').write_text(json.dumps(receipt,indent=2)+'\n');print(receipt)
