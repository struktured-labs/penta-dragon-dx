#!/usr/bin/env python3
"""Synchronize Stage1 moving publications inside the existing mapped packer."""
import hashlib
import json
from build_stage1_coordinate_wait_r427 import ROOT, BASE, SHA, update_checksums
from build_idempotent_latched_publication_r384 import PACK, PACK_OFFSET
OUT=ROOT/'tmp/stage1-moving-publish-wait-r428'
# Native collision handling clears FFCE on rejected/stationary movement.
# Preserve original no-wait behavior there and for every other stage.
TAIL=bytes.fromhex('F0 BA B7 C0 F0 CE B7 C8 FB F0 C4 CB 77 20 FA F3 C9')
def build(source):
    if hashlib.sha256(source).hexdigest()!=SHA:raise ValueError('wrong exact r426')
    assert source[PACK_OFFSET:PACK_OFFSET+len(PACK)]==PACK
    code=PACK[:-1]+TAIL
    assert source[PACK_OFFSET+len(PACK):PACK_OFFSET+len(code)]==b'\xff'*(len(code)-len(PACK))
    rom=bytearray(source);rom[PACK_OFFSET:PACK_OFFSET+len(code)]=code
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
