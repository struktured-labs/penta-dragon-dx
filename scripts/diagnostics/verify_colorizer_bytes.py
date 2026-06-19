"""Verify the installed OBJ colorizer bytes match iter 31's expected layout.

Iter 31's win: tile 0x10-0x1F → sara_palette (not pal_4). The JR offset at
bank13:0x6A41 must be 0x1B (= sara_palette label offset). Reverting this byte
to 0x0B (= pal_4 label) silently regresses Sara secondary tiles to pal-4 when
hwoam_recolor B=40 stamps them — and no live OAM test catches this because
none of our savestates have Sara secondary tiles visible in slot 10-11 at
the consensus-vote frame.

Run from the pre-commit hook with `--rom rom/working/penta_dragon_dx_teleport.gb`.
"""

import argparse
import sys
from pathlib import Path

CHECKS = [
    # (rom_offset, expected_byte, description)
    # Iter 31 — hwoam_recolor's `LD B, 40` operand at bank13:0x7F67 (the
    # post-DMA stamp pass; the SHARED colorizer at 0x6A11 keeps its B=10 for
    # the shadow pass — those are different code paths).
    (
        13 * 0x4000 + (0x7F67 - 0x4000),
        0x28,
        "hwoam_recolor LD B operand at bank13:0x7F67 (40 slots — iter 31 raised from 10)",
    ),
    # Iter 31 — tile 0x10-0x1F → sara_palette remap (JR offset at 0x6A41).
    (
        13 * 0x4000 + (0x6A41 - 0x4000),
        0x1B,
        "tile 0x10-0x1F → sara_palette JR offset at 0x6A41 (iter 31 remap; was 0x0B = pal_4)",
    ),
    # Sanity: the shared colorizer's `LD B, 10` for the shadow pass MUST stay
    # at 0x6A11 = 0x0A. If someone raises it, mGBA-visible regressions show
    # up across many tests, but this check makes the cause explicit.
    (
        13 * 0x4000 + (0x6A11 - 0x4000),
        0x0A,
        "shadow-pass LD B operand at 0x6A11 (10 slots — kept; only post-DMA hwoam_recolor uses B=40)",
    ),
    # Sanity: colorizer LD B opcode itself (catches a wholesale rewrite).
    (
        13 * 0x4000 + (0x6A10 - 0x4000),
        0x06,
        "colorizer LD B opcode at 0x6A10 (sanity: must still be LD B,n)",
    ),
]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rom", required=True, help="ROM file to validate")
    args = parser.parse_args()
    rom = Path(args.rom).read_bytes()
    failed = False
    for off, expected, desc in CHECKS:
        actual = rom[off]
        if actual == expected:
            print(f"  [PASS] {desc}")
        else:
            print(
                f"  [FAIL] {desc}: got 0x{actual:02X}, expected 0x{expected:02X}"
            )
            failed = True
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
