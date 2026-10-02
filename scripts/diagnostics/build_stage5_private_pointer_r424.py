#!/usr/bin/env python3
"""Isolate the shorter native metatile pointer calculation to Stage5."""
import hashlib
import json
from build_native_pointer_increment_r423 import ROOT, OLD, NEW, update_checksums
BASE=ROOT/'tmp/native-metatile-increment-r421/candidate.gb'
SHA='b67fd8f4bdd20991c4dda6d524b5d1c94790f19a81971ffdd0552b7b24053132'
OUT=ROOT/'tmp/stage5-private-pointer-r424'
DISPATCH=bytes.fromhex('F0 BA FE 04 CA 00 78 C3 00 73')

def build(source):
    if hashlib.sha256(source).hexdigest()!=SHA:raise ValueError('wrong exact r421')
    assert source[0x63089:0x6308C]==bytes.fromhex('C3 00 73')
    original=source[0x63300:0x6334B]
    assert original[:3]==bytes.fromhex('CD CE 09')
    assert original[-4:]==bytes.fromhex('CD D6 09 C9')
    assert original[0x14:0x20]==OLD
    # Only relative internal branches and absolute external CALLs: bytewise
    # relocation preserves all native loop targets and stack behavior.
    clone=original[:0x14]+NEW+original[0x20:]
    assert source[0x63380:0x63380+len(DISPATCH)]==b'\xff'*len(DISPATCH)
    assert source[0x63800:0x63800+len(clone)]==b'\xff'*len(clone)
    rom=bytearray(source)
    rom[0x63089:0x6308C]=bytes.fromhex('C3 80 73')
    rom[0x63380:0x63380+len(DISPATCH)]=DISPATCH
    rom[0x63800:0x63800+len(clone)]=clone
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
