"""#8 diagnostic trial: retry only a blocked footer-tile predicate.

Successful title/restore checks and ordinary gameplay stay byte-for-byte
identical to the qualified write-window helper. Its 11-byte zero tail holds
the retry: accessible false predicates still leave immediately; blocked
ones re-read without pushing another saved VBK. Existing GDMA wait remains.
"""
import argparse
import hashlib
import json
from pathlib import Path
import build_title_glyph_window_trial as old

PARENT = '3d581fc835e15e0d6df691b566b7e2053e1b8d17783496c2e2fcade54a33d626'


def helper():
    code = bytearray(old.helper())
    read = code.index(bytes.fromhex('FA459AFE79'))
    operand = read + 6
    if code[operand - 1] != 0x20:
        raise ValueError('footer readiness predicate moved')
    old_delta = int.from_bytes(code[operand:operand + 1], 'little', signed=True)
    done = operand + 1 + old_delta
    retry = len(bytes(code).rstrip(b'\0'))
    body = bytearray.fromhex('F041 E602 2800 1800')
    for index, target in ((5, done), (7, read)):
        delta = target - (retry + index + 1)
        if not -128 <= delta <= 127:
            raise ValueError('retry branch out of range')
        body[index] = delta & 255
    if retry + len(body) > old.SLOT or any(code[retry:]):
        raise ValueError('retry cave not free')
    code[operand] = (retry - operand - 1) & 255
    code[retry:retry + len(body)] = body
    return bytes(code)


def build(parent):
    if hashlib.sha256(parent).hexdigest() != PARENT:
        raise ValueError('exact camera parent required')
    start = old.offset(old.ENTRY)
    if parent[start:start + old.SLOT] != old.helper():
        raise ValueError('footer preimage differs')
    result = bytearray(parent)
    result[start:start + old.SLOT] = helper()
    result[0x14e:0x150] = ((sum(result[:0x14e]) + sum(result[0x150:])) & 65535).to_bytes(2, 'big')
    return bytes(result)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('parent', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    parent, output = args.parent, args.output
    if output.exists() or (Path(__file__).resolve().parents[2] / 'tmp').resolve() not in output.resolve().parents:
        parser.error('fresh repository-local tmp output required')
    output.mkdir(parents=True, exist_ok=False)
    result = build(parent.read_bytes())
    (output / 'candidate.gb').write_bytes(result)
    receipt = dict(parent_sha256=PARENT, candidate_sha256=hashlib.sha256(result).hexdigest(),
                   builder_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                   experimental=True, release_qualified=False)
    (output / 'receipt.json').write_text(json.dumps(receipt, indent=2) + '\n')
    print(json.dumps(receipt))
