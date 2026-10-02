#!/usr/bin/env python3
"""Experimental publisher backpressure with interrupts enabled and IE guard."""
from pathlib import Path
import hashlib
import json
from build_stage1_fast_final_window_selector_r363 import update_checksums
from build_inline_hazard_scanner_r379 import BODY, offset

ROOT = Path(__file__).resolve().parents[2]
BASE = ROOT / 'tmp/native-priority-collision-r381/candidate.gb'
BASE_SHA = 'df46f77f2b6485558f1801f76e1fd72dc90226c96f7faccc987c322538dfbd88'
OUT = ROOT / 'tmp/publication-backpressure-r382'
# Save the same queued-branch AF as before. Never wait with VBlank disabled.
# The native ISR preserves registers and restores SVBK. Timer IRQs remain on.
WAIT = bytes.fromhex('3E 01 EA 5C DF F5 FB F0 FF 0F 30 06 FA 5C DF B7 20 FA F1 C9')
PRIMARY_TAIL = bytes.fromhex('C3 8B 11 00 00 FB C9')
DONE_OFFSET = offset(24, 0x6C80) + len(BODY) - 11
DONE = bytes.fromhex('01 C0 55 C5 3E 13 C3 61 00 00 00')


def build(source):
    if hashlib.sha256(source).hexdigest() != BASE_SHA:
        raise ValueError('wrong exact r381 base')
    assert source[0x1188:0x118B] == bytes.fromhex('CB BF C9')
    assert source[0x12FC:0x1303] == bytes.fromhex('3E 01 EA 5C DF FB C9')
    assert source[DONE_OFFSET:DONE_OFFSET+11] == bytes.fromhex('F5 C5 01 8B 11 C5 3E 13 C3 61 00')
    # Completion discards incoming BC/DE, then overwrites A/flags before use.
    # Mapping directly to this tail therefore needs no AF/BC bridge saves.
    tail = offset(19, 0x55C0)
    assert source[tail:tail+9] == bytes.fromhex('C1 D1 C5 F0 B7 FE 02 00 00')
    assert len(WAIT) <= 0x11A2 - 0x118B
    rom = bytearray(source)
    rom[0x12FC:0x1303] = PRIMARY_TAIL
    rom[0x118B:0x118B+len(WAIT)] = WAIT
    rom[DONE_OFFSET:DONE_OFFSET+11] = DONE
    update_checksums(rom)
    return bytes(rom)


if __name__ == '__main__':
    rom = build(BASE.read_bytes())
    OUT.mkdir(parents=True, exist_ok=True)
    target = OUT / 'candidate.gb'
    if target.exists() and target.read_bytes() != rom:
        raise SystemExit('candidate collision')
    target.write_bytes(rom)
    receipt = {'schema': 'penta-publication-backpressure-r382-build-v1',
               'experimental': True, 'promotable': False,
               'base_sha256': BASE_SHA,
               'candidate_sha256': hashlib.sha256(rom).hexdigest(),
               'wait_hex': WAIT.hex(), 'live_tested': False}
    (OUT / 'build-receipt.json').write_text(json.dumps(receipt, indent=2)+'\n')
    print(receipt['candidate_sha256'])
