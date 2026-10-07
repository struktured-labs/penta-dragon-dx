"""#59/#66 experiment: low-nibble camera domain on exact low-health trial03.

Reuses r274's viewport geometry, not its historical runtime qualification.
Preserves every other guard and patches entry and post-service masks together.
"""
import argparse
import hashlib
import json
from pathlib import Path
from build_stage7_r274_low_nibble import viewport

PARENT = '9bba2276a97e3178f9e860b1bc7008f2185086c46ae0a7979b9c35b160c85399'


def build(parent):
    if hashlib.sha256(parent).hexdigest() != PARENT:
        raise ValueError('exact fastpath trial03 required')
    visible = set().union(*(viewport(x, y) for x in range(16) for y in range(16)))
    if visible != {(y, x) for y in range(20) for x in range(22)}:
        raise ValueError('viewport geometry changed')
    if parent[0x5ACF4:0x5ACFB] != bytes.fromhex('3E14E0E0CD00D4'):
        raise ValueError('20-row attribute compiler changed')
    result = bytearray(parent)
    for pos, before in (
        (0x5ACB4, 'F043E6F3C2B371'), (0x5ACBB, 'F042E6F3C2B371'),
        (0x5B1FE, 'F043E6F3C23172'), (0x5B205, 'F042E6F3C23172'),
    ):
        if parent[pos:pos+7] != bytes.fromhex(before):
            raise ValueError(f'camera guard changed at {pos:x}')
        result[pos+3] = 0xF0
    result[0x14E:0x150] = ((sum(result[:0x14E])+sum(result[0x150:])) & 65535).to_bytes(2, 'big')
    return bytes(result)


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('parent', type=Path)
    p.add_argument('--output', type=Path, required=True)
    args = p.parse_args()
    if args.output.exists() or (Path(__file__).resolve().parents[2]/'tmp').resolve() not in args.output.resolve().parents:
        p.error('fresh repository-local tmp output required')
    source = args.parent.read_bytes()
    result = build(source)
    args.output.mkdir(parents=True)
    (args.output/'candidate.gb').write_bytes(result)
    receipt = dict(issues=[59, 66], experimental=True, release_qualified=False,
                   parent_sha256=PARENT, candidate_sha256=hashlib.sha256(result).hexdigest(),
                   builder_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                   changed_offsets=[i for i, (a, b) in enumerate(zip(source, result)) if a != b])
    (args.output/'receipt.json').write_text(json.dumps(receipt, indent=2)+'\n')
    print(json.dumps(receipt))
