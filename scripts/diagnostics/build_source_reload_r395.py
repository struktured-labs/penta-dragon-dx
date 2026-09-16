#!/usr/bin/env python3
"""Remove dirty-store AF stack traffic without changing source-copy order."""
from pathlib import Path
import hashlib
import json
from build_later_hdma_overlap import Asm
from build_inline_source_reuse_r387 import inline_clone, CLONE, FALLBACK
from build_source_row_reset_r389 import OUTER
from build_stage1_fast_final_window_selector_r363 import update_checksums

ROOT = Path(__file__).resolve().parents[2]
BASE = ROOT/'tmp/cold-art-vblank-guard-r392-early-w4/candidate.gb'
BASE_SHA = 'c8f21f0ed47b40b1372e1e2a73d6f526590e5dc4d1b2b2d00b9c1e916e59c5ff'
OUT = ROOT/'tmp/source-reload-r395'


def clone(original):
    a = Asm(0x7000)
    a.db(0xFA,0x80,0xD8,0xFE,2)
    a.jp(0xC2,'fallback')
    a.db(0xF0,0xBA,0xB7)
    a.jp(0xC2,'fallback')
    a.db(*original[:13])
    a.label('row')
    a.db(*original[13:15])  # Reset C to eleven EVERY row.
    a.label('cell')
    a.db(*original[15:34])
    def store(n, advance):
        a.db(0x0A,0xBE)  # Keep BC on the source byte until after the store.
        a.jr(0x28, f'same{n}')
        a.db(0x3E,0xFF,0xEA,0x53,0xDF,0xEA,0x57,0xDF,0x0A)
        a.label(f'same{n}')
        a.db(0x22 if advance else 0x77)
        if advance:
            a.db(0x03)
    store(0,True)
    store(1,True)
    a.db(0xE5,0x11,0x16,0,0x19)
    store(2,True)
    store(3,False)
    a.db(0xE1,*original[51:55])
    a.jr(0x20,'cell')
    a.db(*original[57:69])
    a.jr(0x20,'row')
    a.db(*original[-4:])
    a.label('fallback')
    a.db(0xC3,0,0x73)
    return a.finish()


def build(source):
    if hashlib.sha256(source).hexdigest() != BASE_SHA:
        raise ValueError('wrong exact early-w4 base')
    original = source[FALLBACK:FALLBACK+75]
    old = bytearray(inline_clone(original))
    operand = old.index(OUTER)+len(OUTER)
    old[operand] = (old[operand]-2)&255
    assert source[CLONE:CLONE+len(old)] == old
    new = clone(original)
    assert len(new) <= len(old)
    rom = bytearray(source)
    rom[CLONE:CLONE+len(old)] = new + bytes([255])*(len(old)-len(new))
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
