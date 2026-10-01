"""#26 chunked staging only for low-health aliases, preserving healthy paths."""
import argparse
import hashlib
import json
from pathlib import Path
from build_secret_chunk_yield_trial import PARENT, body
from build_secret_sound_alias_fast_trial import gate as old_gate

BASE = 38 * 0x4000
GATE = 28 * 0x4000


def gate():
    old = old_gate()
    result = bytearray(old)
    # Redirect only the two alias-success relative jumps to a new bank38 leaf.
    for offset in (43, 49):
        assert old[offset] == 0x28
        result[offset + 1] = len(old) - (offset + 2)
    result.extend(bytes.fromhex('3e26cd47080e003e01c9'))
    return bytes(result)


def build(parent):
    if hashlib.sha256(parent).hexdigest() != PARENT:
        raise ValueError('exact665a parent required')
    old, new = old_gate(), gate()
    if parent[GATE:GATE + len(new)] != old + b'\xff' * (len(new) - len(old)):
        raise ValueError('gate extension occupied')
    if parent[BASE:BASE + 0x4000] != b'\xff' * 0x4000:
        raise ValueError('bank38 occupied')
    result = bytearray(parent)
    result[GATE:GATE + len(new)] = new
    chunk = body()
    assert len(chunk) < 0x2c80
    result[BASE:BASE + len(chunk)] = chunk
    result[BASE + 0x2c80:BASE + 0x2c83] = bytes.fromhex('c30040')
    result[BASE + 0x3f00:BASE + 0x4000] = parent[36 * 0x4000 + 0x3f00:37 * 0x4000]
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
                   builder_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest())
    (args.output / 'receipt.json').write_text(json.dumps(receipt, indent=2) + '\n')
    print(json.dumps(receipt))
