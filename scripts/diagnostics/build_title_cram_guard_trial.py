"""#35 route the old unguarded title copy through the existing CRAM guard."""
import argparse
import hashlib
import json
from pathlib import Path

PARENT = '106c2e0181fa9bee1b3777f82af61d49d181415dafdd0456fea2c56a8234e317'
OFFSET = 0x36A57
OLD = bytes.fromhex('0E08 2A E069 0D 20FA C9')
NEW = bytes.fromhex('0E69 CDE07F 0E00 C9 00')

def build(parent):
    if hashlib.sha256(parent).hexdigest() != PARENT:
        raise ValueError('exact handheld trial parent required')
    if parent[OFFSET:OFFSET+len(OLD)] != OLD:
        raise ValueError('title helper differs')
    if parent[0x37fe0:0x37fe7] != bytes.fromhex('CDDB71 CDDB71 C9'):
        raise ValueError('guarded eight-byte leaf differs')
    result = bytearray(parent)
    result[OFFSET:OFFSET+len(NEW)] = NEW
    result[0x14e:0x150] = ((sum(result[:0x14e])+sum(result[0x150:]))&65535).to_bytes(2,'big')
    return bytes(result)

if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('parent', type=Path)
    p.add_argument('--output', type=Path, required=True)
    a = p.parse_args()
    root = Path(__file__).resolve().parents[2]
    if a.output.exists() or (root/'tmp').resolve() not in a.output.resolve().parents:
        p.error('fresh repository tmp directory required')
    result = build(a.parent.read_bytes())
    a.output.mkdir(parents=True)
    (a.output/'candidate.gb').write_bytes(result)
    receipt = dict(issue=35, parent_sha256=PARENT,
        candidate_sha256=hashlib.sha256(result).hexdigest(),
        builder_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        experimental=True, release_qualified=False,
        scope='title eight-byte copy only; cadence and audiovisual behavior require verification')
    (a.output/'receipt.json').write_text(json.dumps(receipt, indent=2)+'\n')
    print(json.dumps(receipt))
