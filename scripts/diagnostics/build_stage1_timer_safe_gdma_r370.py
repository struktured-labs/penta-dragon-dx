#!/usr/bin/env python3
"""Experiment: Timer-safe wait followed by VBlank-only attribute GDMA.

No Timer IRQ can run with SVBK3 selected or while DMA is active. VBlank
remains masked until the unchanged final publication/ownership code returns.
"""
from pathlib import Path
import hashlib
import json
from build_stage1_sara_priority_clear_r365 import update_checksums

ROOT = Path(__file__).resolve().parents[2]
BASE = ROOT / 'tmp/obj-priority-fast-r368/candidate.gb'
BASE_SHA = '5356bb026cba4d063b1324f1d9b9d9ef9be85dcdb7debe4a03ce7ef300a74111'
OUT = ROOT / 'tmp/stage1-timer-safe-gdma-r370'
ENTRY = 0x4324
END = 0x4354
SERVICE = 23 * 0x4000 + 0x6C80 - 0x4000
OLD = bytes.fromhex(
    '3E 03 E0 70 F0 C4 E6 FC E0 53 AF E0 54 3E 01 E0 4F '
    '3E D0 E0 51 AF E0 52 F0 40 CB 7F 3E 2F 28 02 3E AF '
    'E0 55 F0 55 CB 7F 28 FA AF E0 4F 3C E0 70')
SERVICE_CODE = bytes.fromhex(
    'C5 F0 FF F5 '             # preserve BC and original IE
    '3E 01 E0 70 '             # sound engine's physical WRAM bank
    'F0 FF E6 04 E0 FF FB '    # only originally enabled Timer can interrupt
    'F0 40 CB 7F 28 0C '       # LCD off: bypass LY wait
    'F0 44 FE 90 30 FA '       # finish current VBlank if already in it
    'F0 44 FE 90 38 FA '       # then reach fresh VBlank
    'F3 3E 03 E0 70 '         # critical section BEFORE selecting DMA source
    'F0 C4 E6 FC E0 53 AF E0 54 3E 01 E0 4F '
    '3E D0 E0 51 AF E0 52 3E 2F E0 55 '  # 48 blocks GDMA
    'F0 55 CB 7F 28 FA '       # retain completion check
    'AF E0 4F 3C E0 70 '      # restore VBK0/SVBK1 BEFORE restoring IE
    'F1 E0 FF C1 AF 3C C9')   # restore IE/BC; A=1/F=0 for mapper return


def build(source):
    assert hashlib.sha256(source).hexdigest() == BASE_SHA
    assert source[ENTRY:END] == OLD
    assert source[0x847:0x850] == bytes.fromhex('CD 61 00 CD 80 6C C3 61 00')
    assert source[SERVICE:SERVICE+len(SERVICE_CODE)] == b'\xff' * len(SERVICE_CODE)
    rom = bytearray(source)
    rom[ENTRY:END] = bytes.fromhex('3E 17 CD 47 08 C3 54 43') + bytes(END-ENTRY-8)
    rom[SERVICE:SERVICE+len(SERVICE_CODE)] = SERVICE_CODE
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
    receipt = {'schema': 'penta-stage1-timer-safe-gdma-r370-build-v1',
               'base_sha256': BASE_SHA,
               'candidate_sha256': hashlib.sha256(rom).hexdigest(),
               'experimental': True,
               'changed_offsets': [i for i,(a,b) in enumerate(zip(source,rom)) if a != b]}
    (OUT / 'build-receipt.json').write_text(json.dumps(receipt, indent=2) + '\n')
    print(receipt['candidate_sha256'])
