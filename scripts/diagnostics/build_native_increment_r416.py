#!/usr/bin/env python3
"""Native four-byte groups: retain wide increment only at possible page crossing."""
import hashlib
import json
from build_stationary_copy_r415 import ROOT, update_checksums
BASE=ROOT/'tmp/stationary-copy-r415/candidate.gb'
SHA='3c3fa4dd1fb1848cad3d6a66435dc0cda1474b60569f70228da5951a5d80057d'
OUT=ROOT/'tmp/native-increment-r416'
SITES=(0x42D0,0x42D3,0x42D6)
def build(source):
    if hashlib.sha256(source).hexdigest()!=SHA:raise ValueError('wrong exact r415')
    assert source[0x42CF:0x42DB]==bytes.fromhex('1A 13 22 1A 13 22 1A 13 22 1A 13 22')
    rom=bytearray(source)
    for i in SITES:rom[i]=0x1C
    update_checksums(rom);return bytes(rom)
if __name__=='__main__':
    rom=build(BASE.read_bytes());OUT.mkdir(parents=True,exist_ok=True)
    p=OUT/'candidate.gb'
    if p.exists() and p.read_bytes()!=rom:raise SystemExit('candidate collision')
    p.write_bytes(rom)
    receipt=dict(experimental=True,promotable=False,base_sha256=SHA,candidate_sha256=hashlib.sha256(rom).hexdigest())
    (OUT/'build-receipt.json').write_text(json.dumps(receipt,indent=2)+'\n');print(receipt)
