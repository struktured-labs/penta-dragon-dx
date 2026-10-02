"""#23 diagnostic: use existing fused copier and attribute publisher in scene09.

Not release-qualified. Reinitializes the shared LUT on each secret copy; scene
exit LUT restoration, interrupt behavior and timing require emulator validation.
"""
import argparse
import hashlib
import json
from pathlib import Path
from build_later_hdma_overlap import Asm
from build_secret_attributes_trial import ROOT, PARENT, HOOK, BANK, BASE, PICKUPS


def gate():
    a = Asm(0x4000)
    a.db(0xf0, 0xba, 0xfe, 7); a.jr(0x20, 'native')
    a.db(0xfa, 0x80, 0xd8, 0xfe, 9); a.jr(0x20, 'native')
    a.db(0x3e, BANK, 0xcd, 0x47, 0x08)
    a.label('native')
    a.db(0x11, 0xa0, 0xc1, 0x0e, 0x41, 0xc3, 0x85, 0x6c)
    return a.finish()


def helper():
    a = Asm(0x6c80)
    # Existing atomic setup captures IE and tags the caller's destination in FF01.
    # Keep stack in SVBK1 throughout; native copier owns staging and publication.
    a.db(0xf3, 0xcd, 0x13, 0xda, 0xc5, 0xd5, 0xe5)
    a.db(0x21, 0, 0x7f, 0x11, 0, 0xc6, 0x06, 0)
    a.label('lookup')
    a.db(0x2a, 0x12, 0x13, 0x05); a.jr(0x20, 'lookup')
    a.db(0xaf, 0xe0, 0xe0, 0xe1, 0xd1, 0xc1, 0x3e, 28, 0xc9)
    return a.finish()


def build(parent):
    if hashlib.sha256(parent).hexdigest() != PARENT:
        raise ValueError('exact source07 required')
    if parent[HOOK:HOOK+5] != bytes.fromhex('11a0c10e41'):
        raise ValueError('copier entry differs')
    local = 28 * 0x4000
    g, h = gate(), helper()
    if parent[local:local+len(g)] != b'\xff' * len(g):
        raise ValueError('local gate occupied')
    if parent[BASE:BASE+0x4000] != b'\xff' * 0x4000:
        raise ValueError('helper bank occupied')
    r = bytearray(parent)
    r[HOOK:HOOK+5] = bytes.fromhex('c300400000')
    r[local:local+len(g)] = g
    r[BASE+0x2c80:BASE+0x2c80+len(h)] = h
    table = bytearray(256)
    for pickup in PICKUPS:
        for tile in pickup.tiles:
            table[tile] = pickup.palette
    r[BASE+0x3f00:BASE+0x4000] = table
    r[0x14e:0x150] = ((sum(r[:0x14e])+sum(r[0x150:])) & 65535).to_bytes(2, 'big')
    return bytes(r)


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('parent', type=Path)
    p.add_argument('--output', type=Path, required=True)
    args = p.parse_args()
    out = args.output.resolve()
    if out.exists() or (ROOT / 'tmp').resolve() not in out.parents:
        p.error('fresh repository tmp directory required')
    rom = build(args.parent.read_bytes())
    out.mkdir(parents=True)
    (out / 'candidate.gb').write_bytes(rom)
    receipt = dict(issue=23, experimental=True, release_qualified=False,
                   parent_sha256=PARENT, candidate_sha256=hashlib.sha256(rom).hexdigest(),
                   builder_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest())
    (out / 'build-receipt.json').write_text(json.dumps(receipt, indent=2)+'\n')
    print(json.dumps(receipt))
