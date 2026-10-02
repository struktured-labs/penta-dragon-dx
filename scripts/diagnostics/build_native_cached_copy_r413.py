#!/usr/bin/env python3
"""Experimental native tile-copy fallback for cached Stage1 attribute planes."""
import hashlib
import json
import build_six_tile_groups_r405 as copier
from build_metatile_increment_r412 import ROOT, update_checksums

BASE = ROOT/'tmp/metatile-increment-r412/candidate.gb'
SHA = 'c558d9559dbdcc15c3ad8eb6a100eddfd4546529e2e4faaaf029f064e9edce36'
OUT = ROOT/'tmp/native-cached-copy-r413'


def build(source):
    if hashlib.sha256(source).hexdigest() != SHA:
        raise ValueError('wrong exact r412 base')
    old, new = copier.service(), copier.service(native_cached=True)
    offset = copier.OFFSET
    assert source[offset:offset+len(old)] == old
    assert source[offset+len(old):offset+len(new)] == b'\xff'*(len(new)-len(old))
    rom = bytearray(source)
    rom[offset:offset+len(new)] = new
    update_checksums(rom)
    return bytes(rom)


if __name__ == '__main__':
    rom = build(BASE.read_bytes()); OUT.mkdir(parents=True, exist_ok=True)
    target = OUT/'candidate.gb'
    if target.exists() and target.read_bytes() != rom:
        raise SystemExit('candidate collision')
    target.write_bytes(rom)
    receipt = dict(experimental=True, promotable=False, base_sha256=SHA,
                   candidate_sha256=hashlib.sha256(rom).hexdigest())
    (OUT/'build-receipt.json').write_text(json.dumps(receipt,indent=2)+'\n')
    print(receipt)
