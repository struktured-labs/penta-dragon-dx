#!/usr/bin/env python3
"""Release lock: Sara is hidden behind black ceiling overhangs again (refs #14),
with a frame timeline cycle-identical to the db09de8d parent.

Root cause (db09de8d)
  Stock Penta Dragon gives Sara's four 8x8 quadrants OBJ-to-BG priority (OAM
  attribute bit 7) whenever the map block under a quadrant is an "overhang"
  block: bank1 $5096 walks the four quadrant pointers DC10..DC17 through the
  block-range test $50DF ([FFA0,FFA1)) and stores one flag per quadrant at
  FFC2..FFC5; the OBJ emitter then calls bank0 $1188, which sets bit 7 for
  slots 0..3 whose flag is non-zero. DX reused FFC4 for its map publisher
  (r353), so r365/r368 reduced $1188 to `RES 7,A / RET` and r381 removed the
  FFC4 stores. Sara therefore never gets BG priority and is drawn over the
  black ceiling overhangs (pre-secret corridor, issue #14 comments).

The attract demo, Stage-7 patrol and boss-speed gates depend on the exact
per-frame cycle profile, so every changed path keeps the parent's cycle count:

1. Bank 1 $5096..$50F8 (quadrant flags). Same prologue/epilogue; each quadrant
   now CALLs a shared range test at $50D7 (the old inline block test, folded)
   and stores the flag to FFC2/FFC3/FFC5 as before plus a private copy
   T[q] at WRAM $C0C0+q (OAM-page tail, never DMA'd: OAM DMA copies $C000..$C09F).
   FFC4 is left to the DX publisher. Each of the three compare outcomes costs
   exactly the parent's M-cycles per quadrant (PUSH AF/POP AF pads).
2. Bank 0 $11A0..$11C2 (dead POP HL/RET + flash helper $11A2, 2 callers):
   one fused flash+priority helper. Flash semantics identical to $11A2; it
   additionally returns A = T[slot] for slots 0..3 (0 otherwise).
3. Emitter call sites, bank 0D/10 $7B42 (also copied to WRAM $DA42):
   `CALL 11A2 / CALL 1188 / AND F8 / OR C` becomes
   `CALL 11A0 / RRCA / AND 80 / OR B / OR C / NOP`. Same 9 bytes; the Z and NZ
   flash paths cost 240/260 T-cycles exactly as in the parent.

Verified: attract demo frames 0-26000 lockstep against db09de8d (scene, RNG,
masked WRAM $C000-$DEFF, HRAM and CRAM identical every frame; fixed-PC cycle
log identical apart from interrupt-entry latency jitter of <=24 cycles with no
drift), Stage-7 patrol seeds, and verify_sara_overhang_priority.py.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

PARENT = 'db09de8d1b4293401f587fcce77689d8c13799eb009f13001487786c3accdcb8'
NAME = 'sara-overhang-priority'
T_BASE = 0xC0C0          # private quadrant-priority table (WRAM bank 0)
HELPER = 0x11A0
HELPER_END = 0x11C3
HELPER_OLD = bytes.fromhex(
    'E1C9E5F57BCB3FCB3FE0DDC6C06F26AB7EA728073D77F1CBE71803F1CBA7E1C9000000')
PRIORITY_STUB = (0x1188, bytes.fromhex('CBBFC9'))   # RES 7,A / RET (kept, now unused)
CALLSITES = (0x37B42, 0x43B42)                       # banks 0D/10 $7B42
CALLSITE_OLD = bytes.fromhex('CDA211CD8811E6F8B1')
CALLSITE_NEW = bytes.fromhex('CDA0110FE680B0B100')
FLAGS = 0x5096           # bank 1 (fixed file offset == address)
FLAGS_END = 0x50F9
FLAGS_PROLOGUE = bytes.fromhex('F5C5D5E5454BCD6C482110DC')
RANGE_TEST = 0x50D7
RANGE_TEST_CODE = bytes.fromhex('2A5F2A57F0A04F1AB9380B47F0A14F78B930033E01C9AFC9')
WRAM_COPY = (0x37B00, 0x5D)  # bank0D $7B00..$7B5C copied to $DA00 at boot


def helper_code() -> bytes:
    code = bytes.fromhex(
        'E5'          # PUSH HL
        'E668'        # AND 68        keep bits 6,5,3 (palette re-ORed by caller)
        '47'          # LD B,A
        '7B0F0F6F'    # LD A,E / RRCA / RRCA / LD L,A    L = $C0|slot
        'E63F'        # AND 3F
        'E0DD'        # LDH [FFDD],A  slot (as $11A2)
        '26AB'        # LD H,AB       flash counter $ABC0+slot (as $11A2)
        '7E' 'A7'     # LD A,[HL] / AND A
        '2804'        # JR Z,+4
        '35'          # DEC [HL]
        'CBE0'        # SET 4,B
        '00'          # NOP
        '7D'          # LD A,L
        'FEC4'        # CP C4         carry for slots 0..3
        '9F'          # SBC A,A       FF / 00
        '26' + f'{T_BASE >> 8:02X}' +  # LD H,C0     T[slot]
        'A6'          # AND [HL]
        'F5F1'        # PUSH AF / POP AF  (pad)
        '23'          # INC HL            (pad; HL restored)
        'E1C9')       # POP HL / RET
    return code + bytes(HELPER_END - HELPER - len(code))


def flags_code() -> bytes:
    call = bytes((0xCD, RANGE_TEST & 0xFF, RANGE_TEST >> 8))
    t = lambda q: bytes((0xEA, (T_BASE + q) & 0xFF, T_BASE >> 8))
    pad = bytes.fromhex('2802F5F1')    # JR Z,+2 / PUSH AF / POP AF
    body = FLAGS_PROLOGUE
    body += call + b'\xE0\xC2' + t(0) + pad
    body += call + b'\xE0\xC3' + t(1) + pad
    body += call + t(2) + b'\x00\x00' + pad          # FFC4 belongs to the DX publisher
    body += call + b'\xE0\xC5' + t(3) + pad
    body += bytes.fromhex('E1D1C1F1C9')
    if FLAGS + len(body) != RANGE_TEST:
        raise AssertionError('quadrant body does not end at the range test')
    body += RANGE_TEST_CODE
    return body + bytes(FLAGS_END - FLAGS - len(body))


def edits(parent: bytes | None = None):
    """(offset, new bytes) for every byte run this stage writes."""
    out = [(HELPER, helper_code()), (FLAGS, flags_code())]
    out += [(o, CALLSITE_NEW) for o in CALLSITES]
    return out


def build(parent: bytes, *, with_metadata: bool = False):
    if hashlib.sha256(parent).hexdigest() != PARENT:
        raise ValueError('exact release-lock db09de8d parent required')
    if parent[0x147] != 0x1B or parent[0x148] != 0x05:
        raise ValueError('MBC5 1 MiB expected')
    checks = [
        (parent[HELPER:HELPER_END], HELPER_OLD, 'flash helper'),
        (parent[PRIORITY_STUB[0]:PRIORITY_STUB[0] + 3], PRIORITY_STUB[1], 'priority stub'),
        (parent[FLAGS:FLAGS + len(FLAGS_PROLOGUE)], FLAGS_PROLOGUE, 'quadrant prologue'),
    ]
    checks += [(parent[o:o + 9], CALLSITE_OLD, f'call site {o:#x}') for o in CALLSITES]
    for actual, expected, label in checks:
        if actual != expected:
            raise ValueError(f'{label} preimage differs')
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
                            changed=len(changed), t_table=f'{T_BASE:04X}')
    return result


def verify_installed(rom: bytes) -> bool:
    """Exact bytes of this stage in a candidate (static identity, not live)."""
    if len(rom) != 0x100000:
        return False
    spans = edits(rom) + [PRIORITY_STUB]
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
