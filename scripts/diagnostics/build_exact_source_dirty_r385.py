#!/usr/bin/env python3
"""Experimental source-write change detection; lifecycle qualification pending.

Reuses Stage-1 DF53/DF57 (A5 clean, anything else dirty), DF54/DF58 room.
No new RAM. Alternate source writers and LUT changes require separate audit.
"""
from pathlib import Path
import hashlib
import json
from build_stage1_fast_final_window_selector_r363 import update_checksums
from build_later_hdma_overlap import Asm

ROOT = Path(__file__).resolve().parents[2]
BASE = ROOT / 'tmp/idempotent-latched-publication-r384/candidate.gb'
BASE_SHA = '4b2316c9724e40102bdfc38e24ad0fc089b5df2746a84043d7d3b61fb92d3e89'
OUT = ROOT / 'tmp/exact-source-dirty-r385'


def offset(bank, address):
    return bank*0x4000+address-0x4000


def store_helper(address, *, advance):
    a = Asm(address)
    a.db(0x0A)
    if advance: a.db(0x03)
    a.db(0xF5, 0xBE)  # preserve the native writer's A/flags
    a.jr(0x28, 'store')
    a.db(0xFA, 0x80, 0xD8, 0xFE, 0x02)
    a.jr(0x20, 'store')
    a.db(0xF0, 0xBA, 0xB7)
    a.jr(0x20, 'store')
    a.db(0x3E, 0xFF, 0xEA, 0x53, 0xDF, 0xEA, 0x57, 0xDF)
    a.label('store')
    a.db(0xF1, 0x22 if advance else 0x77, 0xC9)
    return a.finish()


def decider():
    a = Asm(0x4100)
    a.db(0xFA, 0x80, 0xD8, 0xFE, 0x02)
    a.jp(0xC2, 'fallback')
    a.db(0xF0, 0xBA, 0xB7)
    a.jp(0xC2, 'fallback')
    a.db(0x16, 0xDF, 0x7C, 0xEE, 0xCB, 0x5F, 0x1A, 0xFE, 0xA5)
    a.jr(0x20, 'dirty')
    a.db(0x13, 0x1A, 0x4F, 0xF0, 0xE5, 0xB9, 0x1B)
    a.jr(0x20, 'dirty')
    a.db(0x3E, 0x01, 0xC3, 0x61, 0x00)
    a.label('dirty')
    a.db(0x3E, 0xA5, 0x12, 0x13, 0xF0, 0xE5, 0x12,
         0x3E, 0x01, 0xB7, 0xC3, 0x61, 0x00)
    a.label('fallback')
    a.db(0xC3, 0x00, 0x7E)
    return a.finish()


TRAMPOLINE = bytes.fromhex(
    'C5 F0 FF F5 AF E0 FF 3E 18 CD 61 00 CD 00 70 '
    'EF F5 C1 F1 E0 FF C5 F1 C1 C9')


def build(source):
    if hashlib.sha256(source).hexdigest() != BASE_SHA:
        raise ValueError('wrong exact r384 base')
    original = source[0x1399:0x13E5]
    assert original[-5:] == bytes.fromhex('CD D6 09 EF C9')
    clone = bytearray(original[:-2] + b'\xc9')
    for address in (0x13BB, 0x13BE):
        i = address-0x1399
        assert clone[i:i+3] == bytes.fromhex('0A 03 22')
        clone[i:i+3] = bytes.fromhex('CD 00 71')
    i = 0x13C6-0x1399
    assert clone[i:i+5] == bytes.fromhex('0A 03 22 0A 77')
    # First helper writes+advances, then jumps to the non-advancing last cell.
    clone[i:i+5] = bytes.fromhex('CD 80 71 00 00')
    old_decider = source[offset(21, 0x4100):offset(21, 0x4100)+63]
    assert old_decider[-3:] == bytes.fromhex('C3 61 00')
    rom = bytearray(source)
    chunks = ((24, 0x7000, bytes(clone)),
              (24, 0x7100, store_helper(0x7100, advance=True)),
              (24, 0x7140, store_helper(0x7140, advance=False)),
              (24, 0x7180, bytes.fromhex('CD 00 71 C3 40 71')),
              (21, 0x7E00, old_decider))
    for bank, address, code in chunks:
        start = offset(bank, address)
        assert source[start:start+len(code)] == b'\xff'*len(code), (bank, hex(address), 'cave occupied')
        rom[start:start+len(code)] = code
    code = decider()
    assert len(code) <= len(old_decider)
    start = offset(21, 0x4100)
    rom[start:start+len(old_decider)] = code + b'\xff'*(len(old_decider)-len(code))
    rom[0x1399:0x13E5] = TRAMPOLINE + bytes(len(original)-len(TRAMPOLINE))
    update_checksums(rom)
    return bytes(rom)


if __name__ == '__main__':
    rom = build(BASE.read_bytes())
    OUT.mkdir(parents=True, exist_ok=True)
    target = OUT / 'candidate.gb'
    if target.exists() and target.read_bytes() != rom:
        raise SystemExit('candidate collision')
    target.write_bytes(rom)
    receipt = {'schema': 'penta-exact-source-dirty-r385-build-v1',
               'experimental': True, 'promotable': False, 'live_tested': False,
               'base_sha256': BASE_SHA,
               'candidate_sha256': hashlib.sha256(rom).hexdigest(),
               'remaining_audits': ['alternate source writers', 'LUT mutation', 'menu/lifecycle', 'non-Stage1 ABI']}
    (OUT / 'build-receipt.json').write_text(json.dumps(receipt, indent=2)+'\n')
    print(receipt['candidate_sha256'])
