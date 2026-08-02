#!/usr/bin/env python3
"""Create a header-only CGB-compatible copy of the stock ROM for diagnostics."""

from __future__ import annotations

import argparse
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    parser.add_argument("destination", type=Path)
    args = parser.parse_args()

    rom = bytearray(args.source.read_bytes())
    if len(rom) < 0x150:
        raise RuntimeError("input is too small to be a Game Boy ROM")
    rom[0x143] = 0x80
    checksum = 0
    for byte in rom[0x134:0x14D]:
        checksum = (checksum - byte - 1) & 0xFF
    rom[0x14D] = checksum
    args.destination.write_bytes(rom)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
