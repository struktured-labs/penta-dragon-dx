#!/usr/bin/env python3
"""Experimental room-writer synchronization, outside the redraw hot path.

Delay RST0's FFBD store until the bank21 helper. Stage7 waits for a queued
publication with the caller's IME unchanged; native gameplay calls this after
the publishing shim's EI/RET. Boot's stage-zero calls never wait. Saved AF,
mapper AF, return addresses, and saved HL retain their existing stack offsets.
"""
import hashlib
import json
from build_private_stationary_copy_r417 import ROOT, update_checksums
from build_idempotent_latched_publication_r384 import PACK, PACK_OFFSET

BASE = ROOT / 'tmp/private-stationary-copy-r417/candidate.gb'
SHA = '864d9993378dc07f676fb0413b04674b3f687e523d7de94cfa48a81ce34efcf8'
OUT = ROOT / 'tmp/room-writer-wait-r420'
ENTRY = 21 * 0x4000 + 0x2C80
OFFSET = 21 * 0x4000 + 0x2CC0
# PUSH HL; Stage7-only READY wait; retrieve incoming A from saved AF;
# publish FFBD; reload stage; resume original helper at its AND A.
CODE = bytes.fromhex('E5 F0 BA FE 06 20 06 F0 C4 CB 77 20 FA '
                     'F8 07 7E E0 BD F0 BA C3 83 6C')

def build(source):
    if hashlib.sha256(source).hexdigest() != SHA:
        raise ValueError('wrong exact r417')
    assert source[:8] == bytes.fromhex('E0 BD F5 F0 99 C3 38 08')
    assert source[ENTRY:ENTRY+4] == bytes.fromhex('E5 F0 BA B7')
    assert source[OFFSET:OFFSET+len(CODE)] == b'\xff' * len(CODE)
    assert source[PACK_OFFSET:PACK_OFFSET+len(PACK)] == PACK
    rom = bytearray(source)
    rom[:2] = b'\0\0'
    rom[ENTRY:ENTRY+3] = bytes.fromhex('C3 C0 6C')
    rom[OFFSET:OFFSET+len(CODE)] = CODE
    update_checksums(rom)
    return bytes(rom)

if __name__ == '__main__':
    rom = build(BASE.read_bytes())
    OUT.mkdir(parents=True, exist_ok=True)
    target = OUT / 'candidate.gb'
    if target.exists() and target.read_bytes() != rom:
        raise SystemExit('candidate collision')
    target.write_bytes(rom)
    receipt = dict(experimental=True, promotable=False, base_sha256=SHA,
                   candidate_sha256=hashlib.sha256(rom).hexdigest())
    (OUT / 'build-receipt.json').write_text(json.dumps(receipt, indent=2)+'\n')
    print(receipt)
