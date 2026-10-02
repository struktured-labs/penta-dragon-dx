#!/usr/bin/env python3
"""Isolate native-group acceleration to the Stage1 stationary dispatch."""
import hashlib,json
from build_later_hdma_overlap import Asm
from build_native_increment_r416 import ROOT, update_checksums, SITES
BASE=ROOT/'tmp/native-increment-r416/candidate.gb'
SHA='13f34a8f8898fe4fd41c8e3eef695504d28b58c5fd0660e7fbb3afacde430586'
OUT=ROOT/'tmp/private-stationary-copy-r417'
OFFSET=28*0x4000+0x2C80
def service():
    a=Asm(0x6C80)
    a.db(0x11,0xA0,0xC1,0x3E,24)
    a.label('row');a.db(0xF5,0x0E,6)
    a.label('group');a.jp(0xC3,'poll')
    a.label('copy')
    for i in range(4):a.db(0x1A,0x13 if i==3 else 0x1C,0x22)
    a.db(0xFB,0x0D);a.jr(0x20,'group')
    a.db(0x7D,0xC6,8,0x6F);a.jr(0x30,'next')
    a.db(0x24);a.label('next');a.db(0xF1,0x3D);a.jr(0x28,'done')
    a.jr(0x18,'row')
    a.label('done');a.db(0x3E,1,0xC9)
    a.label('poll');a.db(0xF3,0xFA,0x80,0xD8,0xFE,2);a.jr(0x20,'mode3')
    a.db(0xF0,0x44,0xE6,0xF8,0xFE,0x90);a.jr(0x28,'copy')
    a.label('mode3');a.db(0xF0,0x41,0xE6,3,0xFE,3);a.jr(0x20,'mode3')
    a.label('mode0');a.db(0xF0,0x41,0xE6,3);a.jr(0x20,'mode0')
    a.jp(0xC3,'copy');return a.finish()
def build(source):
    if hashlib.sha256(source).hexdigest()!=SHA:raise ValueError('wrong exact r416')
    code=service();assert source[OFFSET:OFFSET+len(code)]==b'\xff'*len(code)
    assert source[0x42C6:0x42CF]==bytes.fromhex('F1 C3 DE 13 00 00 00 00 00')
    rom=bytearray(source)
    for i in SITES:assert source[i]==0x1C;rom[i]=0x13
    rom[0x42C6:0x42CF]=bytes.fromhex('F1 3E 1C CD 47 08 C3 ED 42')
    rom[OFFSET:OFFSET+len(code)]=code
    update_checksums(rom);return bytes(rom)
if __name__=='__main__':
    rom=build(BASE.read_bytes());OUT.mkdir(parents=True,exist_ok=True);p=OUT/'candidate.gb'
    if p.exists() and p.read_bytes()!=rom:raise SystemExit('candidate collision')
    p.write_bytes(rom)
    receipt=dict(experimental=True,promotable=False,base_sha256=SHA,candidate_sha256=hashlib.sha256(rom).hexdigest())
    (OUT/'build-receipt.json').write_text(json.dumps(receipt,indent=2)+'\n');print(receipt)
