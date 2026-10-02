#!/usr/bin/env python3
"""Inline the completed-art return before the existing early VBlank call."""
from pathlib import Path
import hashlib
import json
from build_later_hdma_overlap import Asm
from build_stage1_fast_final_window_selector_r363 import update_checksums

ROOT = Path(__file__).resolve().parents[2]
BASE = ROOT/'tmp/source-reload-r395/candidate.gb'
BASE_SHA = '6a9df65b934be690099c638fd00280abe6d015ac18a6b63b775eed03bba8a6e7'
OUT = ROOT/'tmp/art-done-inline-r396'
START = 13*0x4000+0x2ED3
OLD = bytes.fromhex('FA FD DC B7 C4 0E 6A C3 00 71')


def stub():
    a=Asm(0x6ED3)
    a.db(0xFA,0x5B,0xDF,0x3C,0xE6,3)
    a.jr(0x28,'done')
    a.db(0xFA,0xFD,0xDC,0xB7,0xC4,0x0E,0x6A)
    a.label('done')
    a.db(0xC3,0,0x71)
    return a.finish()


def build(source):
    if hashlib.sha256(source).hexdigest()!=BASE_SHA:
        raise ValueError('wrong exact r395 base')
    code=stub()
    assert source[START:START+len(OLD)]==OLD
    assert source[START+len(OLD):START+len(code)]==bytes.fromhex('18 00 18 00 18 00 18 00')
    assert source[0x36A0E:0x36A17]==bytes.fromhex('FA 5B DF 3C E6 03 28 E1 FA')
    # Incoming A/flags are dead at the unchanged death/story helper.
    assert source[0x37100:0x37105]==bytes.fromhex('FA 80 D8 FE 17')
    # The other prelude branch bypasses the entire sled, not just OLD.
    assert source[0x36EC4:0x36EC6]==bytes.fromhex('18 2E')
    rom=bytearray(source)
    rom[START:START+len(code)]=code
    update_checksums(rom)
    return bytes(rom)


if __name__=='__main__':
    rom=build(BASE.read_bytes())
    OUT.mkdir(parents=True,exist_ok=True)
    target=OUT/'candidate.gb'
    if target.exists() and target.read_bytes()!=rom:
        raise SystemExit('candidate collision')
    target.write_bytes(rom)
    receipt=dict(experimental=True,promotable=False,base_sha256=BASE_SHA,
                 candidate_sha256=hashlib.sha256(rom).hexdigest())
    (OUT/'build-receipt.json').write_text(json.dumps(receipt,indent=2)+'\n')
    print(receipt)
