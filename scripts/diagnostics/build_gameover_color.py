#!/usr/bin/env python3
"""Issue #18: use the existing spectral-purple accent for GAME OVER text.

Palette-only trial atop the secret CHR/BG0 candidate. Keeps the shared charcoal
high byte needed by the death fade seam. No runtime or glyph changes.
"""
import argparse
import hashlib
import json
from pathlib import Path

PARENT_SHA = 'e2473cbaf4060896afaa7f30b5fc250729887ae02cc12cb15f183ea3bfa09405'
ROW = 0x37C34
OLD = bytes.fromhex('ff7fff7fb5564a29')
NEW = bytes.fromhex('ff7fff7f1f7e4a29')


def digest(data):
    return hashlib.sha256(data).hexdigest()


def build(parent):
    if digest(parent) != PARENT_SHA:
        raise ValueError('requires exact secret CHR/BG0 parent')
    if parent[ROW:ROW + 8] != OLD:
        raise ValueError('unexpected GAME OVER palette')
    if parent[ROW - 8:ROW] != NEW:
        raise ValueError('death-screen accent or shared charcoal differs')
    result = bytearray(parent)
    result[ROW:ROW + 8] = NEW
    result[0x14E:0x150] = ((sum(result[:0x14E]) + sum(result[0x150:])) & 65535).to_bytes(2, 'big')
    allowed = {ROW + 4, ROW + 5, 0x14E, 0x14F}
    assert len(result) == len(parent)
    assert all(a == b or i in allowed for i, (a, b) in enumerate(zip(parent, result)))
    return bytes(result)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('parent', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[2]
    if args.output.exists() or (root / 'tmp').resolve() not in args.output.resolve().parents:
        parser.error('output must be fresh beneath repository tmp/')
    result = build(args.parent.read_bytes())
    args.output.mkdir(parents=True)
    (args.output / 'candidate.gb').write_bytes(result)
    receipt = dict(issue=18, parent_sha256=PARENT_SHA,
                   candidate_sha256=digest(result), builder_sha256=digest(Path(__file__).read_bytes()),
                   change='GAME OVER gray accent -> existing death-screen spectral purple',
                   release_qualified=False)
    (args.output / 'build-receipt.json').write_text(json.dumps(receipt, indent=2) + '\n')
    print(json.dumps(receipt))
