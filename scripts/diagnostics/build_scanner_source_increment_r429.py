#!/usr/bin/env python3
"""Shorten safe within-row source steps without changing scanner predicates."""
import hashlib
import json
from build_stage1_bulk_compile_r425 import ROOT, BASE, SHA, update_checksums
import build_inline_hazard_scanner_r379 as scanner
OUT=ROOT/'tmp/scanner-source-increment-r429'
OFFSET=scanner.offset(24,0x6C80)
def build(source):
    if hashlib.sha256(source).hexdigest()!=SHA:raise ValueError('wrong exact r424')
    old=scanner.BODY
    # r383 replaces the final completion bridge, retain that live tail.
    assert source[OFFSET:OFFSET+len(old)-11]==old[:-11]
    new=scanner.make_body(fast_source=True)
    assert len(new)==len(old)
    rom=bytearray(source);rom[OFFSET:OFFSET+len(old)-11]=new[:-11]
    update_checksums(rom);return bytes(rom)
if __name__=='__main__':
    rom=build(BASE.read_bytes());OUT.mkdir(parents=True,exist_ok=True)
    target=OUT/'candidate.gb'
    if target.exists() and target.read_bytes()!=rom:raise SystemExit('candidate collision')
    target.write_bytes(rom)
    receipt=dict(experimental=True,promotable=False,base_sha256=SHA,
                 candidate_sha256=hashlib.sha256(rom).hexdigest())
    (OUT/'build-receipt.json').write_text(json.dumps(receipt,indent=2)+'\n')
    print(receipt)
