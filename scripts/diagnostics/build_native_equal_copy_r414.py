#!/usr/bin/env python3
"""Measure native copy cost on the Stage1 unchanged-map shortcut."""
import hashlib
import json
from build_native_cached_copy_r413 import BASE, SHA, ROOT, update_checksums
OUT = ROOT/'tmp/native-equal-copy-r414'

def build(source):
    if hashlib.sha256(source).hexdigest() != SHA:
        raise ValueError('wrong exact r412 base')
    assert source[0x13CD:0x13D1] == bytes.fromhex('F1 7C C6 03')
    assert source[0x13DE:0x13E4] == bytes.fromhex('11 A0 C1 C3 BB 42')
    rom = bytearray(source)
    # Restore AF exactly as before, then native DE setup and row loop.
    # Other stages already branch to the separate fallback at 13DA.
    rom[0x13CD:0x13D1] = bytes.fromhex('F1 C3 DE 13')
    update_checksums(rom)
    return bytes(rom)

if __name__ == '__main__':
    rom = build(BASE.read_bytes()); OUT.mkdir(parents=True,exist_ok=True)
    target=OUT/'candidate.gb'
    if target.exists() and target.read_bytes()!=rom:raise SystemExit('candidate collision')
    target.write_bytes(rom)
    receipt=dict(experimental=True,promotable=False,base_sha256=SHA,
                 candidate_sha256=hashlib.sha256(rom).hexdigest())
    (OUT/'build-receipt.json').write_text(json.dumps(receipt,indent=2)+'\n')
    print(receipt)
