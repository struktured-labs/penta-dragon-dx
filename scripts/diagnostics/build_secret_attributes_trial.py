"""#23 diagnostic: publish a secret-only attribute plane before native tiles.

Not release-qualified: synchronous compilation/wait must be timed against the
parent. Uses bank36 and the existing compiler's SVBK3 scratch, no new RAM.
"""
import hashlib
import json
from pathlib import Path
import argparse
from build_later_hdma_overlap import Asm
from verify_pickup_class_palettes import PICKUPS

ROOT=Path(__file__).resolve().parents[2]
PARENT='eebf3f190d9d307cb1d3fa714fa2e68b7890fc5309d5da26682ce38cce0134fc'
HOOK=28*0x4000+0x2c80
BANK=36
BASE=BANK*0x4000
TABLE=0x7f00

def helper(chunked=False):
    a=Asm(0x6c80)
    a.db(0xf5,0xfa,0x80,0xd8,0xfe,9);a.jr(0x28,'secret')
    a.db(0xfe,10);a.jp(0xc2,'exit')
    a.label('secret')
    a.db(0xf0,0xba,0xfe,7);a.jp(0xc2,'exit')
    a.db(0xf0,0x55,0xfe,0xff);a.jp(0xc2,'exit')
    a.db(0xc5,0xd5,0xe5,0xf0,0x70,0xf5,0xf0,0x4f,0xf5)
    # Stack must remain on SVBK1: no pushes/pops until SVBK is restored.
    a.db(0xf3,0x3e,3,0xe0,0x70,0x11,0xa0,0xc1,0x21,0,0xd0,0x06,TABLE>>8)
    for row in range(24):
        for col in range(24):
            a.db(0x1a,0x13,0x4f,0x0a,0x22)
        # Initialize all eight padding cells as well.
        a.db(0xaf)
        for _ in range(8):a.db(0x22)
    a.db(0x3e,1,0xe0,0x70)
    # Restore saved registers only after returning to the original stack bank.
    a.db(0xf1,0x4f,0xf1,0x47,0xe1,0xe5,0xc5)
    if not chunked:
        a.db(0xf0,0x40,0xcb,0x7f);a.jr(0x28,'dma')
        a.label('wait')
        a.db(0xf0,0x44,0xfe,144);a.jr(0x20,'wait')
    a.label('dma')
    a.db(0x7c,0xe6,0x1f,0xe0,0x53,0xaf,0xe0,0x54,0xe0,0x52)
    a.db(0x3e,0xd0,0xe0,0x51,0x3e,3,0xe0,0x70)
    a.db(0x3e,1,0xe0,0x4f)
    if chunked:
        a.db(0xf0,0x40,0xcb,0x7f);a.jr(0x28,'whole_dma')
        a.db(0x0e,48)
        a.label('block')
        a.db(0xf0,0x44,0xfe,144);a.jr(0x30,'copy_block')
        a.label('mode3')
        a.db(0xf0,0x41,0xe6,3,0xfe,3);a.jr(0x20,'mode3')
        a.label('mode0')
        a.db(0xf0,0x41,0xe6,3);a.jr(0x20,'mode0')
        a.label('copy_block')
        a.db(0xaf,0xe0,0x55,0x0d);a.jr(0x20,'block')
        a.jr(0x18,'dma_done')
        a.label('whole_dma')
    a.db(0x3e,0x2f,0xe0,0x55)
    a.label('dma_done')
    a.db(0x3e,1,0xe0,0x70)
    a.db(0xc1,0x79,0xe0,0x4f,0x78,0xe0,0x70,0xe1,0xd1,0xc1,0xfb)
    a.label('exit')
    a.db(0xf1,0x11,0xa0,0xc1,0x0e,0x41,0x3e,28,0xc9)
    return a.finish()

def build(parent, chunked=False):
    if hashlib.sha256(parent).hexdigest()!=PARENT:raise ValueError('exact source07 required')
    if parent[HOOK:HOOK+5]!=bytes.fromhex('11a0c10e41'):raise ValueError('copier entry differs')
    if parent[BASE:BASE+0x4000]!=b'\xff'*0x4000:raise ValueError('bank36 occupied')
    code=helper(chunked)
    assert 0x6c80+len(code)<=TABLE
    table=bytearray(256)
    for pickup in PICKUPS:
        for tile in pickup.tiles:table[tile]=pickup.palette
    rom=bytearray(parent)
    rom[HOOK:HOOK+5]=bytes([0x3e,BANK,0xcd,0x47,0x08])
    pos=BASE+0x2c80;rom[pos:pos+len(code)]=code
    pos=BASE+TABLE-0x4000;rom[pos:pos+256]=table
    rom[0x14e:0x150]=((sum(rom[:0x14e])+sum(rom[0x150:]))&65535).to_bytes(2,'big')
    return bytes(rom)

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('parent',type=Path);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--chunked',action='store_true',help='bounded one-block GDMA in each HBlank instead of whole-VBlank wait')
    args=p.parse_args();out=args.output.resolve()
    if out.exists() or (ROOT/'tmp').resolve() not in out.parents:p.error('fresh repo tmp directory required')
    rom=build(args.parent.read_bytes(),args.chunked);out.mkdir(parents=True)
    (out/'candidate.gb').write_bytes(rom)
    receipt=dict(issue=23,parent_sha256=PARENT,candidate_sha256=hashlib.sha256(rom).hexdigest(),
        experimental=True,release_qualified=False,helper_bytes=len(helper(args.chunked)),chunked=args.chunked,
        cave_bank=BANK,scope='scene09/0A with FFBA7 only; synchronous pre-tile attributes',
        builder_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest())
    (out/'build-receipt.json').write_text(json.dumps(receipt,indent=2)+'\n')
    print(json.dumps(receipt))
