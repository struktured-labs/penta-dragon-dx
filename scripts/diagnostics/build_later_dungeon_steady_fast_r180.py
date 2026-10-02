#!/usr/bin/env python3
"""Build an exact-r120 fail-closed steady fast path for Stages 2-7."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from build_later_hdma_overlap import Asm, BANK_SIZE, BASE_SHA256, checksum


BANK = 13
HOOK_ADDR = 0x6E93
HOOK_PREIMAGE = bytes.fromhex("CD B8 69")
CAVE_ADDR = 0x6EC4
CAVE_END = 0x6EF4
NATIVE_BG0_HELPER = 0x69B8


def bank_offset(address: int) -> int:
    return BANK * BANK_SIZE + address - 0x4000


def build_gate(fast_nops: int) -> tuple[bytes, dict[str, int]]:
    a = Asm(CAVE_ADDR)
    # This call site is already admitted only for D880=$02..$0B with FFBA>0;
    # in the release scene table that is exactly the six later dungeons.
    a.db(0xF0, 0x40, 0xE6, 0x20)           # item/window menu disabled
    a.jr(0x20, "fallback")
    a.db(0xFA, 0x02, 0xDF, 0xFE, 0x5A)     # selected table is valid
    a.jr(0x20, "fallback")
    # Discard only this helper call's $6E96 return without clobbering BC, then
    # return from the enclosing prelude directly to the unchanged wrapper.
    a.db(0x33, 0x33)
    a.db(*([0x00] * fast_nops))
    a.db(0xC9)
    a.label("fallback")
    a.db(
        0xF0, 0xBA,                        # restore helper ABI A=FFBA
        0xC3, NATIVE_BG0_HELPER & 0xFF, NATIVE_BG0_HELPER >> 8,
    )
    code = a.finish()
    return code, dict(a.labels)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("base", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--receipt", type=Path, required=True)
    parser.add_argument("--fast-nops", type=int, default=0)
    args = parser.parse_args()
    if not 0 <= args.fast_nops <= 12:
        parser.error("--fast-nops must be between 0 and 12")
    source = args.base.read_bytes()
    base_sha = hashlib.sha256(source).hexdigest()
    if base_sha != BASE_SHA256:
        raise SystemExit(f"wrong exact r120 base: {base_sha}")
    rom = bytearray(source)
    hook = bank_offset(HOOK_ADDR)
    cave = bank_offset(CAVE_ADDR)
    if rom[hook:hook + 3] != HOOK_PREIMAGE:
        raise SystemExit("later-dungeon BG0 call preimage moved")
    if rom[cave:bank_offset(CAVE_END)] != bytes(CAVE_END - CAVE_ADDR):
        raise SystemExit("later-dungeon steady gate cave is not empty")
    gate, labels = build_gate(args.fast_nops)
    if CAVE_ADDR + len(gate) > CAVE_END:
        raise SystemExit("later-dungeon steady gate exceeds audited cave")
    rom[hook:hook + 3] = bytes((0xCD, CAVE_ADDR & 0xFF, CAVE_ADDR >> 8))
    rom[cave:cave + len(gate)] = gate
    checksum(rom)
    output = bytes(rom)
    report = {
        "schema": "penta-later-dungeon-steady-fast-r180-v1",
        "status": "PASS_STATIC_EMULATOR_REQUIRED",
        "promotable": False,
        "base_sha256": base_sha,
        "candidate_sha256": hashlib.sha256(output).hexdigest(),
        "gate": f"bank{BANK}:${CAVE_ADDR:04X}, {len(gate)} bytes",
        "labels": labels,
        "fast_nops": args.fast_nops,
        "admission_is_existing_later_dungeon_branch": True,
        "window_disabled_required": True,
        "palette_sentinel_required": "DF02=$5A",
        "fallback_restores_native_bg0_helper_abi": True,
        "stage1_title_arena_routes_byte_exact": True,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.receipt.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(output)
    args.receipt.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
