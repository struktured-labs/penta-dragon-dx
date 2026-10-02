#!/usr/bin/env python3
"""Reset stale gameplay flags only on the native Game Over -> title exit."""
import argparse
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BASE_SHA = 'b93ebc46ed4ac23ec7d2c44d80fae1ae1538b38c038bab0ba8173b93fe252350'


def patches():
    # Native exit: CALL $007E; CALL $16FD; JP $015F, bank1:$4ACB.
    # Tail-map bank25 through the stock mapper and its same-address bridge.
    # Execute both native callees with their original bank and order intact.
    # $16FD returns to $015F through an explicit stack frame after bank1 is
    # restored. No general title, cold boot, or attract code is modified.
    helper = bytes.fromhex(
        'CD 7E 00 AF E0 B7 '
        '21 5F 01 E5 21 FD 16 E5 3E 01 C3 61 00')
    return (
        (0x4ACB, bytes.fromhex('CD 7E 00 CD FD'), bytes.fromhex('3E 19 CD 61 00')),
        (25 * 0x4000 + 0xAD0, b'\xff' * 3, bytes.fromhex('C3 00 7F')),
        (25 * 0x4000 + 0x3F00, b'\xff' * len(helper), helper),
    )


def build(source):
    if hashlib.sha256(source).hexdigest() != BASE_SHA:
        raise ValueError('requires exact r536 parent')
    assert source[0x4ACB:0x4AD4] == bytes.fromhex('CD7E00 CDFD16 C35F01')
    result = bytearray(source)
    allowed = {0x14E, 0x14F}
    for start, before, after in patches():
        assert len(before) == len(after)
        assert source[start:start+len(before)] == before, hex(start)
        result[start:start+len(after)] = after
        allowed.update(range(start,start+len(after)))
    result[0x14E:0x150] = ((sum(result[:0x14E])+sum(result[0x150:])) & 65535).to_bytes(2,'big')
    assert all(a == b or i in allowed for i,(a,b) in enumerate(zip(source,result,strict=True)))
    return bytes(result)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('source', type=Path)
    p.add_argument('--output', type=Path, required=True)
    args=p.parse_args(); out=args.output.resolve()
    if out.exists() or (ROOT/'tmp').resolve() not in out.parents:
        p.error('output must be fresh beneath repository tmp/')
    result=build(args.source.read_bytes())
    receipt=dict(schema='penta-gameover-exit-reset-trial-v1', release_qualified=False,
                 source_sha256=BASE_SHA,candidate_sha256=hashlib.sha256(result).hexdigest(),
                 builder_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest())
    out.mkdir(parents=True)
    (out/'candidate.gb').write_bytes(result)
    (out/'build-receipt.json').write_text(json.dumps(receipt,indent=2)+'\n')
    print(json.dumps(receipt,indent=2))


if __name__ == '__main__':
    main()
