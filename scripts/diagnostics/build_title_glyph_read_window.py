"""Issue #8 experiment: guard footer VRAM reads as well as its GDMA write.

The existing helper waits only after testing VRAM. A mode-3 read of the
footer tile returns FF and skips the copy, leaving the native 9 visible.
Keep ordinary gameplay's early return unchanged. Title/death paths select
VBK0 and wait before their predicates; the existing GDMA wait is retained.
"""
import argparse
import hashlib
import json
from pathlib import Path

from build_later_hdma_overlap import Asm
import build_title_glyph_window_trial as previous

PARENT = '3d581fc835e15e0d6df691b566b7e2053e1b8d17783496c2e2fcade54a33d626'


def helper():
    a = Asm(previous.ENTRY)
    a.db(*bytes.fromhex('FA80D8 FE02')); a.jr(0x38, 'eligible')
    a.db(*bytes.fromhex('FE15 D8'))
    a.label('eligible')
    a.db(*bytes.fromhex('F04F F5 AF E04F'))
    a.label('read_wait')
    a.db(*bytes.fromhex('F041 E602')); a.jr(0x20, 'read_wait')
    a.db(*bytes.fromhex('FA80D8 FE02')); a.jr(0x38, 'title')
    a.db(*bytes.fromhex('FAFC97 FE18')); a.jr(0x20, 'done')
    a.db(*bytes.fromhex('3E60 E052')); a.jr(0x18, 'copy')
    a.label('title')
    a.db(*bytes.fromhex('FA459A FE79')); a.jr(0x20, 'done')
    a.db(*bytes.fromhex('FAFC97 FE18')); a.jr(0x28, 'done')
    a.db(*bytes.fromhex('3E50 E052'))
    a.label('copy')
    a.db(*bytes.fromhex('3E6D E051 3E17 E053 3EF0 E054'))
    a.label('write_wait')
    a.db(*bytes.fromhex('F041 E602')); a.jr(0x20, 'write_wait')
    a.db(*bytes.fromhex('AF E055'))
    # All no-copy exits must restore VBK through the original shared tail.
    a.label('done')
    a.db(*bytes.fromhex('F1 C3606B'))
    code = a.finish()
    if len(code) > previous.SLOT:
        raise ValueError('footer helper exceeds its owned slot')
    return code + bytes(previous.SLOT - len(code))


def build(parent):
    if hashlib.sha256(parent).hexdigest() != PARENT:
        raise ValueError('exact low-health camera parent required')
    pos = previous.offset(previous.ENTRY)
    if parent[pos:pos + previous.SLOT] != previous.helper():
        raise ValueError('footer helper preimage differs')
    result = bytearray(parent)
    result[pos:pos + previous.SLOT] = helper()
    result[0x14e:0x150] = ((sum(result[:0x14e]) + sum(result[0x150:])) & 65535).to_bytes(2, 'big')
    return bytes(result)


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('parent', type=Path)
    p.add_argument('--output', type=Path, required=True)
    args = p.parse_args()
    if args.output.exists() or (Path(__file__).resolve().parents[2] / 'tmp').resolve() not in args.output.resolve().parents:
        p.error('fresh repository-local tmp output required')
    result = build(args.parent.read_bytes())
    args.output.mkdir(parents=True)
    (args.output / 'candidate.gb').write_bytes(result)
    receipt = dict(issue=8, experimental=True, release_qualified=False,
                   parent_sha256=PARENT, candidate_sha256=hashlib.sha256(result).hexdigest(),
                   builder_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest())
    (args.output / 'receipt.json').write_text(json.dumps(receipt, indent=2) + '\n')
    print(json.dumps(receipt))
