#!/usr/bin/env python3
"""Inline all576 attribute lookups; preserve padding and source crossings."""
import hashlib
import json
import build_precompile_abi_r409 as prior
from build_later_hdma_overlap import Asm
ROOT=prior.ROOT
BASE=ROOT/'tmp/precompile-abi-r409/candidate.gb'
SHA='bb2468ccaafc65c713b169eed9288aeee70e11769b085174ffa30a686721adf5'
OUT=ROOT/'tmp/bulk-attributes-r410'
OFFSET=28*0x4000+0x2C80
def bulk():
    a=Asm(0x6C80)
    for row in range(24):
        for col in range(24):
            source=0xC1A0+row*24+col
            a.db(0x1A,0x13 if source&255==255 else 0x1C,0x4F,0x0A,0x22)
        a.db(0x7D,0xC6,8,0x6F);a.jr(0x30,'next'+str(row))
        a.db(0x24);a.label('next'+str(row))
    # Fixed mapper0847 returns to bank26's precompile helper, stillSVBK3.
    a.db(0x3E,26,0xC9)
    return a.finish()
def build(source):
    if hashlib.sha256(source).hexdigest()!=SHA:raise ValueError('wrong r409')
    old=prior.prior.helper();new=prior.prior.helper(bulk_bank=28);code=bulk()
    assert source[prior.prior.OFFSET:prior.prior.OFFSET+len(old)]==old
    assert len(new)<=len(old) and 0x6C80+len(code)<=0x8000
    assert source[OFFSET:OFFSET+len(code)]==b'\xff'*len(code)
    rom=bytearray(source)
    rom[prior.prior.OFFSET:prior.prior.OFFSET+len(old)]=new+b'\xff'*(len(old)-len(new))
    rom[OFFSET:OFFSET+len(code)]=code
    prior.prior.copy.old.prior.update_checksums(rom)
    return bytes(rom)
if __name__=='__main__':
    rom=build(BASE.read_bytes());OUT.mkdir(parents=True,exist_ok=True)
    target=OUT/'candidate.gb'
    if target.exists() and target.read_bytes()!=rom:raise SystemExit('candidate collision')
    target.write_bytes(rom)
    receipt=dict(experimental=True,promotable=False,base_sha256=SHA,candidate_sha256=hashlib.sha256(rom).hexdigest(),bulk_size=len(bulk()))
    (OUT/'build-receipt.json').write_text(json.dumps(receipt,indent=2)+'\n');print(receipt)
