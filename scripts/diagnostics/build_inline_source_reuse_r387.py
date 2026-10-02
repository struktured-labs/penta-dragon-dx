#!/usr/bin/env python3
"""Experimental inline change detection and Stage-1 clean-page tile reuse."""
from pathlib import Path
import hashlib
import json
from build_later_hdma_overlap import Asm
from build_stage1_fast_final_window_selector_r363 import update_checksums

ROOT = Path(__file__).resolve().parents[2]
BASE = ROOT / 'tmp/conditional-lut-invalidation-r386/candidate.gb'
BASE_SHA = '06e98bdbe412c7dd709370086eadd20431f9bc6322f7b0dff2ada950c52e82a6'
OUT = ROOT / 'tmp/inline-source-reuse-r387'
CLONE = 24*0x4000+0x3000
FALLBACK = 24*0x4000+0x3300


def original_clone(source):
    code = bytearray(source[CLONE:CLONE+75])
    for old in (0x13BB, 0x13BE):
        i = old-0x1399
        assert code[i:i+3] == bytes.fromhex('CD 00 71')
        code[i:i+3] = bytes.fromhex('0A 03 22')
    i = 0x13C6-0x1399
    assert code[i:i+5] == bytes.fromhex('CD 80 71 00 00')
    code[i:i+5] = bytes.fromhex('0A 03 22 0A 77')
    assert code[-4:] == bytes.fromhex('CD D6 09 C9')
    return bytes(code)


def inline_clone(original):
    a = Asm(0x7000)
    a.db(0xFA, 0x80, 0xD8, 0xFE, 0x02)
    a.jp(0xC2, 'fallback')
    a.db(0xF0, 0xBA, 0xB7)
    a.jp(0xC2, 'fallback')
    a.db(*original[:0x13A8-0x1399])
    a.label('cell')
    a.db(*original[0x13A8-0x1399:0x13BB-0x1399])
    def store(number, advance):
        a.db(0x0A)
        if advance: a.db(0x03)
        a.db(0xBE)
        a.jr(0x28, f'same{number}')
        a.db(0xF5, 0x3E, 0xFF, 0xEA, 0x53, 0xDF, 0xEA, 0x57, 0xDF, 0xF1)
        a.label(f'same{number}')
        a.db(0x22 if advance else 0x77)
    store(0, True); store(1, True)
    a.db(0xE5, 0x11, 0x16, 0x00, 0x19)
    store(2, True); store(3, False)
    a.db(0xE1, *original[0x13CC-0x1399:0x13D0-0x1399])
    # DEC C overwrites Z/N/H; ADD HL,BC below overwrites carry before the
    # outer-loop decision. Per-cell compare flags never escape the routine.
    a.jr(0x20, 'cell')
    a.db(*original[0x13D2-0x1399:0x13DE-0x1399])
    a.jr(0x20, 'cell')
    a.db(*original[-4:])
    a.label('fallback')
    a.db(0xC3, 0x00, 0x73)
    return a.finish()


def fast_finish():
    a = Asm(0x13C0)
    a.db(0xF5, 0xF0, 0xBA, 0xB7)
    a.jr(0x20, 'fallback')
    a.db(0xFA, 0x80, 0xD8, 0xFE, 0x02)
    a.jr(0x20, 'fallback')
    a.db(0xF1, 0x7C, 0xC6, 0x03, 0x67, 0x11, 0xE0, 0xC3,
         0x0E, 0x00, 0xC3, 0xED, 0x42)
    a.label('fallback')
    a.db(0xF1, 0xC3, 0xB8, 0x42)
    return a.finish()


def build(source):
    if hashlib.sha256(source).hexdigest() != BASE_SHA:
        raise ValueError('wrong exact r386 base')
    old = original_clone(source)
    clone, fast = inline_clone(old), fast_finish()
    assert len(clone) < 0x100
    assert source[CLONE+len(old):CLONE+len(clone)] == b'\xff'*(len(clone)-len(old))
    assert source[FALLBACK:FALLBACK+len(old)] == b'\xff'*len(old)
    assert 0x13C0+len(fast) <= 0x13E5
    assert source[0x13C0:0x13C0+len(fast)] == bytes(len(fast))
    assert source[0x42B1:0x42B3] == bytes.fromhex('28 05')
    assert source[0x42C3:0x42C6] == bytes(3)
    rom = bytearray(source)
    rom[CLONE:CLONE+len(clone)] = clone
    rom[FALLBACK:FALLBACK+len(old)] = old
    rom[0x13C0:0x13C0+len(fast)] = fast
    rom[0x42B1:0x42B3] = bytes.fromhex('28 10')
    rom[0x42C3:0x42C6] = bytes.fromhex('C3 C0 13')
    update_checksums(rom)
    return bytes(rom)


if __name__ == '__main__':
    rom = build(BASE.read_bytes())
    OUT.mkdir(parents=True, exist_ok=True)
    target = OUT / 'candidate.gb'
    if target.exists() and target.read_bytes() != rom:
        raise SystemExit('candidate collision')
    target.write_bytes(rom)
    receipt = {'schema': 'penta-inline-source-reuse-r387-build-v1',
               'experimental': True, 'promotable': False, 'live_tested': False,
               'base_sha256': BASE_SHA, 'candidate_sha256': hashlib.sha256(rom).hexdigest()}
    (OUT / 'build-receipt.json').write_text(json.dumps(receipt, indent=2)+'\n')
    print(receipt['candidate_sha256'])
