#!/usr/bin/env python3
"""Combine native aligned increments with the proven shorter pointer formula.

Earlier pointer-only timing was worse; this remains an independently measured
experiment on r421, not an assumed additive speed improvement.
"""
import hashlib
import json
from build_native_metatile_increment_r421 import ROOT, update_checksums
from build_metatile_pointer_r406 import OLD, NEW
BASE=ROOT/'tmp/native-metatile-increment-r421/candidate.gb'
SHA='b67fd8f4bdd20991c4dda6d524b5d1c94790f19a81971ffdd0552b7b24053132'
OUT=ROOT/'tmp/native-pointer-increment-r423'
SITE=0x63314
def build(source):
    if hashlib.sha256(source).hexdigest()!=SHA:raise ValueError('wrong exact r421')
    assert source[SITE:SITE+len(OLD)]==OLD
    assert source[SITE+len(OLD):SITE+len(OLD)+4]==bytes.fromhex('6B 62 0A 0C')
    rom=bytearray(source);rom[SITE:SITE+len(OLD)]=NEW
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
