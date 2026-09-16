#!/usr/bin/env python3
"""Restore the reviewed r446 later-stage copy entry on the d82 base.

d82 contains the qualified bank-28 helper at $6C80, including the exact
mode-C entry at bank 1 $42C7, but its separate shared entry at $42BB reverted
to the pre-r446 native loop.  That bypass makes the title attract return
before the Gargoyle reel.  This immutable composer makes only that entry and
the cartridge checksums agree with the reviewed mode-C route.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

BASE_SHA = "d82f563d856995fc1844d48cdd317b12f2ac9218f023eec376ee73bc24308074"
SITE = 0x42BB
OLD = bytes.fromhex("3E 18 F5 0E 06 C3 30 43")
NEW = bytes.fromhex("3E 1C CD 47 08 C3 ED 42")
HELPER_OFF = 28 * 0x4000 + 0x2C80
HELPER_LEN = 240
HELPER_SHA = "60d76facb8807ac2cb84977e3a9395c2aee8c72f51349f98aa81a9228ade1b4e"


def update_checksums(rom: bytearray) -> None:
    header = 0
    for byte in rom[0x134:0x14D]:
        header = (header - byte - 1) & 0xFF
    rom[0x14D] = header
    global_sum = (sum(rom[:0x14E]) + sum(rom[0x150:])) & 0xFFFF
    rom[0x14E:0x150] = global_sum.to_bytes(2, "big")


def build(source: bytes) -> tuple[bytes, dict]:
    """Apply the exact reviewed repair without reading or writing artifacts."""
    assert hashlib.sha256(source).hexdigest() == BASE_SHA, "base is not the reviewed d82 candidate"
    assert source[SITE:SITE + len(OLD)] == OLD, "later-stage entry preimage differs"
    assert source[0x42C6:0x42CF] == bytes.fromhex("F1") + NEW, "mode-C helper entry differs"
    assert source[0x0847:0x0850] == bytes.fromhex("CD 61 00 CD 80 6C C3 61 00"), "bank28 dispatcher differs"
    helper = source[HELPER_OFF:HELPER_OFF + HELPER_LEN]
    assert hashlib.sha256(helper).hexdigest() == HELPER_SHA, "qualified helper differs"

    rom = bytearray(source)
    rom[SITE:SITE + len(NEW)] = NEW
    update_checksums(rom)
    changed = [index for index, (before, after) in enumerate(zip(source, rom)) if before != after]
    allowed = set(range(SITE, SITE + len(NEW))) | {0x14D, 0x14E, 0x14F}
    assert set(changed) <= allowed, changed
    receipt = {
        "schema": "penta-compose-d82-later-stage-copy-recovery-r453-v1",
        "base_sha256": BASE_SHA,
        "candidate_sha256": hashlib.sha256(rom).hexdigest(),
        "changed_offsets": [hex(index) for index in changed],
        "patch": "bank1 $42BB native entry -> exact qualified mode-C bank28-helper entry at $42C7",
        "helper_sha256": HELPER_SHA,
        "acceptance": "title-visual receipts must reach the Gargoyle reel and return to active title; Stage-1 copy receipts remain required",
    }
    return bytes(rom), receipt


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", type=Path, required=True)
    parser.add_argument("--out-dir", type=Path, required=True)
    args = parser.parse_args()
    rom, receipt = build(args.base.read_bytes())
    args.out_dir.mkdir(parents=True, exist_ok=True)
    candidate = args.out_dir / "candidate.gb"
    if candidate.exists() and candidate.read_bytes() != rom:
        raise SystemExit("immutable candidate collision")
    candidate.write_bytes(rom)
    (args.out_dir / "build-receipt.json").write_text(json.dumps(receipt, indent=2) + "\n")
    print(json.dumps({"candidate_sha256": receipt["candidate_sha256"], "changed_offsets": receipt["changed_offsets"]}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
