#!/usr/bin/env python3
"""Experimental direct row addresses for the unrolled Stage1 tile copier."""
import hashlib
import json
from build_room_writer_wait_r420 import ROOT, update_checksums
from build_six_tile_groups_r405 import service, OFFSET
BASE = ROOT / 'tmp/room-writer-wait-r420/candidate.gb'
SHA = '366ebf308b63c489576c3ff0f34d2bbfcd8838ab25537eed834db467d1733dc9'
OUT = ROOT / 'tmp/static-copy-rows-r422'

def build(source):
    if hashlib.sha256(source).hexdigest() != SHA:raise ValueError('wrong exact r420')
    old, new = service(), service(static_rows=True)
    assert source[OFFSET:OFFSET+len(old)] == old
    assert len(new) < len(old)
    rom = bytearray(source)
    rom[OFFSET:OFFSET+len(old)] = new + b'\xff'*(len(old)-len(new))
    update_checksums(rom)
    return bytes(rom)

if __name__ == '__main__':
    rom = build(BASE.read_bytes());OUT.mkdir(parents=True,exist_ok=True)
    target = OUT/'candidate.gb'
    if target.exists() and target.read_bytes()!=rom:raise SystemExit('candidate collision')
    target.write_bytes(rom)
    receipt = dict(experimental=True,promotable=False,base_sha256=SHA,
                   candidate_sha256=hashlib.sha256(rom).hexdigest())
    (OUT/'build-receipt.json').write_text(json.dumps(receipt,indent=2)+'\n')
    print(receipt)
