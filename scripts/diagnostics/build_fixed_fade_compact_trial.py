"""#45 experimental compact return uploads on the late-route parent.

Preserve wait counts, shade values, native card sequence and entry addresses.
Reuse the existing compact uploader; do not shorten or retime acceptance data.
Inherits the parent's unqualified fixed-ROM allocation.
"""
import argparse
import hashlib
import json
from pathlib import Path
from build_return_palette_compact_trial import body

PARENT = '988b3e07bcfd884c01f7355704a48530502cab157d01d33f2767417ffd9921b7'


def build(parent):
    if hashlib.sha256(parent).hexdigest() != PARENT:
        raise ValueError('exact late-route parent required')
    result = bytearray(parent)
    sites = []
    for shade in (0,0x40,0x90,0xE4):
        old, new = body(shade,False), body(shade,True)
        site = parent.find(old,0x5151C,0x51CDC)
        if site < 0 or parent.find(old,site+1,0x51CDC)>=0:
            raise ValueError('missing or ambiguous return upload')
        if len(new)>len(old): raise ValueError('upload exceeds owned region')
        result[site:site+len(old)] = new + bytes(len(old)-len(new))
        sites.append(dict(shade=shade,offset=site,size=len(old)))
    result[0x14E:0x150]=((sum(result[:0x14E])+sum(result[0x150:]))&65535).to_bytes(2,'big')
    return bytes(result), sites


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('parent',type=Path)
    p.add_argument('--output',required=True,type=Path)
    a=p.parse_args()
    root=Path(__file__).resolve().parents[2]
    if a.output.exists() or (root/'tmp').resolve() not in a.output.resolve().parents:
        p.error('fresh repository tmp output required')
    rom,sites=build(a.parent.read_bytes())
    a.output.mkdir()
    (a.output/'candidate.gb').write_bytes(rom)
    r=dict(issue=45,experimental=True,release_qualified=False,
           allocation_review_complete=False,parent_sha256=PARENT,
           candidate_sha256=hashlib.sha256(rom).hexdigest(),sites=sites,
           builder_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
           uploader_source_sha256=hashlib.sha256(Path(__file__).with_name('build_return_palette_compact_trial.py').read_bytes()).hexdigest())
    (a.output/'receipt.json').write_text(json.dumps(r,indent=2)+'\n')
    print(json.dumps(r))
