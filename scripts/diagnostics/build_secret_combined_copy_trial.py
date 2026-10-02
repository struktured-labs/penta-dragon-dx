"""#23 experiment: replace, rather than precede, the secret tile copier."""
import argparse, hashlib, json
from pathlib import Path
from build_later_hdma_overlap import Asm
from build_secret_attributes_trial import ROOT,PARENT,HOOK,BANK,BASE,PICKUPS
CEILING_SOURCE07 = 'f7896dee8620a85ca3e1a9596647968557cf3fa8f4cee58a9b10189ebaad0898'

def gate():
    a=Asm(0x4000)
    a.db(0xf0,0xba,0xfe,7);a.jr(0x20,'native')
    a.db(0xfa,0x80,0xd8,0xfe,9);a.jr(0x28,'secret')
    a.db(0xfe,10);a.jr(0x20,'native')
    a.label('secret');a.db(0x3e,BANK,0xcd,0x47,0x08,0x0e,0,0x3e,1,0xc9)
    a.label('native');a.db(0x11,0xa0,0xc1,0x0e,0x41,0xc3,0x85,0x6c)
    return a.finish()

def helper(scratch_bank=3, yield_between_rows=False):
    a=Asm(0x6c80)
    a.db(0xc5,0xd5,0xe5,0xf3,0x3e,scratch_bank,0xe0,0x70)
    # Bank3 reproduces the rejected collision with executable D400 code.
    # Bank6 is an experimental separate allocation, not release-audited.
    # No stack operations or interrupts until returning to SVBK1.
    a.db(0x11,0xa0,0xc1,0x21,0,0xd0,0x06,0x7f)
    for row in range(24):
        for col in range(24):
            a.db(0x1a,0x13,0x4f,0xcb,0xd4,0x77,0xcb,0x94,0x0a,0x22)
        a.db(0xaf)
        for _ in range(8):a.db(0xcb,0xd4,0x77,0xcb,0x94,0x22)
        if yield_between_rows and row < 23:
            # Interrupt handlers must see their original bank1 stack. Never EI
            # while bank6 is mapped; resume staging only after DI executes.
            a.db(0x3e,1,0xe0,0x70,0xfb,0x00,0xf3,0x3e,scratch_bank,0xe0,0x70)
    # Code exceeds the default 6C80 cave: a separate body is emitted at4000.
    return a

def code(scratch_bank=3, yield_between_rows=False):
    # Compile the unrolled body at4000, with an entry trampoline at6C80.
    a=helper(scratch_bank,yield_between_rows);a.base=0x4000
    a.db(0x3e,1,0xe0,0x70,0xe1,0xe5)
    for plane in (1,0):
        tag=str(plane)
        a.db(0x7c,0xe6,0x1f,0xe0,0x53,0xaf,0xe0,0x54,0xe0,0x52)
        a.db(0x3e,0xd0 if plane else 0xd4,0xe0,0x51,0x0e,24)
        a.label('block'+tag)
        a.db(0xfb,0x00,0xf3,0xf0,0x40,0xcb,0x7f);a.jr(0x28,'copy'+tag)
        a.db(0xf0,0x44,0xfe,144);a.jr(0x30,'copy'+tag)
        a.label('mode3'+tag);a.db(0xf0,0x41,0xe6,3,0xfe,3);a.jr(0x20,'mode3'+tag)
        a.label('mode0'+tag);a.db(0xf0,0x41,0xe6,3);a.jr(0x20,'mode0'+tag)
        a.label('copy'+tag)
        a.db(0x3e,scratch_bank,0xe0,0x70,0x3e,plane,0xe0,0x4f,0x3e,1,0xe0,0x55)
        a.db(0x3e,1,0xe0,0x70,0x0d);a.jr(0x20,'block'+tag)
    # Native copier leaves HL advanced by24 rows, DE by576 bytes and C=0.
    a.db(0xaf,0xe0,0x4f,0xe1,0xd1,0xc1,0x7c,0xc6,3,0x67,0x11,0xe0,0xc3,0x0e,0,0xfb,0x3e,28,0xc9)
    return a.finish()

def build(parent,scratch_bank=3,yield_between_rows=False):
    if scratch_bank not in (3,6):raise ValueError('unsupported diagnostic scratch bank')
    if hashlib.sha256(parent).hexdigest() not in (PARENT, CEILING_SOURCE07):raise ValueError('exact source07 or bounded ceiling-source07 required')
    if parent[HOOK:HOOK+5]!=bytes.fromhex('11a0c10e41'):raise ValueError('entry differs')
    if parent[BASE:BASE+0x4000]!=b'\xff'*0x4000:raise ValueError('bank36 occupied')
    g=gate();body=code(scratch_bank,yield_between_rows);assert 0x4000+len(body)<0x6c80
    loc=28*0x4000
    if parent[loc:loc+len(g)]!=b'\xff'*len(g):raise ValueError('local gate cave occupied')
    r=bytearray(parent);r[HOOK:HOOK+5]=bytes.fromhex('c300400000');r[loc:loc+len(g)]=g
    r[BASE:BASE+len(body)]=body;r[BASE+0x2c80:BASE+0x2c83]=bytes.fromhex('c30040')
    table=bytearray(256)
    for p in PICKUPS:
        for t in p.tiles:table[t]=p.palette
    r[BASE+0x3f00:BASE+0x4000]=table
    r[0x14e:0x150]=((sum(r[:0x14e])+sum(r[0x150:]))&65535).to_bytes(2,'big')
    return bytes(r)

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('parent',type=Path);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--scratch-bank',type=int,choices=(3,6),default=3)
    p.add_argument('--yield-between-rows',action='store_true')
    args=p.parse_args();out=args.output.resolve()
    if out.exists() or (ROOT/'tmp').resolve() not in out.parents:p.error('fresh repository tmp required')
    r=build(args.parent.read_bytes(),args.scratch_bank,args.yield_between_rows);out.mkdir(parents=True);(out/'candidate.gb').write_bytes(r)
    receipt=dict(issue=23,experimental=True,release_qualified=False,parent_sha256=hashlib.sha256(args.parent.read_bytes()).hexdigest(),
        candidate_sha256=hashlib.sha256(r).hexdigest(),helper_bytes=len(code(args.scratch_bank,args.yield_between_rows)),scratch_bank=args.scratch_bank,yield_between_rows=args.yield_between_rows,
        builder_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest())
    (out/'build-receipt.json').write_text(json.dumps(receipt,indent=2)+'\n');print(json.dumps(receipt))
