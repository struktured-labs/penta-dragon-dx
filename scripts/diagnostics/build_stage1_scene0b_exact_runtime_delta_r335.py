#!/usr/bin/env python3
"""Build r335: install the exact serialized-runtime delta only.

Both authenticated operator states already match current DA00-DA5C byte for
byte except DA16: the stale runtime writes the old FFA5 latch while r316+
consumers read FF01.  r335 copies only that one relocated operand, plus the
DA8E-DAFF/DB80-DBFC code/helper regions proven stale.  DA60-DA8D and every
other already-current DA00 byte remain live and untouched.
"""
from __future__ import annotations
import argparse,hashlib,json
from pathlib import Path
import build_stage1_scene0b_complete_runtime_r331 as r331
ROOT=r331.ROOT;TMP=r331.TMP;BASE=r331.BASE;BASE_RECEIPT=r331.BASE_RECEIPT;OUTPUT=TMP/"stage1-scene0b-exact-runtime-delta-r335/candidate.gb";RECEIPT=TMP/"stage1-scene0b-exact-runtime-delta-r335/build-receipt.json"
def selected_regions():
    """Return source-owned (label, ROM offset, WRAM destination, width) layout."""
    bank = r331.r307.CANONICAL_BANK
    # The sole authenticated DA00-DA5C delta: LDH [FFA5],A -> LDH [FF01],A.
    regions = [("DA16-selector-latch", r331.bo(bank, 0x7B16), 0xDA16, 1)]
    for label, address, destination, width in r331.r307.COPY_REGIONS:
        if label.startswith("DA00-") or label.startswith("DA60-"):
            continue
        regions.append((label, r331.bo(bank, address), destination, width))
    regions.append((
        "DBF1-DBFC", r331.bo(bank, r331.r307.CANONICAL_EXTENSION_SOURCE_ADDR),
        0xDBF1, len(r331.r307.CANONICAL_EXTENSION),
    ))
    return regions


def selected(source):
    return [(label, destination, source[offset:offset + width])
            for label, offset, destination, width in selected_regions()]
def construct(source):
    candidate, parent = r331._construct_selected(source, selected(source))
    return candidate, {
        "schema": "penta-stage1-scene0b-exact-runtime-delta-r335-construction-v1",
        "status": "construction-only", "promotable": False,
        "emulator_invoked": False, "historical_evidence_consumed": False,
        "fresh_live_qualification": False,
        "candidate_sha256": hashlib.sha256(candidate).hexdigest(),
        "runtime_regions": parent["runtime_regions"],
        "source_selected_da00_delta": {"address": "DA16", "new": "01"},
        "preserved_live_state": ["DA00-DA15", "DA17-DA8D"],
        "required_live_gates": parent["required_live_gates"],
    }


def build(source, receipt_bytes):
    candidate, parent = r331._build_selected(source, receipt_bytes, selected(source))
    return candidate, {
        "schema": "penta-stage1-scene0b-exact-runtime-delta-r335-build-v1",
        "status": "STATIC_PASS_LIVE_GATES_REQUIRED", "promotable": False,
        "emulator_invoked": False,
        "candidate_sha256": hashlib.sha256(candidate).hexdigest(),
        "runtime_regions": parent["runtime_regions"],
        "authenticated_da00_delta": {"address": "DA16", "old": "A5", "new": "01", "other_DA00_DA5C_differences": 0},
        "preserved_live_state": ["DA00-DA15", "DA17-DA8D"],
        "required_live_gates": parent["required_live_gates"],
    }
def main():
 p=argparse.ArgumentParser();p.add_argument("--base",type=Path,default=BASE);p.add_argument("--base-receipt",type=Path,default=BASE_RECEIPT);p.add_argument("--output",type=Path,default=OUTPUT);p.add_argument("--receipt",type=Path,default=RECEIPT);a=p.parse_args();c,r=build(a.base.read_bytes(),a.base_receipt.read_bytes());a.output.parent.mkdir(parents=True,exist_ok=True);a.receipt.parent.mkdir(parents=True,exist_ok=True);a.output.write_bytes(c);a.receipt.write_text(json.dumps(r,indent=2,sort_keys=True)+"\n");print(json.dumps({"candidate_sha256":r["candidate_sha256"],"output":str(a.output)}));return 0
if __name__=="__main__":raise SystemExit(main())
