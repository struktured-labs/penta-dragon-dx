#!/usr/bin/env python3
"""Stage1-only: four-byte-aligned metatiles never carry between source bytes."""
import hashlib
import json
from pathlib import Path
from build_stage1_fast_final_window_selector_r363 import update_checksums

ROOT = Path(__file__).resolve().parents[2]
BASE = ROOT / 'tmp/stage1-pointer-r407/candidate.gb'
SHA = '1438d4d852d802921baa3f5c1e4d51aaa0dd6e000013d295b3d96371d0224c0a'
OUT = ROOT / 'tmp/metatile-increment-r412'
SITES = (0x63440, 0x63451, 0x63467, 0x634A8, 0x634AB, 0x634B3)


def build(source):
    if hashlib.sha256(source).hexdigest() != SHA:
        raise ValueError('wrong exact r407 base')
    rom = bytearray(source)
    for site in SITES:
        assert source[site-1:site+1] == bytes.fromhex('22 03')
        rom[site] = 0x0C  # INC C (4T), replacing INC BC (8T).
    update_checksums(rom)
    return bytes(rom)


if __name__ == '__main__':
    rom = build(BASE.read_bytes())
    OUT.mkdir(parents=True, exist_ok=True)
    target = OUT / 'candidate.gb'
    if target.exists() and target.read_bytes() != rom:
        raise SystemExit('candidate collision')
    target.write_bytes(rom)
    receipt = dict(experimental=True, promotable=False, base_sha256=SHA,
                   candidate_sha256=hashlib.sha256(rom).hexdigest())
    (OUT / 'build-receipt.json').write_text(json.dumps(receipt, indent=2)+'\n')
    print(receipt)
