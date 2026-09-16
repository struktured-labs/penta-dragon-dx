#!/usr/bin/env python3
"""Experimental: stop comparing once both source caches are invalidated."""
from pathlib import Path
import hashlib
import json
from build_later_hdma_overlap import Asm
from build_stage1_fast_final_window_selector_r363 import update_checksums
from build_inline_source_reuse_r387 import CLONE, FALLBACK

ROOT = Path(__file__).resolve().parents[2]
BASE = ROOT/'tmp/source-reload-r395/candidate.gb'
BASE_SHA = '6a9df65b934be690099c638fd00280abe6d015ac18a6b63b775eed03bba8a6e7'
OUT = ROOT/'tmp/first-dirty-source-r397'
ENTRY = 0x7400
OFFSET = 24*0x4000 + ENTRY-0x4000


def clone(original):
    a = Asm(ENTRY)
    a.db(0xFA,0x80,0xD8,0xFE,2)
    a.jp(0xC2,'fallback')
    a.db(0xF0,0xBA,0xB7)
    a.jp(0xC2,'fallback')
    a.db(*original[:13])
    for raw in (False, True):
        prefix = 'raw' if raw else 'checked'
        a.label(prefix+'row')
        a.db(*original[13:15])
        a.label(prefix+'cell')
        a.db(*original[15:34])
        for n in range(4):
            if n == 2:
                a.db(0xE5,0x11,0x16,0,0x19)
            if raw:
                a.label('rawstore'+str(n))
                a.db(0x0A)
            else:
                a.db(0x0A,0xBE)
                a.jr(0x28,'same'+str(n))
                a.db(0x3E,0xFF,0xEA,0x53,0xDF,0xEA,0x57,0xDF)
                a.jp(0xC3,'rawstore'+str(n))
                a.label('same'+str(n))
            a.db(0x22 if n < 3 else 0x77)
            if n < 3:
                a.db(0x03)
        a.db(0xE1,*original[51:55])
        a.jr(0x20,prefix+'cell')
        a.db(*original[57:69])
        a.jr(0x20,prefix+'row')
        a.db(*original[-4:])
    a.label('fallback')
    a.db(0xC3,0,0x73)
    return a.finish(), a.labels


def build(source):
    if hashlib.sha256(source).hexdigest() != BASE_SHA:
        raise ValueError('wrong exact r395 base')
    code, _ = clone(source[FALLBACK:FALLBACK+75])
    assert source[OFFSET:OFFSET+len(code)] == bytes([255])*len(code)
    assert source[CLONE:CLONE+3] == bytes.fromhex('FA 80 D8')
    rom = bytearray(source)
    rom[OFFSET:OFFSET+len(code)] = code
    rom[CLONE:CLONE+3] = bytes((0xC3,ENTRY&255,ENTRY>>8))
    update_checksums(rom)
    return bytes(rom)


if __name__ == '__main__':
    rom = build(BASE.read_bytes())
    OUT.mkdir(parents=True,exist_ok=True)
    target = OUT/'candidate.gb'
    if target.exists() and target.read_bytes() != rom:
        raise SystemExit('candidate collision')
    target.write_bytes(rom)
    receipt = dict(experimental=True,promotable=False,base_sha256=BASE_SHA,
                   candidate_sha256=hashlib.sha256(rom).hexdigest())
    (OUT/'build-receipt.json').write_text(json.dumps(receipt,indent=2)+'\n')
    print(receipt)
