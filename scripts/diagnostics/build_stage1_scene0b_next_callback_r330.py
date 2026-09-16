#!/usr/bin/env python3
"""Build r330: diagnostic next-callback commit for r329.

This ablates only r329's two physical-key wait predicates.  It determines
whether the temporary current gateway itself breaks menu input or whether the
stackless transaction simply remains armed because one key never repopulates.
Non-promotable regardless of outcome.
"""

from __future__ import annotations
import argparse, hashlib, json
from pathlib import Path
import build_stage1_scene0b_stackless_transaction_r329 as r329

ROOT=r329.ROOT; TMP=r329.TMP; BASE=r329.BASE; BASE_RECEIPT=r329.BASE_RECEIPT
OUTPUT=TMP/"stage1-scene0b-next-callback-r330/candidate.gb"
RECEIPT=TMP/"stage1-scene0b-next-callback-r330/build-receipt.json"

def build(source: bytes, receipt_bytes: bytes):
    candidate, parent = r329.build(source, receipt_bytes)
    rom=bytearray(candidate)
    start=r329.offset(r329.HANDLER_LABELS["pending_keys"])
    end=start
    # Two exact LD A,[a16]; CP FF; JP Z,resume predicates.
    for address in r329.CACHE_ADDRS:
        expected=bytes((0xFA,address&0xFF,address>>8,0xFE,0xFF,0xCA)) + r329.HANDLER_LABELS["resume"].to_bytes(2,"little")
        if rom[end:end+len(expected)] != expected: raise AssertionError("r330 key-wait preimage changed")
        end += len(expected)
    rom[start:end]=bytes(end-start)
    r329.r321.r320.r319.r318.r317.r305.r304.update_checksums(rom)
    result=bytes(rom); checked=bytearray(result); r329.r321.r320.r319.r318.r317.r305.r304.update_checksums(checked)
    if bytes(checked)!=result: raise AssertionError("r330 checksums not canonical")
    sha=hashlib.sha256(result).hexdigest()
    return result,{"schema":"penta-stage1-scene0b-next-callback-r330-build-v1","status":"DIAGNOSTIC_LIVE_GATE_REQUIRED","promotable":False,"emulator_invoked":False,"candidate_sha256":sha,"base_r329":parent["candidate_sha256"],"ablation":"DF53/DF57 repopulation wait removed; next authenticated callback commits"}

def main():
    p=argparse.ArgumentParser(); p.add_argument("--base",type=Path,default=BASE); p.add_argument("--base-receipt",type=Path,default=BASE_RECEIPT); p.add_argument("--output",type=Path,default=OUTPUT); p.add_argument("--receipt",type=Path,default=RECEIPT); a=p.parse_args()
    c,r=build(a.base.read_bytes(),a.base_receipt.read_bytes()); a.output.parent.mkdir(parents=True,exist_ok=True); a.receipt.parent.mkdir(parents=True,exist_ok=True); a.output.write_bytes(c); a.receipt.write_text(json.dumps(r,indent=2,sort_keys=True)+"\n"); print(json.dumps({"candidate_sha256":r["candidate_sha256"],"output":str(a.output)})); return 0
if __name__=="__main__": raise SystemExit(main())
