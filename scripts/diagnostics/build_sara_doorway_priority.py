#!/usr/bin/env python3
"""Issue #14 experimental native quadrant priority restoration.

Keep FFC4 owned by the DX map publisher. Store native quadrant 2 in DB70,
and copy the priority helper to DB40 at cold renderer initialization. New
banks 33/34 hold the installers; apparent zero LUT entries are NOT caves.
DB40..DB70 lifecycle and floor-bleed qualification remain required.
"""
import argparse
import hashlib
import json
from pathlib import Path

PARENT_SHA = '7130c04a3ef9ad9239ae693dad9d5d61953437fa3eccc0c137071b79faeacc23'
SOURCE07_SHA = 'eebf3f190d9d307cb1d3fa714fa2e68b7890fc5309d5da26682ce38cce0134fc'
OLD_COPY = bytes.fromhex(
    'C5D5E5 21007B 1100DA 015D00 CDB309 '
    '21B27B 1160DA 012E00 CDB309 '
    '214D7C 118EDA 017200 CDB309 '
    '213A56 1180DB 012300 CDB309 C35C57')


def digest(data):
    return hashlib.sha256(data).hexdigest()


def helper(combined=False, scratch_b=False):
    if scratch_b and not combined:
        raise ValueError('scratch-B requires combined emitter helper')
    code = bytearray()
    labels, branches = {}, []
    def emit(s):
        code.extend(bytes.fromhex(s))
    def branch(op, name):
        code.extend((op, 0))
        branches.append((len(code)-1, name))
    # The only two CALL $1188 sites are mirrored central emitters. E is the
    # OAM attribute destination offset (3,7,11,15 for Sara). Other slots need
    # neither an HRAM read nor an HL save/restore.
    if combined:
        # Native invulnerability flash helper, minus POP HL/RET. Keep its
        # saved HL on the stack for the priority tail instead of saving it
        # twice. Flash animation and FFDD publication remain unchanged.
        emit('E5F57BCB3FCB3FE0DDC6C06F26AB7EA728073D77F1CBE71803F1CBA7')
        # B is saved by the sole emitter caller and unused until its POP BC.
        # F is overwritten by AND $F8 immediately after return. In this mode
        # retain attribute A in B rather than pushing/popping AF again.
        emit('47 F0DD FE04' if scratch_b else 'F5 F0DD FE04')
        branch(0x30, 'clear')
        emit('FE02')
    else:
        emit('F5 7B FE10')
        branch(0x38, 'sara')
        emit('F1 CBBF C9')
        labels['sara'] = len(code)
        emit('E5 F0DD FE02')
    branch(0x20, 'hram')
    emit('FA3EDB' if combined else 'FA70DB')
    branch(0x18, 'test')
    labels['hram'] = len(code)
    emit('21C2FF D7 7E')
    labels['test'] = len(code)
    emit('A7')
    branch(0x28, 'clear')
    emit(('78' if scratch_b else 'F1')+' CBFF E1 C9' if combined else 'E1 F1 CBFF C9')
    labels['clear'] = len(code)
    emit(('78' if scratch_b else 'F1')+' CBBF E1 C9' if combined else 'E1 F1 CBBF C9')
    for index, name in branches:
        code[index] = (labels[name] - index - 1) & 255
    assert len(code) <= (0x3F if combined else 0x30)
    return bytes(code)


def build(parent, combined=False, scratch_b=False):
    if digest(parent) not in (PARENT_SHA, SOURCE07_SHA):
        raise ValueError('requires exact purple GAME OVER / secret CHR or source07 parent')
    calls = [i for i in range(len(parent)) if parent.startswith(bytes.fromhex('CD8811'), i)]
    if calls != [0x37B45, 0x43B45]:
        raise ValueError('priority helper callers changed')
    result = bytearray(parent)
    def patch(offset, old, new):
        if len(old) != len(new) or parent[offset:offset+len(old)] != old:
            raise ValueError(f'preimage/width mismatch at {offset:06x}')
        result[offset:offset+len(old)] = new
    if combined:
        for offset in (0x37B42, 0x43B42):
            patch(offset, bytes.fromhex('CDA211 CD8811'), bytes.fromhex('CD40DB 000000'))
    else:
        patch(0x1188, bytes.fromhex('CBBFC9'), bytes.fromhex('C340DB'))
    # $50DF already returns exactly 0 or 1 and its Z flag. Preserve that result
    # instead of re-normalizing it through two retired FFC4 stores.
    patch(0x50C1, bytes.fromhex('28063E0100001803AF0000'),
          bytes.fromhex('EA3EDB' if combined else 'EA70DB') + bytes(8))
    payload = helper(combined, scratch_b)
    for origin, extension in ((13, 33), (16, 34)):
        offset = origin * 0x4000 + 0x3CBF
        # Stock memcpy returns BC=0 and advances DE. Reuse B=0 for subsequent
        # lengths and the contiguous DA8E destination, freeing six bytes.
        compact = bytes.fromhex(
            'C5D5E5 21007B 1100DA 015D00 CDB309 '
            '21B27B 1160DA 0E2E CDB309 '
            '214D7C 0E72 CDB309 '
            '213A56 1180DB 0E23 CDB309')
        compact += bytes((0x3E, extension, 0xCD, 0x61, 0x00))
        landing = 0x7CBF + len(compact)
        compact += bytes.fromhex('C35C57 00')
        assert len(compact) == len(OLD_COPY)
        patch(offset, OLD_COPY, compact)
        start = extension * 0x4000
        if parent[start:start+0x4000] != b'\xff' * 0x4000:
            raise ValueError('extension bank is not wholly unused')
        # CALL $0061 returns at the same address in the newly mapped bank.
        # Return through fixed-bank code to the original JP $575C, preserving
        # the existing saved HL/DE/BC stack and renderer initialization tail.
        install = bytes.fromhex('214040 1140DB')
        install += bytes((0x01, len(payload), 0, 0xCD, 0xB3, 0x09))
        install += bytes.fromhex('AF EA3EDB' if combined else 'AF EA70DB')
        install += bytes((0x21, landing & 255, landing >> 8, 0xE5,
                          0x3E, origin, 0xC3, 0x61, 0x00))
        result[start+0x40:start+0x40+len(payload)] = payload
        result[start+landing-0x4000:start+landing-0x4000+len(install)] = install
    result[0x14E:0x150] = ((sum(result[:0x14E]) + sum(result[0x150:])) & 65535).to_bytes(2, 'big')
    return bytes(result)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('parent', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--combined', action='store_true', help='fuse native flash and priority; flag DB3E')
    parser.add_argument('--scratch-b', action='store_true', help='combined helper uses caller-saved B instead of AF stack')
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[2]
    if args.output.exists() or (root/'tmp').resolve() not in args.output.resolve().parents:
        parser.error('output must be fresh beneath repository tmp/')
    rom = build(args.parent.read_bytes(), args.combined, args.scratch_b)
    args.output.mkdir(parents=True)
    (args.output/'candidate.gb').write_bytes(rom)
    receipt = dict(issue=14, experimental=True, release_qualified=False, combined=args.combined, scratch_b=args.scratch_b,
                   parent_sha256=digest(args.parent.read_bytes()), candidate_sha256=digest(rom),
                   builder_sha256=digest(Path(__file__).read_bytes()),
                   pending=['doorway replay', 'ordinary floor bleed', 'WRAM lifecycle',
                            'game-loop cadence', 'menu/death/later stages'])
    (args.output/'build-receipt.json').write_text(json.dumps(receipt, indent=2)+'\n')
    print(json.dumps(receipt))
