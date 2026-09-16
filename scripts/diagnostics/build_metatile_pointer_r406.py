#!/usr/bin/env python3
"""Compute A000+4*tile in BC without the temporary 16-bit HL arithmetic."""
import hashlib
import json
import build_six_tile_groups_r405 as prior
ROOT=prior.ROOT
BASE=ROOT/'tmp/six-tile-groups-r405/candidate.gb'
SHA='79e83ac5f63fe51d2c68fe3f3f3c7e2123c5607018ee381e76b48e18129a053b'
OUT=ROOT/'tmp/metatile-pointer-r406'
SITES=(0x63314,0x63422,0x63498)
OLD=bytes.fromhex('6F 26 00 4C 29 29 01 00 A0 09 4D 44')
NEW=bytes.fromhex('4F 07 07 E6 03 F6 A0 47 79 87 87 4F')
def build(source):
    if hashlib.sha256(source).hexdigest()!=SHA:raise ValueError('wrong r405')
    rom=bytearray(source)
    for site in SITES:
        assert source[site:site+12]==OLD
        # Destination HL restored from DE immediately; A then loaded from BC.
        assert source[site+12:site+15]==bytes.fromhex('6B 62 0A')
        rom[site:site+12]=NEW
    prior.old.prior.update_checksums(rom)
    return bytes(rom)
if __name__=='__main__':
    rom=build(BASE.read_bytes());OUT.mkdir(parents=True,exist_ok=True)
    target=OUT/'candidate.gb'
    if target.exists() and target.read_bytes()!=rom:raise SystemExit('candidate collision')
    target.write_bytes(rom)
    receipt=dict(experimental=True,promotable=False,base_sha256=SHA,
                 candidate_sha256=hashlib.sha256(rom).hexdigest())
    (OUT/'build-receipt.json').write_text(json.dumps(receipt,indent=2)+'\n')
    print(receipt)
