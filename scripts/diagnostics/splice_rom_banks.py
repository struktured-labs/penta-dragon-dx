#!/usr/bin/env python3
"""Create a diagnostic ROM by restoring selected banks from a reference.

This is intentionally a test-only bisect helper.  It lets runtime regressions
be localized without treating a byte-range splice as a publishable fix.
"""

from __future__ import annotations

import argparse
from pathlib import Path


BANK_SIZE = 0x4000


def header_checksum(rom: bytes | bytearray) -> int:
    value = 0
    for byte in rom[0x0134:0x014D]:
        value = (value - byte - 1) & 0xFF
    return value


def global_checksum(rom: bytes | bytearray) -> int:
    return (
        sum(rom[:0x014E]) + sum(rom[0x0150:])
    ) & 0xFFFF


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("candidate", type=Path)
    parser.add_argument("reference", type=Path)
    parser.add_argument("--restore-bank", type=int, action="append", default=[])
    parser.add_argument(
        "--restore-range",
        action="append",
        default=[],
        metavar="START:END",
        help="restore a half-open byte range; integers accept 0x prefixes",
    )
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    candidate = bytearray(args.candidate.read_bytes())
    reference = args.reference.read_bytes()
    if len(candidate) != len(reference) or len(candidate) % BANK_SIZE:
        raise SystemExit("candidate/reference sizes must match whole ROM banks")

    bank_count = len(candidate) // BANK_SIZE
    restored = sorted(set(args.restore_bank))
    ranges: list[tuple[int, int]] = []
    for specification in args.restore_range:
        try:
            start_text, end_text = specification.split(":", 1)
            start = int(start_text, 0)
            end = int(end_text, 0)
        except (ValueError, TypeError):
            raise SystemExit(f"invalid range {specification!r}; use START:END")
        if not 0 <= start < end <= len(candidate):
            raise SystemExit(f"range {specification!r} is outside the ROM")
        ranges.append((start, end))
    if not restored and not ranges:
        raise SystemExit("at least one --restore-bank or --restore-range is required")
    for bank in restored:
        if not 0 <= bank < bank_count:
            raise SystemExit(f"bank {bank} is outside 0..{bank_count - 1}")
        start = bank * BANK_SIZE
        candidate[start:start + BANK_SIZE] = reference[start:start + BANK_SIZE]
    for start, end in ranges:
        candidate[start:end] = reference[start:end]

    candidate[0x014D] = header_checksum(candidate)
    checksum = global_checksum(candidate)
    candidate[0x014E:0x0150] = checksum.to_bytes(2, "big")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(candidate)
    rendered_ranges = [f"0x{start:X}:0x{end:X}" for start, end in ranges]
    print(
        f"wrote {args.output}; restored banks {restored}; "
        f"ranges {rendered_ranges}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
