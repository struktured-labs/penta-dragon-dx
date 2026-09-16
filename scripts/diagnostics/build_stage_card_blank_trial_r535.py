#!/usr/bin/env python3
"""Retire the Stage-1 card before native dungeon CHR loading."""
import argparse
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
from arena_position import _Asm

BASE_SHA = "681b4668446c547644aaa4924ca0d6dd44782dc59133540c59708fa160c178d3"
BANK31 = 31 * 0x4000 - 0x4000
CALLER = 0x4046
HOOK = 0x4146
HOOK_END = 0x417D
FALLBACK = BANK31 + 0x6D5A
MUX = BANK31 + 0x7500
HELPER = BANK31 + 0x7540
def payloads():
    a = _Asm()
    # Only Stage 1's normal cold-load route retires the card. Boss/card entries
    # and later stages replay the replaced native HL/B setup untouched.
    a.db(bytes.fromhex("FA 80 D8 FE 18"))
    a.jr(0x20, "replay")
    a.db(bytes.fromhex("F0 BA B7"))
    a.jr(0x20, "replay")
    a.db(bytes.fromhex("D5 F0 68 F5 F3 F0 40 CB 7F"))
    a.jr(0x28, "blank")
    a.label("active")
    a.db(bytes.fromhex("F0 44 FE 90"))
    a.jr(0x30, "active")
    a.label("vblank")
    a.db(bytes.fromhex("F0 44 FE 90"))
    a.jr(0x38, "vblank")
    a.label("blank")
    a.db(bytes.fromhex("3E 80 E0 68 AF"))
    # All four BG0 colors become the same quiet black blank. The
    # existing atomic VBlank map commit reinstalls Stage-1 BG0 on reveal.
    for _ in range(8):
        a.db(bytes.fromhex("E0 69"))
    a.db(bytes.fromhex("F1 E0 68 FB D1"))
    a.label("replay")
    a.db(bytes.fromhex("21 85 DC 06 28 3E 01 C9"))
    helper = bytes(a.finish())

    mux = _Asm()
    # Authenticate the outer return before entering the helper. Other callers
    # retain the bank-31 fallback's original POP AF / LD A,1 / OR A / RET.
    mux.db(bytes.fromhex("F8 04 7E FE 4B"))
    mux.jr(0x20, "old")
    mux.db(bytes.fromhex("23 7E FE 41"))
    mux.jr(0x20, "old")
    mux.db(bytes.fromhex("E1 C3 40 75"))
    mux.label("old")
    mux.db(bytes.fromhex("E1 3E 01 B7 C9"))
    return bytes(mux.finish()), helper


def build(source: bytes) -> bytes:
    if hashlib.sha256(source).hexdigest() != BASE_SHA:
        raise ValueError("requires exact menu/title tile-retirement trial")
    mux, helper = payloads()
    native_prefix = bytes.fromhex("21 85 DC 06 28")
    retirement_call = bytes.fromhex("3E 1F CD 47 08")
    patches = [
        (HOOK, native_prefix, retirement_call),
        (FALLBACK, bytes.fromhex("E1 3E 01"), bytes.fromhex("C3 00 75")),
        (MUX, b"\xff" * len(mux), mux),
        (HELPER, b"\xff" * len(helper), helper),
    ]
    rom = bytearray(source)
    owned = {0x14E, 0x14F}
    for offset, old, new in patches:
        if source[offset:offset + len(old)] != old:
            raise ValueError(f"loading retirement preimage differs at {offset:06X}")
        assert len(old) == len(new)
        rom[offset:offset + len(new)] = new
        owned.update(range(offset, offset + len(new)))
    rom[0x14E:0x150] = ((sum(rom[:0x14E]) + sum(rom[0x150:])) & 0xFFFF).to_bytes(2, "big")
    if any(i not in owned for i, (x, y) in enumerate(zip(source, rom, strict=True)) if x != y):
        raise ValueError("retirement escaped its gated cold-loader bytes")
    return bytes(rom)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("source", type=Path)
    p.add_argument("--output", type=Path, required=True)
    args = p.parse_args()
    out = args.output.resolve()
    if out.exists() or (ROOT / "tmp").resolve() not in out.parents:
        p.error("output must be fresh below repository tmp/")
    try:
        rom = build(args.source.read_bytes())
    except ValueError as error:
        p.error(str(error))
    receipt = dict(schema="penta-stage-card-blank-r535-trial-v2", release_qualified=False,
                   source_sha256=BASE_SHA, candidate_sha256=hashlib.sha256(rom).hexdigest(),
                   builder_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest())
    out.mkdir(parents=True)
    (out / "candidate.gb").write_bytes(rom)
    (out / "build-receipt.json").write_text(json.dumps(receipt, indent=2) + "\n")
    print(json.dumps(receipt))


if __name__ == "__main__":
    main()
