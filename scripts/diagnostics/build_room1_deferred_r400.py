#!/usr/bin/env python3
"""Experimental deferred DMA only in Stage1 room01, synchronous elsewhere."""
from pathlib import Path
import hashlib
import json
from build_later_hdma_overlap import Asm
from build_stage1_fast_final_window_selector_r363 import update_checksums
import build_deferred_dma_pipeline_r397 as prior

ROOT=Path(__file__).resolve().parents[2]
BASE=ROOT/'tmp/deferred-dma-pipeline-r397b/candidate.gb'
SHA='7f1dcd6e9479e41e0dfa338b0414f0052f88b55bfc268b7aa1f86a0c17d60109'
OUT=ROOT/'tmp/room1-deferred-r400'
PREFIX=bytes.fromhex('F0 BA B7 20 09 F0 BD FE 01 20 03 3E 01 C9')


def packer():
    a=Asm(0x6E00)
    a.db(0xF0,0xC4,0xE6,0x60,0xC0,0xFA,0,0xDC,0xEA,0x5C,0xDF)
    a.db(0xF0,0xC4,0xB7);a.jr(0x28,'relative')
    a.db(0xE6,4,7,7,0xF6,0x80)
    a.label('relative');a.db(0x47)
    a.db(0xF0,1,0x1F,0x3E,0x40);a.jr(0x30,'pack')
    a.db(0xF0,0xBA,0xB7,0x3E,0x40);a.jr(0x20,'pack')
    a.db(0xF0,0xBD,0xFE,1,0x3E,0x40);a.jr(0x20,'pack')
    a.db(0x3E,0x20)
    a.label('pack');a.db(0xB0,0x47,0xFA,2,0xDC,0xE6,15,0xB0,0xE0,0xC4,0xC9)
    return a.finish()


def build(source):
    if hashlib.sha256(source).hexdigest()!=SHA:raise ValueError('wrong r397b')
    rom=bytearray(source)
    start=23*0x4000+0x2C80
    old_prefix=bytes.fromhex('F0 BA B7 20 03 3E 01 C9')
    assert source[start:start+8]==old_prefix
    body=source[start+8:start+8+prior.SYNC_OLD_LEN]
    assert body[-3:]==bytes.fromhex('AF 3C C9')
    end=start+len(PREFIX)+len(body)
    assert source[start+8+len(body):end]==bytes([255])*(len(PREFIX)-8)
    rom[start:end]=PREFIX+body
    start=24*0x4000+0x2E00;old=prior.packer();new=packer()
    assert source[start:start+len(old)]==old
    assert source[start+len(old):start+len(new)]==bytes([255])*(len(new)-len(old))
    rom[start:start+len(new)]=new
    assert source[0x4351:0x4357]==bytes.fromhex('F0 BA B7 C4 F1 DB')
    # Deferred prefix returns Z=1; real DMA returns Z=0. Keep that decision
    # through the mapper and skip only the deferred scanner invocation.
    rom[0x4351:0x4357]=bytes.fromhex('CA 57 43 CD F1 DB')
    update_checksums(rom)
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
