#!/usr/bin/env python3
"""NON-PROMOTABLE timing control: omit the legacy scanner, retain its tail.

This deliberately removes work without proving equivalence. Never deploy it.
"""
from pathlib import Path
import hashlib
import json
from build_stage1_fast_final_window_selector_r363 import update_checksums

ROOT=Path(__file__).resolve().parents[2]
BASE=ROOT/'tmp/deferred-commit-guard-r374/candidate.gb'
BASE_SHA='85b390e48d1d8405acc1f03dee3de8944610e35206f9dbd53be1c0e3e6682922'
OUT=ROOT/'tmp/NON-PROMOTABLE-scanner-control-r378'
OFFSET=19*0x4000+0x21B7


def build(source):
    if hashlib.sha256(source).hexdigest()!=BASE_SHA:raise ValueError('wrong r374 base')
    assert source[OFFSET:OFFSET+5]==bytes.fromhex('11 A0 C1 06 18')
    rom=bytearray(source)
    # Tail $55C0 restores the saved map base and original CALL frame itself.
    # No scanner-local PUSH is outstanding at this entry.
    rom[OFFSET:OFFSET+3]=bytes.fromhex('C3 C0 55')
    update_checksums(rom)
    return bytes(rom)


if __name__=='__main__':
    rom=build(BASE.read_bytes());OUT.mkdir(parents=True,exist_ok=True)
    target=OUT/'DO-NOT-DEPLOY.gb'
    if target.exists() and target.read_bytes()!=rom:raise SystemExit('candidate collision')
    target.write_bytes(rom)
    receipt={'schema':'penta-scanner-timing-control-r378-v1',
             'status':'NON_PROMOTABLE_TIMING_CONTROL','promotable':False,
             'base_sha256':BASE_SHA,'rom_sha256':hashlib.sha256(rom).hexdigest(),
             'removed_work':'legacy 24-row hazard scanner; equivalence NOT proved'}
    (OUT/'build-receipt.json').write_text(json.dumps(receipt,indent=2)+'\n')
    print(receipt['rom_sha256'])
