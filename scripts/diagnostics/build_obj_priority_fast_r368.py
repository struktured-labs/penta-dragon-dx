#!/usr/bin/env python3
"""Collapse r365's identical priority-clear branches; retain every caller.

Both old paths restore AF and HL then RES 7,A. RES preserves flags, so
RES 7,A; RET has the same register result without stack saves or HRAM reads.
The remaining helper bytes are retained, not reclaimed as a new code cave.
"""
from pathlib import Path
import hashlib
import json

from build_stage1_sara_priority_clear_r365 import (
    HELPER_START, HELPER_POSTIMAGE, CALL_SITES, CALL, update_checksums,
)

ROOT = Path(__file__).resolve().parents[2]
BASE = ROOT / 'tmp/stage1-sara-priority-clear-r365/candidate.gb'
BASE_SHA = '4243fa84946bc0325ff46b510103c1e1c4213f0879e40b5aff77d026bf69ea88'
OUT = ROOT / 'tmp/obj-priority-fast-r368'


def build(source: bytes) -> bytes:
    if hashlib.sha256(source).hexdigest() != BASE_SHA:
        raise ValueError('wrong exact r365 base')
    assert source[HELPER_START:HELPER_START + len(HELPER_POSTIMAGE)] == HELPER_POSTIMAGE
    assert all(source[p:p+3] == CALL for p in CALL_SITES)
    rom = bytearray(source)
    rom[HELPER_START:HELPER_START+3] = bytes.fromhex('CB BF C9')
    update_checksums(rom)
    return bytes(rom)


if __name__ == '__main__':
    source = BASE.read_bytes()
    rom = build(source)
    OUT.mkdir(parents=True, exist_ok=True)
    target = OUT / 'candidate.gb'
    if target.exists() and target.read_bytes() != rom:
        raise SystemExit('refusing to overwrite different candidate')
    target.write_bytes(rom)
    receipt = {
        'schema': 'penta-obj-priority-fast-r368-build-v1',
        'base_sha256': BASE_SHA,
        'candidate_sha256': hashlib.sha256(rom).hexdigest(),
        'changed_offsets': [i for i, (a,b) in enumerate(zip(source,rom)) if a != b],
        'emulator_tested': False,
    }
    (OUT / 'build-receipt.json').write_text(json.dumps(receipt, indent=2) + '\n')
    print(json.dumps(receipt, indent=2))
