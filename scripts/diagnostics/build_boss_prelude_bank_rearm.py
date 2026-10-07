"""#27 trial: explicitly select bank1 before the boss-entry rearm helper.

Use the game's AF-preserving RST28 mapper; do not assume the incoming bank.
This is an experiment. Both native entry and inherited-miniboss routes must
be verified before adoption; entry timing is not yet qualified.
"""
import argparse
import hashlib
import json
from pathlib import Path

PARENT = 'f2ff141007fa59acf1afd76f397682c499e3eb108fa02e9a0e3c4e2b5b84f7d4'


def build(parent):
    if hashlib.sha256(parent).hexdigest() != PARENT:
        raise ValueError('exact early-rearm parent required')
    for address, expected in (
        (0x1A43, bytes.fromhex('CD9A7C000000')),
        (0x7C9A, bytes.fromhex('3E01E091E0DAE0E4C9')),
        (0x0028, bytes.fromhex('C39A09')),
        (0x099A, bytes.fromhex('F53E01CD6100F1C9')),
        (0x0061, bytes.fromhex('EA09DCC3BE09')),
        (0x09BE, bytes.fromhex('E099EA0021C9')),
    ):
        if parent[address:address+len(expected)] != expected:
            raise ValueError('entry/mapper preimage changed')
    result = bytearray(parent)
    result[0x1A43:0x1A49] = bytes.fromhex('EFCD9A7C0000')
    result[0x14e:0x150] = ((sum(result[:0x14e])+sum(result[0x150:])) & 65535).to_bytes(2, 'big')
    return bytes(result)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('parent', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[2]
    if args.output.exists() or (root/'tmp').resolve() not in args.output.resolve().parents:
        parser.error('fresh worktree tmp output required')
    rom = build(args.parent.read_bytes())
    args.output.mkdir(parents=True)
    (args.output/'candidate.gb').write_bytes(rom)
    receipt = dict(issue=27, experimental=True, release_qualified=False,
                   parent_sha256=PARENT, candidate_sha256=hashlib.sha256(rom).hexdigest(),
                   builder_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                   scope=__doc__)
    (args.output/'receipt.json').write_text(json.dumps(receipt, indent=2)+'\n')
    print(json.dumps(receipt))
