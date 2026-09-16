#!/usr/bin/env python3
"""Stage1 double-speed eight-tile writes per fresh VRAM access interval.

No staging or asynchronous publication. Eight LD A,(DE)/INC DE/LD(HL+),A
triples take192 Tcycles =96dots at double speed. Fresh mode0 plus following
mode2 provides at least165dots (Pan Docs); polling/branch overhead fits the
remaining69dots. Interrupts are disabled until all eight writes finish.
https://gbdev.io/pandocs/Accessing_VRAM_and_OAM.html
"""
from pathlib import Path
import hashlib
import json
from build_later_hdma_overlap import Asm
from build_stage1_fast_final_window_selector_r363 import update_checksums

ROOT=Path(__file__).resolve().parents[2]
BASE=ROOT/'tmp/first-dirty-isolated-r398/candidate.gb'
SHA='486146829f79674437e05dcf4537aec7a68a051247e21b650743c89cfd850fd2'
OUT=ROOT/'tmp/eight-tile-groups-r401'
OFFSET=26*0x4000+0x2C80


def service():
    a=Asm(0x6C80)
    a.db(0xFA,0x80,0xD8,0xFE,2);a.jp(0xC2,'fallback')
    a.db(0xF0,0xBA,0xB7);a.jp(0xC2,'fallback')
    a.db(0xF0,0x4D,0xCB,0x7F);a.jp(0xCA,'fallback')
    a.db(0xC5,0x11,0xA0,0xC1,0x06,24)
    a.label('row');a.db(0x0E,3)
    a.label('group');a.db(0xF3)
    a.db(0xF0,0x40,0xCB,0x7F);a.jr(0x28,'copy')
    a.db(0xF0,0x44,0xE6,0xF8,0xFE,0x90);a.jr(0x28,'copy')
    a.label('mode3');a.db(0xF0,0x41,0xE6,3,0xFE,3);a.jr(0x20,'mode3')
    a.label('mode0');a.db(0xF0,0x41,0xE6,3);a.jr(0x20,'mode0')
    a.label('copy')
    for _ in range(8):a.db(0x1A,0x13,0x22)
    a.db(0xFB,0x0D);a.jr(0x20,'group')
    a.db(0x7D,0xC6,8,0x6F);a.jr(0x30,'nextrow')
    a.db(0x24)
    a.label('nextrow');a.db(0x05);a.jr(0x20,'row')
    a.db(0xC1,0x0E,0,0xAF,0x3C,0xC9)
    a.label('fallback');a.db(0xAF,0x3E,1,0xC9)
    return a.finish()


def build(source, code=None):
    if hashlib.sha256(source).hexdigest()!=SHA:raise ValueError('wrong r398')
    if code is None:code=service()
    assert source[0x42B8:0x42C3]==bytes.fromhex('11 A0 C1 3E 18 F5 0E 06 C3 30 43')
    assert source[0x13B3:0x13C0]==bytes(13)
    assert source[0x13DE:0x13E5]==bytes(7)
    assert source[OFFSET:OFFSET+len(code)]==bytes([255])*len(code)
    rom=bytearray(source)
    rom[0x42B8:0x42BB]=bytes.fromhex('C3 B3 13')
    rom[0x13B3:0x13BE]=bytes.fromhex('3E 1A CD 47 08 C2 ED 42 C3 DE 13')
    rom[0x13DE:0x13E4]=bytes.fromhex('11 A0 C1 C3 BB 42')
    rom[OFFSET:OFFSET+len(code)]=code
    update_checksums(rom)
    return bytes(rom)


if __name__=='__main__':
    rom=build(BASE.read_bytes());OUT.mkdir(parents=True,exist_ok=True)
    target=OUT/'candidate.gb'
    if target.exists() and target.read_bytes()!=rom:raise SystemExit('candidate collision')
    target.write_bytes(rom)
    receipt=dict(experimental=True,promotable=False,base_sha256=SHA,
                 candidate_sha256=hashlib.sha256(rom).hexdigest())
    (OUT/'build-receipt.json').write_text(json.dumps(receipt,indent=2)+'\n')
    print(receipt)
