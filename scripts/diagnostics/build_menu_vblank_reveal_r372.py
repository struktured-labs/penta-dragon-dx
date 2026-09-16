#!/usr/bin/env python3
"""Reveal the completed native menu during VBlank, not midway down a frame."""
from pathlib import Path
import hashlib
import json
from build_stage1_sara_priority_clear_r365 import update_checksums

ROOT = Path(__file__).resolve().parents[2]
BASE = ROOT / 'tmp/stage1-timer-safe-stack-r371/candidate.gb'
BASE_SHA = '6368f89cb8712ea9915f81e97684a900808195a38d3ed0575a22a0cc8067a365'
OUT = ROOT / 'tmp/menu-vblank-reveal-r372'
offset = lambda a: 20 * 0x4000 + a - 0x4000
CODE = bytes.fromhex(
    'F5 C5 F0 FF F5 '          # preserve AF, BC, original IE
    'E6 04 E0 FF FB '          # Timer only while waiting; no VBlank publisher
    'F0 40 CB 7F 28 0C '
    'F0 44 FE 90 30 FA '
    'F0 44 FE 90 38 FA '
    'F3 F1 E0 FF C1 F1 '      # restore IE/BC/AF with IME disabled
    'F0 40 CB EF E0 40 C9')   # original reveal; caller retains EI/RET


def build(source):
    assert hashlib.sha256(source).hexdigest() == BASE_SHA
    assert source[offset(0x407C):offset(0x4084)] == bytes.fromhex('F0 40 CB EF E0 40 FB C9')
    assert source[offset(0x7F00):offset(0x7F00)+len(CODE)] == b'\xff' * len(CODE)
    rom = bytearray(source)
    rom[offset(0x407C):offset(0x4082)] = bytes.fromhex('CD 00 7F 00 00 00')
    rom[offset(0x7F00):offset(0x7F00)+len(CODE)] = CODE
    update_checksums(rom)
    return bytes(rom)


if __name__ == '__main__':
    rom = build(BASE.read_bytes())
    OUT.mkdir(parents=True, exist_ok=True)
    target = OUT / 'candidate.gb'
    if target.exists() and target.read_bytes() != rom:
        raise SystemExit('refusing to overwrite different candidate')
    target.write_bytes(rom)
    receipt = {'schema': 'penta-menu-vblank-reveal-r372-build-v1',
               'base_sha256': BASE_SHA,
               'candidate_sha256': hashlib.sha256(rom).hexdigest(),
               'experimental': True}
    (OUT / 'build-receipt.json').write_text(json.dumps(receipt, indent=2) + '\n')
    print(receipt['candidate_sha256'])
