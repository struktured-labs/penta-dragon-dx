#!/usr/bin/env python3
"""Retain r387 inline detection but restore every native tile copy."""
from pathlib import Path
import hashlib
import json
from build_stage1_fast_final_window_selector_r363 import update_checksums

ROOT = Path(__file__).resolve().parents[2]
BASE = ROOT / 'tmp/inline-source-reuse-r387/candidate.gb'
BASE_SHA = '653d4c25f13d0fd1154528be76dd89cb5f84418d721c9c26631d01b19fa8ef32'
OUT = ROOT / 'tmp/inline-source-control-r388'


def build(source):
    if hashlib.sha256(source).hexdigest() != BASE_SHA:
        raise ValueError('wrong exact r387 base')
    assert source[0x42B1:0x42B3] == bytes.fromhex('28 10')
    rom = bytearray(source)
    rom[0x42B2] = 5
    update_checksums(rom)
    return bytes(rom)


if __name__ == '__main__':
    rom = build(BASE.read_bytes())
    OUT.mkdir(parents=True, exist_ok=True)
    target = OUT / 'candidate.gb'
    if target.exists() and target.read_bytes() != rom:
        raise SystemExit('candidate collision')
    target.write_bytes(rom)
    receipt = {'schema': 'penta-inline-source-control-r388-build-v1',
               'experimental': True, 'promotable': False, 'live_tested': False,
               'base_sha256': BASE_SHA, 'candidate_sha256': hashlib.sha256(rom).hexdigest()}
    (OUT / 'build-receipt.json').write_text(json.dumps(receipt, indent=2)+'\n')
    print(receipt['candidate_sha256'])
