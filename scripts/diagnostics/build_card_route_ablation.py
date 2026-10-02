"""#45 diagnostic: remove only the fixed card-entry dispatch from988b.

Not a release fix. Retains the parent's unqualified allocation and final-fade
dispatch, so a PCM comparison isolates the card-entry contribution.
"""
import argparse
import hashlib
import json
from pathlib import Path

PARENT = '988b3e07bcfd884c01f7355704a48530502cab157d01d33f2767417ffd9921b7'
LATE_PARENT = '46eb95a0c0f770fb3cf8c3211b8030a9e881f59077e558b93703ba08da71d3fb'


def build(parent, late_return=False):
    if hashlib.sha256(parent).hexdigest() != (LATE_PARENT if late_return else PARENT):
        raise ValueError('exact fixed-route parent required')
    if parent[0x75F0:0x75F3] != bytes.fromhex('C3CF00'):
        raise ValueError('card-entry preimage differs')
    result = bytearray(parent)
    result[0x75F0:0x75F3] = bytes.fromhex('C38942')
    result[0x14E:0x150] = ((sum(result[:0x14E])+sum(result[0x150:])) & 65535).to_bytes(2, 'big')
    return bytes(result)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('parent', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--late-return', action='store_true',
                        help='explicit exact46eb late-upload parent, still diagnostic only')
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[2]
    if args.output.exists() or (root/'tmp').resolve() not in args.output.resolve().parents:
        parser.error('fresh repository-local tmp output required')
    rom = build(args.parent.read_bytes(), args.late_return)
    args.output.mkdir()
    (args.output/'candidate.gb').write_bytes(rom)
    receipt = dict(issue=45, diagnostic_only=True, release_qualified=False,
                   allocation_review_complete=False, late_return=args.late_return,
                   parent_sha256=LATE_PARENT if args.late_return else PARENT,
                   candidate_sha256=hashlib.sha256(rom).hexdigest(),
                   builder_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest())
    (args.output/'receipt.json').write_text(json.dumps(receipt, indent=2)+'\n')
    print(json.dumps(receipt))
