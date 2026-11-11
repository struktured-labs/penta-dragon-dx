#!/usr/bin/env python3
"""#73: reinstall the static pause-menu frame before 1F60 fills the deck.

Root cause. The pause-menu publisher (``00:1F60``) only writes the dynamic
title, items and HP into WRAM ``C4E0``; it assumes the 120-byte static chrome
from ``00:212E`` is already sitting there. Stage 1 leaves that template in
``C4E0``. The Ted arena reuses ``C4E0`` as battle scratch, so Select publishes
the leftover bytes through ``00:200E`` / ``14:4017`` and the window shows
scrambled tiles. This is #36-class workspace reuse, not a missing ``4295``
map publish and not #34 (no Select buffer). ``FFC4`` is already 0 and the
attract-shared ISR at ``0D:7459`` never runs.

Fix (new construction stage on the death-fade-white parent). Replace the
first 15 bytes of ``00:1F60`` with a ``00F0``-style far-call trampoline:
save ``FF99``, map bank ``$14``, ``CALL 14:5CE2``, restore the previous bank
and return. The body at the ``14:5CE2`` FF cave memcpy's ``00:212E`` to
``C4E0`` (120 bytes via the existing ``00:09B3``) and then runs the original
``1F60`` body (relocated as a blob; it has no intra-function absolute
branches). Call sites at ``1B45`` / ``1D75`` / ``1EBA`` / ``01:77ED`` are
unchanged. Attract never calls ``1F60``, so the extra memcpy and bank switch
stay off attract paths. ``00F0``, ``00:0F33``, ``0D:7459`` and the #81
``14:7F32`` hook are not patched.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

# Current main / death-fade-white tip (PR #87).
PARENT = '23aa5f44f604d120877169f7dfa32186c3b089afbbadae4618b5cd06e7cb7d6c'
CANDIDATE = '01f8e0b22719a438c9c28f16c09c5bde8ae06f3f8561ffe0c88c08ba02b39d20'

ENTRY = 0x1F60
ORIG_END = 0x200E  # exclusive; includes the 200A-200D HP-zero tail
BANK = 0x14
BODY_CPU = 0x5CE2
MEMCPY = bytes.fromhex('212E2111E0C4017800CDB309')  # HL=212E, DE=C4E0, BC=120, CALL 09B3
TRAMPOLINE_HEAD = bytes.fromhex('F099F53E14CD6100')  # LDH A,(FF99); PUSH AF; LD A,$14; CALL 0061
TRAMPOLINE_TAIL = bytes.fromhex('F1C36100')          # POP AF; JP 0061
TRAMPOLINE_LEN = 15
BODY_LEN = len(MEMCPY) + (ORIG_END - ENTRY)  # 186

# Untouched attract / earlier-fix markers.
F0_PRE = bytes.fromhex('F099F53E30CD6100CD0040F1C36100')
HOOK81 = 0x14 * 0x4000 + (0x7F32 - 0x4000)
HOOK81_PRE = bytes.fromhex('AFE0C4C9')
FADE_STUB = 0x758E
FADE_STUB_PRE = bytes.fromhex('CD330F3E30CD6100')
ISR_7459 = 0x0D * 0x4000 + (0x7459 - 0x4000)


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def update_checksums(rom: bytearray) -> None:
    header = 0
    for value in rom[0x0134:0x014D]:
        header = (header - value - 1) & 0xFF
    rom[0x014D] = header
    rom[0x014E:0x0150] = ((sum(rom[:0x014E]) + sum(rom[0x0150:])) & 0xFFFF).to_bytes(2, 'big')


def body_offset() -> int:
    return BANK * 0x4000 + (BODY_CPU - 0x4000)


def trampoline() -> bytes:
    code = TRAMPOLINE_HEAD + bytes([0xCD, BODY_CPU & 0xFF, BODY_CPU >> 8]) + TRAMPOLINE_TAIL
    if len(code) != TRAMPOLINE_LEN:
        raise ValueError('menu-frame trampoline length drift')
    return code


def body(parent: bytes) -> bytes:
    original = parent[ENTRY:ORIG_END]
    if len(original) != ORIG_END - ENTRY or original[0x2009 - ENTRY] != 0xC9:
        raise ValueError('00:1F60 body preimage differs')
    return MEMCPY + original


def changed_spans(_original: bytes | None = None) -> list[tuple[int, int]]:
    off = body_offset()
    return [
        (ENTRY, ENTRY + TRAMPOLINE_LEN),
        (off, off + BODY_LEN),
        (0x014D, 0x0150),
    ]


def build(parent: bytes, original: bytes | None = None) -> bytes:
    if sha(parent) != PARENT:
        raise ValueError('exact death-fade-white parent required')
    code = body(parent)
    if len(code) != BODY_LEN:
        raise ValueError('menu-frame body length drift')
    off = body_offset()
    if parent[off:off + BODY_LEN] != b'\xff' * BODY_LEN:
        raise ValueError('bank $14 cave at 5CE2 is not free')
    if parent[0x00F0:0x00FF] != F0_PRE:
        raise ValueError('00F0 trampoline preimage differs')
    if parent[HOOK81:HOOK81 + len(HOOK81_PRE)] != HOOK81_PRE:
        raise ValueError('14:7F32 menu-hold hook preimage differs')
    if parent[FADE_STUB:FADE_STUB + len(FADE_STUB_PRE)] != FADE_STUB_PRE:
        raise ValueError('01:758E death-fade stub preimage differs')
    result = bytearray(parent)
    result[off:off + BODY_LEN] = code
    result[ENTRY:ENTRY + TRAMPOLINE_LEN] = trampoline()
    update_checksums(result)
    out = bytes(result)
    if CANDIDATE is not None and sha(out) != CANDIDATE:
        raise ValueError(f'candidate identity drift: {sha(out)}')
    return out


def reconstruct_parent(rom: bytes, original: bytes | None = None) -> bytes:
    if CANDIDATE is not None and sha(rom) != CANDIDATE:
        raise ValueError('not the exact menu-frame-reinstall candidate')
    if rom[ENTRY:ENTRY + TRAMPOLINE_LEN] != trampoline():
        raise ValueError('menu-frame trampoline differs')
    off = body_offset()
    # Recover the original 1F60 body from the bank-14 copy (after the memcpy prefix).
    original_body = rom[off + len(MEMCPY):off + BODY_LEN]
    if len(original_body) != ORIG_END - ENTRY:
        raise ValueError('menu-frame body length differs')
    parent = bytearray(rom)
    parent[ENTRY:ORIG_END] = original_body
    parent[off:off + BODY_LEN] = b'\xff' * BODY_LEN
    update_checksums(parent)
    out = bytes(parent)
    if sha(out) != PARENT or build(out, original) != rom:
        raise ValueError('menu-frame-reinstall parent reconstruction failed')
    return out


def verify_installed(rom: bytes, original: bytes | None = None) -> list[str]:
    errors = []
    if sha(rom) != CANDIDATE:
        errors.append('candidate sha256 differs')
    if rom[ENTRY:ENTRY + TRAMPOLINE_LEN] != trampoline():
        errors.append('00:1F60 trampoline differs')
    off = body_offset()
    expected_body = MEMCPY + rom[off + len(MEMCPY):off + BODY_LEN]
    if rom[off:off + BODY_LEN] != expected_body or rom[off:off + len(MEMCPY)] != MEMCPY:
        errors.append('14:5CE2 memcpy+1F60 body differs')
    if rom[off + len(MEMCPY) + (0x2009 - ENTRY)] != 0xC9:
        errors.append('relocated 1F60 RET is missing')
    if rom[0x00F0:0x00FF] != F0_PRE:
        errors.append('00F0 trampoline was patched')
    if rom[HOOK81:HOOK81 + len(HOOK81_PRE)] != HOOK81_PRE:
        errors.append('14:7F32 menu-hold hook was patched')
    if rom[FADE_STUB:FADE_STUB + len(FADE_STUB_PRE)] != FADE_STUB_PRE:
        errors.append('01:758E death-fade stub was patched')
    return errors


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
    receipt = dict(issue=73, parent_sha256=PARENT, candidate_sha256=sha(result),
                   builder_sha256=sha(Path(__file__).read_bytes()),
                   static_failures=verify_installed(result),
                   entry=hex(ENTRY), body=hex(BODY_CPU), body_len=BODY_LEN)
    (args.output / 'receipt.json').write_text(json.dumps(receipt, indent=2) + '\n')
    print(json.dumps(receipt, indent=2))
