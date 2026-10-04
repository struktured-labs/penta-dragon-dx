#!/usr/bin/env python3
"""Release lock: Continue into a live miniboss restores the fight's palettes,
every CRAM burst is mode-3-proof, and the frame timing is cycle-identical to
the 792319cb parent on every path (refs #28).

Root causes (792319cb)
  a. Continue after dying to a miniboss resumes straight into scene D880=$0A.
     The deferred BG reload ($DF5D) is consumed by the VBlank commit gate
     (bank13 $7703) only while D880==$02, so the death/white-fade CRAM survives
     until the miniboss dies (flat pink room/HUD, garbled-looking Sara).
  b. Palette-sequencer CRAM bursts go through the bank-20 router ($732A): it
     waits for a fresh HBlank and then spends 35 M-cycles on the fixed mapper
     switch ($0061/$09BE) before the bank-13 writer ($71E3) issues its four
     writes. On long mode-3 lines the 4th write lands in the next line's mode 3
     and the PPU drops it (stale BG byte 59 / OBJ byte $CF seen live).
  c. The death service (bank13/bank16 $7182..$7188) repeats one direct,
     unchecked write of BG byte 39 that can hit mode 3 during the death fade.

The frame-timed attract demo, boss-speed parity and Stage-7 gates depend on the
exact per-frame cycle profile, so this stage changes no cycle count on any
path except the post-death Continue acceptance (a menu frame; the demo never
dies):

1. Cycle-funded dispatch (bank 20). The forward entry chain ($7A2A..$7A59)
   kept the source bank in B and then did PUSH BC / LD B,A ... LD A,B / POP BC
   and a JP hop to $7320 before $732A. Keeping the bank in D instead
   ($7A2B PUSH DE / LD D,A, $7A54 LD A,D / POP DE) and jumping straight to the
   new dispatcher ($7A59 JP $6320) frees 13 M-cycles per burst. The dispatcher
   spends exactly those 13 M (per leaf, NOP / INC BC+DEC BC padding and
   identical carry-flag results) choosing a router:
     - source page $68xx (bank 13/16): RC68, writes from a bank-20 copy of the
       page at the same address;
     - source page $7Cxx: RC7C, H translated to the bank-20 copy ($6E for
       bank 13, $70 for bank 16) and restored to $7C;
     - Stage-7 local path ($7DB1) and every other source: the original router
       bytes (inline copy, RCOLD) or the original $732A, unchanged.
   RC68/RC7C use the identical VBlank/LCD-off fast paths and HBlank wait, then
   issue the four writes immediately after the edge (4th write <= 28 M after
   HBlank begins, inside the minimum 167-dot mode-0+mode-2 window), pad, load
   A=D and enter the shared tail at $71E9 (CALL $0061 -> bank13 $71EC). From
   the edge to $7FE3 the path is exactly 65 M-cycles, as in the parent, with
   the same registers, flags, $DC09/$FF99/IE and bank.
2. Death service (banks 13 and 16, $7182): `LD A,A7 / LDH [68],A / DEC HL /
   LD A,[HL] / LDH [C],A` becomes `LD A,A8 / LDH [68],A / DEC HL / LD A,[HL] /
   LD A,[HL]`: same bytes count and cycles, the index register still ends at
   $A8, and the redundant unchecked byte-39 repair write is gone (the following
   mode-safe bursts already write that byte).
3. Continue acceptance (bank 1 $4AD4, runs only when the player picks Continue):
   `LD A,FF / LD [DCBB],A` becomes `LD A,27 / CALL $0847` (bank-call ABI). The
   bank-$27 helper does the original store and, when the resume scene has a
   live miniboss (FFBF!=0), queues the palette sequencer's reload job
   ($DF4C:=$11, what the $7703 gate's reload path hands it). The sequencer
   does not step during scene $17, so the job runs from the first $0A frame
   after resume through the mode-safe routers. Returns A=1 (bank for $0061).

Verified: attract demo frames 0-26000 lockstep against 792319cb (emu cycle
counter, scene, RNG, WRAM $C000-$DEFF, HRAM and CRAM identical every frame;
only a dead stack slot at $DFC1-$DFC4 differs) and
verify_stage1_miniboss_continue_palette.py.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

PARENT = '792319cbe9db7d56ae6497018b727c8a0a8737c3c8c7a4a122713054677022db'
NAME = 'continue-miniboss-reload'
ROUTER_BANK = 20
TREE_ORG = 0x6320
TREE_LIMIT = 0x67E0
PRIVATE_BANK = 0x27
PRIVATE_ENTRY = 0x6C80
PAGE_COPIES = ((0x6800, 13, 0x6800), (0x6E00, 13, 0x7C00), (0x7000, 16, 0x7C00))
# Per-leaf padding (M-cycles) that makes every dispatch leaf reach its router
# with the parent's cycle count; RC_PAD is the post-write padding.
PADS = {'B7C': 2, 'Both': 1, 'F68': 9, 'S7a': 6, 'S7b': 5, 'E68': 11, 'D68': 12,
        'C7C': 5, 'Coth': 6, 'A68': 3, 'A7C': 1, 'OLDA': 6}
RC_PAD = {'RC68': 8, 'RC7C': 6}

OLD_ROUTER = bytes.fromhex('F040CB7F2820F041E603FE01200AF044FE903804FE98380E'
                           'F041E603FE0320F8F041E60320FA7AE521E371E5C36100')
CHAIN_EDITS = ((0x7A2B, 0xC5, 0xD5), (0x7A2C, 0x47, 0x57), (0x7A54, 0x78, 0x7A), (0x7A55, 0xC1, 0xD1))
CHAIN_JP_OLD = bytes.fromhex('C32073')
TAIL = bytes.fromhex('3E0DCD6100')               # bank20 $71E7, unchanged
WRITER = bytes.fromhex('E12AE22AE22AE22AE27BD1E0FFC9')   # bank13 $71E3, unchanged
DEATH_OLD = bytes.fromhex('3EA7E0682B7EE2')
DEATH_NEW = bytes.fromhex('3EA8E0682B7E7E')
ACCEPT_OLD = bytes.fromhex('3EFFEABBDC')
ACCEPT_NEW = bytes.fromhex('3E27CD4708')
BANK_CALL_ABI = bytes.fromhex('CD6100CD806CC36100')
MAPPER_SWITCH = bytes.fromhex('EA09DCC3BE09')
MAPPER_TAIL = bytes.fromhex('E099EA0021C9')


def off(bank, addr):
    return bank * 0x4000 + addr - (0x4000 if bank else 0)


def assemble(org, items):
    """Label-aware SM83 assembler: hex strings, ('label',n), ('jr',cc,n),
    ('jpc',cc,n), ('jp',n|addr)."""
    size = lambda it: (len(bytes.fromhex(it)) if isinstance(it, str)
                       else {'label': 0, 'jr': 2}.get(it[0], 3))
    labels, pc = {}, org
    for it in items:
        if not isinstance(it, str) and it[0] == 'label':
            assert it[1] not in labels, it
            labels[it[1]] = pc
        pc += size(it)
    out, pc = bytearray(), org
    for it in items:
        if isinstance(it, str):
            out += bytes.fromhex(it)
        elif it[0] == 'jr':
            rel = labels[it[2]] - (pc + 2)
            assert -128 <= rel <= 127, it
            out += bytes(({None: 0x18, 'NZ': 0x20, 'Z': 0x28, 'C': 0x38}[it[1]], rel & 0xFF))
        elif it[0] == 'jpc':
            t = labels[it[2]]
            out += bytes(({'NZ': 0xC2, 'Z': 0xCA}[it[1]], t & 0xFF, t >> 8))
        elif it[0] == 'jp':
            t = it[1] if isinstance(it[1], int) else labels[it[1]]
            out += bytes((0xC3, t & 0xFF, t >> 8))
        pc += size(it)
    return bytes(out), labels


def pad(n):
    """n M-cycles of padding: INC BC/DEC BC pairs (4 M) then NOPs."""
    assert n >= 0
    return '030B' * (n // 4) + '00' * (n % 4)


def router_copy(prefix, post, n):
    p = prefix
    return [('label', p), 'F040', 'CB7F', ('jr', 'Z', p + 'S'), 'F041', 'E603', 'FE01',
            ('jr', 'NZ', p + 'E'), 'F044', 'FE90', ('jr', 'C', p + 'E'), 'FE98', ('jr', 'C', p + 'S'),
            ('label', p + 'E'), 'F041', 'E603', 'FE03', '20F8', 'F041', 'E603', '20FA',
            ('label', p + 'S'), '2AE2', '2AE2', '2AE2', '2AE2', *post,
            '7A', pad(n), ('jp', 0x71E9)]


def dispatcher_items():
    P = lambda k: pad(PADS[k])
    return [
        'F0FF', '5F', 'AF', 'E0FF',            # E:=IE, IE:=0 (as the parent's $7D84)
        '7A', 'FE0D', ('jr', 'NZ', 'LA'),
        '79', 'FE6B', ('jr', 'NZ', 'LB'),
        '7C', 'FE68', ('jr', 'NZ', 'LC'),
        '7D', 'E6FB', 'FE58', ('jpc', 'NZ', 'D68'),
        'F0BA', 'FE07', ('jpc', 'NZ', 'E68'),
        'FA80D8', 'FE09', ('jpc', 'Z', 'S7a'),
        'FE0A', ('jpc', 'NZ', 'F68'),
        ('label', 'S7b'), P('S7b'), ('jp', 0x7DB1),
        ('label', 'LB'), '7C', 'FE7C', ('jr', 'Z', 'B7C'), 'FE68', ('jr', 'Z', 'B68'),
        ('label', 'Both'), '79', 'FE6B', P('Both'), ('jp', 0x732A),
        ('label', 'B68'), '79', 'FE6B', ('jp', 'RC68'),
        ('label', 'B7C'), '266E', '79', 'FE6B', P('B7C'), ('jp', 'RC7C'),
        ('label', 'LC'), 'FE7C', ('jr', 'Z', 'C7C'),
        ('label', 'Coth'), '7C', 'FE68', P('Coth'), ('jp', 0x732A),
        ('label', 'C7C'), '266E', 'B7', P('C7C'), ('jp', 'RC7C'),
        ('label', 'LA'), 'FE10', ('jr', 'NZ', 'OLDA'),
        '7C', 'FE68', ('jr', 'Z', 'A68'), 'FE7C', ('jr', 'Z', 'A7C'),
        ('label', 'Aoth'), 'B7', ('jr', None, 'RCOLD'),
        ('label', 'OLDA'), '7A', 'FE0D', P('OLDA'), ('jr', None, 'RCOLD'),
        ('label', 'A68'), P('A68'), ('jp', 'RC68'),
        ('label', 'A7C'), '2670', P('A7C'),
        *router_copy('RC7C', ['267C'], RC_PAD['RC7C']),
        ('label', 'RCOLD'), OLD_ROUTER.hex(),
        *router_copy('RC68', [], RC_PAD['RC68']),
        ('label', 'S7a'), P('S7a'), ('jp', 0x7DB1),
        ('label', 'D68'), P('D68'), ('jp', 'RC68'),
        ('label', 'E68'), P('E68'), ('jp', 'RC68'),
        ('label', 'F68'), P('F68'), ('jp', 'RC68'),
    ]


def private_helper():
    return assemble(PRIVATE_ENTRY, [
        '3EFF', 'EABBDC',          # original Continue store
        'F0BF', 'B7', ('jr', 'Z', 'done'),   # resume scene has a live miniboss?
        '3E11', 'EA4CDF',          # palette-sequencer reload job
        ('label', 'done'), '3E01', 'C9'])[0]


def edits(parent: bytes):
    """(offset, new bytes) for every byte run this stage writes."""
    tree, _ = assemble(TREE_ORG, dispatcher_items())
    if TREE_ORG + len(tree) > TREE_LIMIT:
        raise ValueError('dispatcher overflows its cave')
    out = [(off(ROUTER_BANK, TREE_ORG), tree)]
    out += [(off(ROUTER_BANK, a), bytes((new,))) for a, _, new in CHAIN_EDITS]
    out.append((off(ROUTER_BANK, 0x7A5A), bytes((TREE_ORG & 0xFF, TREE_ORG >> 8))))
    out += [(off(ROUTER_BANK, dst), parent[off(b, a):off(b, a) + 0x100]) for dst, b, a in PAGE_COPIES]
    out += [(off(b, 0x7182), DEATH_NEW) for b in (13, 16)]
    out.append((off(1, 0x4AD4), ACCEPT_NEW))
    out.append((off(PRIVATE_BANK, PRIVATE_ENTRY), private_helper()))
    return out


def build(parent: bytes, *, with_metadata: bool = False):
    if hashlib.sha256(parent).hexdigest() != PARENT:
        raise ValueError('exact release-lock 792319cb parent required')
    if parent[0x147] != 0x1B or parent[0x148] != 0x05:
        raise ValueError('MBC5 1 MiB expected')
    r20 = lambda a, n: parent[off(ROUTER_BANK, a):off(ROUTER_BANK, a) + n]
    checks = [
        (r20(0x732A, len(OLD_ROUTER)), OLD_ROUTER, 'bank20 router'),
        (r20(0x7A59, 3), CHAIN_JP_OLD, 'chain hop'),
        (r20(0x7320, 10), bytes.fromhex('C3807D57F0FF5FAFE0FF'), 'bank20 hop'),
        (r20(0x71E7, 5), TAIL, 'bank20 tail'),
        (parent[off(13, 0x71E3):off(13, 0x71E3) + len(WRITER)], WRITER, 'bank13 writer'),
        (parent[off(16, 0x71E3):off(16, 0x71E3) + len(WRITER)], WRITER, 'bank16 writer'),
        (parent[0x0061:0x0067], MAPPER_SWITCH, 'mapper switch'),
        (parent[0x09BE:0x09C4], MAPPER_TAIL, 'mapper tail'),
        (parent[0x0847:0x0850], BANK_CALL_ABI, 'bank-call ABI'),
        (parent[off(1, 0x4AD4):off(1, 0x4AD9)], ACCEPT_OLD, 'Continue acceptance'),
        (parent[off(13, 0x6800):off(13, 0x6900)], parent[off(16, 0x6800):off(16, 0x6900)], '68 pages'),
    ]
    checks += [(r20(a, 1), bytes((old,)), f'chain {a:04X}') for a, old, _ in CHAIN_EDITS]
    checks += [(parent[off(b, 0x7182):off(b, 0x7189)], DEATH_OLD, f'death service {b}') for b in (13, 16)]
    for actual, expected, label in checks:
        if actual != expected:
            raise ValueError(f'{label} preimage differs')
    free = [(off(ROUTER_BANK, TREE_ORG), TREE_LIMIT - TREE_ORG)]
    free += [(off(ROUTER_BANK, dst), 0x100) for dst, _, _ in PAGE_COPIES]
    free.append((off(PRIVATE_BANK, 0x4000), 0x4000))
    for o, n in free:
        if set(parent[o:o + n]) != {0xFF}:
            raise ValueError(f'cave {o:#x} not free')
    rom = bytearray(parent)
    owned = set()
    for o, data in edits(parent):
        rom[o:o + len(data)] = data
        owned.update(range(o, o + len(data)))
    rom[0x14E:0x150] = ((sum(rom[:0x14E]) + sum(rom[0x150:])) & 0xFFFF).to_bytes(2, 'big')
    changed = {i for i, (x, y) in enumerate(zip(parent, rom)) if x != y}
    if not changed <= owned | {0x14E, 0x14F}:
        raise AssertionError('unowned byte changed')
    result = bytes(rom)
    if with_metadata:
        return result, dict(name=NAME, parent_sha256=PARENT,
                            candidate_sha256=hashlib.sha256(result).hexdigest(),
                            dispatcher=f'20:{TREE_ORG:04X}', changed=len(changed))
    return result


def verify_installed(rom: bytes) -> bool:
    """Exact bytes of this stage in a candidate (static identity, not live)."""
    if len(rom) != 0x100000:
        return False
    try:
        spans = edits(rom)
    except (AssertionError, ValueError):
        return False
    # page copies must equal their live source pages
    spans += [(off(ROUTER_BANK, 0x732A), OLD_ROUTER), (off(ROUTER_BANK, 0x71E7), TAIL),
              (off(13, 0x71E3), WRITER), (off(16, 0x71E3), WRITER), (0x0847, BANK_CALL_ABI)]
    return all(rom[o:o + len(data)] == data for o, data in spans)


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
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
