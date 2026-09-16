#!/usr/bin/env python3
"""Build r332: install only resident code/helper regions, preserving live state.

r331 restores menu control and final semantic attributes, but copying active
DA00-DA8D state changes the reconstructed world source and produces an 87-cell
geometry drift.  r332 retains the coherent DA8E-DAFF and DB80-DBFC executable/
helper inventory while leaving DA00-DA8D untouched.
"""
from __future__ import annotations
import argparse, hashlib, json
from pathlib import Path
import build_stage1_scene0b_complete_runtime_r331 as r331

ROOT=r331.ROOT; TMP=r331.TMP; BASE=r331.BASE; BASE_RECEIPT=r331.BASE_RECEIPT
OUTPUT=TMP/"stage1-scene0b-code-runtime-r332/candidate.gb"; RECEIPT=TMP/"stage1-scene0b-code-runtime-r332/build-receipt.json"

def code_regions(source):
    result=[]
    for label,src,dst,width in r331.r307.COPY_REGIONS:
        if label.startswith("DA00-") or label.startswith("DA60-"): continue
        result.append((label,dst,source[r331.bo(r331.r307.CANONICAL_BANK,src):r331.bo(r331.r307.CANONICAL_BANK,src)+width]))
    src=r331.r307.CANONICAL_EXTENSION_SOURCE_ADDR
    result.append(("DBF1-DBFC",0xDBF1,source[r331.bo(r331.r307.CANONICAL_BANK,src):r331.bo(r331.r307.CANONICAL_BANK,src)+len(r331.r307.CANONICAL_EXTENSION)]))
    return result

def build(source,receipt_bytes):
    original=r331.regions; r331.regions=code_regions
    try: candidate,parent=r331.build(source,receipt_bytes)
    finally: r331.regions=original
    sha=hashlib.sha256(candidate).hexdigest()
    return candidate,{"schema":"penta-stage1-scene0b-code-runtime-r332-build-v1","status":"STATIC_PASS_LIVE_GATES_REQUIRED","promotable":False,"emulator_invoked":False,"candidate_sha256":sha,"base_r331_builder":parent["candidate_sha256"],"runtime_regions":parent["runtime_regions"],"preserved_live_state":["DA00-DA5C","DA60-DA8D"],"patch":parent["patch"],"required_live_gates":parent["required_live_gates"]}

def main():
    p=argparse.ArgumentParser(); p.add_argument("--base",type=Path,default=BASE); p.add_argument("--base-receipt",type=Path,default=BASE_RECEIPT); p.add_argument("--output",type=Path,default=OUTPUT); p.add_argument("--receipt",type=Path,default=RECEIPT); a=p.parse_args(); c,r=build(a.base.read_bytes(),a.base_receipt.read_bytes()); a.output.parent.mkdir(parents=True,exist_ok=True); a.receipt.parent.mkdir(parents=True,exist_ok=True); a.output.write_bytes(c); a.receipt.write_text(json.dumps(r,indent=2,sort_keys=True)+"\n"); print(json.dumps({"candidate_sha256":r["candidate_sha256"],"regions":[x["label"] for x in r["runtime_regions"]],"output":str(a.output)})); return 0
if __name__=="__main__": raise SystemExit(main())
