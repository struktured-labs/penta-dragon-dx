#!/usr/bin/env python3
"""Check a reviewed Stage-1 ceiling capture without running an emulator.

Inputs must share the same room/camera. Background must come from a reviewed
sprite-free reference, and mask must select only opaque solid ceiling pixels.
This checks visual occlusion, not world-space collision.
"""
import argparse
from verify_gameover_restart import check_ceiling
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--frame", type=Path, required=True)
    parser.add_argument("--background", type=Path, required=True)
    parser.add_argument("--mask", type=Path, required=True)
    args = parser.parse_args()
    try:
        check_ceiling(args.frame, args.background, args.mask)
    except (ValueError, OSError) as exc:
        parser.exit(1, f"FAIL: {exc}\n")
    print("PASS: supplied ceiling mask has no visual leakage; collision not assessed")


if __name__ == "__main__":
    main()
