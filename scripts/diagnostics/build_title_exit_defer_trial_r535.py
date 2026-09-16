#!/usr/bin/env python3
"""Negative/diagnostic experiment: defer old-title attribute cleanup on r534.

This deliberately tests the scene-transition hypothesis, not a complete
presentation-bound handoff. Selector/story leakage must still fail the gates.
"""
import argparse
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
from arena_position import _Asm
BASE_SHA = "727ee4969da086fe3c62185ca2f0bba1b62cc60d8190710f5db9bfc8b50b260b"


def late_clear_patches() -> list[tuple[int, bytes, bytes]]:
    """Move the selector clear after native $408E has retired title tiles."""
    bank31 = 31 * 0x4000 - 0x4000
    mux = _Asm()
    # Enter only from the old unknown-caller fallback, with HL already saved.
    # Ordinary room, dirty-map and menu dispatch retain their exact hot path.
    mux.db(bytes.fromhex("F8 04 7E FE 47"))
    mux.jr(0x20, "title")
    mux.db(bytes.fromhex("23 7E FE 3B"))
    mux.jr(0x20, "title")
    mux.db(bytes.fromhex("E1 C3 50 75"))
    mux.label("title")
    mux.db(bytes.fromhex("F8 04 7E FE DC"))
    mux.jr(0x20, "old")
    mux.db(bytes.fromhex("23 7E FE 76"))
    mux.jr(0x20, "old")
    mux.db(bytes.fromhex("E1 C3 A0 75"))
    mux.label("old")
    mux.db(bytes.fromhex("E1 3E 01 B7 C9"))
    mux_code = bytes(mux.finish())
    a = _Asm()
    a.db(bytes.fromhex("C5 E5 11 FD DC 1A A7"))
    a.jr(0x28, "done")
    a.db(bytes.fromhex("F3 F0 40 F5 CB 7F"))
    a.jr(0x28, "off")
    a.label("vblank")
    a.db(bytes.fromhex("F0 44 FE 90"))
    a.jr(0x38, "vblank")
    a.label("off")
    a.db(bytes.fromhex("F0 40 CB BF E0 40 F0 4F F5 3E 01 E0 4F 21 00 98 0E 08 AF"))
    a.label("page")
    a.db(0x06, 0x00)
    a.label("clear")
    a.db(bytes.fromhex("22 05"))
    a.jr(0x20, "clear")
    a.db(0x0D)
    a.jr(0x20, "page")
    a.db(bytes.fromhex("F1 E0 4F F1 E0 40 FB"))
    a.label("done")
    # Native continuation only consumes the DCFD zero flag; A is dead before
    # its next use. A=1 restores bank 1 through the existing fixed mapper.
    a.db(bytes.fromhex("E1 C1 11 FD DC 1A A7 3E 01 C9"))
    clear_code = bytes(a.finish())
    # Scene 00 also occurs during the idle title animation. Defer only when
    # the real GAME START selector entry armed its existing DF4C=$A0 marker.
    rearm = bytes.fromhex("FA 4C DF FE A0 28 08 7E 3D 20 04 AF EA 08 DF 3E 0D C9")
    return [(0x3B42, bytes.fromhex("11 FD DC 1A A7"), bytes.fromhex("3E 1F CD 47 08")),
            (bank31 + 0x6D5A, bytes.fromhex("E1 3E 01"), bytes.fromhex("C3 00 75")),
            (bank31 + 0x7500, b"\xff" * len(mux_code), mux_code),
            (bank31 + 0x7550, b"\xff" * len(clear_code), clear_code),
            (bank31 + 0x75A0, b"\xff" * len(rearm), rearm)]

def build(source: bytes, preserve_outgoing_title: bool = False, late_clear: bool = False) -> bytes:
    if late_clear and not preserve_outgoing_title:
        raise ValueError("late clear requires outgoing-title preservation")
    if hashlib.sha256(source).hexdigest() != BASE_SHA:
        raise ValueError("requires exact r534")
    offset = 13 * 0x4000 + 0x6E9F - 0x4000
    if source[offset:offset+5] != bytes.fromhex("AF EA 08 DF C9"):
        raise ValueError("title rearm leaf preimage differs")
    rom = bytearray(source)
    if preserve_outgoing_title:
        # Keep entry/return-to-title rearming. Only remove the OLD-title
        # rearm, and defer the separate selector's early attr-map clear.
        wrapper = 13 * 0x4000 + 0x76D7 - 0x4000
        front = 13 * 0x4000 + 0x53C2 - 0x4000
        if source[wrapper:wrapper+14] != bytes.fromhex("7E 3D CC 9F 6E 78 3D CC 9F 6E 78 C3 DF 6B"):
            raise ValueError("title transition wrapper differs")
        if source[front:front+7] != bytes.fromhex("FA FD DC B7 CA 01 6F"):
            raise ValueError("selector clear entry differs")
        pad = 13 * 0x4000 + 0x2E60
        if source[pad:pad+11] != bytes(11):
            raise ValueError("conditional title rearm live pad differs")
        # The native fallthrough skips the private nine-byte leaf. It skips
        # old-title cleanup only for new scene 00 (GAME START), not attract
        # or story exits. Entry-to-title rearming below is unchanged.
        if late_clear:
            rom[wrapper:wrapper+5] = bytes.fromhex("3E 1F CD 47 08")
        else:
            rom[pad:pad+11] = bytes.fromhex("18 09 78 B7 C8 7E 3D CA 9F 6E C9")
            rom[wrapper:wrapper+5] = bytes.fromhex("CD 62 6E 00 00")
        rom[front:front+15] = bytes.fromhex("FA FD DC B7 CA 01 6F 3E A0 EA 4C DF C3 01 6F")
    else:
        rom[offset:offset+5] = bytes.fromhex("C9 00 00 00 00")
    if late_clear:
        for start, old, new in late_clear_patches():
            if source[start:start+len(old)] != old:
                raise ValueError(f"late clear preimage differs at {start:06X}")
            rom[start:start+len(new)] = new
    rom[0x14E:0x150] = ((sum(rom[:0x14E]) + sum(rom[0x150:])) & 0xFFFF).to_bytes(2,"big")
    return bytes(rom)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("source", type=Path)
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--preserve-outgoing-title", action="store_true")
    p.add_argument("--late-clear", action="store_true")
    a = p.parse_args()
    out = a.output.resolve()
    if out.exists() or (ROOT / "tmp").resolve() not in out.parents:
        p.error("output must be fresh below repository tmp/")
    try:
        rom = build(a.source.read_bytes(), a.preserve_outgoing_title, a.late_clear)
    except ValueError as error:
        p.error(str(error))
    out.mkdir(parents=True)
    (out / "candidate.gb").write_bytes(rom)
    receipt = dict(schema="penta-title-exit-defer-trial-v1", release_qualified=False,
                   preserve_outgoing_title=a.preserve_outgoing_title,
                   late_clear=a.late_clear,
                   source_sha256=BASE_SHA, candidate_sha256=hashlib.sha256(rom).hexdigest())
    (out / "build-receipt.json").write_text(json.dumps(receipt, indent=2) + "\n")
    print(json.dumps(receipt))

if __name__ == "__main__":
    main()
