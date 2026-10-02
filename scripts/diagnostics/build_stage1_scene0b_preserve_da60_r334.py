#!/usr/bin/env python3
"""Build r334: preserve live DA60-DA8D while installing DA00-DA5C/DA8E-DBFC."""
from __future__ import annotations
import argparse,hashlib,json
from pathlib import Path
import build_stage1_scene0b_complete_runtime_r331 as r331
ROOT=r331.ROOT;TMP=r331.TMP;BASE=r331.BASE;BASE_RECEIPT=r331.BASE_RECEIPT;OUTPUT=TMP/"stage1-scene0b-preserve-da60-r334/candidate.gb";RECEIPT=TMP/"stage1-scene0b-preserve-da60-r334/build-receipt.json"
def selected(s):
 r=[]
 for l,a,d,n in r331.r307.COPY_REGIONS:
  if l.startswith("DA60-"):continue
  r.append((l,d,s[r331.bo(r331.r307.CANONICAL_BANK,a):r331.bo(r331.r307.CANONICAL_BANK,a)+n]))
 a=r331.r307.CANONICAL_EXTENSION_SOURCE_ADDR;r.append(("DBF1-DBFC",0xDBF1,s[r331.bo(r331.r307.CANONICAL_BANK,a):r331.bo(r331.r307.CANONICAL_BANK,a)+len(r331.r307.CANONICAL_EXTENSION)]));return r
def build(s,q):
 old=r331.regions;r331.regions=selected
 try:c,p=r331.build(s,q)
 finally:r331.regions=old
 h=hashlib.sha256(c).hexdigest();return c,{"schema":"penta-stage1-scene0b-preserve-da60-r334-build-v1","status":"STATIC_PASS_LIVE_GATES_REQUIRED","promotable":False,"emulator_invoked":False,"candidate_sha256":h,"runtime_regions":p["runtime_regions"],"preserved_live_state":["DA60-DA8D"],"required_live_gates":p["required_live_gates"]}
def main():
 p=argparse.ArgumentParser();p.add_argument("--base",type=Path,default=BASE);p.add_argument("--base-receipt",type=Path,default=BASE_RECEIPT);p.add_argument("--output",type=Path,default=OUTPUT);p.add_argument("--receipt",type=Path,default=RECEIPT);a=p.parse_args();c,r=build(a.base.read_bytes(),a.base_receipt.read_bytes());a.output.parent.mkdir(parents=True,exist_ok=True);a.receipt.parent.mkdir(parents=True,exist_ok=True);a.output.write_bytes(c);a.receipt.write_text(json.dumps(r,indent=2,sort_keys=True)+"\n");print(json.dumps({"candidate_sha256":r["candidate_sha256"],"output":str(a.output)}));return 0
if __name__=="__main__":raise SystemExit(main())
