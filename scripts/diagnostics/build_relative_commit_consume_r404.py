#!/usr/bin/env python3
"""Consume relative page snapshots exactly once, like absolute commits."""
import hashlib
import json
import build_six_line_dma_r403 as prior
ROOT=prior.ROOT
BASE=ROOT/'tmp/six-line-dma-r403/candidate.gb'
SHA='ed51cfd5297bb5f35a610943df6b87e2664b361aeb87099138d23d29a9bc3909'
OUT=ROOT/'tmp/relative-commit-consume-r404'
OFFSET=0x3745B
OLD=bytes.fromhex('F0 40 EE 48 E0 40 C3 1D 6F')
# Fits the existing slot. Fall through the unchanged guard: either its LY
# rejection exits directly, or cleared READY makes $7400 exit to $6F1D.
# ISR already has IME disabled. No new RAM, code cave, or partial publication.
NEW=bytes.fromhex('AF E0 C4 F0 40 EE 48 E0 40')
GUARD=bytes.fromhex('F0 44 E6 FC FE 90 C2 1D 6F F0 C4 E6 40 C3 00 74')
def build(source):
    if hashlib.sha256(source).hexdigest()!=SHA:raise ValueError('wrong r403')
    assert source[OFFSET:OFFSET+9]==OLD
    assert source[OFFSET+9:OFFSET+9+len(GUARD)]==GUARD
    assert source[0x37400:0x37403]==bytes.fromhex('CA 1D 6F')
    rom=bytearray(source);rom[OFFSET:OFFSET+9]=NEW
    prior.prior.prior.dma.update_checksums(rom)
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
