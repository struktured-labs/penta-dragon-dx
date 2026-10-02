#!/usr/bin/env python3
"""Compact r444's early-VBlank helper without changing its timing window."""
from pathlib import Path
import hashlib
import json
from build_later_stage_deferred_dma_r443 import update_checksums

ROOT = Path(__file__).resolve().parents[2]
BASE = ROOT / 'tmp/later-vblank-copy-r444/candidate.gb'
SHA = 'd763a2e9b4610bac28e7a54da809b74227a1baf289c851b02774a2a2968e154e'
OUT = ROOT / 'tmp/compact-vblank-copy-r444b'
OLD = bytes.fromhex('F3 AF 00 00 00 00 20 08 F0 44 E6 F8 FE 90 28 0E '
                    'F0 41 E6 03 FE 03 20 F8 F0 41 E6 03 20 FA C3 CF 42')
NEW = bytes.fromhex('F3 F0 44 E6 F8 FE 90 28 0E '
                    'F0 41 E6 03 FE 03 20 F8 F0 41 E6 03 20 FA C3 CF 42')


def build(source):
    assert hashlib.sha256(source).hexdigest() == SHA, 'wrong exact r444 base'
    assert source[0x4330:0x4330+len(OLD)] == OLD
    assert source[0x42CF:0x42DC] == bytes.fromhex('1A 13 22 1A 13 22 1A 13 22 1A 13 22 FB')
    assert NEW[1:] == OLD[8:], 'only remove redundant predicate'
    rom = bytearray(source)
    rom[0x4330:0x4330+len(OLD)] = NEW + bytes(len(OLD)-len(NEW))
    update_checksums(rom)
    assert all(a == b or i in {0x14D,0x14E,0x14F,*range(0x4330,0x4351)}
               for i,(a,b) in enumerate(zip(source,rom)))
    return bytes(rom)


if __name__ == '__main__':
    candidate = build(BASE.read_bytes())
    OUT.mkdir(parents=True, exist_ok=True)
    path = OUT / 'candidate.gb'
    if path.exists() and path.read_bytes() != candidate:
        raise SystemExit('immutable candidate collision')
    path.write_bytes(candidate)
    receipt = dict(experimental=True, promotable=False, live_tested=False,
                   base_sha256=SHA, candidate_sha256=hashlib.sha256(candidate).hexdigest(),
                   helper_hex=NEW.hex(), early_vblank_lines=[144,151])
    (OUT/'build-receipt.json').write_text(json.dumps(receipt,indent=2)+'\n')
    print(json.dumps(receipt))
