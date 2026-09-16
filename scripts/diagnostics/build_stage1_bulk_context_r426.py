#!/usr/bin/env python3
"""Use unbanked scene context after the compiler has selected SVBK3."""
import hashlib
import json
import build_stage1_bulk_compile_r425 as prior
ROOT=prior.ROOT
BASE=prior.BASE
OUT=ROOT/'tmp/stage1-bulk-context-r426'

def service():
    old=prior.service()
    assert old[6:11]==bytes.fromhex('FA 80 D8 FE 02')
    # FFB7 is native scene context, valid independently of SVBK. Stage1's
    # context2 includes its low-health subscene; the existing setup already
    # established the contextual LUT before changing SVBK.
    return old[:6]+bytes.fromhex('F0 B7 00')+old[9:]

def build(source):
    rom=bytearray(prior.build(source));code=service()
    rom[prior.OFFSET:prior.OFFSET+len(code)]=code
    prior.update_checksums(rom);return bytes(rom)

if __name__=='__main__':
    rom=build(BASE.read_bytes());OUT.mkdir(parents=True,exist_ok=True)
    target=OUT/'candidate.gb'
    if target.exists() and target.read_bytes()!=rom:raise SystemExit('candidate collision')
    target.write_bytes(rom)
    receipt=dict(experimental=True,promotable=False,base_sha256=prior.SHA,
                 candidate_sha256=hashlib.sha256(rom).hexdigest())
    (OUT/'build-receipt.json').write_text(json.dumps(receipt,indent=2)+'\n')
    print(receipt)
