#!/usr/bin/env python3
"""Exact r536 successor: do not paint hazard attributes over scene1 title.

Preserves native state flags, title/attract code, palettes and row cleanup.
Gameplay qualification is required; this builder alone does not certify it.
"""
import argparse
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BASE_SHA = 'b93ebc46ed4ac23ec7d2c44d80fae1ae1538b38c038bab0ba8173b93fe252350'
CANDIDATE_SHA = 'e709869c85edfd647dd01dbca0c222a493b335ee6759adaa573416143a66e45b'


def patches():
    # Both callers have selected the game's WRAM bank. Preserve all BC/DE/HL
    # and stack values. Rejected spans still execute the original VBK0 cleanup
    # and mapper bridge; accepted spans execute their displaced LCD test.
    return (
        (0x4300, bytes.fromhex('C3 80 43 00'), bytes.fromhex('C3 B0 43 00')),
        (0x4500, bytes.fromhex('F0 40 CB 7F'), bytes.fromhex('C3 BB 43 00')),
        (0x43B0, b'\xff' * 26, bytes.fromhex(
            'FA 80 D8 FE 01 CA 5D 43 C3 80 43 '
            'FA 80 D8 FE 01 CA 5D 45 F0 40 CB 7F C3 04 45')),
    )


def build(source):
    if hashlib.sha256(source).hexdigest() != BASE_SHA:
        raise ValueError('requires exact r536 parent')
    result=bytearray(source)
    for address,before,after in patches():
        offset=20*0x4000+address-0x4000
        assert len(before)==len(after) and source[offset:offset+len(before)]==before
        result[offset:offset+len(after)]=after
    result[0x14E:0x150]=((sum(result[:0x14E])+sum(result[0x150:]))&65535).to_bytes(2,'big')
    assert hashlib.sha256(result).hexdigest()==CANDIDATE_SHA
    return bytes(result)


def authenticated_parent(candidate):
    """Recover only this exact delta for inherited static component checks."""
    if hashlib.sha256(candidate).hexdigest() != CANDIDATE_SHA:
        raise ValueError('not the exact row-guard successor')
    parent=bytearray(candidate)
    for address,before,after in patches():
        start=20*0x4000+address-0x4000
        assert parent[start:start+len(after)]==after
        parent[start:start+len(before)]=before
    parent[0x14E:0x150]=((sum(parent[:0x14E])+sum(parent[0x150:]))&65535).to_bytes(2,'big')
    assert hashlib.sha256(parent).hexdigest()==BASE_SHA
    return bytes(parent)


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('source',type=Path);p.add_argument('--output',type=Path,required=True)
    args=p.parse_args();out=args.output.resolve()
    if out.exists() or (ROOT/'tmp').resolve() not in out.parents:
        p.error('output must be fresh beneath repository tmp/')
    result=build(args.source.read_bytes())
    out.mkdir(parents=True)
    (out/'candidate.gb').write_bytes(result)
    receipt=dict(schema='penta-gameover-row-guard-v1',source_sha256=BASE_SHA,
                 candidate_sha256=CANDIDATE_SHA,release_qualified=False,
                 builder_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest())
    (out/'build-receipt.json').write_text(json.dumps(receipt,indent=2)+'\n')
    print(json.dumps(receipt,indent=2))


if __name__=='__main__':main()
