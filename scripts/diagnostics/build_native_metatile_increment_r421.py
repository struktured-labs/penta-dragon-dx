#!/usr/bin/env python3
"""Shorten aligned metatile source increments in the native fallback."""
import hashlib
import json
from build_room_writer_wait_r420 import ROOT, update_checksums

BASE = ROOT / 'tmp/room-writer-wait-r420/candidate.gb'
SHA = '366ebf308b63c489576c3ff0f34d2bbfcd8838ab25537eed834db467d1733dc9'
OUT = ROOT / 'tmp/native-metatile-increment-r421'
SITES = (0x63323, 0x63326, 0x6332E)

def build(source):
    if hashlib.sha256(source).hexdigest() != SHA:
        raise ValueError('wrong exact r420')
    rom = bytearray(source)
    for site in SITES:
        assert source[site-1:site+2] == bytes.fromhex('0A 03 22')
        rom[site] = 0x0C
    update_checksums(rom)
    return bytes(rom)

if __name__ == '__main__':
    rom = build(BASE.read_bytes())
    OUT.mkdir(parents=True, exist_ok=True)
    target = OUT / 'candidate.gb'
    if target.exists() and target.read_bytes() != rom:
        raise SystemExit('candidate collision')
    target.write_bytes(rom)
    receipt = dict(experimental=True, promotable=False, base_sha256=SHA,
                   candidate_sha256=hashlib.sha256(rom).hexdigest())
    (OUT / 'build-receipt.json').write_text(json.dumps(receipt, indent=2)+'\n')
    print(receipt)
