#!/usr/bin/env python3
"""Experimental Stage-1 four-tile copying during early VBlank as well as HBlank."""
from pathlib import Path
import hashlib
import json
from build_stage1_fast_final_window_selector_r363 import update_checksums

ROOT = Path(__file__).resolve().parents[2]
BASE = ROOT / 'tmp/deferred-commit-guard-r374/candidate.gb'
BASE_SHA = '85b390e48d1d8405acc1f03dee3de8944610e35206f9dbd53be1c0e3e6682922'
OUT = ROOT / 'tmp/vblank-tile-copy-r376'
ENTRY, CAVE, CAVE_END = 0x42C0, 0x4330, 0x4354
OLD = bytes.fromhex('F3 F0 41 E6 03 FE 03 20 F8 F0 41 E6 03 20 FA')


def make_helper():
    code, labels, jumps = bytearray(), {}, []
    def emit(s): code.extend(bytes.fromhex(s))
    def mark(s): labels[s] = len(code)
    def jr(op, target):
        code.extend((op, 0)); jumps.append((len(code)-1,target))
    emit('F3 FA 80 D8 FE 02')
    jr(0x20,'mode3')
    # LY144..151 leaves at least two complete lines before visible drawing.
    # Only the unchanged four-tile (96 native T-cycle) write group follows.
    emit('F0 44 E6 F8 FE 90')
    jr(0x28,'copy')
    mark('mode3'); emit('F0 41 E6 03 FE 03'); jr(0x20,'mode3')
    mark('mode0'); emit('F0 41 E6 03'); jr(0x20,'mode0')
    mark('copy'); emit('C3 CF 42')
    for operand,target in jumps:
        delta=labels[target]-operand-1
        assert -128<=delta<=127
        code[operand]=delta&255
    return bytes(code),labels


HELPER,LABELS=make_helper()


def build(source):
    if hashlib.sha256(source).hexdigest()!=BASE_SHA: raise ValueError('wrong r374 base')
    assert source[ENTRY:ENTRY+len(OLD)]==OLD
    assert len(HELPER)<=CAVE_END-CAVE
    assert source[CAVE:CAVE_END]==bytes(CAVE_END-CAVE)
    rom=bytearray(source)
    rom[ENTRY:ENTRY+len(OLD)]=bytes.fromhex('C3 30 43')+bytes(len(OLD)-3)
    rom[CAVE:CAVE+len(HELPER)]=HELPER
    update_checksums(rom)
    return bytes(rom)


if __name__=='__main__':
    rom=build(BASE.read_bytes()); OUT.mkdir(parents=True,exist_ok=True)
    target=OUT/'candidate.gb'
    if target.exists() and target.read_bytes()!=rom: raise SystemExit('candidate collision')
    target.write_bytes(rom)
    receipt={'schema':'penta-vblank-tile-copy-r376-build-v1','experimental':True,
             'base_sha256':BASE_SHA,'candidate_sha256':hashlib.sha256(rom).hexdigest(),
             'helper_hex':HELPER.hex(),'live_tested':False}
    (OUT/'build-receipt.json').write_text(json.dumps(receipt,indent=2)+'\n')
    print(receipt['candidate_sha256'])
