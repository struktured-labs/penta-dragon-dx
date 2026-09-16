#!/usr/bin/env python3
"""Experimental synchronous 48-block GDMA admission through LY149.

Worst remaining time after sampling LY149 is four complete lines (1824
dots). DMA takes1536 dots; setup from the protected read through FF55
takes less than224 normal-speed dots, leaving a conservative64-dot margin.
Keep the post-DI recheck and original transfer/publication order.
"""
import hashlib
import json
import build_early_vblank_dma_r375 as prior

ROOT=prior.ROOT
BASE=ROOT/'tmp/five-tile-groups-r402/candidate.gb'
SHA='728ae2a750b35c8e373f76d15909883ca97298c86c00cfb4bacfe4b1e1fa69bb'
OUT=ROOT/'tmp/six-line-dma-r403'
WAIT=prior.WAIT.replace(bytes.fromhex('E6 FC FE 90 20'),bytes.fromhex('D6 90 FE 06 30')).replace(
    bytes.fromhex('E6 FC FE 90 28'),bytes.fromhex('D6 90 FE 06 38'))

def build(source):
    if hashlib.sha256(source).hexdigest()!=SHA:raise ValueError('wrong r402')
    service=prior.prior.dma.SERVICE
    old=prior.prior.dma.SERVICE_CODE.replace(prior.prior.OLD_WAIT,prior.WAIT)
    assert source[service:service+len(old)]==old
    new=old.replace(prior.WAIT,WAIT)
    assert len(new)==len(old)
    rom=bytearray(source);rom[service:service+len(new)]=new
    prior.prior.dma.update_checksums(rom)
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
