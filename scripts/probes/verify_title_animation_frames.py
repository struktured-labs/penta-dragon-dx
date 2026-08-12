"""Verify that title-animation frames load a non-white CGB palette.

Usage:
    python scripts/probes/verify_title_animation_frames.py ROM_PATH

The probe boots the ROM in headless PyBoy with NO key presses, letting the
YANOMAN logo + title screen play naturally. Analyzes every rendered frame
from 120 through 600.

PASS criteria:
  1. NO frame between 120-600 is 100% white (would mean palette never loaded)
  2. At least one frame has non-white pixels (confirms palette / bg_table active)

The YANOMAN bitmap is ~90% white background, so the white ratio never drops
below ~90%. The true failure mode is an all-white frame (the v2.90 regression
where CGB BG palette RAM stayed at boot-ROM defaults).
"""
from __future__ import annotations

import argparse
from collections import Counter
from pathlib import Path

from pyboy import PyBoy


CAPTURE_START = 120   # title screen is fully showing by this point
CAPTURE_END = 600
WHITE_THRESHOLD = 240


def analyze_frame(image) -> tuple[float, Counter[tuple[int, int, int]]]:
    """Return the near-white ratio and RGB palette distribution."""
    rgb_image = image.convert("RGB")
    distribution = Counter(rgb_image.getdata())
    total_pixels = sum(distribution.values())
    white_pixels = sum(
        count
        for (red, green, blue), count in distribution.items()
        if red >= WHITE_THRESHOLD
        and green >= WHITE_THRESHOLD
        and blue >= WHITE_THRESHOLD
    )
    return white_pixels / total_pixels, distribution


def format_distribution(distribution: Counter[tuple[int, int, int]]) -> str:
    """Format all rendered RGB colors as hex color/count pairs, limited to key entries."""
    colors = sorted(distribution.items(), key=lambda item: (-item[1], item[0]))
    return " ".join(
        f"#{red:02X}{green:02X}{blue:02X}={count}"
        for (red, green, blue), count in colors[:5]
    )


def run_probe(rom_path: Path) -> bool:
    pyboy = PyBoy(
        str(rom_path), window="null", cgb=True,
        sound_emulated=False, log_level=5,
    )
    pyboy.set_emulation_speed(0)

    white_ratios: dict[int, float] = {}
    try:
        for frame in range(CAPTURE_END + 1):
            pyboy.tick(1, True)

            if frame >= CAPTURE_START:
                white_ratio, distribution = analyze_frame(pyboy.screen.image)
                white_ratios[frame] = white_ratio
                print(
                    f"frame={frame:03d} white_ratio={white_ratio:.6f} "
                    f"palette={format_distribution(distribution)}"
                )
    finally:
        pyboy.stop(save=False)

    first_non_white = next(
        (f for f, r in white_ratios.items() if r < 1.0), None
    )
    min_frame, min_ratio = min(white_ratios.items(), key=lambda item: item[1])
    max_frame, max_ratio = max(white_ratios.items(), key=lambda item: item[1])

    all_frames_have_non_white = all(r < 1.0 for r in white_ratios.values())

    print("\nSummary:")
    print(f"  first non-white frame: {first_non_white}")
    print(f"  min white ratio: {min_ratio:.6f} (frame {min_frame})")
    print(f"  max white ratio: {max_ratio:.6f} (frame {max_frame})")
    print(f"  total frames analyzed: {len(white_ratios)}")

    failures = []
    if not all_frames_have_non_white:
        white_frames = [str(f) for f, r in white_ratios.items() if r >= 1.0]
        failures.append("100% white frame(s): " + ", ".join(white_frames))

    if failures:
        print("FAIL:")
        for failure in failures:
            print(f"  - {failure}")
        return False

    print("PASS: all title frames have non-white pixels (palette is loaded).")
    return True


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Verify title animation palette loading with PyBoy."
    )
    parser.add_argument("rom", type=Path, help="path to the Game Boy ROM")
    args = parser.parse_args()

    if not args.rom.is_file():
        print(f"FAIL: ROM not found: {args.rom}")
        return 1

    try:
        return 0 if run_probe(args.rom) else 1
    except Exception as exc:
        print(f"FAIL: PyBoy harness error: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
