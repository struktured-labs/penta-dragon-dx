#!/usr/bin/env python3
"""Experiment: extend the existing early-VBlank four-tile window to all stages.

The LY144..151 bound and DI-protected 96-T-cycle write group are unchanged.
Outside that window, the original STAT mode3->mode0 wait is unchanged.
This is not release-qualified until fresh visual and speed gates pass.
"""
from pathlib import Path
import hashlib
import json
from build_later_stage_deferred_dma_r443 import update_checksums

ROOT = Path(__file__).resolve().parents[2]
BASE = ROOT / 'tmp/later-stage-deferred-dma-r443d/candidate.gb'
SHA = '7b3de7acf60614b958658b9f7f7139bb7b855dd23bc5f41c6c42d7322cead620'
OUT = ROOT / 'tmp/later-vblank-copy-r444'


def build(source):
    assert hashlib.sha256(source).hexdigest() == SHA, 'wrong exact r443d base'
    assert source[0x4330:0x4351] == bytes.fromhex(
        'F3 FA 80 D8 FE 02 20 08 F0 44 E6 F8 FE 90 28 0E '
        'F0 41 E6 03 FE 03 20 F8 F0 41 E6 03 20 FA C3 CF 42')
    assert source[0x42CF:0x42DC] == bytes.fromhex('1A 13 22 1A 13 22 1A 13 22 1A 13 22 FB')
    rom = bytearray(source)
    rom[0x4331:0x4336] = bytes.fromhex('AF 00 00 00 00')
    update_checksums(rom)
    assert all(a == b or i in {0x14D, 0x14E, 0x14F, *range(0x4331, 0x4336)}
               for i, (a, b) in enumerate(zip(source, rom)))
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
                   early_vblank_lines=[144, 151], tile_group_bytes=4)
    (OUT / 'build-receipt.json').write_text(json.dumps(receipt, indent=2) + '\n')
    print(json.dumps(receipt))
