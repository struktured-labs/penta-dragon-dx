#!/usr/bin/env python3
"""Correct the relocated source loop: each row must reset C to eleven."""
from pathlib import Path
import hashlib
import json
from build_stage1_fast_final_window_selector_r363 import update_checksums

ROOT = Path(__file__).resolve().parents[2]
BASE = ROOT / 'tmp/inline-source-control-r388/candidate.gb'
BASE_SHA = '9302fee5fa1533c9996b3a154b3639610e11886aa86ed839c60866f6e6246438'
OUT = ROOT / 'tmp/source-row-reset-r389'
CLONE = 24*0x4000+0x3000
OUTER = bytes.fromhex('78 01 1A 00 09 13 13 13 13 13 47 05 20')


def build(source):
    if hashlib.sha256(source).hexdigest() != BASE_SHA:
        raise ValueError('wrong exact r388 base')
    code = source[CLONE:CLONE+256]
    assert code.count(OUTER) == 1
    operand = code.index(OUTER)+len(OUTER)
    target = operand+1+int.from_bytes(code[operand:operand+1], 'little', signed=True)
    assert code[target-2:target+1] == bytes.fromhex('0E 0B C5')
    rom = bytearray(source)
    rom[CLONE+operand] = (code[operand]-2) & 255
    update_checksums(rom)
    return bytes(rom)


if __name__ == '__main__':
    rom = build(BASE.read_bytes())
    OUT.mkdir(parents=True, exist_ok=True)
    target = OUT / 'candidate.gb'
    if target.exists() and target.read_bytes() != rom:
        raise SystemExit('candidate collision')
    target.write_bytes(rom)
    receipt = {'schema': 'penta-source-row-reset-r389-build-v1',
               'experimental': True, 'promotable': False, 'live_tested': False,
               'base_sha256': BASE_SHA, 'candidate_sha256': hashlib.sha256(rom).hexdigest()}
    (OUT / 'build-receipt.json').write_text(json.dumps(receipt, indent=2)+'\n')
    print(receipt['candidate_sha256'])
