"""#26 experimental shorter bank6 staging critical sections; not qualified."""
import argparse
import hashlib
import json
from pathlib import Path
from build_secret_combined_copy_trial import code, helper

PARENT = '665a33b6b26d0a8ec1622a7c897d4fc10bdf7c8c5e0e5a2edaae98df0dafe0e7'
BASE = 36 * 0x4000
YIELD = bytes.fromhex('3e01e070fb00f33e06e070')


def body():
    old = code(6, True)
    staging = helper(6, True).finish()
    result = bytearray(staging[:16])
    cursor = 16
    for row in range(24):
        for chunk in range(3):
            result.extend(staging[cursor:cursor + 80])
            cursor += 80
            if chunk < 2:
                # Next instruction reloads A from [DE]; no live A/flags lost.
                result.extend(YIELD)
        result.extend(staging[cursor:cursor + 49])
        cursor += 49
        if row < 23:
            assert staging[cursor:cursor + len(YIELD)] == YIELD
            result.extend(YIELD)
            cursor += len(YIELD)
    assert cursor == len(staging)
    result.extend(old[len(staging):])  # Relative DMA loops remain unchanged.
    return bytes(result)


def build(parent):
    if hashlib.sha256(parent).hexdigest() != PARENT:
        raise ValueError('exact665a parent required')
    old, new = code(6, True), body()
    if parent[BASE:BASE + len(new)] != old + b'\xff' * (len(new) - len(old)):
        raise ValueError('copier body or extension cave differs')
    if len(new) >= 0x2c80:
        raise ValueError('body overlaps entry trampoline')
    result = bytearray(parent)
    result[BASE:BASE + len(new)] = new
    result[0x14e:0x150] = ((sum(result[:0x14e]) + sum(result[0x150:])) & 65535).to_bytes(2, 'big')
    return bytes(result)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('parent', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[2]
    if args.output.exists() or (root / 'tmp').resolve() not in args.output.resolve().parents:
        parser.error('fresh repository tmp output required')
    result = build(args.parent.read_bytes())
    args.output.mkdir(parents=True)
    (args.output / 'candidate.gb').write_bytes(result)
    receipt = dict(issue=26, experimental=True, release_qualified=False,
                   parent_sha256=PARENT, candidate_sha256=hashlib.sha256(result).hexdigest(),
                   builder_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                   added_interrupt_windows=48, body_bytes=len(body()))
    (args.output / 'receipt.json').write_text(json.dumps(receipt, indent=2) + '\n')
    print(json.dumps(receipt))
