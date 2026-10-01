#!/usr/bin/env python3
"""#14: disable SET 7 in exact combined trial, retaining instruction timing.

Diagnostic negative control only: the two SET 7,A instructions become
RES 7,A (both 8T, two bytes, flags unaffected). Installer, relocated flag,
flash behavior, branches and all other helper instructions are unchanged.
"""
import argparse
import hashlib
import json
from pathlib import Path

PARENT = '707507de35c1e0c638d7b9837c3d19009ac6f059564f3e92de5ecdde4f8172ac'


def build(rom):
    if hashlib.sha256(rom).hexdigest() != PARENT:
        raise ValueError('exact combined priority trial required')
    result = bytearray(rom)
    changed = []
    for bank in (33, 34):
        start = bank*0x4000+0x40
        block = rom[start:start+0x3F]
        if block.count(bytes.fromhex('F1CBFFE1C9')) != 1:
            raise ValueError('SET-priority return is not unique')
        offset = start+block.index(bytes.fromhex('F1CBFFE1C9'))+2
        result[offset] = 0xBF
        changed.append(offset)
    result[0x14E:0x150] = ((sum(result[:0x14E])+sum(result[0x150:])) & 65535).to_bytes(2, 'big')
    assert all(a == b or i in {*changed, 0x14E, 0x14F}
               for i,(a,b) in enumerate(zip(rom,result)))
    return bytes(result), changed


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('parent', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[2]
    if args.output.exists() or (root/'tmp').resolve() not in args.output.resolve().parents:
        parser.error('output must be fresh beneath repository tmp/')
    rom, changed = build(args.parent.read_bytes())
    args.output.mkdir(parents=True)
    (args.output/'candidate.gb').write_bytes(rom)
    receipt = dict(issue=14, diagnostic_only=True, release_qualified=False,
                   parent_sha256=PARENT, candidate_sha256=hashlib.sha256(rom).hexdigest(),
                   builder_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                   opcode_offsets=changed, change='SET 7,A -> RES 7,A; equal cycles/flags/width')
    (args.output/'receipt.json').write_text(json.dumps(receipt,indent=2)+'\n')
    print(json.dumps(receipt))
