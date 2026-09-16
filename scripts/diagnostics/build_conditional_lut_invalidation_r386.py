#!/usr/bin/env python3
"""Invalidate both Stage-1 pages only when the four wall LUT bytes change."""
from pathlib import Path
import hashlib
import json
from build_later_hdma_overlap import Asm
from build_stage1_fast_final_window_selector_r363 import update_checksums

ROOT = Path(__file__).resolve().parents[2]
BASE = ROOT / 'tmp/exact-source-dirty-r385/candidate.gb'
BASE_SHA = '9712f93bd83cadc601e85d71e6358264748e03997c1893335e959bf2eb97ad4e'
OUT = ROOT / 'tmp/conditional-lut-invalidation-r386'
SITES = (0xC624, 0xC627, 0xC630, 0xC633)
ENTRY = 21*0x4000+0x2C90
CAVE = 21*0x4000+0x3D00
OLD = bytes.fromhex('EA 24 C6 EA 27 C6 EA 30 C6 EA 33 C6 3E FF EA 53 DF EA 57 DF')


def helper():
    a = Asm(0x7D00)
    a.db(0xF5, 0xC5, 0x47)
    for address in SITES:
        a.db(0xFA, address & 255, address >> 8, 0xB8)
        a.jr(0x20, 'changed')
    a.jr(0x18, 'done')
    a.label('changed')
    a.db(0x78)
    for address in SITES:
        a.db(0xEA, address & 255, address >> 8)
    a.db(0x3E, 0xFF, 0xEA, 0x53, 0xDF, 0xEA, 0x57, 0xDF)
    a.label('done')
    a.db(0xC1, 0xF1, 0xC9)
    return a.finish()


CODE = helper()


def build(source):
    if hashlib.sha256(source).hexdigest() != BASE_SHA:
        raise ValueError('wrong exact r385 base')
    assert source[ENTRY:ENTRY+len(OLD)] == OLD
    assert source[ENTRY-16:ENTRY] == bytes.fromhex('E5 F0 BA B7 20 1E F8 07 7E 3D 3E 00 20 02 3E 06')
    assert source[ENTRY+len(OLD):ENTRY+len(OLD)+2] == bytes.fromhex('3E 12')
    assert source[CAVE:CAVE+len(CODE)] == b'\xff'*len(CODE)
    rom = bytearray(source)
    rom[ENTRY:ENTRY+len(OLD)] = bytes.fromhex('CD 00 7D') + bytes(len(OLD)-3)
    rom[CAVE:CAVE+len(CODE)] = CODE
    update_checksums(rom)
    return bytes(rom)


if __name__ == '__main__':
    rom = build(BASE.read_bytes())
    OUT.mkdir(parents=True, exist_ok=True)
    target = OUT / 'candidate.gb'
    if target.exists() and target.read_bytes() != rom:
        raise SystemExit('candidate collision')
    target.write_bytes(rom)
    receipt = {'schema': 'penta-conditional-lut-invalidation-r386-build-v1',
               'experimental': True, 'promotable': False, 'live_tested': False,
               'base_sha256': BASE_SHA, 'candidate_sha256': hashlib.sha256(rom).hexdigest()}
    (OUT / 'build-receipt.json').write_text(json.dumps(receipt, indent=2)+'\n')
    print(receipt['candidate_sha256'])
