#!/usr/bin/env python3
"""Stage1 coordinates cannot overtake the previous queued display update."""
import hashlib
import json
from build_stage1_bulk_context_r426 import ROOT
from build_stage1_bulk_compile_r425 import update_checksums
BASE=ROOT/'tmp/stage1-bulk-context-r426/candidate.gb'
SHA='f6d9550d04ff34b32f299b817ab9cb9da5f84c90577cd11f35ad6a0d239a0b58'
OUT=ROOT/'tmp/stage1-coordinate-wait-r427'
OFFSET=29*0x4000+0x2C80
NATIVE=bytes.fromhex('7D EA 02 DC 7C EA 03 DC 7B EA 00 DC 7A EA 01 DC C9')
HOOK=bytes.fromhex('F5 3E 1D CD 47 08 F1 7A C9')
# IME unchanged. Main-loop callers permit the queued VBlank to run. No
# waiting for other stages. Native writes use unchanged HL/DE, no new RAM.
CODE=bytes.fromhex('F0 BA B7 20 06 F0 C4 CB 77 20 FA')+NATIVE[:-1]+bytes.fromhex('3E 01 C9')
def build(source):
    if hashlib.sha256(source).hexdigest()!=SHA:raise ValueError('wrong exact r426')
    assert source[0x4284:0x4295]==NATIVE
    assert source[OFFSET:OFFSET+len(CODE)]==b'\xff'*len(CODE)
    rom=bytearray(source);rom[0x4284:0x4295]=HOOK+bytes(len(NATIVE)-len(HOOK))
    rom[OFFSET:OFFSET+len(CODE)]=CODE
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
