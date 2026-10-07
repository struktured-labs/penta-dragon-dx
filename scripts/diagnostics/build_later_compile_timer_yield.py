"""#59 experimental later-dungeon row compiler with bounded Timer service.

Bank30 already owns compilation and its mirrored-stack return ABI. Stage1's
bulk compiler is unchanged. Only later dungeon scenes with IE exactly04 use
this helper at low health. Every row is compiled in SVBK3, then a pending Timer may run in
SVBK1 before returning to SVBK3. No VBlank interrupt is admitted mid-buffer.
"""
import argparse
import hashlib
import json
from pathlib import Path
from build_later_hdma_overlap import Asm

PARENT='0fd7f1e50f688927e21541bca99cd8d353391a85a626530df9f39ac9435fbf08'
BANK=30
ENTRY=0x78A0
RETURN=0x788D


def off(address):return BANK*0x4000+address-0x4000


def helper():
    a=Asm(ENTRY)
    # All early returns must use the mapper ABI (A=bank1), not RET directly.
    a.db(0xF0,0xFF,0xFE,4,0xC2,RETURN&255,RETURN>>8)
    a.db(0xF0,0xB7,0xD6,3,0xFE,6,0xD2,RETURN&255,RETURN>>8)
    # IRQs are still disabled. Read the native scene from physical bank1;
    # the mirrored caller stack stays in bank3 and is not touched here.
    a.db(0x3E,1,0xE0,0x70,0xFA,0x80,0xD8,0xFE,11)
    a.jr(0x28,'accepted')
    a.db(0x3E,3,0xE0,0x70,0xC3,RETURN&255,RETURN>>8)
    a.label('accepted')
    a.db(0x3E,3,0xE0,0x70)
    # Stage2's D400 entry is a mapper-owning dispatcher, not a callable row
    # routine: it always returns to ROM1. Compile the exact LUT cells here.
    # Invalidate its two map-ready bits so a later normal-health sparse path
    # cannot reuse cache validity from before this full-buffer replacement.
    a.db(0xF0,0xBA,0xFE,1);a.jr(0x20,'uncached')
    a.db(0xAF,0xEA,0x7F,0xD4)
    a.label('uncached')
    a.db(0x3E,24,0xE0,0xE0)
    a.label('row')
    for _ in range(24):a.db(0x1A,0x13,0x4F,0x0A,0x22)
    # No PUSH/POP/CALL/RET while the other stack bank is selected. The
    # Timer interrupt pushes below SP and restores registers/bank normally.
    a.db(0x3E,1,0xE0,0x70,0xFB,0,0xF3,0x3E,3,0xE0,0x70)
    a.db(0x7D,0xC6,8,0x6F);a.jr(0x30,'next')
    a.db(0x24)
    a.label('next')
    a.db(0xF0,0xE0,0x3D,0xE0,0xE0);a.jp(0xC2,'row')
    # Stack:084D mapper return,430E caller return,older frames. Reuse the
    # exact Stage1 completion ABI to skip only the now-completed row loop.
    a.db(0xE5,0xF8,4,0x36,0x24,0x23,0x36,0x43,0xE1,0xAF,0xE0,0xE0,
         0x3E,1,0xC9)
    return a.finish()


def build(parent):
    if hashlib.sha256(parent).hexdigest()!=PARENT:raise ValueError('exact dispatch-only parent required')
    if parent[off(RETURN):off(RETURN)+3]!=bytes.fromhex('3E01C9'):
        raise ValueError('compiler mapper return changed')
    if parent[0x4303:0x4316]!=bytes.fromhex('11A0C1 2100D0 3E1E CD4708 00 3E18 E0E0 CD00D4'):
        raise ValueError('native row-loop ABI changed')
    if parent[0x6B3:0x6D1]!=bytes.fromhex('F5 C5 D5 E5 3E03 EA0021 CD0040 3E01 EA0021 CD790D F099 EA0021 E1 D1 C1 F1 D9'):
        raise ValueError('Timer register/bank preservation changed')
    if parent[0x9BE:0x9C4]!=bytes.fromhex('E099 EA0021 C9'):
        raise ValueError('mapper bank-shadow contract changed')
    code=helper()
    if ENTRY+len(code)>0x8000 or parent[off(ENTRY):off(ENTRY)+len(code)]!=b'\xff'*len(code):
        raise ValueError('compiler cave occupied')
    result=bytearray(parent)
    # Only FFBA!=0 reaches the new helper. Stage1's scene0B fallback retains
    # its original instruction path and timing, not merely its bulk body.
    for addr in (0x6D03,):
        if parent[off(addr):off(addr)+3]!=bytes.fromhex('C28D78'):
            raise ValueError('Stage1 compiler fallback changed')
        result[off(addr):off(addr)+3]=bytes((0xC2,ENTRY&255,ENTRY>>8))
    result[off(ENTRY):off(ENTRY)+len(code)]=code
    result[0x14E:0x150]=((sum(result[:0x14E])+sum(result[0x150:]))&65535).to_bytes(2,'big')
    return bytes(result)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('parent',type=Path);p.add_argument('--output',type=Path,required=True)
    args=p.parse_args();root=Path(__file__).resolve().parents[2]
    if args.output.exists() or (root/'tmp').resolve() not in args.output.resolve().parents:
        p.error('fresh repository-local tmp directory required')
    source=args.parent.read_bytes();result=build(source);args.output.mkdir(parents=True)
    (args.output/'candidate.gb').write_bytes(result)
    receipt=dict(issue=59,experimental=True,release_qualified=False,parent_sha256=PARENT,
                 candidate_sha256=hashlib.sha256(result).hexdigest(),helper_bytes=len(helper()),
                 builder_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                 changed_offsets=[i for i,(a,b) in enumerate(zip(source,result)) if a!=b])
    (args.output/'receipt.json').write_text(json.dumps(receipt,indent=2)+'\n')
    print(json.dumps(receipt))
