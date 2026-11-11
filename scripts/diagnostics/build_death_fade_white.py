#!/usr/bin/env python3
"""#74: colorized white fade when BGP hits 00 on the gameplay death path.

Root cause. The native death fade-out (``01:4A5C CALL 0F33``) walks BGP
``E4 -> 90 -> 40 -> 00`` (and the Game Over / title-return fades at
``01:4AC8`` and ``01:745A`` do the same). DMG hides the next map/art load
behind BGP=00. CGB ignores BGP, so the previous CRAM stays on screen for
several frames — stale death tiles at the fade, and later Japanese/yellow
fragments on the title-return initialization.

Fix (new construction stage on the menu-open-map-hold parent). Replace those
the gameplay death ``CALL 0F33`` at ``01:4A5C`` with ``CALL 758E``. The 8-byte
unreferenced zero pad at ``01:758E`` (after ``LD A,$3F; CALL 0061`` at ``7589``-
``758D``, which resumes in bank $3F, and before ``JP 0F33`` at ``7598``) runs native
``CALL 0F33`` with bank 1 still mapped (same FF99/DA21 cadence as the
original), then switches to bank ``$30``. ``CALL 0061`` returns at
``7598``, which in bank $30 (erased fill) waits for vblank and writes all
16 CGB palettes to white (``7FFF``) using the #55/#83 ``write`` routine at
``30:41BB``, then restores bank 1 and returns to the original site.

The #55/#83 trampoline at ``00F0`` and the bank-$30 dispatcher at
``30:4008`` are not patched, so stage fade-in / secret-entry timing stays
cycle-identical. ``00:0F33`` and the attract-shared ISR are unchanged.
Attract never calls these bank-1 sites. The death-art capture at scene-17
age 15 still happens before BGP hits 00.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

# Current main / menu-open-map-hold tip (PR #86).
PARENT = '952f9b9f2b3feafb1882282e8ac7e5d0f462a597b79da49e74587469d8f6888a'
CANDIDATE = '23aa5f44f604d120877169f7dfa32186c3b089afbbadae4618b5cd06e7cb7d6c'

# Bank-1 gameplay-only CALL 0F33 sites (file offset == CPU address in bank 1).
SITE_DEATH = 0x4A5C
SITE_GAMEOVER_EXIT = 0x4AC8
SITE_TITLE_RETURN = 0x745A
SITES = (SITE_DEATH,)
CALL_FADE = bytes.fromhex('CD330F')
STUB = 0x758E
STUB_LEN = 8
STUB_PRE = bytes(8)
# CALL 0F33; LD A,$30; CALL 0061
# After 0061 the next fetch is 7596 in bank $30 (two leftover zeros, then 7598 arm).
# Do not use 758D: that byte is the 00 of LD A,$3F; CALL 0061 at 7589.
STUB_NEW = bytes.fromhex('CD330F3E30CD6100')

BANK = 0x30
WRITE = 0x41BB
WRITE_PRE = bytes.fromhex('F040CB7F2849F3F041E603FE01')
# CALL 0061 from 01:758E resumes at 7596 in the switched bank; arm starts at 7598.
ARM = 0x7598


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def update_checksums(rom: bytearray) -> None:
    header = 0
    for value in rom[0x0134:0x014D]:
        header = (header - value - 1) & 0xFF
    rom[0x014D] = header
    rom[0x014E:0x0150] = ((sum(rom[:0x014E]) + sum(rom[0x0150:])) & 0xFFFF).to_bytes(2, 'big')


class Asm:
    def __init__(self, org):
        self.org, self.b, self.labels, self.fix = org, bytearray(), {}, []

    def db(self, *v):
        self.b.extend(v)

    def label(self, name):
        self.labels[name] = self.org + len(self.b)

    def jr(self, op, name):
        self.b.extend((op, 0)); self.fix.append(('jr', len(self.b) - 1, name))

    def abs16(self, op, name):
        self.b.extend((op, 0, 0)); self.fix.append(('abs', len(self.b) - 2, name))

    def ld16(self, op, name):
        self.abs16(op, name)

    def finish(self):
        for kind, at, name in self.fix:
            target = self.labels[name] if isinstance(name, str) else name
            if kind == 'jr':
                rel = target - (self.org + at + 1)
                assert -128 <= rel <= 127, name
                self.b[at] = rel & 0xFF
            else:
                self.b[at:at + 2] = target.to_bytes(2, 'little')
        return bytes(self.b)


def arm() -> bytes:
    a = Asm(ARM)
    a.db(0xF0, 0x40, 0xCB, 0x7F)           # LCD off -> skip DI
    a.jr(0x28, 'white_write')
    a.db(0xF3)                             # DI: ISR must not interrupt the writes
    # STAT-safe byte loop (mode 0 or 1 only). 41BB's vblank burst and
    # a 4-byte post-check group can both spill into LY=0 mode 3.
    a.label('white_write')
    a.db(0x3E, 0x80, 0xE0, 0x68)
    a.ld16(0x21, 'white')
    a.db(0x0E, 0x69, 0x06, 0x40)           # B = 64 BG bytes
    a.abs16(0xCD, 'safe_write')
    a.db(0x3E, 0x80, 0xE0, 0x6A)
    a.ld16(0x21, 'white')
    a.db(0x0E, 0x6B, 0x06, 0x40)           # B = 64 OBJ bytes
    a.abs16(0xCD, 'safe_write')
    a.db(0xFB, 0x3E, 0x01, 0xC3, 0x61, 0x00)  # EI; LD A,$01; JP 0061 -> bank 1
    a.label('safe_write')
    a.label('safe_wait')
    a.db(0xF0, 0x41, 0xE6, 0x03)
    a.jr(0x28, 'safe_ok')                  # mode 0 hblank
    a.db(0xFE, 0x01)
    a.jr(0x20, 'safe_wait')                # wait out mode 2/3
    a.label('safe_ok')
    a.db(0x2A, 0xE2)
    a.db(0x05)
    a.jr(0x20, 'safe_wait')
    a.db(0xC9)
    a.label('white')
    a.db(*b'\xff\x7f' * 32)
    return a.finish()

def bank1_offset(cpu: int) -> int:
    return cpu  # bank 1 file offset == CPU address


def bank30_offset(cpu: int) -> int:
    return BANK * 0x4000 + (cpu - 0x4000)


def build(parent: bytes, original: bytes | None = None) -> bytes:
    if sha(parent) != PARENT:
        raise ValueError('exact menu-open-map-hold parent required')
    for site in SITES:
        if parent[site:site + 3] != CALL_FADE:
            raise ValueError(f'CALL 0F33 preimage differs at {site:04X}')
    if parent[STUB:STUB + STUB_LEN] != STUB_PRE:
        raise ValueError('bank-1 stub pad at 758E is not free')
    if parent[0x7589:0x758E] != bytes.fromhex('3E3FCD6100'):
        raise ValueError('01:7589 LD A,$3F; CALL 0061 preimage differs')
    if len(STUB_NEW) != STUB_LEN:
        raise ValueError('bank-1 stub length drift')
    write_off = bank30_offset(WRITE)
    if parent[write_off:write_off + len(WRITE_PRE)] != WRITE_PRE:
        raise ValueError('bank $30 write routine preimage differs')
    arm_off = bank30_offset(ARM)
    code = arm()
    if parent[arm_off:arm_off + len(code)] != b'\xff' * len(code):
        raise ValueError('bank $30 resume tail at 7598 is not free')
    result = bytearray(parent)
    for site in SITES:
        result[site:site + 3] = bytes([0xCD, STUB & 0xFF, STUB >> 8])
    result[STUB:STUB + STUB_LEN] = STUB_NEW
    result[arm_off:arm_off + len(code)] = code
    update_checksums(result)
    out = bytes(result)
    if CANDIDATE is not None and sha(out) != CANDIDATE:
        raise ValueError(f'candidate identity drift: {sha(out)}')
    return out


def changed_spans(_original: bytes | None = None) -> list[tuple[int, int]]:
    arm_off = bank30_offset(ARM)
    spans = [(site, site + 3) for site in SITES]
    spans.append((STUB, STUB + STUB_LEN))
    spans.append((arm_off, arm_off + len(arm())))
    spans.append((0x014D, 0x0150))
    return spans


def reconstruct_parent(rom: bytes, original: bytes | None = None) -> bytes:
    if CANDIDATE is not None and sha(rom) != CANDIDATE:
        raise ValueError('not the exact death-fade-white candidate')
    parent = bytearray(rom)
    call_stub = bytes([0xCD, STUB & 0xFF, STUB >> 8])
    for site in SITES:
        if rom[site:site + 3] != call_stub:
            raise ValueError(f'death-fade-white site {site:04X} differs')
        parent[site:site + 3] = CALL_FADE
    if rom[STUB:STUB + STUB_LEN] != STUB_NEW:
        raise ValueError('death-fade-white stub differs')
    parent[STUB:STUB + STUB_LEN] = STUB_PRE
    arm_off = bank30_offset(ARM)
    code = arm()
    parent[arm_off:arm_off + len(code)] = b'\xff' * len(code)
    update_checksums(parent)
    out = bytes(parent)
    if sha(out) != PARENT or build(out, original) != rom:
        raise ValueError('death-fade-white parent reconstruction failed')
    return out


def verify_installed(rom: bytes, original: bytes | None = None) -> list[str]:
    failures = []
    call_stub = bytes([0xCD, STUB & 0xFF, STUB >> 8])
    for site in SITES:
        if rom[site:site + 3] != call_stub:
            failures.append(f'site {site:04X} does not call the 758E stub')
    if rom[STUB:STUB + STUB_LEN] != STUB_NEW:
        failures.append('bank-1 758E stub differs')
    if rom[0x7589:0x758E] != bytes.fromhex('3E3FCD6100'):
        failures.append('01:7589 CALL 0061 was overwritten')
    code = arm()
    arm_off = bank30_offset(ARM)
    if rom[arm_off:arm_off + len(code)] != code:
        failures.append('bank $30 death-fade arm differs')
    return failures


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('parent', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists() or (ROOT / 'tmp').resolve() not in args.output.resolve().parents:
        parser.error('fresh repository-local tmp output required')
    result = build(args.parent.read_bytes())
    args.output.mkdir(parents=True)
    (args.output / 'candidate.gb').write_bytes(result)
    receipt = dict(issue=74, parent_sha256=PARENT, candidate_sha256=sha(result),
                   builder_sha256=sha(Path(__file__).read_bytes()),
                   static_failures=verify_installed(result),
                   sites=[hex(site) for site in SITES], stub=hex(STUB), arm=hex(ARM))
    (args.output / 'receipt.json').write_text(json.dumps(receipt, indent=2) + '\n')
    print(json.dumps(receipt, indent=2))
