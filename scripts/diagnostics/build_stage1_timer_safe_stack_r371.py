#!/usr/bin/env python3
"""Correct r370's call-stack bank before entering the banked DMA service."""
import hashlib
import json
import build_stage1_timer_safe_gdma_r370 as parent

OUT = parent.ROOT / 'tmp/stage1-timer-safe-stack-r371'


def build(source):
    rom = bytearray(parent.build(source))
    # The native stack lives in WRAM1. Compiler return leaves SVBK3 selected;
    # no CALL/PUSH may occur until bank1 is restored at this ROM entry point.
    entry = bytes.fromhex('3E 01 E0 70 3E 17 CD 47 08 C3 54 43')
    rom[parent.ENTRY:parent.END] = entry + bytes(parent.END-parent.ENTRY-len(entry))
    parent.update_checksums(rom)
    return bytes(rom)


if __name__ == '__main__':
    rom = build(parent.BASE.read_bytes())
    OUT.mkdir(parents=True, exist_ok=True)
    target = OUT / 'candidate.gb'
    if target.exists() and target.read_bytes() != rom:
        raise SystemExit('refusing to overwrite different candidate')
    target.write_bytes(rom)
    receipt = {'schema': 'penta-stage1-timer-safe-stack-r371-build-v1',
               'base_sha256': parent.BASE_SHA,
               'candidate_sha256': hashlib.sha256(rom).hexdigest(),
               'experimental': True,
               'entry': rom[parent.ENTRY:parent.ENTRY+12].hex()}
    (OUT / 'build-receipt.json').write_text(json.dumps(receipt, indent=2) + '\n')
    print(receipt['candidate_sha256'])
