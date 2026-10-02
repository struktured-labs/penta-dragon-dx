"""Issue #45: count palette-backup acquisition inside the first card interval.

Experimental only: requires same-ROM replay and unmodified audio gates.
"""
import argparse
import hashlib
import json
from pathlib import Path

PARENT = 'f938ae85785b4bc30133dad1c39e5f45ee0bcbea249d94f160132970ce22be29'
OLD = bytes.fromhex('E1 F1 E5 D5 C5 CD 0A 57 AF E0 D4')
NEW = bytes.fromhex('E1 F1 E5 D5 C5 AF E0 D4 CD 0A 57')


def build(parent):
    if hashlib.sha256(parent).hexdigest() != PARENT:
        raise ValueError('exact trial10 parent required')
    site = 20 * 0x4000 + 0x16ae
    if parent[site:site + len(OLD)] != OLD:
        raise ValueError('private card entry mismatch')
    result = bytearray(parent)
    result[site:site + len(OLD)] = NEW
    result[0x14e:0x150] = ((sum(result[:0x14e]) + sum(result[0x150:])) & 65535).to_bytes(2, 'big')
    return bytes(result)


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('parent', type=Path)
    p.add_argument('--output', type=Path, required=True)
    a = p.parse_args()
    root = Path(__file__).resolve().parents[2]
    if a.output.exists() or (root / 'tmp').resolve() not in a.output.resolve().parents:
        p.error('fresh repository tmp output required')
    rom = build(a.parent.read_bytes())
    a.output.mkdir()
    (a.output / 'candidate.gb').write_bytes(rom)
    receipt = dict(issue=45, experimental=True, release_qualified=False,
                   parent_sha256=PARENT, candidate_sha256=hashlib.sha256(rom).hexdigest(),
                   builder_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest())
    (a.output / 'receipt.json').write_text(json.dumps(receipt, indent=2) + '\n')
    print(json.dumps(receipt))
