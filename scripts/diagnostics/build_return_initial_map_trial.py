"""#45 trial: require a real Stage1 map copy while native gameplay is inactive."""
import argparse
import hashlib
import json
from pathlib import Path

PARENT = '2b797a6af30598141d874a8a272e9a7c77012044fe82f649f1b3e9142d31f306'
OFFSET = 27 * 0x4000 + 0x2c80
OLD = bytes.fromhex('F0 CE B7 28 09 7C C6 03 67 11 E0 C3 0E 00 3E 01 C9')
# FFC1=0: Z survives LD A,1; mapper must return to bank1, never bank0.
# FFC1!=0: retain the original FFCE decision and synthetic copy-end registers.
PREFIX = bytes.fromhex('F0 C1 B7 20 03 3E 01 C9')


def build(parent):
    if hashlib.sha256(parent).hexdigest() != PARENT:
        raise ValueError('exact 2b797 parent required')
    body = PREFIX + OLD
    if parent[OFFSET:OFFSET+len(body)] != OLD + b'\xff' * len(PREFIX):
        raise ValueError('copy helper or extension preimage differs')
    if parent[0x13cd:0x13d8] != bytes.fromhex('3E 1B CD 47 08 CA C6 42 F1 C3 ED'):
        raise ValueError('native-copy return branch differs')
    result = bytearray(parent)
    result[OFFSET:OFFSET+len(body)] = body
    result[0x14e:0x150] = ((sum(result[:0x14e])+sum(result[0x150:]))&65535).to_bytes(2,'big')
    return bytes(result)


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('parent', type=Path)
    p.add_argument('--output', type=Path, required=True)
    a = p.parse_args()
    root = Path(__file__).resolve().parents[2]
    if a.output.exists() or (root/'tmp').resolve() not in a.output.resolve().parents:
        p.error('fresh repository tmp output required')
    rom = build(a.parent.read_bytes())
    a.output.mkdir()
    (a.output/'candidate.gb').write_bytes(rom)
    receipt = dict(issue=45, experimental=True, release_qualified=False,
                   parent_sha256=PARENT, candidate_sha256=hashlib.sha256(rom).hexdigest(),
                   builder_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                   limitations=['requires own cold-route replay; no state retargeting',
                                'CGB native fade remains unmodified', 'timing and audio unverified'])
    (a.output/'receipt.json').write_text(json.dumps(receipt,indent=2)+'\n')
    print(json.dumps(receipt))
