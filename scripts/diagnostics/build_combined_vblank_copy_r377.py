#!/usr/bin/env python3
"""Combine exact r376 tile-copy shortcut with r375's bounded DMA wait."""
from pathlib import Path
import hashlib
import json
import build_early_vblank_dma_r375 as dma

ROOT=Path(__file__).resolve().parents[2]
BASE=ROOT/'tmp/vblank-tile-copy-r376/candidate.gb'
BASE_SHA='2768f010eec14788f65e3bfe55eab8aa77c80dbd8aa60dc29b6f5585816c6602'
OUT=ROOT/'tmp/combined-vblank-copy-r377'


def build(source):
    if hashlib.sha256(source).hexdigest()!=BASE_SHA:raise ValueError('wrong r376 base')
    old=dma.prior.dma.SERVICE_CODE.replace(dma.prior.OLD_WAIT,dma.prior.WAIT)
    new=dma.prior.dma.SERVICE_CODE.replace(dma.prior.OLD_WAIT,dma.WAIT)
    offset=dma.prior.dma.SERVICE
    assert source[offset:offset+len(old)]==old
    assert len(new)<=len(old)
    rom=bytearray(source)
    rom[offset:offset+len(old)]=new+b'\xff'*(len(old)-len(new))
    dma.prior.dma.update_checksums(rom)
    return bytes(rom)


if __name__=='__main__':
    rom=build(BASE.read_bytes());OUT.mkdir(parents=True,exist_ok=True)
    target=OUT/'candidate.gb'
    if target.exists() and target.read_bytes()!=rom:raise SystemExit('candidate collision')
    target.write_bytes(rom)
    receipt={'schema':'penta-combined-vblank-copy-r377-build-v1','experimental':True,
             'base_sha256':BASE_SHA,'candidate_sha256':hashlib.sha256(rom).hexdigest(),
             'live_tested':False}
    (OUT/'build-receipt.json').write_text(json.dumps(receipt,indent=2)+'\n')
    print(receipt['candidate_sha256'])
