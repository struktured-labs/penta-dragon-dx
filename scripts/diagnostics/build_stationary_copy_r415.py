#!/usr/bin/env python3
"""Conditional native unchanged-map copy based on native FFCE movement result."""
import hashlib
import json
from build_native_equal_copy_r414 import BASE, SHA, ROOT, update_checksums
OUT=ROOT/'tmp/stationary-copy-r415'
OFFSET=27*0x4000+0x2C80
# A=1 returns through the established mapper to bank1. Zero FFCE leaves Z;
# moving case recreates synthetic copy-end HL/DE/C, then returns NZ.
HELPER=bytes.fromhex('F0 CE B7 28 09 7C C6 03 67 11 E0 C3 0E 00 3E 01 C9')
ENTRY=bytes.fromhex('3E 1B CD 47 08 CA C6 42 F1 C3 ED 42 00')
NATIVE=bytes.fromhex('F1 C3 DE 13')

def build(source):
    if hashlib.sha256(source).hexdigest()!=SHA:raise ValueError('wrong exact r412 base')
    assert source[0x13CD:0x13DA]==bytes.fromhex('F1 7C C6 03 67 11 E0 C3 0E 00 C3 ED 42')
    assert source[0x42C6:0x42CA]==bytes(4)
    assert source[OFFSET:OFFSET+len(HELPER)]==b'\xff'*len(HELPER)
    rom=bytearray(source);rom[0x13CD:0x13DA]=ENTRY
    rom[0x42C6:0x42CA]=NATIVE;rom[OFFSET:OFFSET+len(HELPER)]=HELPER
    update_checksums(rom);return bytes(rom)

if __name__=='__main__':
    rom=build(BASE.read_bytes());OUT.mkdir(parents=True,exist_ok=True)
    target=OUT/'candidate.gb'
    if target.exists() and target.read_bytes()!=rom:raise SystemExit('candidate collision')
    target.write_bytes(rom)
    receipt=dict(experimental=True,promotable=False,base_sha256=SHA,candidate_sha256=hashlib.sha256(rom).hexdigest())
    (OUT/'build-receipt.json').write_text(json.dumps(receipt,indent=2)+'\n');print(receipt)
