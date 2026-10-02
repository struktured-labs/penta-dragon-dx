#!/usr/bin/env python3
"""Issue #28: retain death rendering and sample joypad before its early exit.

The --after-visuals variant preserves both original visual CALLs and enters
the existing joypad sampler in unused bank35 afterwards. Its stack adapter
returns through the fixed bank-call ABI into the original wrapper epilogue.
The older mirror variants are retained to reproduce their failed fade tests.
No gameplay path or native Continue button semantics are changed.
"""
import argparse
import hashlib
import json
from pathlib import Path

PARENT='3c5951bf86f429f2d6299ea68704514672b5e90d4726572b8c2981bd2963b73e'
TAIL=bytes.fromhex('CD3065 CDD069 E1 C38C6F')
SAMPLER=bytes.fromhex('3E20 E000 F000 F000 2F E60F CB37 47 3E10 E000 '
                      'F000 F000 F000 F000 F000 F000 F000 2F E60F B0 E093 47 3E30 E000')

def digest(data):
    return hashlib.sha256(data).hexdigest()

def build(parent, settled_window=False, after_visuals=False):
    if digest(parent)!=PARENT:
        raise ValueError('requires exact projectile-fixed parent')
    if len(parent)!=0x100000 or parent[35*0x4000:36*0x4000]!=b'\xff'*0x4000:
        raise ValueError('bank35 must be unused expansion space')
    if parent[0x37189:0x37193]!=TAIL:
        raise ValueError('death rendering tail differs')
    if parent[0x36F3D:0x36F68]!=SAMPLER:
        raise ValueError('existing joypad sampler differs')
    if parent[0x847:0x850]!=bytes.fromhex('CD6100 CD806C C36100'):
        raise ValueError('fixed far-call ABI differs')
    if parent[0x371DB:0x371E4]!=bytes.fromhex('3E0D F5 3E14 CD6100 E1'):
        raise ValueError('palette reader return-bank preimage differs')
    result=bytearray(parent)
    if after_visuals:
        if settled_window:
            raise ValueError('choose one experimental mechanism')
        # Source builder reserves two unreachable bytes before OAM clear7195.
        # Leave both visual CALLs untouched. Tail-enter the fixed bank-call ABI,
        # replacing the discarded death-service return with wrapper epilogue.
        if parent[0x37193:0x37195]!=bytes(2):
            raise ValueError('death tail padding occupied')
        helper=SAMPLER+bytes.fromhex('E1 D1 118C6F D5 E5 3E0D C9')
        result[0x8EC80:0x8EC80+len(helper)]=helper
        result[0x3718F:0x37195]=bytes.fromhex('3E23 C34708 00')
        result[0x14E:0x150]=((sum(result[:0x14E])+sum(result[0x150:]))&65535).to_bytes(2,'big')
        return bytes(result)
    mirror=bytearray(parent[13*0x4000:14*0x4000])
    # Keep historical ungated trial reproducible. New experiment samples only
    # with LCDC.window enabled and native BGP=E4, after the white fade.
    gate=bytes.fromhex('F040 E620 2806 F047 FEE4 2803 3E0D C9') if settled_window else b''
    helper=bytes.fromhex('CD3065 CDD069')+gate+SAMPLER+bytes.fromhex('3E0D C9')
    mirror[0x2C80:0x2C80+len(helper)]=helper
    mirror[0x31DC]=35
    result[35*0x4000:36*0x4000]=mirror
    result[0x37189:0x37193]=bytes.fromhex('3E23 CD4708 E1 C38C6F 00')
    result[0x14E:0x150]=((sum(result[:0x14E])+sum(result[0x150:]))&65535).to_bytes(2,'big')
    return bytes(result)

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('parent',type=Path)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--settled-window',action='store_true')
    parser.add_argument('--after-visuals',action='store_true')
    args=parser.parse_args()
    root=Path(__file__).resolve().parents[2]
    if args.output.exists() or (root/'tmp').resolve() not in args.output.resolve().parents:
        parser.error('output must be fresh beneath repository tmp/')
    result=build(args.parent.read_bytes(),args.settled_window,args.after_visuals)
    args.output.mkdir(parents=True)
    (args.output/'candidate.gb').write_bytes(result)
    receipt=dict(issue=28,parent_sha256=PARENT,candidate_sha256=digest(result),
                 builder_sha256=digest(Path(__file__).read_bytes()),release_qualified=False,
                 settled_window_only=args.settled_window,after_visuals=args.after_visuals)
    (args.output/'receipt.json').write_text(json.dumps(receipt,indent=2)+'\n')
    print(json.dumps(receipt))
