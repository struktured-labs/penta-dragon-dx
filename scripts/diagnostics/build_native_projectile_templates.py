#!/usr/bin/env python3
"""#31: read native miniboss projectile patterns from preserved stock bank32.

Bank13 contains injected code in inactive projectile records. Only change
the native loader's bank operand; copy length, RNG and instruction timing
remain unchanged. This is not a hardware/release qualification receipt.
"""
import argparse
import hashlib
import json
from pathlib import Path

PARENTS = {
    '7130c04a3ef9ad9239ae693dad9d5d61953437fa3eccc0c137071b79faeacc23',
    '707507de35c1e0c638d7b9837c3d19009ac6f059564f3e92de5ecdde4f8172ac',
}
STOCK_SHA = '2f32570cff62b8664bfa06b939988c3fd6a7efabf870a990a5fa65bab37eac30'
LOADER = bytes.fromhex('3E0D CD6100 F0BF 3D 87 210053 D7 2A666F')


def sha(data):
    return hashlib.sha256(data).hexdigest()


def build(parent, stock):
    if sha(parent) not in PARENTS or sha(stock) != STOCK_SHA:
        raise ValueError('requires exact supported parent and original cartridge')
    if len(parent) != 0x100000 or parent[0x147:0x149] != bytes((0x1B,5)):
        raise ValueError('requires expanded MBC5 parent')
    if parent[0x80000:0x84000] != stock[0x34000:0x38000]:
        raise ValueError('bank32 is not the preserved original bank13')
    if parent[0x2AE0:0x2AE0+len(LOADER)] != LOADER:
        raise ValueError('native projectile-loader preimage differs')
    result = bytearray(parent)
    result[0x2AE1] = 32
    result[0x14E:0x150] = ((sum(result[:0x14E])+sum(result[0x150:])) & 65535).to_bytes(2, 'big')
    assert all(a==b or i in (0x2AE1,0x14E,0x14F)
               for i,(a,b) in enumerate(zip(parent,result)))
    return bytes(result)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('parent', type=Path)
    parser.add_argument('--stock', type=Path, default=Path('rom/Penta Dragon (J).gb'))
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[2]
    if args.output.exists() or (root/'tmp').resolve() not in args.output.resolve().parents:
        parser.error('output must be fresh beneath repository tmp/')
    parent=args.parent.read_bytes()
    result=build(parent,args.stock.read_bytes())
    args.output.mkdir(parents=True)
    (args.output/'candidate.gb').write_bytes(result)
    receipt=dict(issue=31,parent_sha256=sha(parent),candidate_sha256=sha(result),
                 builder_sha256=sha(Path(__file__).read_bytes()),release_qualified=False,
                 change='native miniboss pattern source bank13 -> original bank32',
                 instruction_count_delta=0,instruction_cycle_delta=0)
    (args.output/'receipt.json').write_text(json.dumps(receipt,indent=2)+'\n')
    print(json.dumps(receipt))
