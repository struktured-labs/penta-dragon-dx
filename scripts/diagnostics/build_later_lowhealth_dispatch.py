"""#59 trial: resolve later-dungeon sound aliases in the attribute runtime.

No native sound state or cache is changed. Same instructions and allocation;
only four resolver immediates change. Emulator/timing qualification required.
"""
import argparse
import hashlib
import json
from pathlib import Path

PARENT = '6c4a9654b5c6dad70c8ea21bfd39b6e53766a3cd1a642153c6085774392ec228'
FRAGMENTS = ((0x3569A, 36), (0x356CA, 36), (0x356FA, 5))
OLD = bytes.fromhex('FA80D8 FE0B C0 F0B7 D60C FE09 3802 3EFF C60C')
NEW = bytes.fromhex('FA80D8 FE0B C0 F0B7 D603 FE12 3802 3E08 C603')


def build(parent):
    if hashlib.sha256(parent).hexdigest() != PARENT:
        raise ValueError('exact qualified parent required')
    runtime = bytearray(b''.join(parent[p:p+n] for p,n in FRAGMENTS))
    if runtime[59:] != OLD or parent[0x35830] != 0xC9:
        raise ValueError('split DBDF resolver/RET contract changed')
    # Canonical scenes03..14 include later dungeons and arenas. Scenes09..0B
    # remain rejected by the existing dispatcher, just like the old fallback.
    # Stage1 (canonical02) keeps its prior0B fallback/special handling.
    runtime[59:] = NEW
    result = bytearray(parent)
    cursor = 0
    for pos,size in FRAGMENTS:
        result[pos:pos+size] = runtime[cursor:cursor+size]
        cursor += size
    result[0x14E:0x150] = ((sum(result[:0x14E])+sum(result[0x150:]))&65535).to_bytes(2,'big')
    return bytes(result)


if __name__ == '__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('parent',type=Path)
    p.add_argument('--output',type=Path,required=True)
    args=p.parse_args()
    root=Path(__file__).resolve().parents[2]
    if args.output.exists() or (root/'tmp').resolve() not in args.output.resolve().parents:
        p.error('fresh repository tmp output required')
    source=args.parent.read_bytes()
    result=build(source)
    args.output.mkdir(parents=True)
    (args.output/'candidate.gb').write_bytes(result)
    report=dict(issue=59,experimental=True,release_qualified=False,parent_sha256=PARENT,
                candidate_sha256=hashlib.sha256(result).hexdigest(),
                changed_offsets=[i for i,(a,b) in enumerate(zip(source,result)) if a!=b],
                builder_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest())
    (args.output/'receipt.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report))
