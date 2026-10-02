#!/usr/bin/env python3
"""Build r339: preserve r335's carry-preserving final DEC-B ABI."""
from __future__ import annotations
import argparse, hashlib, json
from pathlib import Path
import build_stage1_scene0b_covered_admission_r337 as r337

ROOT=r337.ROOT; TMP=r337.TMP; BASE=r337.BASE; BASE_RECEIPT=r337.BASE_RECEIPT
OUTPUT=TMP/"stage1-scene0b-covered-admission-abi-r339/candidate.gb"
RECEIPT=TMP/"stage1-scene0b-covered-admission-abi-r339/build-receipt.json"

def build(source:bytes, receipt_bytes:bytes)->tuple[bytes,dict]:
    candidate,parent=r337.build(source,receipt_bytes); rom=bytearray(candidate)
    cave_offset=r337.r335.r331.o(r337.r335.r331.CAVE_ADDR)
    chunks=r337.r335.selected(source)
    cave_size=1+14*len(chunks)+r337.r335.r331.REPAIR_SIZE+3+15
    cave=bytearray(rom[cave_offset:cave_offset+cave_size])
    insertion=len(cave)-(r337.r335.r331.REPAIR_SIZE+3)
    if cave[insertion-3:insertion] != bytes.fromhex("F1 E0 40"):
        raise AssertionError("r339 uncover sequence changed")
    # r335 enters with carry set and its final DEC B (1->0) produces the
    # exact B=0, Z=1,N=1,H=0,C=1 downstream contract.  Recreate it after AF
    # restoration without changing the LCDC value held in A.
    abi=bytes.fromhex("06 01 37 05")
    extended=cave[:insertion]+abi+cave[insertion:]
    if rom[cave_offset+cave_size:cave_offset+cave_size+len(abi)] != bytes([0xFF])*len(abi):
        raise AssertionError("r339 ABI extension preimage changed")
    rom[cave_offset:cave_offset+len(extended)]=extended
    r337.r335.r331.r325.r324.r321.r320.r319.r318.r317.r305.r304.update_checksums(rom)
    candidate=bytes(rom);sha=hashlib.sha256(candidate).hexdigest()
    return candidate,{"schema":"penta-stage1-scene0b-covered-admission-abi-r339-build-v1","status":"STATIC_PASS_LIVE_GATES_REQUIRED","promotable":False,"emulator_invoked":False,"candidate_sha256":sha,"base_r337":parent["candidate_sha256"],"patch":{"window_cover":"retained","post_copy_abi":"B=0; Z/N/H/C=1/1/0/1, exact r335 final DEC-B with entry carry"},"required_live_gates":parent["required_live_gates"]}

def main()->int:
 p=argparse.ArgumentParser();p.add_argument('--base',type=Path,default=BASE);p.add_argument('--base-receipt',type=Path,default=BASE_RECEIPT);p.add_argument('--output',type=Path,default=OUTPUT);p.add_argument('--receipt',type=Path,default=RECEIPT);a=p.parse_args();c,r=build(a.base.read_bytes(),a.base_receipt.read_bytes());a.output.parent.mkdir(parents=True,exist_ok=True);a.receipt.parent.mkdir(parents=True,exist_ok=True);a.output.write_bytes(c);a.receipt.write_text(json.dumps(r,indent=2,sort_keys=True)+'\n');print(json.dumps({'candidate_sha256':r['candidate_sha256'],'output':str(a.output)}));return 0
if __name__=='__main__':raise SystemExit(main())
