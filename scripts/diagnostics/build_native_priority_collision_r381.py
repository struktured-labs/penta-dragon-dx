#!/usr/bin/env python3
"""Experimental removal of obsolete Sara priority stores colliding with FFC4.

Not a general HRAM ownership proof: native lifecycle bulk clears remain and
must be exercised by the menu/death/Continue gates before promotion.
"""
from pathlib import Path
import hashlib
import json
from build_stage1_fast_final_window_selector_r363 import update_checksums

ROOT = Path(__file__).resolve().parents[2]
BASE = ROOT / 'tmp/combined-scanner-copy-r380/candidate.gb'
BASE_SHA = '64fece44776ac75d9822b264decd08736d63e67a259b76c625ebe8721a4939f1'
OUT = ROOT / 'tmp/native-priority-collision-r381'
STORES = (0x50C5, 0x50CA)
CONTEXT = bytes.fromhex('CD DF 50 28 06 3E 01 E0 C4 18 03 AF E0 C4 CD DF 50')


def build(source):
    if hashlib.sha256(source).hexdigest() != BASE_SHA:
        raise ValueError('wrong exact r380 base')
    # The replacement helper makes the old four priority inputs obsolete.
    # Never apply this change to stock, or to a candidate still reading them.
    assert source[0x1188:0x118B] == bytes.fromhex('CB BF C9')
    assert source[0x50BE:0x50CF] == CONTEXT
    rom = bytearray(source)
    for address in STORES:
        assert source[address:address+2] == bytes.fromhex('E0 C4')
        rom[address:address+2] = bytes(2)
    update_checksums(rom)
    changed = {i for i, (a, b) in enumerate(zip(source, rom)) if a != b}
    assert changed <= {0x14D, 0x14E, 0x14F, 0x50C5, 0x50C6, 0x50CA, 0x50CB}
    return bytes(rom)


if __name__ == '__main__':
    rom = build(BASE.read_bytes())
    OUT.mkdir(parents=True, exist_ok=True)
    target = OUT / 'candidate.gb'
    if target.exists() and target.read_bytes() != rom:
        raise SystemExit('refusing candidate collision')
    target.write_bytes(rom)
    receipt = {
        'schema': 'penta-native-priority-collision-r381-build-v1',
        'base_sha256': BASE_SHA,
        'candidate_sha256': hashlib.sha256(rom).hexdigest(),
        'experimental': True, 'promotable': False, 'live_tested': False,
        'remaining_ownership_audit': 'native FFC2-FFC5 lifecycle bulk clears',
    }
    (OUT / 'build-receipt.json').write_text(json.dumps(receipt, indent=2)+'\n')
    print(receipt['candidate_sha256'])
