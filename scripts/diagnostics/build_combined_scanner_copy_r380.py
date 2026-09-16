#!/usr/bin/env python3
"""Combine exact r379 classifier inlining with the disjoint r377 waits."""
from pathlib import Path
import hashlib
import json
import build_inline_hazard_scanner_r379 as scanner
import build_vblank_tile_copy_r376 as tiles
import build_combined_vblank_copy_r377 as waits

ROOT=Path(__file__).resolve().parents[2]
BASE=ROOT/'tmp/inline-hazard-scanner-r379/candidate.gb'
BASE_SHA='084c62ae02b34c09bec94d56d9eb122f9ad0315f4f580f6dc4aba8c2179345e0'
OUT=ROOT/'tmp/combined-scanner-copy-r380'


def build(source, *, reference=None):
    if hashlib.sha256(source).hexdigest()!=BASE_SHA:raise ValueError('wrong r379 base')
    # The source-lineage replay supplies the freshly built r374 checkpoint.
    # Keep the historical standalone entry compatible with its retained input.
    if reference is None:
        reference=scanner.BASE.read_bytes()
    combined=waits.build(tiles.build(reference))
    service=waits.dma.prior.dma.SERVICE
    old=waits.dma.prior.dma.SERVICE_CODE.replace(waits.dma.prior.OLD_WAIT,waits.dma.prior.WAIT)
    spans=((tiles.ENTRY,len(tiles.OLD)),(tiles.CAVE,len(tiles.HELPER)),(service,len(old)))
    rom=bytearray(source)
    for start,size in spans:
        assert source[start:start+size]==reference[start:start+size]
        rom[start:start+size]=combined[start:start+size]
    scanner.update_checksums(rom)
    return bytes(rom)


if __name__=='__main__':
    rom=build(BASE.read_bytes());OUT.mkdir(parents=True,exist_ok=True)
    target=OUT/'candidate.gb'
    if target.exists() and target.read_bytes()!=rom:raise SystemExit('candidate collision')
    target.write_bytes(rom)
    receipt={'schema':'penta-combined-scanner-copy-r380-v1','experimental':True,
             'base_sha256':BASE_SHA,'candidate_sha256':hashlib.sha256(rom).hexdigest(),
             'live_tested':False}
    (OUT/'build-receipt.json').write_text(json.dumps(receipt,indent=2)+'\n')
    print(receipt['candidate_sha256'])
