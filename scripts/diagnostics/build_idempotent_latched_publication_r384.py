#!/usr/bin/env python3
"""Keep an already-queued page/scroll snapshot intact on repeated requests."""
from pathlib import Path
import hashlib
import json
from build_stage1_fast_final_window_selector_r363 import update_checksums
from build_latched_publication_r383 import PACK as OLD_PACK, PACK_OFFSET

ROOT = Path(__file__).resolve().parents[2]
BASE = ROOT / 'tmp/latched-publication-r383/candidate.gb'
BASE_SHA = '0ee7d3947260967c1b36e7b9795bd109797a49ac4392ded8186a82c66b818930'
OUT = ROOT / 'tmp/idempotent-latched-publication-r384'
PACK = bytes.fromhex('F0 C4 CB 77 C0') + OLD_PACK


def build(source):
    if hashlib.sha256(source).hexdigest() != BASE_SHA:
        raise ValueError('wrong exact r383 base')
    assert source[PACK_OFFSET:PACK_OFFSET+len(PACK)] == OLD_PACK + b'\xff'*5
    rom = bytearray(source)
    rom[PACK_OFFSET:PACK_OFFSET+len(PACK)] = PACK
    update_checksums(rom)
    return bytes(rom)


if __name__ == '__main__':
    rom = build(BASE.read_bytes())
    OUT.mkdir(parents=True, exist_ok=True)
    target = OUT / 'candidate.gb'
    if target.exists() and target.read_bytes() != rom:
        raise SystemExit('candidate collision')
    target.write_bytes(rom)
    receipt = {'schema': 'penta-idempotent-latched-publication-r384-build-v1',
               'experimental': True, 'promotable': False, 'live_tested': False,
               'base_sha256': BASE_SHA, 'candidate_sha256': hashlib.sha256(rom).hexdigest()}
    (OUT / 'build-receipt.json').write_text(json.dumps(receipt, indent=2)+'\n')
    print(receipt['candidate_sha256'])
