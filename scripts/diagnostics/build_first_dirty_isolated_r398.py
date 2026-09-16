#!/usr/bin/env python3
"""Keep the r395 non-Stage1 instruction path byte-for-byte unchanged."""
import hashlib
import json
import build_first_dirty_source_r397 as r397

BASE = r397.BASE
OUT = r397.ROOT/'tmp/first-dirty-isolated-r398'


def build(source):
    rom = bytearray(r397.build(source))
    code,_ = r397.clone(source[r397.FALLBACK:r397.FALLBACK+75])
    # Both entry predicates occupy fourteen bytes. Their old fallback
    # destination remains live in the untouched r395 clone.
    assert source[r397.CLONE+14:r397.CLONE+17] == bytes.fromhex('CD CE 09')
    assert code[14:17] == bytes.fromhex('CD CE 09')
    rom[r397.CLONE:r397.CLONE+3] = source[r397.CLONE:r397.CLONE+3]
    target = r397.ENTRY+14
    rom[r397.CLONE+14:r397.CLONE+17] = bytes((0xC3,target&255,target>>8))
    r397.update_checksums(rom)
    return bytes(rom)


if __name__=='__main__':
    rom=build(BASE.read_bytes())
    OUT.mkdir(parents=True,exist_ok=True)
    target=OUT/'candidate.gb'
    if target.exists() and target.read_bytes()!=rom:
        raise SystemExit('candidate collision')
    target.write_bytes(rom)
    receipt=dict(experimental=True,promotable=False,base_sha256=r397.BASE_SHA,
                 candidate_sha256=hashlib.sha256(rom).hexdigest())
    (OUT/'build-receipt.json').write_text(json.dumps(receipt,indent=2)+'\n')
    print(receipt)
