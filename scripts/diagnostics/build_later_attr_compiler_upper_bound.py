#!/usr/bin/env python3
"""Build a non-promotable upper bound that skips later attr compilation.

This control keeps the dirty-copy completion ABI: it still runs the existing
post-copy scene guard and atomic wrapper, but jumps over the 24-row attribute
compiler and its DMA.  The resulting ROM is visually invalid whenever a
semantic plane changes.  Its only purpose is to bound how much throughput the
compiler/publication path can possibly recover before production work begins.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


ALLOWED_BASES = {
    "029a413b4ef5c0d3fdb6d9d39902821e8b0d9f35a36bed20ab82973f2ab10742": "r120",
    # r194 changes only the Stage-1 semantic decision sources and attract
    # trampoline; the shared compiler and completion ABI are byte-identical.
    "c6bd39a4eac5bcce00bd621a19af13c0a54f87f51ea89aec5fde8a3b42593272": "r194-visual-repair",
    # r199 changes only the bank-13 stale-Window branch/padding. The fixed
    # bank-1 later-stage compiler and completion ABI remain byte-identical.
    "0ebae52b5c74ecb5e0cd2bbee11c4ee4fa6aca118aeb0515333722e0273518e8": "r199-window-safe",
}
DIRTY_COMPILER_ENTRY = 0x42FC
DIRTY_COMPLETION = 0x4354
COMPILER_PREIMAGE = bytes.fromhex("F0 E0 FE")
COMPLETION_PREIMAGE = bytes.fromhex("CD F1 DB C3 DF DB")


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def update_checksums(rom: bytearray) -> None:
    header = 0
    for value in rom[0x0134:0x014D]:
        header = (header - value - 1) & 0xFF
    rom[0x014D] = header
    total = (sum(rom[:0x014E]) + sum(rom[0x0150:])) & 0xFFFF
    rom[0x014E] = total >> 8
    rom[0x014F] = total & 0xFF


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("base", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--receipt", type=Path, required=True)
    args = parser.parse_args()

    source = args.base.read_bytes()
    digest = sha256(source)
    if digest not in ALLOWED_BASES:
        raise SystemExit(f"wrong exact qualified base: {digest}")
    rom = bytearray(source)
    if rom[
        DIRTY_COMPILER_ENTRY:DIRTY_COMPILER_ENTRY + len(COMPILER_PREIMAGE)
    ] != COMPILER_PREIMAGE:
        raise SystemExit("dirty compiler preimage changed")
    if rom[
        DIRTY_COMPLETION:DIRTY_COMPLETION + len(COMPLETION_PREIMAGE)
    ] != COMPLETION_PREIMAGE:
        raise SystemExit("dirty completion ABI preimage changed")

    rom[DIRTY_COMPILER_ENTRY:DIRTY_COMPILER_ENTRY + 3] = bytes(
        (0xC3, DIRTY_COMPLETION & 0xFF, DIRTY_COMPLETION >> 8)
    )
    update_checksums(rom)
    output = bytes(rom)
    receipt = {
        "status": "PASS_STATIC_EMULATOR_REQUIRED",
        "promotable": False,
        "warning": "attribute planes are deliberately stale on dirty copies",
        "base_sha256": digest,
        "base_profile": ALLOWED_BASES[digest],
        "candidate_sha256": sha256(output),
        "patch": "$42FC: JP $4354",
        "preserved_completion": "$4354: CALL $DBF1; JP $DBDF",
        "required_use": "throughput upper-bound measurement only",
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.receipt.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(output)
    args.receipt.write_text(json.dumps(receipt, indent=2) + "\n")
    print(json.dumps(receipt, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
