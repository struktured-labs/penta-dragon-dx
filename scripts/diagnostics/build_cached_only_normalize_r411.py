#!/usr/bin/env python3
"""Keep ordinary compilation native; normalize only cached-plane branch."""
import hashlib
import json
import build_precompile_abi_r409 as prior
ROOT=prior.ROOT
BASE=ROOT/'tmp/precompile-abi-r409/candidate.gb'
SHA='bb2468ccaafc65c713b169eed9288aeee70e11769b085174ffa30a686721adf5'
OUT=ROOT/'tmp/cached-only-normalize-r411'
ENTRY=bytes.fromhex('F0 E0 FE 03 28 C4 F3')
STUB=bytes.fromhex('3E 1B CD 47 08 C3 24 43 00')
def build(source):
    if hashlib.sha256(source).hexdigest()!=SHA:raise ValueError('wrong r409')
    assert source[0x42FC:0x4303]==bytes.fromhex('3E 1B CD 47 08 28 21')
    assert source[0x42C6:0x42CF]==bytes(9)
    rom=bytearray(source);rom[0x42FC:0x4303]=ENTRY;rom[0x42C6:0x42CF]=STUB
    prior.prior.copy.old.prior.update_checksums(rom)
    return bytes(rom)
if __name__=='__main__':
    rom=build(BASE.read_bytes());OUT.mkdir(parents=True,exist_ok=True)
    target=OUT/'candidate.gb'
    if target.exists() and target.read_bytes()!=rom:raise SystemExit('candidate collision')
    target.write_bytes(rom)
    receipt=dict(experimental=True,promotable=False,base_sha256=SHA,candidate_sha256=hashlib.sha256(rom).hexdigest())
    (OUT/'build-receipt.json').write_text(json.dumps(receipt,indent=2)+'\n');print(receipt)
