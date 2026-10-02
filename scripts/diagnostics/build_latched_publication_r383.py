#!/usr/bin/env python3
"""Experimental atomic page/scroll snapshot using existing DF5C and FFC4.

FFC4 before request: raw completed-map H=9B/9F (bit6 clear).
After request: bit7 absolute, bit6 ready, bit4 page, bits0..3 SCY.
DF5C holds SCX (masked on consumption). No additional RAM is allocated.
"""
from pathlib import Path
import hashlib
import json
from build_stage1_fast_final_window_selector_r363 import update_checksums
from build_publication_backpressure_r382 import DONE, DONE_OFFSET

ROOT = Path(__file__).resolve().parents[2]
BASE = ROOT / 'tmp/native-priority-collision-r381/candidate.gb'
BASE_SHA = 'df46f77f2b6485558f1801f76e1fd72dc90226c96f7faccc987c322538dfbd88'
OUT = ROOT / 'tmp/latched-publication-r383'
PACK_OFFSET = 24 * 0x4000 + 0x2E00
# Fixed bank shim: preserve BC, remember mapping and incoming flags; pack
# with IME still disabled, restore bank, return A=1 and original AF flags.
SHIM = bytes.fromhex('C5 F0 99 F5 3E 18 CD 61 00 CD 00 6E F1 CD 61 00 C1 3E 01 FB C9')
PACK = bytes.fromhex('FA 00 DC EA 5C DF F0 C4 B7 28 06 E6 04 07 07 F6 80 F6 40 47 FA 02 DC E6 0F B0 E0 C4 C9')
PRIMARY_TAIL = bytes.fromhex('C3 8B 11 00 00 FB C9')
GUARD = bytes.fromhex('F0 44 E6 FC FE 90 C2 1D 6F F0 C4 E6 40 C3 00 74')


def commit_bytes(old):
    assert old[:4] == bytes.fromhex('C3 64 74 00')
    new = old.replace(bytes.fromhex('AF EA 5C DF'), bytes(4), 1)
    new = new.replace(bytes.fromhex('FA 00 DC E6 0F E0 43'), bytes.fromhex('FA 5C DF E6 0F E0 43'), 1)
    new = new.replace(bytes.fromhex('FA 02 DC E6 0F E0 42'), bytes.fromhex('F0 C4 E6 0F E0 42'), 1)
    new = new.replace(bytes.fromhex('F0 C4 B7 28 15 E6 04 07'), bytes.fromhex('F0 C4 CB 7F 28 15 E6 10 0F'), 1)
    assert len(new) == len(old)
    return new


def build(source):
    if hashlib.sha256(source).hexdigest() != BASE_SHA:
        raise ValueError('wrong exact r381 base')
    assert source[0x1188:0x118B] == bytes.fromhex('CB BF C9')
    assert source[0x12FC:0x1303] == bytes.fromhex('3E 01 EA 5C DF FB C9')
    assert source[DONE_OFFSET:DONE_OFFSET+11] == bytes.fromhex('F5 C5 01 8B 11 C5 3E 13 C3 61 00')
    assert source[PACK_OFFSET:PACK_OFFSET+len(PACK)] == b'\xff'*len(PACK)
    assert len(SHIM) <= 0x11A2-0x118B
    rom = bytearray(source)
    rom[0x118B:0x118B+len(SHIM)] = SHIM
    rom[0x12FC:0x1303] = PRIMARY_TAIL
    rom[DONE_OFFSET:DONE_OFFSET+11] = DONE
    rom[PACK_OFFSET:PACK_OFFSET+len(PACK)] = PACK
    rom[0x373FC:0x37464] = commit_bytes(source[0x373FC:0x37464])
    rom[0x37464:0x37464+len(GUARD)] = GUARD
    update_checksums(rom)
    return bytes(rom)


if __name__ == '__main__':
    rom = build(BASE.read_bytes())
    OUT.mkdir(parents=True, exist_ok=True)
    target = OUT / 'candidate.gb'
    if target.exists() and target.read_bytes() != rom:
        raise SystemExit('candidate collision')
    target.write_bytes(rom)
    receipt = {'schema': 'penta-latched-publication-r383-build-v1',
               'experimental': True, 'promotable': False,
               'base_sha256': BASE_SHA,
               'candidate_sha256': hashlib.sha256(rom).hexdigest(),
               'live_tested': False, 'packed_ffc4': 'absolute:7 ready:6 page:4 scy:0..3'}
    (OUT / 'build-receipt.json').write_text(json.dumps(receipt, indent=2)+'\n')
    print(receipt['candidate_sha256'])
