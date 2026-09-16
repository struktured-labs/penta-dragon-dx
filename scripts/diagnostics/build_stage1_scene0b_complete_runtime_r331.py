#!/usr/bin/env python3
"""Build r331: install the complete DF51-owned resident runtime inventory.

r327 copied only DA8E-DAFF and still entered a non-returning current DAD7
route.  The native installer publishes DF51 only after DA00-DAFF, DB80-DBF0,
and DBF1-DBFC are coherent.  r331 mirrors that complete canonical inventory
into bank31 and copies every region under DI before enabling DAD7.  It retains
r325's native menu-art wrapper and r320's atomic presentation leaf.
"""

from __future__ import annotations
import argparse, hashlib, json
from pathlib import Path
import build_stage1_scene0b_menu_art_phase_repair_r325 as r325
import build_stage1_scene0b_runtime_selfheal_r313 as r313
import build_stage1_bank16_installer_mirror_r307 as r307

ROOT=r325.ROOT; TMP=r325.TMP; BASE=r325.BASE; BASE_RECEIPT=r325.BASE_RECEIPT
OUTPUT=TMP/"stage1-scene0b-complete-runtime-r331/candidate.gb"
RECEIPT=TMP/"stage1-scene0b-complete-runtime-r331/build-receipt.json"
REPAIR_ADDR=r313.HANDLER_LABELS["repair"]; RESUME_ADDR=r313.HANDLER_LABELS["resume"]
REPAIR_SIZE=RESUME_ADDR-REPAIR_ADDR; CAVE_ADDR=0x6F00; PAYLOAD_ADDR=0x7100

def bo(bank,address): return r325.r324.r321.bank_offset(bank,address)
def o(address): return bo(31,address)

def regions(source):
    result=[]
    for label,src,dst,width in r307.COPY_REGIONS:
        result.append((label,dst,source[bo(r307.CANONICAL_BANK,src):bo(r307.CANONICAL_BANK,src)+width]))
    ext_src=r307.CANONICAL_EXTENSION_SOURCE_ADDR
    result.append(("DBF1-DBFC",0xDBF1,source[bo(r307.CANONICAL_BANK,ext_src):bo(r307.CANONICAL_BANK,ext_src)+len(r307.CANONICAL_EXTENSION)]))
    return result

def _emit(base, parent, chunks):
    rom=bytearray(base)
    payload=b""; code=bytearray((0xF3,)); cursor=PAYLOAD_ADDR
    for label,dst,data in chunks:
        if not data or len(data)>255: raise AssertionError(f"r331 bad region {label}")
        # LD HL,src; LD DE,dst; LD B,n; loop: LDI A,[HL]; LD [DE],A; INC DE; DEC B; JR NZ loop.
        code += bytes((0x21,))+cursor.to_bytes(2,"little")+bytes((0x11,))+dst.to_bytes(2,"little")+bytes((0x06,len(data),0x2A,0x12,0x13,0x05,0x20,0xFA))
        payload += data; cursor += len(data)
    local=REPAIR_ADDR-r313.HANDLER_ADDR; repair=r313.HANDLER[local:local+REPAIR_SIZE]
    code += repair + bytes((0xC3,))+RESUME_ADDR.to_bytes(2,"little")
    repair_off=o(REPAIR_ADDR); cave_off=o(CAVE_ADDR); payload_off=o(PAYLOAD_ADDR)
    for off,width,label in ((cave_off,len(code),"copy cave"),(payload_off,len(payload),"payload")):
        if rom[off:off+width] != bytes([0xFF])*width: raise AssertionError(f"r331 {label} preimage not erased")
    rom[repair_off:repair_off+REPAIR_SIZE]=bytes((0xC3,))+CAVE_ADDR.to_bytes(2,"little")+bytes(REPAIR_SIZE-3)
    rom[cave_off:cave_off+len(code)]=code; rom[payload_off:payload_off+len(payload)]=payload
    r325.r324.r321.r320.r319.r318.r317.r305.r304.update_checksums(rom); candidate=bytes(rom)
    checked=bytearray(candidate); r325.r324.r321.r320.r319.r318.r317.r305.r304.update_checksums(checked)
    if bytes(checked)!=candidate: raise AssertionError("r331 checksums not canonical")
    sha=hashlib.sha256(candidate).hexdigest()
    return candidate,{"schema":"penta-stage1-scene0b-complete-runtime-r331-construction-v1","status":"construction-only","historical_evidence_consumed":False,"fresh_live_qualification":False,"promotable":False,"emulator_invoked":False,"candidate_sha256":sha,"base_r325":parent["candidate_sha256"],"runtime_regions":[{"label":l,"destination":f"${d:04X}","bytes":len(x)} for l,d,x in chunks],"runtime_payload_bytes":len(payload),"copy_code_bytes":len(code),"patch":{"ordering":"DI; copy selected DF51-owned inventory; exact r313 gateway/cache repair","menu_art":"r325 retained","atomic_publisher":"r320 retained"},"required_live_gates":["scene0B full menu/visual","hazard","north","speed"]}


def _construct_selected(source, chunks):
    base, parent = r325.construct(source)
    return _emit(base, parent, chunks)


def construct(source):
    return _construct_selected(source, regions(source))


def _build_selected(source, receipt_bytes, chunks):
    base, parent = r325.build(source, receipt_bytes)
    candidate, receipt = _emit(base, parent, chunks)
    receipt.update({"schema": "penta-stage1-scene0b-complete-runtime-r331-build-v1",
                    "status": "STATIC_PASS_LIVE_GATES_REQUIRED"})
    receipt["patch"]["ordering"] = "DI; copy full DF51-owned inventory; exact r313 gateway/cache repair"
    del receipt["historical_evidence_consumed"], receipt["fresh_live_qualification"]
    return candidate, receipt


def build(source, receipt_bytes):
    return _build_selected(source, receipt_bytes, regions(source))

def main():
    p=argparse.ArgumentParser(); p.add_argument("--base",type=Path,default=BASE); p.add_argument("--base-receipt",type=Path,default=BASE_RECEIPT); p.add_argument("--output",type=Path,default=OUTPUT); p.add_argument("--receipt",type=Path,default=RECEIPT); a=p.parse_args(); c,r=build(a.base.read_bytes(),a.base_receipt.read_bytes()); a.output.parent.mkdir(parents=True,exist_ok=True); a.receipt.parent.mkdir(parents=True,exist_ok=True); a.output.write_bytes(c); a.receipt.write_text(json.dumps(r,indent=2,sort_keys=True)+"\n"); print(json.dumps({"candidate_sha256":r["candidate_sha256"],"runtime_payload_bytes":r["runtime_payload_bytes"],"output":str(a.output)})); return 0
if __name__=="__main__": raise SystemExit(main())
