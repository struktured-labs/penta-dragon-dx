"""Issue #24: bound VBlank admission before the banked four-byte publisher."""
import argparse
import hashlib
import json
from pathlib import Path
from build_later_hdma_overlap import Asm
from compose_palette_publisher_atomic_r532 import build_router, source_writer

PARENT = 'e8002aea7117e6416b546e39655d7c792959913af66c827c28223bf6b01b6c57'
OFFSET = 20 * 0x4000 + 0x3320


def router():
    a = Asm(0x7320)
    a.db(*bytes.fromhex('78 C1 D5 57 F0 FF 5F AF E0 FF'))
    a.db(0xF0, 0x40, 0xCB, 0x7F)
    a.jr(0x28, 'write')
    a.db(0xF0, 0x41, 0xE6, 3, 0xFE, 1)
    a.jr(0x20, 'wait3')
    # LY153 briefly reads153 then0. Accept only144..151, leaving more
    # than a whole scanline for the mapper/stack path and four writes.
    a.db(0xF0, 0x44, 0xFE, 144)
    a.jr(0x38, 'wait3')
    a.db(0xFE, 152)
    a.jr(0x38, 'write')
    a.label('wait3')
    a.db(0xF0, 0x41, 0xE6, 3, 0xFE, 3)
    a.jr(0x20, 'wait3')
    a.label('wait0')
    a.db(0xF0, 0x41, 0xE6, 3)
    a.jr(0x20, 'wait0')
    a.label('write')
    a.db(*bytes.fromhex('7A E5 21 E3 71 E5 C3 61 00'))
    return a.finish()


def build(parent):
    if hashlib.sha256(parent).hexdigest() != PARENT:
        raise ValueError('exact combined experimental parent required')
    old, new = build_router(), router()
    if parent[OFFSET:OFFSET+len(old)] != old:
        raise ValueError('publisher router differs')
    if parent[OFFSET+len(old):OFFSET+len(new)] != b'\xff' * (len(new)-len(old)):
        raise ValueError('router extension occupied')
    for bank in (13, 16):
        offset = bank * 0x4000 + 0x31E3
        if parent[offset:offset+len(source_writer())] != source_writer():
            raise ValueError('source writer differs')
    result = bytearray(parent)
    result[OFFSET:OFFSET+len(new)] = new
    result[0x14E:0x150] = ((sum(result[:0x14E])+sum(result[0x150:])) & 65535).to_bytes(2,'big')
    return bytes(result)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('parent', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[2]
    out = args.output.resolve()
    if out.exists() or (root/'tmp').resolve() not in out.parents:
        parser.error('fresh repository tmp directory required')
    result = build(args.parent.read_bytes())
    out.mkdir(parents=True)
    (out/'candidate.gb').write_bytes(result)
    receipt = dict(issue=24, experimental=True, release_qualified=False,
                   parent_sha256=PARENT, candidate_sha256=hashlib.sha256(result).hexdigest(),
                   builder_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest())
    (out/'receipt.json').write_text(json.dumps(receipt, indent=2)+'\n')
    print(json.dumps(receipt))
