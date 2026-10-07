"""#27: rearm boss scene setup in place without changing the incoming bank.

The first clear loop leaves H=FF and A=0. Reuse those values for the second
clear loop (LD L,B2 instead of LD HL,FFB2; omit redundant XOR A), freeing two
bytes for LDH (FF91),A after LD A,1. Preserve every native register/flag and
memory write, with one additional FF91=1 write and +4T once per boss entry.
No banked helper, stack operation, mapper write or per-frame work is added.
"""
import argparse
import hashlib
import json
from pathlib import Path

PARENT = '398891b62781ddceb1893103b2b8b204dc5da6eb3d95bbe3b755c36a710c18b5'
HOOK = 0x1A2F
OLD = bytes.fromhex('21C2FFAF0604220520FC21B2FFAF0605220520FC3E01E0DAE0E4')
NEW = bytes.fromhex('21C2FFAF0604220520FC2EB20605220520FC3E01E091E0DAE0E4')


def build(parent):
    if hashlib.sha256(parent).hexdigest() != PARENT:
        raise ValueError('exact projectile parent required')
    if parent[HOOK:HOOK + len(OLD)] != OLD or len(NEW) != len(OLD):
        raise ValueError('native boss prelude preimage changed')
    result = bytearray(parent)
    result[HOOK:HOOK + len(NEW)] = NEW
    result[0x14E:0x150] = ((sum(result[:0x14E]) + sum(result[0x150:])) & 65535).to_bytes(2, 'big')
    return bytes(result)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('parent', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[2]
    if args.output.exists() or (root / 'tmp').resolve() not in args.output.resolve().parents:
        parser.error('fresh worktree tmp output required')
    rom = build(args.parent.read_bytes())
    args.output.mkdir(parents=True)
    (args.output / 'candidate.gb').write_bytes(rom)
    receipt = dict(issues=[27, 59], experimental=True, release_qualified=False,
                   parent_sha256=PARENT, candidate_sha256=hashlib.sha256(rom).hexdigest(),
                   builder_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                   added_entry_tcycles=4, scope=__doc__)
    (args.output / 'receipt.json').write_text(json.dumps(receipt, indent=2) + '\n')
    print(json.dumps(receipt))
