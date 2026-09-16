#!/usr/bin/env python3
"""Experimental clean-page reuse on the corrected r389 source loop."""
from pathlib import Path
import hashlib
import json
from build_stage1_fast_final_window_selector_r363 import update_checksums

ROOT = Path(__file__).resolve().parents[2]
BASE = ROOT / 'tmp/source-row-reset-r389/candidate.gb'
BASE_SHA = '230c28f9615d2e2a08530782517aa4f353a7625a9e3b849605d7bf705c57a814'
OUT = ROOT / 'tmp/corrected-source-reuse-r390'


def build(source):
    if hashlib.sha256(source).hexdigest() != BASE_SHA:
        raise ValueError('wrong exact r389 base')
    assert source[0x42B1:0x42B3] == bytes.fromhex('28 05')
    assert source[0x42C3:0x42C6] == bytes.fromhex('C3 C0 13')
    rom = bytearray(source)
    rom[0x42B2] = 0x10
    update_checksums(rom)
    return bytes(rom)


if __name__ == '__main__':
    rom = build(BASE.read_bytes())
    OUT.mkdir(parents=True, exist_ok=True)
    target = OUT / 'candidate.gb'
    if target.exists() and target.read_bytes() != rom:
        raise SystemExit('candidate collision')
    target.write_bytes(rom)
    receipt = {'schema': 'penta-corrected-source-reuse-r390-build-v1',
               'experimental': True, 'promotable': False, 'live_tested': False,
               'base_sha256': BASE_SHA, 'candidate_sha256': hashlib.sha256(rom).hexdigest()}
    (OUT / 'build-receipt.json').write_text(json.dumps(receipt, indent=2)+'\n')
    print(receipt['candidate_sha256'])
