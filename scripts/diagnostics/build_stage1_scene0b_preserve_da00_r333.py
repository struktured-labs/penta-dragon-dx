#!/usr/bin/env python3
"""Build r333: preserve live DA00-DA5C while installing DA60-DAFF/DB80-DBFC."""
from __future__ import annotations
import argparse, hashlib, json
from pathlib import Path
import build_stage1_scene0b_complete_runtime_r331 as r331
ROOT=r331.ROOT; TMP=r331.TMP; BASE=r331.BASE; BASE_RECEIPT=r331.BASE_RECEIPT
OUTPUT=TMP/"stage1-scene0b-preserve-da00-r333/candidate.gb"; RECEIPT=TMP/"stage1-scene0b-preserve-da00-r333/build-receipt.json"
def selected(source):
    return [row for row in _all(source) if not row[0].startswith("DA00-")]
def _all(source):
    result=[]
    for label,src,dst,width in r331.r307.COPY_REGIONS: result.append((label,dst,source[r331.bo(r331.r307.CANONICAL_BANK,src):r331.bo(r331.r307.CANONICAL_BANK,src)+width]))
    src=r331.r307.CANONICAL_EXTENSION_SOURCE_ADDR; result.append(("DBF1-DBFC",0xDBF1,source[r331.bo(r331.r307.CANONICAL_BANK,src):r331.bo(r331.r307.CANONICAL_BANK,src)+len(r331.r307.CANONICAL_EXTENSION)])); return result
def build(source,receipt):
    old=r331.regions; r331.regions=selected
    try:c,p=r331.build(source,receipt)
    finally:r331.regions=old
    sha=hashlib.sha256(c).hexdigest(); return c,{"schema":"penta-stage1-scene0b-preserve-da00-r333-build-v1","status":"STATIC_PASS_LIVE_GATES_REQUIRED","promotable":False,"emulator_invoked":False,"candidate_sha256":sha,"runtime_regions":p["runtime_regions"],"preserved_live_state":["DA00-DA5C"],"required_live_gates":p["required_live_gates"]}
def main():
    p=argparse.ArgumentParser();p.add_argument("--base",type=Path,default=BASE);p.add_argument("--base-receipt",type=Path,default=BASE_RECEIPT);p.add_argument("--output",type=Path,default=OUTPUT);p.add_argument("--receipt",type=Path,default=RECEIPT);a=p.parse_args();c,r=build(a.base.read_bytes(),a.base_receipt.read_bytes());a.output.parent.mkdir(parents=True,exist_ok=True);a.receipt.parent.mkdir(parents=True,exist_ok=True);a.output.write_bytes(c);a.receipt.write_text(json.dumps(r,indent=2,sort_keys=True)+"\n");print(json.dumps({"candidate_sha256":r["candidate_sha256"],"output":str(a.output)}));return 0
if __name__=="__main__":raise SystemExit(main())
