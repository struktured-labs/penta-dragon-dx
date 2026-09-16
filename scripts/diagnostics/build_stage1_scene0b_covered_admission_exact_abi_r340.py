#!/usr/bin/env python3
"""Build r340: preserve each capture's entry carry through the cover."""
from __future__ import annotations
import argparse,hashlib,json
from pathlib import Path
import build_stage1_scene0b_covered_admission_r337 as r337
ROOT=r337.ROOT;TMP=r337.TMP;BASE=r337.BASE;BASE_RECEIPT=r337.BASE_RECEIPT
OUTPUT=TMP/'stage1-scene0b-covered-admission-exact-abi-r340/candidate.gb';RECEIPT=TMP/'stage1-scene0b-covered-admission-exact-abi-r340/build-receipt.json'
def build(source:bytes,receipt_bytes:bytes)->tuple[bytes,dict]:
 c,p=r337.build(source,receipt_bytes);rom=bytearray(c);o=r337.r335.r331.o(r337.r335.r331.CAVE_ADDR);chunks=r337.r335.selected(source);n=1+14*len(chunks)+r337.r335.r331.REPAIR_SIZE+3+15;cave=bytearray(rom[o:o+n]);i=len(cave)-(r337.r335.r331.REPAIR_SIZE+3)
 if cave[i-3:i]!=bytes.fromhex('F1 E0 40'):raise AssertionError('r340 uncover changed')
 # POP AF restores the capture-specific carry; LD B,1 / DEC B recreates the
 # final r335 loop's B=0 and Z/N/H while DEC preserves that exact carry.
 abi=bytes.fromhex('06 01 05');x=cave[:i]+abi+cave[i:]
 if rom[o+n:o+n+len(abi)]!=bytes([0xFF])*len(abi):raise AssertionError('r340 preimage changed')
 rom[o:o+len(x)]=x;r337.r335.r331.r325.r324.r321.r320.r319.r318.r317.r305.r304.update_checksums(rom);c=bytes(rom);h=hashlib.sha256(c).hexdigest();return c,{'schema':'penta-stage1-scene0b-covered-admission-exact-abi-r340-build-v1','status':'STATIC_PASS_LIVE_GATES_REQUIRED','promotable':False,'emulator_invoked':False,'candidate_sha256':h,'base_r337':p['candidate_sha256'],'patch':{'window_cover':'retained','post_copy_abi':'B=0; Z/N/H exact; capture-specific carry preserved'},'required_live_gates':p['required_live_gates']}
def main()->int:
 p=argparse.ArgumentParser();p.add_argument('--base',type=Path,default=BASE);p.add_argument('--base-receipt',type=Path,default=BASE_RECEIPT);p.add_argument('--output',type=Path,default=OUTPUT);p.add_argument('--receipt',type=Path,default=RECEIPT);a=p.parse_args();c,r=build(a.base.read_bytes(),a.base_receipt.read_bytes());a.output.parent.mkdir(parents=True,exist_ok=True);a.receipt.parent.mkdir(parents=True,exist_ok=True);a.output.write_bytes(c);a.receipt.write_text(json.dumps(r,indent=2,sort_keys=True)+'\n');print(json.dumps({'candidate_sha256':r['candidate_sha256'],'output':str(a.output)}));return 0
if __name__=='__main__':raise SystemExit(main())
