#!/usr/bin/env python3
"""Experiment: inline all nine classifier calls, preserving matched handlers.

No RAM allocation and no scanner predicate is omitted. Bank24 owns the new
row loop; exact bank19 handlers still own every matched phase and transition.
"""
from pathlib import Path
import hashlib
import json
from build_stage1_fast_final_window_selector_r363 import update_checksums

ROOT=Path(__file__).resolve().parents[2]
BASE=ROOT/'tmp/deferred-commit-guard-r374/candidate.gb'
BASE_SHA='85b390e48d1d8405acc1f03dee3de8944610e35206f9dbd53be1c0e3e6682922'
OUT=ROOT/'tmp/inline-hazard-scanner-r379'
TARGETS=(0x618F,0x6CE9,0x67E4,0x6B60,0x6B64,0x62CD,0x6CEF,0x6CF5,0x61A9)
COLS=(0,1,2,4,5,6,7,9,10)
STUB=bytes.fromhex('F5 3E 18 CD 61 00 F1 C3 80 6C')


def offset(bank,addr):return bank*0x4000+addr-0x4000


def make_body(fast_source=False):
    code=bytearray();labels={};fixups=[]
    def emit(s):code.extend(bytes.fromhex(s))
    def mark(s):labels[s]=0x6C80+len(code)
    def jump(op,label):
        code.append(op);fixups.append((len(code),label));code.extend((0,0))
    mark('row');emit('C5 D5 E5')
    previous=0
    for index,col in enumerate(COLS):
        code.extend([0x1C if fast_source else 0x13]*(col-previous));previous=col
        emit('1A')
        if col==4:
            emit('FE 6A');jump(0xCA,f'match{index}')
        emit('E6 EF D6 64 FE 06');jump(0xDA,f'match{index}')
    # Exact no-match row-advance ABI, including original carry behavior.
    emit('E1 D1 C1 7D C6 20 6F 30 01 24 7B C6 18 5F 30 01 14 05')
    jump(0xC2,'row');jump(0xC3,'done')
    for index in range(len(COLS)):
        mark(f'match{index}')
        # Preserve AF/BC around MBC mapping. The mirrored bank19 bridge
        # removes these saves before entering the original matched handler.
        bridge=0x61C6+index*5
        emit('F5 C5 01');code.extend(bridge.to_bytes(2,'little'))
        emit('C5 3E 13 C3 61 00')
    mark('done')
    emit('F5 C5 01 8B 11 C5 3E 13 C3 61 00')
    for pos,label in fixups:code[pos:pos+2]=labels[label].to_bytes(2,'little')
    return bytes(code)


BODY=make_body()


def build(source):
    if hashlib.sha256(source).hexdigest()!=BASE_SHA:raise ValueError('wrong r374 base')
    assert source[offset(19,0x61B7):offset(19,0x61BC)]==bytes.fromhex('11 A0 C1 06 18')
    assert source[offset(19,0x6C88):offset(19,0x6C8F)]==bytes.fromhex('E6 EF D6 64 FE 06 C9')
    assert source[offset(19,0x6208):offset(19,0x620E)]==bytes.fromhex('C2 BC 61 C3 C0 55')
    assert source[0x1188:0x118B]==bytes.fromhex('CB BF C9')
    for addr,payload in ((0x61BC,STUB),(0x6C80,BODY)):
        start=offset(24,addr)
        assert source[start:start+len(payload)]==b'\xff'*len(payload)
    rom=bytearray(source)
    for bank in (19,24):
        start=offset(bank,0x61BC);rom[start:start+len(STUB)]=STUB
    for index,target in enumerate(TARGETS):
        start=offset(19,0x61C6+index*5)
        rom[start:start+5]=bytes.fromhex('C1 F1 C3')+target.to_bytes(2,'little')
    # The row-advance tail $61F6 remains untouched. The zero-row completion
    # bridge uses five bytes retired by r368's unconditional priority RET.
    rom[0x118B:0x1190]=bytes.fromhex('C1 F1 C3 C0 55')
    start=offset(24,0x6C80);rom[start:start+len(BODY)]=BODY
    update_checksums(rom)
    return bytes(rom)


if __name__=='__main__':
    rom=build(BASE.read_bytes());OUT.mkdir(parents=True,exist_ok=True)
    target=OUT/'candidate.gb'
    if target.exists() and target.read_bytes()!=rom:raise SystemExit('candidate collision')
    target.write_bytes(rom)
    receipt={'schema':'penta-inline-hazard-scanner-r379-build-v1','experimental':True,
             'base_sha256':BASE_SHA,'candidate_sha256':hashlib.sha256(rom).hexdigest(),
             'live_tested':False,'body_size':len(BODY),'matched_targets':list(TARGETS)}
    (OUT/'build-receipt.json').write_text(json.dumps(receipt,indent=2)+'\n')
    print(receipt['candidate_sha256'])
