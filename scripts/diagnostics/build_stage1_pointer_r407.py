#!/usr/bin/env python3
"""Keep the shorter pointer calculation only on Stage1 checked/raw paths."""
import hashlib
import json
import build_metatile_pointer_r406 as prior
ROOT=prior.ROOT
BASE=prior.BASE
OUT=ROOT/'tmp/stage1-pointer-r407'
def build(source):
    rom=bytearray(prior.build(source))
    site=prior.SITES[0]
    rom[site:site+len(prior.OLD)]=source[site:site+len(prior.OLD)]
    prior.prior.old.prior.update_checksums(rom)
    return bytes(rom)
if __name__=='__main__':
    rom=build(BASE.read_bytes());OUT.mkdir(parents=True,exist_ok=True)
    target=OUT/'candidate.gb'
    if target.exists() and target.read_bytes()!=rom:raise SystemExit('candidate collision')
    target.write_bytes(rom)
    receipt=dict(experimental=True,promotable=False,base_sha256=prior.SHA,
                 candidate_sha256=hashlib.sha256(rom).hexdigest())
    (OUT/'build-receipt.json').write_text(json.dumps(receipt,indent=2)+'\n')
    print(receipt)
