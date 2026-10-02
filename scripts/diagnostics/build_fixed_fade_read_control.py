"""#45 observer self-test only: CPU reads00CF at entry, then halts.

Never a playable/release candidate. Changes no watched byte, so the value read
is still the exact unmodified allocation parent's first proposed cave byte.
"""
import argparse
import hashlib
import json
from pathlib import Path

PARENT = 'ec8be28897810fac01a8918a0403900780015bf6703531f0f82ae259f209f21b'


def build(parent, repeat=False):
    if hashlib.sha256(parent).hexdigest() != PARENT:
        raise ValueError('exact allocation parent required')
    if parent[0x100:0x104] != bytes.fromhex('00C35001'):
        raise ValueError('entry preimage changed')
    result = bytearray(parent)
    if repeat:
        # Keep reading after observer installation; a one-shot entry read may
        # precede Qt's script setup. This destroys startup, never gameplay.
        result[0x150:0x155] = bytes.fromhex('FACF0018FB')
    else:
        result[0x100:0x104] = bytes.fromhex('FACF0076')  # LD A,(00CF); HALT
    result[0x14E:0x150] = ((sum(result[:0x14E])+sum(result[0x150:])) & 65535).to_bytes(2, 'big')
    return bytes(result)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('parent', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--repeat', action='store_true')
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[2]
    if args.output.exists() or (root/'tmp').resolve() not in args.output.resolve().parents:
        parser.error('fresh repository-local tmp output required')
    rom = build(args.parent.read_bytes(), repeat=args.repeat)
    args.output.mkdir()
    (args.output/'candidate.gb').write_bytes(rom)
    receipt = dict(issue=45, diagnostic_only=True, playable=False,
                   release_qualified=False, repeated_read=args.repeat, parent_sha256=PARENT,
                   candidate_sha256=hashlib.sha256(rom).hexdigest(),
                   builder_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest())
    (args.output/'receipt.json').write_text(json.dumps(receipt, indent=2)+'\n')
    print(json.dumps(receipt))
