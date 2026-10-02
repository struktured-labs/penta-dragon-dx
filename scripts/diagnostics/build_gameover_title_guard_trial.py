#!/usr/bin/env python3
"""Exact-parent diagnostic: retire gameplay-active state when painting title.

Passes the physical-WRAM two-cycle restart regression; broader qualification
is still required before deployment. Earlier mapped-WRAM probe rejection was
a sampling error when the compiler selected SVBK3.
Keep the original r536 artifact immutable.
"""
import argparse
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BASE_SHA = 'b93ebc46ed4ac23ec7d2c44d80fae1ae1538b38c038bab0ba8173b93fe252350'


def offset(address):
    return 25 * 0x4000 + address - 0x4000


def patches():
    # This point already requires LCD off and D880==1. Cold boot has FFC1=0,
    # but Game Over retains 1 and the native stage marker FFB7 retains 2.
    # Restore both cold-title values before the first returned-title frame.
    # Gameplay hazard code and its timing remain byte-for-byte unchanged.
    code = bytes.fromhex('AF E0 C1 E0 B7 3E 88 E0 68 C3 11 6D')
    return (
        (0x6D0D, bytes.fromhex('3E 88 E0 68'), bytes.fromhex('C3 00 7F 00')),
        (0x7F00, b'\xff' * len(code), code),
    )


def build(source):
    if hashlib.sha256(source).hexdigest() != BASE_SHA:
        raise ValueError('requires exact r536 parent')
    result = bytearray(source)
    allowed = {0x14E, 0x14F}
    for address, before, after in patches():
        start = offset(address)
        if len(before) != len(after) or source[start:start + len(before)] != before:
            raise ValueError(f'preimage/width mismatch at bank25:${address:04X}')
        result[start:start + len(after)] = after
        allowed.update(range(start, start + len(after)))
    result[0x14E:0x150] = ((sum(result[:0x14E]) + sum(result[0x150:])) & 65535).to_bytes(2, 'big')
    assert all(a == b or i in allowed for i, (a, b) in enumerate(zip(source, result, strict=True)))
    return bytes(result)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    out = args.output.resolve()
    if out.exists() or (ROOT / 'tmp').resolve() not in out.parents:
        parser.error('output must be fresh beneath repository tmp/')
    result = build(args.source.read_bytes())
    receipt = dict(schema='penta-gameover-title-guard-trial-v1', release_qualified=False,
                   status='built-unqualified',
                   source_sha256=BASE_SHA, candidate_sha256=hashlib.sha256(result).hexdigest(),
                   builder_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest())
    out.mkdir(parents=True)
    (out / 'candidate.gb').write_bytes(result)
    (out / 'build-receipt.json').write_text(json.dumps(receipt, indent=2) + '\n')
    print(json.dumps(receipt, indent=2))


if __name__ == '__main__':
    main()
