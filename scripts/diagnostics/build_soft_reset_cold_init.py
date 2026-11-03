#!/usr/bin/env python3
"""Post-ending soft reset: rearm the DX cold-boot init (opening-story freeze).

After the ending the native script reaches ``01:5553 CALL 428F`` then
``01:5556 JP 0150`` (the only soft-reset site; stock ``JP 0150`` too). Boot
``0150 -> 01:4000`` clears C000-DEFF, FF80-FFFC and the 9800 map, but not
DF00-DFFF. DX keeps its cold-boot guards there (``DF02 = 5A`` checked at
``13:6E00``; ``DF08 = 5A`` gates the cold VRAM/attribute init at ``13:6E2D``),
so after the reset the cold init is skipped, the WRAM runtime at DBC0-DBFC is
never reinstalled, and ``CALL $DBF3`` (``01:42F5``) runs through zeroed WRAM
into an RST 38 / runaway-stack hang on the opening story.

Stock uses DF00-DFFF only as the stack (``LD SP,DFFF`` at 0155, before any
pop), so nothing there must survive a reset; DX bank-1 DF bytes are all
cold-boot state that a power-on starts from zero.

Single deterministic pass, no markers:

1. ``01:5556 JP 0150`` -> ``JP 00E2`` (JP nn is 16 T-cycles for any target;
   ``CALL 428F`` at 5553 and its return address 5556 are unchanged, so the
   428F caller dispatch is unchanged).
2. Fixed-bank ``00E2``: ``DI; LD HL,DF00; LD B,F0; XOR A; loop LD (HL+),A;
   DEC B; JR NZ; JP 0150`` -- clears DF00-DFEF (DFF0-DFFF is left to the
   boot's own ``LD SP,DFFF``) and enters the unchanged boot. ``00E2-00EF`` is
   inside the unreferenced stock fill ``00CF-00FF`` already used by #54 for
   ``00D0-00E1``. Power-on, attract and gameplay never execute either site.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

PARENT = '050209058633e2723a25c4ad60f92e0a3d54d51dbdd27d449b23069d98323ed4'
ORIGINAL = '2f32570cff62b8664bfa06b939988c3fd6a7efabf870a990a5fa65bab37eac30'

RESET_SITE = 0x5556                       # bank 1, file offset == address
RESET_PREFIX = bytes.fromhex('CD8F42')    # CALL 428F at 01:5553
STUB_AT = 0x00E2
STUB = bytes.fromhex('F32100DF06F0AF220520FCC35001')
FILL_START, FILL_END = 0x00E2, 0x0100     # unclaimed remainder of 00CF-00FF


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def jp(address: int) -> bytes:
    return bytes((0xC3, address & 0xFF, address >> 8))


def checksum(rom: bytearray) -> None:
    rom[0x14E:0x150] = ((sum(rom[:0x14E]) + sum(rom[0x150:])) & 0xFFFF).to_bytes(2, 'big')


def build(parent: bytes, original: bytes) -> bytes:
    if sha(parent) != PARENT:
        raise ValueError('exact native-stage-records parent required')
    if sha(original) != ORIGINAL:
        raise ValueError('exact original cartridge required')
    if parent[RESET_SITE:RESET_SITE + 3] != jp(0x0150) or original[RESET_SITE:RESET_SITE + 3] != jp(0x0150):
        raise ValueError('soft-reset JP 0150 preimage differs')
    if parent[RESET_SITE - 3:RESET_SITE] != RESET_PREFIX:
        raise ValueError('CALL 428F preimage differs')
    if parent[FILL_START:FILL_END] != original[FILL_START:FILL_END]:
        raise ValueError('bank-0 fill 00E2-00FF is no longer stock')
    result = bytearray(parent)
    result[STUB_AT:STUB_AT + len(STUB)] = STUB
    result[RESET_SITE:RESET_SITE + 3] = jp(STUB_AT)
    checksum(result)
    return bytes(result)


def changed_spans(original: bytes) -> list[tuple[int, int]]:
    return [(STUB_AT, STUB_AT + len(STUB)), (RESET_SITE + 1, RESET_SITE + 3)]


def reconstruct_parent(rom: bytes, original: bytes) -> bytes:
    parent = bytearray(rom)
    parent[STUB_AT:STUB_AT + len(STUB)] = original[STUB_AT:STUB_AT + len(STUB)]
    parent[RESET_SITE:RESET_SITE + 3] = jp(0x0150)
    checksum(parent)
    parent = bytes(parent)
    if sha(parent) != PARENT or build(parent, original) != rom:
        raise ValueError('soft-reset cold-init reconstruction failed')
    return parent


def verify_installed(rom: bytes, original: bytes) -> list[str]:
    failures = []
    if rom[STUB_AT:STUB_AT + len(STUB)] != STUB:
        failures.append('soft-reset DF clear stub missing')
    if rom[RESET_SITE:RESET_SITE + 3] != jp(STUB_AT):
        failures.append('soft-reset site does not enter the DF clear stub')
    if rom[STUB_AT + len(STUB):FILL_END] != original[STUB_AT + len(STUB):FILL_END]:
        failures.append('bank-0 fill after the stub is no longer stock')
    return failures


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('parent', type=Path)
    parser.add_argument('--original', type=Path, default=ROOT / 'rom/Penta Dragon (J).gb')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists() or (ROOT / 'tmp').resolve() not in args.output.resolve().parents:
        parser.error('fresh repository-local tmp output required')
    original = args.original.read_bytes()
    result = build(args.parent.read_bytes(), original)
    args.output.mkdir(parents=True)
    (args.output / 'candidate.gb').write_bytes(result)
    receipt = dict(parent_sha256=PARENT, original_sha256=ORIGINAL, candidate_sha256=sha(result),
                   builder_sha256=sha(Path(__file__).read_bytes()),
                   static_failures=verify_installed(result, original))
    (args.output / 'receipt.json').write_text(json.dumps(receipt, indent=2) + '\n')
    print(json.dumps(receipt))
