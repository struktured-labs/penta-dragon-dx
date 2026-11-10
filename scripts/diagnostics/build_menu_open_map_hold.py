#!/usr/bin/env python3
"""#81: hold packed-map commits while the Select menu owns the window.

Root cause. The menu publisher writes the inventory to the current window map
and then ``14:7F00`` sets LCDC.5 in VBlank. Two frames after a room-id change
a pending packed-map commit in the attract-shared VBlank ISR (``0D:7459``,
``xor $48``) still runs later in the same VBlank, swaps LCDC.3/.6, and leaves
the menu tiles on the new BG map. The menu is then published again to the new
window map — a persistent double HUD.

Fix. After the gameplay-only window-enable hook sets LCDC.5, clear ``FFC4``
so the ISR pretest (``FFC4 & $60 == 0``) skips that commit while the menu is
up. Attract never calls this hook; the ISR itself is unchanged. Menu close
uses ``RES 5`` (AB -> 8B), leaving the room on the displayed BG; later
commits resume normally. Mid-room Select is unchanged. This is not #34 (no
Select buffer).

#82 (room-entry black on the 3->1 shaft) is the settled room geometry, not
this mid-menu flip, and is not changed here.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

# Current main / transition-palette-blanking tip (PR #84).
PARENT = '91d58599d3df5dde80131ce20d0a639d7056d015dc91cedd2e699b66a141ba18'
CANDIDATE = '952f9b9f2b3feafb1882282e8ac7e5d0f462a597b79da49e74587469d8f6888a'

# 14:7F32 — RET after SET 5 / LDH [LCDC],A in the menu window-enable hook.
SITE = 0x14 * 0x4000 + (0x7F32 - 0x4000)
PRE = bytes.fromhex('C9FFFFFF')
NEW = bytes.fromhex('AFE0C4C9')  # XOR A / LDH [FFC4],A / RET


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def update_checksums(rom: bytearray) -> None:
    header = 0
    for value in rom[0x0134:0x014D]:
        header = (header - value - 1) & 0xFF
    rom[0x014D] = header
    rom[0x014E:0x0150] = ((sum(rom[:0x014E]) + sum(rom[0x0150:])) & 0xFFFF).to_bytes(2, 'big')


def changed_spans(_original: bytes | None = None) -> list[tuple[int, int]]:
    return [(SITE, SITE + len(NEW)), (0x014D, 0x0150)]


def build(parent: bytes, original: bytes | None = None) -> bytes:
    if sha(parent) != PARENT:
        raise ValueError('exact transition-palette-blanking parent required')
    if parent[SITE:SITE + len(PRE)] != PRE:
        raise ValueError('menu window-enable tail differs')
    result = bytearray(parent)
    result[SITE:SITE + len(NEW)] = NEW
    update_checksums(result)
    out = bytes(result)
    if sha(out) != CANDIDATE:
        raise ValueError(f'candidate identity drift: {sha(out)}')
    return out


def reconstruct_parent(rom: bytes, original: bytes | None = None) -> bytes:
    if sha(rom) != CANDIDATE:
        raise ValueError('not the exact menu-open-map-hold candidate')
    if rom[SITE:SITE + len(NEW)] != NEW:
        raise ValueError('menu-open-map-hold site differs')
    parent = bytearray(rom)
    parent[SITE:SITE + len(PRE)] = PRE
    update_checksums(parent)
    out = bytes(parent)
    if sha(out) != PARENT or build(out, original) != rom:
        raise ValueError('menu-open-map-hold parent reconstruction failed')
    return out


def verify_installed(rom: bytes, original: bytes | None = None) -> list[str]:
    errors = []
    if sha(rom) != CANDIDATE:
        errors.append('candidate sha256 differs')
    if rom[SITE:SITE + len(NEW)] != NEW:
        errors.append('FFC4 clear was not installed at 14:7F32')
    return errors


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('parent', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    out = args.output.resolve()
    if out.exists() or (ROOT / 'tmp').resolve() not in out.parents:
        parser.error('fresh repository tmp directory required')
    result = build(args.parent.read_bytes())
    out.mkdir(parents=True)
    (out / 'candidate.gb').write_bytes(result)
    receipt = dict(issue=81, parent_sha256=PARENT, candidate_sha256=sha(result),
                   builder_sha256=sha(Path(__file__).read_bytes()),
                   site=f'14:7F32', pre=PRE.hex(), new=NEW.hex())
    (out / 'receipt.json').write_text(json.dumps(receipt, indent=2) + '\n')
    print(json.dumps(receipt))
