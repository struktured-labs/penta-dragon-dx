#!/usr/bin/env python3
"""Experimental late-VBlank deferral; preserve pending work on rejection."""
from pathlib import Path
import hashlib
import json
from build_stage1_fast_final_window_selector_r363 import update_checksums

ROOT = Path(__file__).resolve().parents[2]
BASE = ROOT / 'tmp/interrupt-checked-vblank-r373/candidate.gb'
BASE_SHA = '21b03a23a447f6990c72bcb5723c3733d1e45153ce97c0939b80707ba44d0a21'
OUT = ROOT / 'tmp/deferred-commit-guard-r374'
ENTRY = 0x373FC
CAVE = 0x37464
# Called inside the native ISR with IME disabled. Accept LY144..147 only,
# leaving six complete VBlank lines for the palette/scroll/map transaction.
# A late entry jumps to the existing ISR continuation without clearing DF5C,
# FFE1 or FFC4. No wait, EI, stack manipulation, or graphics write occurs here.
GUARD = bytes.fromhex('F0 44 E6 FC FE 90 C2 1D 6F FA 5C DF B7 C3 00 74')


def build(source):
    if hashlib.sha256(source).hexdigest() != BASE_SHA:
        raise ValueError('wrong exact r373 base')
    assert source[ENTRY:ENTRY+4] == bytes.fromhex('FA 5C DF B7')
    assert source[CAVE:CAVE+len(GUARD)] == bytes(len(GUARD))
    rom = bytearray(source)
    rom[ENTRY:ENTRY+4] = bytes.fromhex('C3 64 74 00')
    rom[CAVE:CAVE+len(GUARD)] = GUARD
    update_checksums(rom)
    return bytes(rom)


if __name__ == '__main__':
    rom = build(BASE.read_bytes())
    OUT.mkdir(parents=True, exist_ok=True)
    target = OUT / 'candidate.gb'
    if target.exists() and target.read_bytes() != rom:
        raise SystemExit('refusing to overwrite different candidate')
    target.write_bytes(rom)
    receipt = {'schema': 'penta-deferred-commit-guard-r374-build-v1',
               'base_sha256': BASE_SHA,
               'candidate_sha256': hashlib.sha256(rom).hexdigest(),
               'experimental': True, 'live_tested': False,
               'guard_hex': GUARD.hex()}
    (OUT / 'build-receipt.json').write_text(json.dumps(receipt, indent=2)+'\n')
    print(receipt['candidate_sha256'])
