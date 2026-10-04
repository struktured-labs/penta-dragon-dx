#!/usr/bin/env python3
"""Release lock: reload BG palettes after Continue into a miniboss, and make the
CRAM source writer immune to mode-3 drops.

1. Continue during a miniboss fight (refs #28 follow-up).
   A death in a miniboss fight followed by Continue resumes straight into scene
   D880=$0A with the miniboss alive. The deferred BG reload request $DF5D is
   raised only by the scene-02 entry hook (bank13 $7D18 -> $7719). The VBlank
   commit gate ($7703) consumes it only while D880==$02. So the death/white-fade
   CRAM (FFFF/FFFF/7E1F/294A in every BG palette) survives until the miniboss
   dies and the room and HUD render flat pink.
   - $7703 gate: accept D880 AND $F7 == $02 (scenes $02 and $0A). Same 22
     bytes. The palette sequencer's BG writer ($71B6) already folds $0A onto
     $02 the same way.
   - $7D18: the scene-02 path jumps straight to its continuation $7D26.
   - $7D35: the common hook tail CALL $6D9E -> CALL $7719.
   - $7719 cave: PUSH AF; LD A,$27; CALL $0847; POP AF; JP $6D9E (the old
     7-byte setter plus its 3 free bytes).
   - bank $27:$6C80 (entered through the existing $0847 bank-call ABI): raise
     $DF5D:=1 when D880==$02 (old behaviour), or when D880==$0A and the
     previous observed scene $DF0D==$17 (Continue out of the death sequence).
     Miniboss spawn ($02->$0A) and kill ($0A->$02) keep their exact old
     behaviour.

2. Mode-3-proof CRAM source writer (stale pal4 colour-3 / #28 "4A29" byte).
   The bank-20 router ($732A) waits for a fresh HBlank and then reaches the
   bank-13 writer ($71E3) through the fixed mapper switch ($0061/$09BE). That
   costs 38 M-cycles before the first of four writes. On lines with a long mode
   3 (sprite-heavy miniboss lines) the 4th write lands in the next line's mode 3
   and the PPU drops it. The router now publishes the bank-13 mapper state
   ($DC09, $FF99) and saves HL before the wait; IE is already 0 here, so no
   interrupt can observe the early bookkeeping. After the edge it writes $2100
   directly from bank-20 $71E0, so execution falls through into bank-13 $71E3.
   Worst case the 4th write now lands 32 M-cycles (128 dots) after HBlank
   begins, inside the minimum 167-dot mode-0 + mode-2 window. Same wait
   condition, same VBlank/LCD-off fast paths, same stack/IE/DE contract. The
   writer itself is unchanged. Each burst ends ~30 M-cycles earlier, still on
   the same scan line.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

PARENT = '792319cbe9db7d56ae6497018b727c8a0a8737c3c8c7a4a122713054677022db'
NAME = 'continue-miniboss-reload'
PRIVATE_BANK = 0x27
PRIVATE_ENTRY = 0x6C80
ROUTER_BANK = 20
ROUTER_ENTRY = 0x732A
SWITCH = 0x71DE            # bank 20: PUSH-free switch tail ends at $71E2
WRITER = 0x71E3            # bank 13 source writer (unchanged)

GATE_OLD = bytes.fromhex('FA80D8 FE02 C22D74 FA5DDF 3D C22D74 AF EA5DDF C30F74')
GATE_NEW = bytes.fromhex(
    'FA5DDF'    # 7703 LD A,[DF5D]
    '3D'        # 7706 DEC A
    'C22D74'    # 7707 JP NZ,742D      (no request)
    'FA80D8'    # 770A LD A,[D880]
    'E6F7'      # 770D AND F7          ($02 and $0A)
    'D602'      # 770F SUB 02          (A=0 on match)
    '20F4'      # 7711 JR NZ,7707      (Z clear -> JP NZ,742D)
    'EA5DDF'    # 7713 LD [DF5D],A     (consume: A=0)
    'C30F74')   # 7716 JP 740F
SETTER_OLD = bytes.fromhex('3C EA5DDF C3267D 000000')
CAVE_NEW = bytes.fromhex('F5 3E27 CD4708 F1 C39E6D')
HOOK02_OLD = bytes.fromhex('C31977 0000')
HOOK02_NEW = bytes.fromhex('C3267D 0000')
TAIL_OLD = bytes.fromhex('CD9E6D')
TAIL_NEW = bytes.fromhex('CD1977')
TAIL_CALLEE = bytes.fromhex('AF EA49DF EA4BDF C9')
BANK_CALL_ABI = bytes.fromhex('CD6100 CD806C C36100')
PRIVATE = bytes.fromhex(
    'FA80D8'    # LD A,[D880]
    'FE02'      # CP 02
    '280B'      # JR Z,set
    'FE0A'      # CP 0A
    '200C'      # JR NZ,done
    'FA0DDF'    # LD A,[DF0D]   previous observed scene
    'FE17'      # CP 17
    '2005'      # JR NZ,done
    '3E01'      # set: LD A,1
    'EA5DDF'    # LD [DF5D],A
    '3E0D'      # done: LD A,0D  (bank for $0847's JP $0061)
    'C9')

# bank 20 router entry ($732A) and its retired wait/switch sequence
ROUTER_OLD = bytes.fromhex(
    'F040 CB7F 2820 F041 E603 FE01 200A F044 FE90 3804 FE98 380E'
    'F041 E603 FE03 20F8 F041 E603 20FA 7A E5 21E371 E5 C36100')
WRITER_OLD = bytes.fromhex('E1 2AE2 2AE2 2AE2 2AE2 7B D1 E0FF C9')
MAPPER_SWITCH = bytes.fromhex('EA09DC C3BE09')            # $0061
MAPPER_TAIL = bytes.fromhex('E099 EA0021 C9')              # $09BE


def assemble_router():
    """Bank-20 router placed so that its LD [$2100],A ends at $71E2."""
    S, E = 'switch', 'edge'
    parts = [
        '7A',            # LD A,D            source bank (13)
        'EA09DC',        # LD [DC09],A       mapper shadow, as $0061 would
        'E099',          # LDH [FF99],A      ISR bank-restore byte, as $09BE would
        'E5',            # PUSH HL           operand for the writer's POP HL
        'F040', 'CB7F',  # LCDC.7
        ('28', S),       # JR Z,switch       LCD off: write now
        'F041', 'E603', 'FE01',
        ('20', E),       # JR NZ,edge        not VBlank
        'F044', 'FE90',
        ('38', E),       # JR C,edge         (parity with the old router)
        'FE98',
        ('38', S),       # JR C,switch       VBlank LY $90..$97: write now
        E,
        'F041', 'E603', 'FE03', '20F8',   # acquire mode 3
        'F041', 'E603', '20FA',           # then a fresh mode 0
        S,
        '7A', 'EA0021',  # LD A,D ; LD [2100],A -> falls into bank13 $71E3
    ]
    size = sum(2 if isinstance(x, tuple) else (0 if x in (S, E) else len(x) // 2) for x in parts)
    start = WRITER - size
    labels, pc = {}, start
    for x in parts:
        if isinstance(x, tuple):
            pc += 2
        elif x in (S, E):
            labels[x] = pc
        else:
            pc += len(x) // 2
    code, pc = bytearray(), start
    for x in parts:
        if isinstance(x, tuple):
            rel = labels[x[1]] - (pc + 2)
            assert -128 <= rel <= 127
            code += bytes((int(x[0], 16), rel & 0xFF)); pc += 2
        elif x not in (S, E):
            code += bytes.fromhex(x); pc += len(x) // 2
    assert start + len(code) == WRITER
    return start, bytes(code)


def off(bank, addr):
    return bank * 0x4000 + addr - 0x4000


def build(parent: bytes, *, with_metadata: bool = False):
    if hashlib.sha256(parent).hexdigest() != PARENT:
        raise ValueError('exact release-lock 792319cb parent required')
    if parent[0x147] != 0x1B or parent[0x148] != 0x05:
        raise ValueError('MBC5 1 MiB expected')
    b13 = lambda a, n: parent[off(13, a):off(13, a) + n]
    checks = (
        (b13(0x7703, 22), GATE_OLD, 'gate'),
        (b13(0x7719, 10), SETTER_OLD, 'setter/cave'),
        (b13(0x7D18, 5), HOOK02_OLD, 'scene-02 hook'),
        (b13(0x7D35, 3), TAIL_OLD, 'hook tail'),
        (b13(0x6D9E, 8), TAIL_CALLEE, 'tail callee'),
        (b13(WRITER, len(WRITER_OLD)), WRITER_OLD, 'bank13 source writer'),
        (parent[0x0847:0x0850], BANK_CALL_ABI, 'bank-call ABI'),
        (parent[0x0061:0x0067], MAPPER_SWITCH, 'mapper switch'),
        (parent[0x09BE:0x09C4], MAPPER_TAIL, 'mapper tail'),
        (parent[off(ROUTER_BANK, ROUTER_ENTRY):off(ROUTER_BANK, ROUTER_ENTRY) + len(ROUTER_OLD)],
         ROUTER_OLD, 'bank20 router'),
    )
    for actual, expected, label in checks:
        if actual != expected:
            raise ValueError(f'{label} preimage differs')
    start, router = assemble_router()
    if set(parent[off(ROUTER_BANK, start):off(ROUTER_BANK, WRITER)]) != {0xFF}:
        raise ValueError('bank20 router cave is not free')
    # bank 20 $71E3.. must stay the bank-20 forward entry (JP $7A2A) untouched
    if parent[off(ROUTER_BANK, WRITER):off(ROUTER_BANK, WRITER) + 3] != bytes.fromhex('C32A7A'):
        raise ValueError('bank20 forward entry differs')
    if set(parent[off(PRIVATE_BANK, 0x4000):off(PRIVATE_BANK, 0x8000)]) != {0xFF}:
        raise ValueError('private bank not free')
    for i in range(len(parent) - 2):
        if parent[i] in (0xEA, 0xFA) and parent[i + 1] == 0x5D and parent[i + 2] == 0xDF:
            if not off(13, 0x7703) <= i < off(13, 0x7723):
                raise ValueError(f'unexpected $DF5D reference at {i:#x}')
    rom = bytearray(parent)
    owned = set()

    def put(o, data):
        rom[o:o + len(data)] = data
        owned.update(range(o, o + len(data)))

    put(off(13, 0x7703), GATE_NEW)
    put(off(13, 0x7719), CAVE_NEW)
    put(off(13, 0x7D18), HOOK02_NEW)
    put(off(13, 0x7D35), TAIL_NEW)
    put(off(PRIVATE_BANK, PRIVATE_ENTRY), PRIVATE)
    put(off(ROUTER_BANK, start), router)
    put(off(ROUTER_BANK, ROUTER_ENTRY), bytes((0xC3, start & 0xFF, start >> 8)))
    rom[0x14E:0x150] = ((sum(rom[:0x14E]) + sum(rom[0x150:])) & 0xFFFF).to_bytes(2, 'big')
    changed = {i for i, (x, y) in enumerate(zip(parent, rom)) if x != y}
    if not changed <= owned | {0x14E, 0x14F}:
        raise AssertionError('unowned byte changed')
    result = bytes(rom)
    if with_metadata:
        return result, dict(name=NAME, parent_sha256=PARENT,
                            candidate_sha256=hashlib.sha256(result).hexdigest(),
                            router_cave=f'20:{start:04X}', changed=len(changed))
    return result


def verify_installed(rom: bytes) -> bool:
    """Exact bytes of this stage in a candidate (static identity, not live)."""
    if len(rom) != 0x100000:
        return False
    start, router = assemble_router()
    spans = (
        (off(13, 0x7703), GATE_NEW), (off(13, 0x7719), CAVE_NEW),
        (off(13, 0x7D18), HOOK02_NEW), (off(13, 0x7D35), TAIL_NEW),
        (off(13, WRITER), WRITER_OLD),
        (off(PRIVATE_BANK, PRIVATE_ENTRY), PRIVATE),
        (off(ROUTER_BANK, start), router),
        (off(ROUTER_BANK, ROUTER_ENTRY), bytes((0xC3, start & 0xFF, start >> 8))),
        (off(ROUTER_BANK, WRITER), bytes.fromhex('C32A7A')),
        (0x0847, BANK_CALL_ABI),
    )
    return all(rom[o:o + len(data)] == data for o, data in spans)


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
