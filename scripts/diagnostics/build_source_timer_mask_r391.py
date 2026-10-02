#!/usr/bin/env python3
"""Allow the bank-restoring Timer ISR during fixed-WRAM source expansion."""
from pathlib import Path
import hashlib
import json
from build_stage1_fast_final_window_selector_r363 import update_checksums
from build_exact_source_dirty_r385 import TRAMPOLINE

ROOT = Path(__file__).resolve().parents[2]
BASE = ROOT / 'tmp/corrected-source-reuse-r390/candidate.gb'
BASE_SHA = 'dbf34a3714721e790711432472cf28617dee30479e4e38bf4c27e116f5a13938'
OUT = ROOT / 'tmp/source-timer-mask-r391'


def build(source):
    if hashlib.sha256(source).hexdigest() != BASE_SHA:
        raise ValueError('wrong exact r390 base')
    # Timer saves AF/BC/DE/HL and restores ROM bank from FF99. Source
    # expansion uses fixed WRAM with the native WRAM1 stack. Do not enable
    # IME here: preserve the caller's state and only retain its Timer IE bit.
    assert source[0x6B3:0x6D1] == bytes.fromhex(
        'F5 C5 D5 E5 3E 03 EA 00 21 CD 00 40 3E 01 EA 00 21 '
        'CD 79 0D F0 99 EA 00 21 E1 D1 C1 F1 D9')
    assert source[0x9BE:0x9C4] == bytes.fromhex('E0 99 EA 00 21 C9')
    assert source[0x1399:0x1399+len(TRAMPOLINE)] == TRAMPOLINE
    assert TRAMPOLINE[4] == 0xAF
    code = TRAMPOLINE[:4] + bytes.fromhex('E6 04') + TRAMPOLINE[5:]
    assert 0x1399+len(code) <= 0x13C0
    assert source[0x1399+len(TRAMPOLINE)] == 0
    rom = bytearray(source)
    rom[0x1399:0x1399+len(code)] = code
    update_checksums(rom)
    return bytes(rom)


if __name__ == '__main__':
    rom = build(BASE.read_bytes())
    OUT.mkdir(parents=True, exist_ok=True)
    target = OUT / 'candidate.gb'
    if target.exists() and target.read_bytes() != rom:
        raise SystemExit('candidate collision')
    target.write_bytes(rom)
    receipt = {'schema': 'penta-source-timer-mask-r391-build-v1',
               'experimental': True, 'promotable': False, 'live_tested': False,
               'base_sha256': BASE_SHA, 'candidate_sha256': hashlib.sha256(rom).hexdigest()}
    (OUT / 'build-receipt.json').write_text(json.dumps(receipt, indent=2)+'\n')
    print(receipt['candidate_sha256'])
