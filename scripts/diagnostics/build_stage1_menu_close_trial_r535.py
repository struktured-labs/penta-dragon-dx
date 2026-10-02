#!/usr/bin/env python3
"""Experimental r534 menu-close invalidation; not a release candidate."""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
from arena_position import _Asm
BASE_SHA = "727ee4969da086fe3c62185ca2f0bba1b62cc60d8190710f5db9bfc8b50b260b"
HOOK = 31 * 0x4000 + 0x6CCD - 0x4000
CAVE = 31 * 0x4000 + 0x7400 - 0x4000
# Existing SVBK=1 gate is upstream. Preserve the original scene-$0B path.
HELPER = bytes.fromhex(
    "FA 80 D8 FE 02 20 12 "  # other scene -> original CP $0B
    "F0 B7 FE 02 20 0F "    # not Stage 1 -> common exit
    "F3 3E FF EA 53 DF EA 57 DF C3 E2 6C "
    "C3 D0 6C C3 E2 6C"
)


def visible_map_repair(wait_reveal: bool = False) -> bytes:
    """Restore only the six by twenty cells owned by the menu attr writer.

    C600 is the current contextual gameplay lookup, not the menu's private
    ROM lookup. Each two-cell read/lookup/write acquires a fresh HBlank.
    The helper preserves caller BC/DE/HL and VBK; caller owns DI/EI.
    """
    a = _Asm()
    # This rendered incident is room 01 only. Other rooms retain the cache
    # invalidation without projecting this six-row repair onto hazard rooms.
    # Native close normally has LCD on; fail closed against a polling hang.
    a.db(bytes.fromhex("F0 BD FE 01 C0 F0 40 CB 7F C8"))
    a.db(bytes.fromhex("C5 D5 E5 F0 4F F5 F0 40 CB 5F 11 00 98"))
    a.jr(0x28, "map")
    a.db(0x16, 0x9C)
    a.label("map")
    a.db(bytes.fromhex("26 C6 06 06"))
    a.label("row")
    a.db(0x0E, 0x0A)
    a.label("pair")
    a.db(0xC5)
    a.label("mode3")
    a.db(bytes.fromhex("F0 41 E6 03 FE 03"))
    a.jr(0x20, "mode3")
    a.label("mode0")
    a.db(bytes.fromhex("F0 41 E6 03"))
    a.jr(0x20, "mode0")
    a.db(bytes.fromhex(
        "AF E0 4F 1A 6F 7E 47 13 1A 6F 7E 4F 1B "
        "3E 01 E0 4F 78 12 13 79 12 13 C1 0D"))
    a.jr(0x20, "pair")
    a.db(bytes.fromhex("7B C6 0C 5F"))
    a.jr(0x30, "no_carry")
    a.db(0x14)
    a.label("no_carry")
    a.db(0x05)
    a.jr(0x20, "row")
    if wait_reveal:
        # Finish one rendered frame with menu ownership retained. A frame
        # callback can otherwise see repaired VRAM paired with old raster.
        a.label("active")
        a.db(bytes.fromhex("F0 44 FE 90"))
        a.jr(0x30, "active")
        a.label("vblank")
        a.db(bytes.fromhex("F0 44 FE 90"))
        a.jr(0x38, "vblank")
    a.db(bytes.fromhex("F1 E0 4F E1 D1 C1 C9"))
    return bytes(a.finish())

def build(source: bytes, repair_visible: bool = False, wait_reveal: bool = False) -> bytes:
    if hashlib.sha256(source).hexdigest() != BASE_SHA:
        raise ValueError("requires exact rejected r534 source")
    if source[HOOK:HOOK+3] != bytes.fromhex("FA 80 D8"):
        raise ValueError("menu hook preimage differs")
    if source[CAVE:CAVE+len(HELPER)] != b"\xff" * len(HELPER):
        raise ValueError("trial helper cave is occupied")
    result = bytearray(source)
    result[HOOK:HOOK+3] = bytes.fromhex("C3 00 74")
    result[CAVE:CAVE+len(HELPER)] = HELPER
    if repair_visible:
        helper = bytes.fromhex(
            "FA 80 D8 FE 02 20 15 F0 B7 FE 02 20 12 "
            "F3 CD 80 74 3E FF EA 53 DF EA 57 DF C3 E2 6C "
            "C3 D0 6C C3 E2 6C")
        repair = visible_map_repair(wait_reveal)
        if source[CAVE:CAVE+len(helper)] != b"\xff" * len(helper) or source[CAVE+0x80:CAVE+0x80+len(repair)] != b"\xff" * len(repair):
            raise ValueError("visible repair cave is occupied")
        result[CAVE:CAVE+len(helper)] = helper
        result[CAVE+0x80:CAVE+0x80+len(repair)] = repair
    result[0x14E:0x150] = ((sum(result[:0x14E]) + sum(result[0x150:])) & 0xFFFF).to_bytes(2, "big")
    owned = set(range(HOOK, HOOK+3)) | set(range(CAVE, CAVE+0x100)) | {0x14E,0x14F}
    if any(i not in owned for i,(a,b) in enumerate(zip(source,result)) if a != b):
        raise ValueError("trial escaped its owned menu-close bytes")
    return bytes(result)

def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--repair-visible", action="store_true")
    parser.add_argument("--wait-reveal", action="store_true")
    args = parser.parse_args()
    out = args.output.resolve()
    if out.exists() or (ROOT / "tmp").resolve() not in out.parents:
        parser.error("output must be fresh below repository tmp/")
    source = args.source.read_bytes()
    if args.wait_reveal and not args.repair_visible:
        parser.error("--wait-reveal requires --repair-visible")
    result = build(source, args.repair_visible, args.wait_reveal)
    out.mkdir(parents=True)
    (out / "candidate.gb").write_bytes(result)
    receipt = dict(schema="penta-menu-close-r535-trial-v1", release_qualified=False,
                   repair_visible=args.repair_visible,
                   wait_reveal=args.wait_reveal,
                   source=str(args.source.resolve()), source_sha256=BASE_SHA,
                   candidate_sha256=hashlib.sha256(result).hexdigest(),
                   changed_offsets=[i for i,(a,b) in enumerate(zip(source,result)) if a != b])
    (out / "build-receipt.json").write_text(json.dumps(receipt, indent=2) + "\n")
    print(json.dumps(receipt, indent=2))

if __name__ == "__main__":
    main()
