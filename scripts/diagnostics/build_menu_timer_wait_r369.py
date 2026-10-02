#!/usr/bin/env python3
"""Experimental Timer-only IRQ window during menu-close VBlank wait.

Clone the existing bank31:$6E50 art service. Preserve IE and BC, permit only
an already-enabled Timer IRQ while waiting, then DI before any VRAM bank or
DMA setup change. Restore exact IE/BC/result flags; return with IME disabled
so r364's ownership-clear/Window-hide atomic exit is unchanged.
"""
from pathlib import Path
import hashlib
import json
from build_stage1_sara_priority_clear_r365 import update_checksums

ROOT = Path(__file__).resolve().parents[2]
BASE = ROOT / 'tmp/obj-priority-fast-r368/candidate.gb'
BASE_SHA = '5356bb026cba4d063b1324f1d9b9d9ef9be85dcdb7debe4a03ce7ef300a74111'
OUT = ROOT / 'tmp/menu-timer-wait-r369'
OFFSET = lambda a: 31 * 0x4000 + a - 0x4000
OLD = bytes.fromhex(
    'F0 55 CB 7F 20 0B F0 40 CB 7F 20 F4 AF E0 55 18 EF '
    'F0 40 CB 7F 28 0C F0 44 FE 90 30 FA F0 44 FE 90 38 FA '
    'C5 F0 4F 47 AF E0 4F 3E 70 E0 51 AF E0 52 3E 11 E0 53 '
    'AF E0 54 3E 0F E0 55 F0 55 FE FF F5 78 E0 4F F1 C1 C9')
PREFIX = bytes.fromhex('C5 F0 FF F5 E6 04 E0 FF FB')
SUFFIX = bytes.fromhex('F5 C1 F1 E0 FF C5 F1 C1 C9')
DMA_START = OLD.index(bytes.fromhex('C5 F0 4F'))
NEW = PREFIX + OLD[:DMA_START] + bytes([0xF3]) + OLD[DMA_START:-1] + SUFFIX


def build(source):
    assert hashlib.sha256(source).hexdigest() == BASE_SHA
    assert source[OFFSET(0x6E50):OFFSET(0x6E50)+len(OLD)] == OLD
    assert source[OFFSET(0x6EE0):OFFSET(0x6EE0)+3] == bytes.fromhex('CD 50 6E')
    assert source[OFFSET(0x7300):OFFSET(0x7300)+len(NEW)] == b'\xff' * len(NEW)
    rom = bytearray(source)
    rom[OFFSET(0x7300):OFFSET(0x7300)+len(NEW)] = NEW
    rom[OFFSET(0x6EE0):OFFSET(0x6EE0)+3] = bytes.fromhex('CD 00 73')
    update_checksums(rom)
    return bytes(rom)


if __name__ == '__main__':
    source = BASE.read_bytes()
    rom = build(source)
    OUT.mkdir(parents=True, exist_ok=True)
    target = OUT / 'candidate.gb'
    if target.exists() and target.read_bytes() != rom:
        raise SystemExit('refusing to overwrite different candidate')
    target.write_bytes(rom)
    receipt = {'schema': 'penta-menu-timer-wait-r369-build-v1',
               'base_sha256': BASE_SHA,
               'candidate_sha256': hashlib.sha256(rom).hexdigest(),
               'experimental': True, 'helper_size': len(NEW),
               'changed_offsets': [i for i,(a,b) in enumerate(zip(source,rom)) if a != b]}
    (OUT / 'build-receipt.json').write_text(json.dumps(receipt, indent=2) + '\n')
    print(receipt['candidate_sha256'])
