#!/usr/bin/env python3
"""Experimental Stage1 tile GDMA using the not-yet-compiled attribute buffer.

Preserve all 8 padding columns by reading them in fresh HBlank. Build the
24x32 tile image in SVBK3:D000, GDMA in VBlank, then let the unchanged code
compile attributes into that same buffer. No new RAM or dropped tile writes.
"""
from pathlib import Path
import hashlib
import json
from build_later_hdma_overlap import Asm
from build_stage1_fast_final_window_selector_r363 import update_checksums

ROOT=Path(__file__).resolve().parents[2]
BASE=ROOT/'tmp/first-dirty-isolated-r398/candidate.gb'
SHA='486146829f79674437e05dcf4537aec7a68a051247e21b650743c89cfd850fd2'
OUT=ROOT/'tmp/staged-tile-gdma-r399'
BANK=26
OFFSET=BANK*0x4000+0x2C80


def service():
    a=Asm(0x6C80)
    a.db(0xFA,0x80,0xD8,0xFE,2);a.jp(0xC2,'fallback')
    a.db(0xF0,0xBA,0xB7);a.jp(0xC2,'fallback')
    a.db(0xF3,0xC5,0x4C)  # DI; save BC; C=destination page H
    a.db(0xAF,0xE0,0x4F,0x3E,3,0xE0,0x70)
    a.db(0x11,0xA0,0xC1,0x21,0,0xD0,0x06,24)
    a.label('source_row')
    for _ in range(24): a.db(0x1A,0x22,0x13)
    a.db(0x7D,0xC6,8,0x6F);a.jr(0x30,'source_next')
    a.db(0x24)
    a.label('source_next');a.db(0x05);a.jr(0x20,'source_row')
    a.db(0x51,0x1E,24,0x21,24,0xD0,0x06,24) # DE=VRAM padding; HL=buffer padding
    a.label('padding_row')
    a.db(0xF0,0x40,0xCB,0x7F);a.jr(0x28,'padding_copy')
    a.label('mode3');a.db(0xF0,0x41,0xE6,3,0xFE,3);a.jr(0x20,'mode3')
    a.label('mode0');a.db(0xF0,0x41,0xE6,3);a.jr(0x20,'mode0')
    a.label('padding_copy')
    for _ in range(8):a.db(0x1A,0x22,0x13)
    a.db(0x7D,0xC6,24,0x6F);a.jr(0x30,'padding_hl')
    a.db(0x24)
    a.label('padding_hl')
    a.db(0x7B,0xC6,24,0x5F);a.jr(0x30,'padding_de')
    a.db(0x14)
    a.label('padding_de');a.db(0x05);a.jr(0x20,'padding_row')
    a.db(0x3E,1,0xE0,0x70,0xFB) # restore stack bank before admitting Timer
    a.label('wait')
    a.db(0xF0,0x40,0xCB,0x7F);a.jr(0x28,'lcd_off')
    a.db(0xF0,0x44,0xE6,0xFC,0xFE,0x90);a.jr(0x20,'wait')
    a.db(0xF3,0xF0,0x44,0xE6,0xFC,0xFE,0x90);a.jr(0x28,'dma')
    a.db(0xFB);a.jr(0x18,'wait')
    a.label('lcd_off');a.db(0xF3)
    a.label('dma')
    a.db(0x3E,3,0xE0,0x70,0x3E,0xD0,0xE0,0x51,0xAF,0xE0,0x52)
    a.db(0x79,0xE6,0x1F,0xE0,0x53,0xAF,0xE0,0x54,0x3E,0x2F,0xE0,0x55)
    a.db(0x3E,1,0xE0,0x70) # GDMA completion stalls CPU; restore stack bank
    a.db(0x79,0xC6,3,0x67,0x2E,0,0x11,0xE0,0xC3,0xC1,0x0E,0)
    a.db(0xAF,0x3C,0xC9) # A=1,Z=0: fixed bridge reaches tiles_end
    a.label('fallback');a.db(0xAF,0x3E,1,0xC9) # A=1,Z=1
    return a.finish()


def build(source):
    if hashlib.sha256(source).hexdigest()!=SHA:raise ValueError('wrong exact r398')
    code=service()
    assert source[0x42B3:0x42C3]==bytes.fromhex('F3 CD 13 DA 00 11 A0 C1 3E 18 F5 0E 06 C3 30 43')
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
