"""#26 experimental omission of the duplicate stage7 BG0 repair."""
import argparse
import hashlib
import json
from pathlib import Path

PARENT='665a33b6b26d0a8ec1622a7c897d4fc10bdf7c8c5e0e5a2edaae98df0dafe0e7'
BANK=13*0x4000
HOOK=BANK+0x29CD
CAVE=BANK+0x2D4E
# Preserve AF on both paths; only stage7 bypasses the repair publisher.
CODE=bytes.fromhex('f5f0bafe072804f1c3e07ff1c9')


def build(parent):
    if hashlib.sha256(parent).hexdigest()!=PARENT:
        raise ValueError('Exact fast-alias parent required')
    if parent[HOOK:HOOK+3]!=bytes.fromhex('c3e07f'):
        raise ValueError('BG0 repair tail differs')
    if parent[CAVE:CAVE+len(CODE)]!=bytes(len(CODE)):
        raise ValueError('Dedup cave occupied')
    result=bytearray(parent)
    result[HOOK:HOOK+3]=bytes.fromhex('c34e6d')
    result[CAVE:CAVE+len(CODE)]=CODE
    result[0x14E:0x150]=((sum(result[:0x14E])+sum(result[0x150:]))&65535).to_bytes(2,'big')
    return bytes(result)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('parent',type=Path);p.add_argument('--output',type=Path,required=True)
    args=p.parse_args();root=Path(__file__).resolve().parents[2];out=args.output.resolve()
    if out.exists() or (root/'tmp').resolve() not in out.parents:
        p.error('Fresh repository-local tmp output required')
    rom=build(args.parent.read_bytes());out.mkdir(parents=True)
    (out/'candidate.gb').write_bytes(rom)
    receipt=dict(issue=26,experimental=True,release_qualified=False,parent_sha256=PARENT,
                 candidate_sha256=hashlib.sha256(rom).hexdigest(),
                 builder_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest())
    (out/'receipt.json').write_text(json.dumps(receipt,indent=2)+'\n')
    print(json.dumps(receipt))
