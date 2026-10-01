"""#45 scratch-only late routing experiment; allocation not release-qualified.

Retain native loader/card waits. Route stage-zero fades through the existing
bank20 wrapper, other stages directly to native fades. The original random
bytes after the LCD-enable RET are a placement hypothesis, not proven free ROM.
Do not integrate without an independent allocation review and full regressions.
"""
import argparse
import hashlib
import json
from pathlib import Path

PARENT = 'ec8be28897810fac01a8918a0403900780015bf6703531f0f82ae259f209f21b'
START = 0xCF
PREIMAGE = bytes.fromhex('FF7C76CEF8DDEFFFFFDFFF57FF7DFFDDFF70')


def build(parent):
    if hashlib.sha256(parent).hexdigest() != PARENT:
        raise ValueError('exact fastpath parent required')
    if parent[0xC8:START] != bytes.fromhex('F040F680E040C9'):
        raise ValueError('LCD-enable fence changed')
    if parent[START:START+18] != PREIMAGE:
        raise ValueError('experimental placement preimage changed')
    result = bytearray(parent)
    # Native routines initialize A/flags before use. No RAM ownership added.
    result[START:START+18] = bytes.fromhex(
        'F0BA B7 C2330F C38942 F0BA B7 C27A0F C38942')
    for site, old, new in (
        (0x75F0, 'C38942', 'C3CF00'),
        (0x15DA, 'CD8942', 'CDD800'),
    ):
        if parent[site:site+3] != bytes.fromhex(old):
            raise ValueError('fade call preimage changed')
        result[site:site+3] = bytes.fromhex(new)
    result[0x14E:0x150] = ((sum(result[:0x14E])+sum(result[0x150:]))&65535).to_bytes(2,'big')
    return bytes(result)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('parent', type=Path)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[2]
    if args.output.exists() or (root/'tmp').resolve() not in args.output.resolve().parents:
        parser.error('fresh repository-local tmp output required')
    rom = build(args.parent.read_bytes())
    args.output.mkdir()
    (args.output/'candidate.gb').write_bytes(rom)
    receipt = dict(issue=45, experimental=True, allocation_review_complete=False,
                   release_qualified=False, parent_sha256=PARENT,
                   candidate_sha256=hashlib.sha256(rom).hexdigest(),
                   builder_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest())
    (args.output/'receipt.json').write_text(json.dumps(receipt,indent=2)+'\n')
    print(json.dumps(receipt))
