#!/usr/bin/env python3
"""Skip a redundant equal fourth-byte metatile store; retain dirty branch."""
import hashlib,json
from build_private_stationary_copy_r417 import ROOT, update_checksums
BASE=ROOT/'tmp/private-stationary-copy-r417/candidate.gb'
SHA='864d9993378dc07f676fb0413b04674b3f687e523d7de94cfa48a81ce34efcf8'
OUT=ROOT/'tmp/skip-equal-tail-r418'
def build(source):
    if hashlib.sha256(source).hexdigest()!=SHA:raise ValueError('wrong exact r417')
    assert source[0x63468:0x63479]==bytes.fromhex('0A BE 28 0B 3E FF EA 53 DF EA 57 DF C3 B4 74 77 E1')
    rom=bytearray(source);rom[0x6346B]=12;update_checksums(rom);return bytes(rom)
if __name__=='__main__':
    rom=build(BASE.read_bytes());OUT.mkdir(parents=True,exist_ok=True);p=OUT/'candidate.gb'
    if p.exists() and p.read_bytes()!=rom:raise SystemExit('candidate collision')
    p.write_bytes(rom)
    receipt=dict(experimental=True,promotable=False,base_sha256=SHA,candidate_sha256=hashlib.sha256(rom).hexdigest())
    (OUT/'build-receipt.json').write_text(json.dumps(receipt,indent=2)+'\n');print(receipt)
