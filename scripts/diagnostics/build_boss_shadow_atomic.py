"""Issue #21 experimental atomic 64-byte boss shadow publication."""
import argparse
import hashlib
import json
from pathlib import Path

PARENTS = {
    '4f5a67b8a9afb178ac0760daa2357de74fd7eb7f3de4de010385c50ea4cb08f5',
    'eebf3f190d9d307cb1d3fa714fa2e68b7890fc5309d5da26682ce38cce0134fc',
}
OLD = bytes.fromhex('1100C13E10CDE4092100C03E10D7014000CDB309C9')
# Fold native DE+=16 into its immediate load. Retain HL+16 setup and its
# flags/A; memcpy preserves AF. Only the 64-byte copy becomes DI/EI.
NEW = bytes.fromhex('1110C12100C03E10D7014000F3CDB309FBC9').ljust(len(OLD), b'\0')


def build(parent):
    if hashlib.sha256(parent).hexdigest() not in PARENTS:
        raise ValueError('unreviewed parent')
    if parent[0x2bc5:0x2bc5+len(OLD)] != OLD:
        raise ValueError('boss publication preimage differs')
    result = bytearray(parent)
    result[0x2bc5:0x2bc5+len(OLD)] = NEW
    result[0x14e:0x150] = ((sum(result[:0x14e])+sum(result[0x150:]))&65535).to_bytes(2,'big')
    return bytes(result)


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('parent', type=Path)
    p.add_argument('--output', type=Path, required=True)
    args = p.parse_args()
    root = Path(__file__).resolve().parents[2]
    out = args.output.resolve()
    if out.exists() or (root/'tmp').resolve() not in out.parents:
        p.error('fresh repository tmp output required')
    parent = args.parent.read_bytes()
    rom = build(parent)
    out.mkdir()
    (out/'candidate.gb').write_bytes(rom)
    receipt = dict(issue=21, experimental=True, release_qualified=False,
                   parent_sha256=hashlib.sha256(parent).hexdigest(),
                   candidate_sha256=hashlib.sha256(rom).hexdigest(),
                   builder_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest())
    (out/'build-receipt.json').write_text(json.dumps(receipt, indent=2)+'\n')
    print(json.dumps(receipt))
