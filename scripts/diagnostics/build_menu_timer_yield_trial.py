"""Issue #33: experimental timer-only yield before each menu attribute pair."""
import argparse
import hashlib
import json
from pathlib import Path

PARENT = 'eebf3f190d9d307cb1d3fa714fa2e68b7890fc5309d5da26682ce38cce0134fc'
COMBINED_PARENT = '00f2629895d886d36dee8c1e1a9e1c3d47e681760ac40ec9d71f99f94a683492'
FAST_ROW_PARENT = '32bd961cd7a5eb70f65d5a47820ffcba11cd82856ff0c6ce18260e55bc29e628'
ROOT = Path(__file__).resolve().parents[2]
CAVE = 0x7E00


def build(parent, per_row=False, pending_only=False, midpoint_only=False):
    if midpoint_only and not pending_only:
        raise ValueError('midpoint trial requires pending-only row yield')
    if pending_only and not per_row:
        raise ValueError('pending-only trial requires row-tail placement')
    parent_sha = hashlib.sha256(parent).hexdigest()
    if parent_sha not in (PARENT, COMBINED_PARENT, FAST_ROW_PARENT):
        raise ValueError('exact source07, ceiling-secret composition or fast-row parent required')
    if parent_sha == FAST_ROW_PARENT and not per_row:
        raise ValueError('fast-row staging requires a row-tail yield')
    base = 20 * 0x4000
    bank = parent[base:base + 0x4000]
    # Hook the row tail, not its two-byte prefix: the inner pair loop jumps
    # directly to the following PUSH BC, which must remain an instruction.
    pattern = bytes.fromhex('7806000E0C094705' if per_row else 'C51A13CD844047')
    if bank.count(pattern) != 1:
        raise ValueError('menu pair preimage differs')
    offset = bank.index(pattern)
    resume = 0x4000 + offset + 3
    # Preserve every caller register and IE. Only the timer can run; VBK0
    # and the original bank1 stack are visible to it. Reacquire HBlank in
    # the unmodified pair body after returning, never reuse a sampled edge.
    helper = bytes.fromhex(
        'F5 C5 D5 E5 F0 FF F5 E6 04 E0 FF AF E0 4F '
        'FB 00 F3 3E 01 E0 4F F1 E0 FF E1 D1 C1 F1 '
    ) + pattern[:3] + b'\xc3' + resume.to_bytes(2, 'little')
    if pending_only:
        # No timer pending: skip register/bank/IE shuffling. The branch lands
        # on the common POP AF, retaining the caller's flags on both paths.
        body = helper[1:-7]
        assert helper[-7] == 0xF1
        helper = bytes.fromhex('F5 F0 0F E6 04 28') + bytes([len(body)]) + body + helper[-7:]
        if midpoint_only:
            # B=4 at the third row tail (before the native decrement).
            rest = helper[1:]
            helper = bytes.fromhex('F5 78 FE 04 20') + bytes([len(rest)-7]) + rest
    cave = base + CAVE - 0x4000
    if parent[cave:cave + len(helper)] != b'\xff' * len(helper):
        raise ValueError('menu yield cave occupied')
    result = bytearray(parent)
    result[base + offset:base + offset + 3] = b'\xc3' + CAVE.to_bytes(2, 'little')
    result[cave:cave + len(helper)] = helper
    result[0x14E:0x150] = ((sum(result[:0x14E]) + sum(result[0x150:])) & 65535).to_bytes(2, 'big')
    return bytes(result)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('parent', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--per-row', action='store_true')
    parser.add_argument('--pending-only', action='store_true')
    parser.add_argument('--midpoint-only', action='store_true')
    args = parser.parse_args()
    out = args.output.resolve()
    if out.exists() or (ROOT / 'tmp').resolve() not in out.parents:
        parser.error('fresh repository tmp directory required')
    rom = build(args.parent.read_bytes(), args.per_row, args.pending_only, args.midpoint_only)
    out.mkdir()
    (out / 'candidate.gb').write_bytes(rom)
    receipt = dict(issue=33, experimental=True, release_qualified=False, per_row=args.per_row,
                   pending_only=args.pending_only,
                   midpoint_only=args.midpoint_only,
                   parent_sha256=hashlib.sha256(args.parent.read_bytes()).hexdigest(), candidate_sha256=hashlib.sha256(rom).hexdigest(),
                   builder_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest())
    (out / 'build-receipt.json').write_text(json.dumps(receipt, indent=2) + '\n')
    print(json.dumps(receipt))
