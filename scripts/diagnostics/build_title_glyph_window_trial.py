"""Release lock: run the v3.01 footer glyph GDMA only in a VRAM-accessible window.

The footer helper (bank13:6DA7, build_v302_title_fix.build_vram_glyph_copy)
installs the temporary period over title tile $7F, and restores digit 9 on
leaving the title, with a one-block GDMA. It assumes it runs inside VBlank,
but the VBlank wrapper's earlier work places it in active display. On the
release-lock chain the returned title (after Game Over) enters the helper at
LY 0 in mode 3 on every frame, so each GDMA write is discarded and the footer
reads "DX V3901". The 126dd #34 select-buffer bytes only masked this by
shifting the timing.

Rewrite the helper in place (89-byte slot, unchanged entry and tail) so that
every non-copy path runs the identical instruction sequence and cycle cost.
Only a frame that actually copies a glyph waits until STAT reports mode 0 or 1
(LCD off also reads mode 0) before triggering GDMA. A 16-byte GDMA (32 dots) plus the
trigger fits inside the following mode 2 even when the wait exits on the last
mode-0/1 dot, so the copy never reaches mode 3.
"""
import argparse
import hashlib
import json
from pathlib import Path

from build_later_hdma_overlap import Asm

PARENT = '6ec44fe6b77dd59088c06a07e0631187737e8471365a68806c0d5aa407563b97'
BANK = 13
ENTRY = 0x6DA7
SLOT = 0x6E00 - ENTRY
OLD = bytes.fromhex(
    'fa80d8fe023828fe15d8f04ff5afe04ffafc97fe1820143e6de0513e60e0523e17e053'
    '3ef0e0543e00e055f1c3606bf04ff5afe04ffa459afe7920effafc97fe1828e83e6de051'
    '3e50e0523e17e0533ef0e0543e00e05518d2')


def offset(address):
    return BANK * 0x4000 + address - 0x4000


def helper():
    a = Asm(ENTRY)
    a.db(*bytes.fromhex('FA80D8 FE02')); a.jr(0x38, 'title')
    a.db(*bytes.fromhex('FE15 D8'))                # RET C: ordinary gameplay
    a.db(*bytes.fromhex('F04F F5 AF E04F'))         # save VBK; select bank 0
    a.db(*bytes.fromhex('FAFC97 FE18')); a.jr(0x20, 'done')
    a.db(*bytes.fromhex('3E60 E052'))               # source: native digit 9
    a.jr(0x18, 'copy')
    a.label('title')
    a.db(*bytes.fromhex('F04F F5 AF E04F'))
    a.db(*bytes.fromhex('FA459A FE79')); a.jr(0x20, 'done')
    a.db(*bytes.fromhex('FAFC97 FE18')); a.jr(0x28, 'done')
    a.db(*bytes.fromhex('3E50 E052'))               # source: period
    a.label('copy')                                 # bank13:6D50/6D60 -> 97F0
    a.db(*bytes.fromhex('3E6D E051 3E17 E053 3EF0 E054'))
    a.label('wait')
    a.db(*bytes.fromhex('F041 E602')); a.jr(0x20, 'wait')   # mode 2/3: wait
    a.db(*bytes.fromhex('AF E055'))                 # one-block GDMA
    a.label('done')
    a.db(*bytes.fromhex('F1 C3606B'))              # unchanged shared tail
    code = a.finish()
    if len(code) > SLOT:
        raise AssertionError(len(code))
    return code + bytes(SLOT - len(code))


def build(parent):
    if hashlib.sha256(parent).hexdigest() != PARENT:
        raise ValueError('exact release-lock 6ec44fe6 parent required')
    pos = offset(ENTRY)
    if parent[pos:pos + len(OLD)] != OLD or len(OLD) != SLOT:
        raise ValueError('footer glyph helper preimage differs')
    result = bytearray(parent)
    result[pos:pos + SLOT] = helper()
    result[0x14E:0x150] = ((sum(result[:0x14E]) + sum(result[0x150:])) & 65535).to_bytes(2, 'big')
    return bytes(result)


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('parent', type=Path)
    p.add_argument('--output', type=Path, required=True)
    a = p.parse_args()
    root = Path(__file__).resolve().parents[2]
    if a.output.exists() or (root / 'tmp').resolve() not in a.output.resolve().parents:
        p.error('fresh repository tmp output required')
    rom = build(a.parent.read_bytes())
    a.output.mkdir()
    (a.output / 'candidate.gb').write_bytes(rom)
    r = dict(experimental=False, release_qualified=False, parent_sha256=PARENT,
             candidate_sha256=hashlib.sha256(rom).hexdigest(),
             builder_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest())
    (a.output / 'receipt.json').write_text(json.dumps(r, indent=2) + '\n')
    print(json.dumps(r))
