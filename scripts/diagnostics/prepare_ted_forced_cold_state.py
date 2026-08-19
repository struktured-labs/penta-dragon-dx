#!/usr/bin/env python3
"""Retarget a qualified Ted state and clear both lazy-install destinations."""

from __future__ import annotations

import argparse
from pathlib import Path
import zlib

from normalize_mgba_state_pc import (
    GB_STATE_SIZE,
    normalize,
    png_chunks,
    state_offset,
    write_png,
)

WRAM_IMAGE_OFFSET = 0x4400
WRAM_BANK_SIZE = 0x1000


def clear_private_install_destinations(path: Path) -> None:
    chunks = png_chunks(path.read_bytes())
    indices = [i for i, (kind, _) in enumerate(chunks) if kind == b"gbAs"]
    if len(indices) != 1:
        raise RuntimeError(f"expected one gbAs chunk, found {len(indices)}")
    index = indices[0]
    raw = bytearray(zlib.decompress(chunks[index][1]))
    if len(raw) != GB_STATE_SIZE:
        raise RuntimeError(f"unexpected Game Boy state size 0x{len(raw):X}")

    # The serialized WRAM image is bank0 followed by switchable banks 1..7.
    # Clear only the exact direct-plane runtime/pointer/helper destinations;
    # D900/DC00 publication planes deliberately survive fixture retargeting.
    for bank in (4, 5):
        base = WRAM_IMAGE_OFFSET + bank * WRAM_BANK_SIZE
        for first, last in ((0x300, 0x39A), (0x500, 0x8FF)):
            raw[base + first:base + last + 1] = bytes(last - first + 1)

    for address in range(0xC4FA, 0xC4FD):
        raw[state_offset(address)] = 0
    raw[state_offset(0xC5FE)] = 0
    raw[state_offset(0xC5FF)] = 0
    chunks[index] = (b"gbAs", zlib.compress(bytes(raw), level=9))
    write_png(path, chunks)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    parser.add_argument("destination", type=Path)
    parser.add_argument("--rom", required=True, type=Path)
    parser.add_argument("--normalize-main-loop", action="store_true")
    args = parser.parse_args()
    normalize(
        args.source,
        args.destination,
        pc=0,
        writes=[],
        rom=args.rom,
        preserve_machine=True,
        arena_table=4,
    )
    if args.normalize_main_loop:
        normalize(
            args.destination,
            args.destination,
            pc=0x016C,
            writes=[],
            rom=args.rom,
            bank=1,
        )
    clear_private_install_destinations(args.destination)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
