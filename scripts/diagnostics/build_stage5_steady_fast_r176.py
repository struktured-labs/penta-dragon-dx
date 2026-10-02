#!/usr/bin/env python3
"""Build an exact-r120, fail-closed Stage 5 steady-prelude fast path."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from build_later_hdma_overlap import Asm, BANK_SIZE, BASE_SHA256, checksum


BANK = 13
HOOK_ADDR = 0x6E83
HOOK_PREIMAGE = bytes.fromhex("FE 0A C8")
CAVE_ADDR = 0x6EC4
CAVE_END = 0x6EF4
FALLBACK_ADDR = 0x6E88


def bank_offset(address: int) -> int:
    return BANK * BANK_SIZE + address - 0x4000


def build_gate(fast_nops: int = 0) -> tuple[bytes, dict[str, int]]:
    a = Asm(CAVE_ADDR)
    a.db(0xFE, 0x06)                       # exact Stage 5 scene
    a.jr(0x20, "fallback")
    a.db(0xF0, 0x40, 0xE6, 0x20)           # item/window menu disabled
    a.jr(0x20, "fallback")
    a.db(0xFA, 0x02, 0xDF, 0xFE, 0x5A)     # selected table is valid
    a.jr(0x20, "fallback")
    a.db(*([0x00] * fast_nops))
    a.db(0xC9)                              # steady live Stage 5 only
    a.label("fallback")
    a.db(
        0xFA, 0x80, 0xD8,                  # restore scene-detect result A
        0xFE, 0x0A, 0xC8,                  # displaced CP/RET Z
        0xFE, 0x0C,                        # displaced upper-scene compare
        0xC3, FALLBACK_ADDR & 0xFF, FALLBACK_ADDR >> 8,
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
    source = args.base.read_bytes()
    base_sha = hashlib.sha256(source).hexdigest()
    if base_sha != BASE_SHA256:
        raise SystemExit(f"wrong exact r120 base: {base_sha}")
    rom = bytearray(source)
    hook = bank_offset(HOOK_ADDR)
    cave = bank_offset(CAVE_ADDR)
    if rom[hook:hook + 3] != HOOK_PREIMAGE:
        raise SystemExit("Stage 5 prelude hook preimage moved")
    if rom[cave:bank_offset(CAVE_END)] != bytes(CAVE_END - CAVE_ADDR):
        raise SystemExit("Stage 5 prelude gate cave is not empty")
    if not 0 <= args.fast_nops <= 12:
        parser.error("--fast-nops must be between 0 and 12")
    gate, labels = build_gate(args.fast_nops)
    if CAVE_ADDR + len(gate) > CAVE_END:
        raise SystemExit("Stage 5 steady gate exceeds audited cave")
    rom[hook:hook + 3] = bytes((0xC3, CAVE_ADDR & 0xFF, CAVE_ADDR >> 8))
    rom[cave:cave + len(gate)] = gate
    checksum(rom)
    output = bytes(rom)
    report = {
        "schema": "penta-stage5-steady-fast-r176-v1",
        "status": "PASS_STATIC_EMULATOR_REQUIRED",
        "promotable": False,
        "base_sha256": base_sha,
        "candidate_sha256": hashlib.sha256(output).hexdigest(),
        "gate": f"bank{BANK}:${CAVE_ADDR:04X}, {len(gate)} bytes",
        "labels": labels,
        "admit": {
            "scene": "D880=$06",
            "stage_selector": "implied uniquely by D880=$06",
            "window_disabled": True,
            "palette_sentinel": "DF02=$5A",
            "timing_nops": args.fast_nops,
        },
        "fallback_restores_scene_a_and_displaced_flags": True,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.receipt.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(output)
    args.receipt.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
