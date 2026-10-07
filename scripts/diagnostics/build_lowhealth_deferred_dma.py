"""#59 experimental: retain later-dungeon deferred DMA during low-health music.

The r454 boss-domain restriction remains: only canonical dungeons03..08 may
defer, only with LCD on. Native scene and sound state are never written.
"""
import argparse
import hashlib
import json
from pathlib import Path

PARENT = '0fd7f1e50f688927e21541bca99cd8d353391a85a626530df9f39ac9435fbf08'
OFFSET = 23 * 0x4000 + 0x2D20
OLD = bytes.fromhex('FA80D8 D603 FE06 D29E6C F040 CB7F CA9E6C F0C4 E6F7 E0C4 3E01 C9')
NEW = bytes.fromhex('FA80D8 FE0B 2002 F0B7') + OLD[3:]


def build(parent):
    if hashlib.sha256(parent).hexdigest() != PARENT:
        raise ValueError('exact low-health dispatch parent required')
    if parent[OFFSET:OFFSET+len(NEW)] != OLD + b'\xff'*(len(NEW)-len(OLD)):
        raise ValueError('deferred DMA domain/cave preimage changed')
    result=bytearray(parent)
    result[OFFSET:OFFSET+len(NEW)]=NEW
    result[0x14E:0x150]=((sum(result[:0x14E])+sum(result[0x150:]))&65535).to_bytes(2,'big')
    return bytes(result)


if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('parent',type=Path)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    root=Path(__file__).resolve().parents[2]
    if args.output.exists() or (root/'tmp').resolve() not in args.output.resolve().parents:
        parser.error('fresh repository-local tmp directory required')
    source=args.parent.read_bytes(); result=build(source)
    args.output.mkdir(parents=True)
    (args.output/'candidate.gb').write_bytes(result)
    receipt=dict(issue=59,experimental=True,release_qualified=False,
                 parent_sha256=PARENT,candidate_sha256=hashlib.sha256(result).hexdigest(),
                 builder_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                 changed_offsets=[i for i,(a,b) in enumerate(zip(source,result)) if a!=b])
    (args.output/'receipt.json').write_text(json.dumps(receipt,indent=2)+'\n')
    print(json.dumps(receipt))
