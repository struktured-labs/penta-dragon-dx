"""#45 experimental removal of the unchanged E4 palette rewrite.

Replace that transaction with one existing native frame wait, preserving the
intended four-frame card step. Requires replay/audio qualification; not a release.
"""
import argparse
import hashlib
import json
from pathlib import Path

PARENT='f938ae85785b4bc30133dad1c39e5f45ee0bcbea249d94f160132970ce22be29'


def build(parent):
    if hashlib.sha256(parent).hexdigest()!=PARENT:
        raise ValueError('exact trial10 parent required')
    start=20*0x4000+0x151c
    end=start+1984
    def unique(pattern):
        i=parent.find(pattern,start,end)
        if i<0 or parent.find(pattern,i+1,end)>=0:
            raise ValueError('missing or ambiguous private instruction sequence')
        return i
    wait=unique(bytes.fromhex('F0 41 E6 03 FE 03 20 F8 F0 41 E6 03 3D 20 F9 C9'))
    # Three timer ticks then E4 publication: retain the intended final frame,
    # but no CRAM write or extra masked interval for the identity mapping.
    site=unique(bytes.fromhex('AF E0 D4 F0 D4 FE 03 38 FA 3E E4 E0 47 CD'))+13
    result=bytearray(parent)
    target=wait%0x4000+0x4000
    result[site+1:site+3]=target.to_bytes(2,'little')
    result[0x14e:0x150]=((sum(result[:0x14e])+sum(result[0x150:]))&65535).to_bytes(2,'big')
    return bytes(result),site,target


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('parent',type=Path)
    p.add_argument('--output',type=Path,required=True)
    a=p.parse_args()
    root=Path(__file__).resolve().parents[2]
    if a.output.exists() or (root/'tmp').resolve() not in a.output.resolve().parents:
        p.error('fresh repository tmp output required')
    rom,site,target=build(a.parent.read_bytes())
    a.output.mkdir()
    (a.output/'candidate.gb').write_bytes(rom)
    r=dict(issue=45,experimental=True,release_qualified=False,parent_sha256=PARENT,
           candidate_sha256=hashlib.sha256(rom).hexdigest(),site=hex(site),target=hex(target),
           builder_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest())
    (a.output/'receipt.json').write_text(json.dumps(r,indent=2)+'\n')
    print(json.dumps(r))
