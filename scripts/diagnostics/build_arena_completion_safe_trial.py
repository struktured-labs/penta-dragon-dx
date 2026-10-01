"""Issue #27: direct scene lookup with installer-specific completion preserved.

Experimental only. Bank13 gets a direct resolver; bank16 and bank31 retain
their legacy completion behavior and native raw scene reads. Runtime ownership,
timing, transitions, and visible output still require emulator qualification.
"""
import argparse
import hashlib
import json
from pathlib import Path

from build_arena_direct_scene_trial import PARENT, RESOLVER, FRAGMENTS, offset

OLD_GUARD = bytes.fromhex('F0BA B7 2804 AF E001 C9 C3E210')
NEW_GUARD = bytes.fromhex('C9 00 F0BA B7 CAE210 AF E001 C9')
LEGACY = bytes.fromhex('F0E1 B7 CA9734 F3 3E15 EA0021 C30040 C39734')


# Re-pin (docs/audit/release-lock-20261001-repin.md): the release-lock chain
# defers #14 and #34. Parent 1b3bbf84... yields byte-identical
# changes (same offsets, preimages and values) as on the original 585f5830...
REPINNED_PARENT = '1b3bbf845a096dd5e5818b4f98fe68cb00f95468ad1a7ad8926c4946d3f2ed4e'


def build(parent):
    if hashlib.sha256(parent).hexdigest() not in (PARENT, REPINNED_PARENT):
        raise ValueError('exact fastpath parent required')
    result = bytearray(parent)

    def replace(pos, before, after):
        if len(before) != len(after) or parent[pos:pos+len(before)] != before:
            raise ValueError(f'preimage/length mismatch at {pos:x}')
        result[pos:pos+len(before)] = after

    for bank in (13, 16, 31):
        fragments = ([(0x7f196, 77)] if bank == 31 else
                     [(offset(bank, a), n) for a, n in FRAGMENTS])
        runtime = b''.join(parent[p:p+n] for p, n in fragments)
        tail = bytes.fromhex('C39734') + bytes(15) if bank == 13 else LEGACY
        if (runtime[56:] != bytes.fromhex('AFE1C9') + tail or
                runtime[49:52] != bytes.fromhex('AFE1C9') or
                runtime[9:11] != bytes.fromhex('282D') or
                runtime[14:16] != bytes.fromhex('2828')):
            raise ValueError(f'installer {bank} semantic layout changed')
        code = bytearray(runtime)
        code[10], code[15] = 0x26, 0x21  # shared pure return at DBD5
        if bank == 13:
            code[2:5] = bytes.fromhex('CDDFDB')
            code[56:] = bytes.fromhex('C39734') + RESOLVER[:-1]
        else:
            code[2:5] = bytes.fromhex('FA80D8')
            code[56:59] = bytes.fromhex('C3DFDB')
        cursor = 0
        for pos, size in fragments:
            replace(pos, runtime[cursor:cursor+size], code[cursor:cursor+size])
            cursor += size
    # DBF1 holds the resolver RET; the equivalent guard moves to DBF3.
    for pos in (0x35830, 0x4155d, 0x7f1e3):
        replace(pos, OLD_GUARD, NEW_GUARD)
    for pos in (0x42f5, 0x4354):
        replace(pos, bytes.fromhex('CDF1DB'), bytes.fromhex('CDF3DB'))
    replace(0x4357, bytes.fromhex('C3DFDB'), bytes.fromhex('C3DCDB'))
    for bank in (13, 16):
        for address in (0x7c7a, 0x563a):
            replace(offset(bank, address), bytes.fromhex('FA0DDF'),
                    bytes.fromhex('CDDFDB' if bank == 13 else 'FA80D8'))
    result[0x14e:0x150] = ((sum(result[:0x14e])+sum(result[0x150:])) & 65535).to_bytes(2, 'big')
    return bytes(result)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('parent', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[2]
    if args.output.exists() or (root/'tmp').resolve() not in args.output.resolve().parents:
        parser.error('fresh repository tmp output required')
    rom = build(args.parent.read_bytes())
    args.output.mkdir(parents=True)
    (args.output/'candidate.gb').write_bytes(rom)
    receipt = dict(issue=27, experimental=True, release_qualified=False,
                   parent_sha256=PARENT, candidate_sha256=hashlib.sha256(rom).hexdigest(),
                   builder_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                   qualification='not emulator tested; bank16/31 raw reads remain')
    (args.output/'receipt.json').write_text(json.dumps(receipt, indent=2)+'\n')
    print(json.dumps(receipt))
