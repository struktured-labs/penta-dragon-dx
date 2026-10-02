"""#27 experiment: route attribute work using the installed graphics owner.

Depends on the sound-alias-aware scene cache. This is deliberately not a
release claim: DF0D freshness across every scene transition requires replay.
"""
import argparse
import hashlib
import json
from pathlib import Path

PARENT = '4eff32d4aa5519486371835690730bba26d2c282f3b3481199e34125d88588db'
# Mirrored source records for DABB, DBA6 and DB80, respectively. Preserve
# instructions, flags, widths and cycles; only the absolute read changes.
SITES = ((0x7C7A, 'FA80D8D603FE06'),
         (0x569C, 'FA80D85F7AFE44'),
         (0x563A, 'FA80D8FE102809FE0C'))


# Re-pin (docs/audit/release-lock-20261001-repin.md): the release-lock chain
# defers #14 and #34. Parent 35b71de0... yields byte-identical
# changes (same offsets, preimages and values) as on the original 4eff32d4...
REPINNED_PARENT = '35b71de0fea498e208e521d74e0dcd8abf0b11117f6f8bfd573b433487ef732e'


def build(parent):
    if hashlib.sha256(parent).hexdigest() not in (PARENT, REPINNED_PARENT):
        raise ValueError('exact sound-alias scene-cache parent required')
    result = bytearray(parent)
    for bank in (13, 16):
        for address, signature in SITES:
            pos = bank*0x4000 + address-0x4000
            old = bytes.fromhex(signature)
            if parent[pos:pos+len(old)] != old:
                raise ValueError('attribute runtime source changed')
            result[pos+1:pos+3] = bytes.fromhex('0DDF')
    result[0x14E:0x150] = ((sum(result[:0x14E])+sum(result[0x150:]))&65535).to_bytes(2,'big')
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
                   parent_sha256=PARENT,
                   candidate_sha256=hashlib.sha256(rom).hexdigest(),
                   builder_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                   scope='three graphics-owner reads in mirrored runtime sources; transition freshness unqualified')
    (args.output/'receipt.json').write_text(json.dumps(receipt,indent=2)+'\n')
    print(json.dumps(receipt))
