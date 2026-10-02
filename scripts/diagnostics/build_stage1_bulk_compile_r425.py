#!/usr/bin/env python3
"""Compile Stage1 attributes at the native post-tile point, not early."""
import hashlib
import json
from build_stage5_private_pointer_r424 import ROOT, update_checksums
from build_later_hdma_overlap import Asm
BASE=ROOT/'tmp/stage5-private-pointer-r424/candidate.gb'
SHA='a36469fed9b7a47d5949c867865c13064efa3c575803fb76464698064b7e071b'
OUT=ROOT/'tmp/stage1-bulk-compile-r425'
OFFSET=30*0x4000+0x2D00

def service():
    a=Asm(0x6D00)
    a.db(0xF0,0xBA,0xB7);a.jp(0xC2,'return')
    a.db(0xFA,0x80,0xD8,0xFE,2);a.jp(0xC2,'return')
    # Setup already owns SVBK3 with IRQs disabled. LUT B=C6, source DE=C1A0,
    # destination HL=D000; preserve native 24x24 writes and 8-cell padding.
    for row in range(24):
        for col in range(24):
            address=0xC1A0+row*24+col
            a.db(0x1A,0x13 if address&255==255 else 0x1C,0x4F,0x0A,0x22)
        a.db(0x2E,((row+1)*32)&255)
        if row%8==7:a.db(0x24)
    # Preserve final HL while replacing ONLY the saved bank1 caller return.
    # Stack on entry:084D (mapper),430E (row loop),older frames. No bank swap.
    a.db(0xE5,0xF8,4,0x36,0x24,0x23,0x36,0x43,0xE1)
    a.db(0xAF,0xE0,0xE0)
    a.label('return');a.db(0x3E,1,0xC9)
    return a.finish()

def build(source):
    if hashlib.sha256(source).hexdigest()!=SHA:raise ValueError('wrong exact r424')
    assert source[0x7ACBC:0x7ACBF]==bytes.fromhex('3E 01 C9')
    assert source[0x4303:0x4316]==bytes.fromhex('11 A0 C1 21 00 D0 3E 1E CD 47 08 00 3E 18 E0 E0 CD 00 D4')
    assert source[0x7ACA7:0x7ACBC]==bytes.fromhex('3E 01 EA 09 DC C1 D1 3E 03 E0 70 D5 C5 11 A0 C1 06 C6 F0 E0 4F')
    code=service();assert 0x6D00+len(code)<0x8000
    assert source[OFFSET:OFFSET+len(code)]==b'\xff'*len(code)
    rom=bytearray(source);rom[0x7ACBC:0x7ACBF]=bytes.fromhex('C3 00 6D')
    rom[OFFSET:OFFSET+len(code)]=code
    update_checksums(rom);return bytes(rom)

if __name__=='__main__':
    rom=build(BASE.read_bytes());OUT.mkdir(parents=True,exist_ok=True)
    target=OUT/'candidate.gb'
    if target.exists() and target.read_bytes()!=rom:raise SystemExit('candidate collision')
    target.write_bytes(rom)
    receipt=dict(experimental=True,promotable=False,base_sha256=SHA,
                 candidate_sha256=hashlib.sha256(rom).hexdigest())
    (OUT/'build-receipt.json').write_text(json.dumps(receipt,indent=2)+'\n')
    print(receipt)
