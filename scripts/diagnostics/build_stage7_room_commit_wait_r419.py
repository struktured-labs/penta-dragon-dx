#!/usr/bin/env python3
"""Stage7 room transitions wait for the queued physical publication."""
import hashlib,json
from build_idempotent_latched_publication_r384 import PACK, PACK_OFFSET
from build_private_stationary_copy_r417 import ROOT, update_checksums
BASE=ROOT/'tmp/private-stationary-copy-r417/candidate.gb'
SHA='864d9993378dc07f676fb0413b04674b3f687e523d7de94cfa48a81ce34efcf8'
OUT=ROOT/'tmp/stage7-room-commit-wait-r419'
# Only actual nonzero next-room changes in Stage7. SHIM owns saved BC/AF.
# IME is off on entry; enable delivery until READY clears, then restore DI.
TAIL=bytes.fromhex('F0 BA FE 06 C0 F0 CE B7 C8 47 F0 BD B8 C8 FB F0 C4 CB 77 20 FA F3 C9')
def build(source):
    if hashlib.sha256(source).hexdigest()!=SHA:raise ValueError('wrong exact r417')
    assert source[PACK_OFFSET:PACK_OFFSET+len(PACK)]==PACK
    code=PACK[:-1]+TAIL
    assert source[PACK_OFFSET+len(PACK):PACK_OFFSET+len(code)]==b'\xff'*(len(code)-len(PACK))
    rom=bytearray(source);rom[PACK_OFFSET:PACK_OFFSET+len(code)]=code
    update_checksums(rom);return bytes(rom)
if __name__=='__main__':
    rom=build(BASE.read_bytes());OUT.mkdir(parents=True,exist_ok=True);p=OUT/'candidate.gb'
    if p.exists() and p.read_bytes()!=rom:raise SystemExit('candidate collision')
    p.write_bytes(rom)
    receipt=dict(experimental=True,promotable=False,base_sha256=SHA,candidate_sha256=hashlib.sha256(rom).hexdigest())
    (OUT/'build-receipt.json').write_text(json.dumps(receipt,indent=2)+'\n');print(receipt)
