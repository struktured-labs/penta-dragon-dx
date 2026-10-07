"""Issues #59/#66: experimental low-health alias admission to Stage7 fast paths.

Not release-qualified. Bank22 uses its own ROM-local resolver because DBDF
has installer-specific ownership. Bank13 also uses a ROM-local resolver:
calling DBDF there failed at startup before runtime installation in trial01.
All other eligibility checks and the native sound scene remain unchanged.
"""
import argparse
import hashlib
import json
from pathlib import Path

PARENT = 'ee359af0c1ad11d9b66539c587b59f0134a69810d8c32aa8603869e37e25c99c'
RESOLVER = bytes.fromhex('FA80D8 FE0B C0 F0B7 C9')
CAVE = 0x5BF80
CACHE_RESOLVER = bytes.fromhex('FA80D8 FE0B C0 F0B7 FE08 C8 3E0B C9')


def build(parent, cache_alias=False):
    if hashlib.sha256(parent).hexdigest() != PARENT:
        raise ValueError('exact Timer-yield trial03 parent required')
    result = bytearray(parent)
    # Tail of the documented 6EC4..6EF4 code cave, beyond the unconditional
    # JP5422 installed at 6EE5. Do not allocate zero runs in palette tables.
    if parent[0x36EE5:0x36EF4] != bytes.fromhex('C32254') + bytes(12):
        raise ValueError('bank13 code-cave fence/allocation changed')
    changes = (
        (0x3570E, bytes.fromhex('FA80D8FE08C8'), bytes.fromhex('CDE86EFE08C8')),
        (0x36EE8, bytes(len(RESOLVER)), RESOLVER),
        (0x5AC80, bytes.fromhex('FA80D8FE08C23B72'), bytes.fromhex('CD807FFE08C23B72')),
        (0x5B1DA, bytes.fromhex('FA80D8FE08C23172'), bytes.fromhex('CD807FFE08C23172')),
        (CAVE, b'\xff' * len(RESOLVER), RESOLVER),
    )
    if cache_alias:
        # Rejected trial04, retained only for explicit diagnostic reproduction.
        changes += (
        # The bank28 copier compares DF0D's canonical cache key to raw scene.
        # Resolve only Stage7's alias here; preserve all other scene behavior.
        (0x72C9A, bytes.fromhex('FA80D8B82005'), bytes.fromhex('CD807FB82005')),
        (0x73F80, b'\xff' * len(CACHE_RESOLVER), CACHE_RESOLVER),
        )
    for pos, before, after in changes:
        if parent[pos:pos + len(before)] != before or len(before) != len(after):
            raise ValueError(f'preimage changed at {pos:x}')
        result[pos:pos + len(after)] = after
    result[0x14E:0x150] = ((sum(result[:0x14E]) + sum(result[0x150:])) & 65535).to_bytes(2, 'big')
    return bytes(result)


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('parent', type=Path)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--cache-alias', action='store_true', help='reproduce rejected trial04')
    args = p.parse_args()
    root = Path(__file__).resolve().parents[2]
    if args.output.exists() or (root / 'tmp').resolve() not in args.output.resolve().parents:
        p.error('fresh repository-local tmp output required')
    source = args.parent.read_bytes()
    result = build(source, cache_alias=args.cache_alias)
    args.output.mkdir(parents=True)
    (args.output / 'candidate.gb').write_bytes(result)
    receipt = dict(issues=[59, 66], experimental=True, release_qualified=False,
                   rejected_cache_alias_trial=args.cache_alias,
                   parent_sha256=PARENT, candidate_sha256=hashlib.sha256(result).hexdigest(),
                   builder_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                   changed_offsets=[i for i, (a, b) in enumerate(zip(source, result)) if a != b])
    (args.output / 'receipt.json').write_text(json.dumps(receipt, indent=2) + '\n')
    print(json.dumps(receipt))
