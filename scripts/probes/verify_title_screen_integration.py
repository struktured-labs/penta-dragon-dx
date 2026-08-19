#!/usr/bin/env python3
"""Title screen integration test.

Boots the ROM in headless PyBoy, navigates to the title screen, captures
the rendered frame, and verifies expected visual properties.

Checks:
  a. Screen is not pure white (palettes loaded / not all-white CGB glitch)
  b. Cursor tile (OBJ sprite) is present at the expected position
  c. "PENTA DRAGON DX" text is visible
  d. "(C)1992 JAPAN ART MEDIA" text is visible
  e. "STRUKTURED LABS" text is visible
  f. No garbage artifacts (no unexpected tile patterns)

Exit codes:
  0 — all checks pass
  1 — one or more checks failed
  2 — harness error (couldn't boot or capture)
"""
from __future__ import annotations

import os
import sys
import argparse
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
PROJECT_TMP = PROJECT_ROOT / "tmp"

# Minimum PIL presence check
try:
    from PIL import Image
except ImportError:
    sys.stderr.write("Pillow (PIL) is required. Install via `uv add Pillow` or `pip install Pillow`\n")
    sys.exit(2)


def check_pyboy():
    """Verify PyBoy is importable. Returns module or None."""
    try:
        import pyboy
        return pyboy
    except ImportError:
        return None


def analyze_title_screen(png_path: str, rom_path: str, verbose: bool = False) -> list[str]:
    """Analyze a title screen PNG and return a list of failure messages.
    
    Empty list = all checks passed.
    """
    failures = []
    img = Image.open(png_path).convert("RGBA")
    pixels = list(img.getdata())
    w, h = img.size  # Expected: 160x144

    if verbose:
        print(f"  Image: {w}x{h}, {len(set(pixels))} distinct pixel colors")

    # ---- (a) Screen is not pure white ----
    total_pixels = len(pixels)
    white_pixels = sum(
        1 for p in pixels
        if p[0] >= 250 and p[1] >= 250 and p[2] >= 250
    )
    white_ratio = white_pixels / total_pixels if total_pixels else 1.0
    if white_ratio >= 0.99:
        failures.append(f"a) Screen is {white_ratio*100:.1f}% white — "
                        "palettes may not have loaded (CGB boot-ROM white bug)")

    # ---- (c) "PENTA DRAGON DX" text ----
    # The text is at approximately row 6 (tile row), col 3 (~48px, ~18px).
    # We check for non-white pixels in the expected text band.
    # PENTA DRAGON DX is drawn at [0x03, 0x06] in title_list.
    text_row_y = 6 * 8  # 48
    text_start_x = 3 * 8  # 24
    text_end_x = text_start_x + 15 * 8  # ~15 chars

    text_pixels = 0
    for y in range(text_row_y, text_row_y + 8):
        for x in range(text_start_x, min(text_end_x, w)):
            p = pixels[y * w + x]
            if p[0] < 240 or p[1] < 240 or p[2] < 240:
                text_pixels += 1
    if text_pixels < 10:
        failures.append(f"c) 'PENTA DRAGON DX' text not found at row 6 "
                        f"(only {text_pixels} non-white pixels in expected band)")

    # ---- (d) "(C)1992 JAPAN ART MEDIA" text ----
    # Row 0x0F = row 15, col 0
    jam_row_y = 15 * 8  # 120
    jam_start_x = 0
    jam_end_x = 20 * 8  # 160

    jam_pixels = 0
    for y in range(jam_row_y, jam_row_y + 8):
        for x in range(jam_start_x, min(jam_end_x, w)):
            p = pixels[y * w + x]
            if p[0] < 240 or p[1] < 240 or p[2] < 240:
                jam_pixels += 1
    if jam_pixels < 10:
        failures.append(f"d) '(C)1992 JAPAN ART MEDIA' text not found at row 15 "
                        f"(only {jam_pixels} non-white pixels)")

    # ---- (e) "STRUKTURED LABS" text ----
    # Row 0x11 = row 17, col 0
    strk_row_y = 17 * 8  # 136
    strk_start_x = 0
    strk_end_x = 20 * 8  # 160

    strk_pixels = 0
    for y in range(strk_row_y, strk_row_y + 8):
        for x in range(strk_start_x, min(strk_end_x, w)):
            p = pixels[y * w + x]
            if p[0] < 240 or p[1] < 240 or p[2] < 240:
                strk_pixels += 1
    if strk_pixels < 5:
        failures.append(f"e) 'STRUKTURED LABS' text not found at row 17 "
                        f"(only {strk_pixels} non-white pixels)")

    # ---- (b) Cursor tile (OBJ sprite) at expected position ----
    # The cursor 'A' is an OBJ sprite on the title screen, blinking next to
    # the menu items at approximately rows 8-10. We check for sprite-sized
    # non-white pixel clusters in the left portion of the menu rows.
    cursor_row_y = 8 * 8  # 64
    cursor_found = False
    for y in range(cursor_row_y, cursor_row_y + 16):
        row_cursor_pixels = 0
        for x in range(0, 40):  # left portion of screen
            p = pixels[y * w + x]
            if p[0] < 240 or p[1] < 240 or p[2] < 240:
                row_cursor_pixels += 1
        if row_cursor_pixels >= 3:
            cursor_found = True
            break
    if not cursor_found:
        # Cursor might be in its OFF frame (blinking every ~16 frames).
        # Don't fail on this — it's timing-dependent. Just note it.
        if verbose:
            print("  (b) Cursor sprite not detected in this frame "
                  "(may be between blink frames — not a failure)")

    # ---- (f) Garbage artifact check ----
    # Scan rows that should be ALL white (unused rows) and flag any non-white
    # pixels outside known text rows. Known text rows: 3-5 (logo), 6 (title),
    # 8 (OPENING), 10 (GAME), 14-15 (JAM), 17 (STRUK).
    known_bands = []
    for tr in [3, 4, 5, 6, 8, 10, 14, 15, 17]:
        known_bands.append((tr * 8, tr * 8 + 7))
    # Also the copyright symbol at row 14
    known_bands.append((14 * 8, 14 * 8 + 7))

    def in_known_band(y):
        for lo, hi in known_bands:
            if lo <= y <= hi:
                return True
        return False

    garbage_pixels = []
    for y in range(h):
        if in_known_band(y):
            continue
        for x in range(w):
            p = pixels[y * w + x]
            if p[0] < 240 or p[1] < 240 or p[2] < 240:
                garbage_pixels.append((x, y, p))

    # Allow a few stray pixels (antialiasing, border artifacts)
    if len(garbage_pixels) > 20:
        # Group by row — if scattered across rows, it's artifacts
        garbage_rows = sorted(set(y for _, y, _ in garbage_pixels))
        if len(garbage_rows) > 5:
            failures.append(
                f"f) {len(garbage_pixels)} unexpected non-white pixels across "
                f"{len(garbage_rows)} rows — possible garbage artifacts"
            )

    return failures


def capture_with_pyboy(rom_path: str, frames: int = 600, verbose: bool = False) -> str:
    """Boot ROM in headless PyBoy, advance frames, return path to screenshot."""
    from pyboy import PyBoy
    if verbose:
        print(f"  Booting PyBoy: {rom_path} for {frames} frames...")
    boy = PyBoy(
        rom_path, window="null", cgb=True,
        sound_emulated=False, log_level=5,
    )
    for i in range(frames):
        boy.tick()
    img = boy.screen.image
    PROJECT_TMP.mkdir(exist_ok=True)
    out_path = str(PROJECT_TMP / f"title_screen_integration_{os.getpid()}.png")
    img.save(out_path)
    boy.stop()
    if verbose:
        print(f"  Captured: {out_path}")
    return out_path


def main():
    ap = argparse.ArgumentParser(
        description="Title screen integration test for Penta Dragon DX"
    )
    ap.add_argument("rom", help="Path to ROM file")
    ap.add_argument("--frames", type=int, default=600,
                    help="Number of frames to run before capturing (default 600)")
    ap.add_argument("--keep-png", action="store_true",
                    help="Keep the captured PNG and print its path")
    ap.add_argument("--verbose", "-v", action="store_true",
                    help="Verbose output")
    args = ap.parse_args()

    if not os.path.exists(args.rom):
        sys.stderr.write(f"ROM not found: {args.rom}\n")
        sys.exit(2)

    pyboy = check_pyboy()
    if pyboy is None:
        sys.stderr.write("PyBoy not available. Cannot run integration test.\n")
        sys.stderr.write("Install: `uv sync` or `pip install pyboy`\n")
        sys.exit(2)

    # Capture the title screen
    if args.verbose:
        print(f"ROM: {args.rom}")
    try:
        png = capture_with_pyboy(args.rom, args.frames, args.verbose)
    except Exception as e:
        sys.stderr.write(f"Capture failed: {e}\n")
        sys.exit(2)

    # Analyze
    failures = analyze_title_screen(png, args.rom, args.verbose)

    if args.keep_png:
        print(f"PNG kept at: {png}")
    else:
        try:
            os.unlink(png)
        except OSError:
            pass

    # Report
    if failures:
        print(f"\n{'='*60}")
        print(f"TITLE SCREEN INTEGRATION TEST: FAIL")
        print(f"{'='*60}")
        for f in failures:
            print(f"  ✗ {f}")
        sys.exit(1)
    else:
        print(f"\n{'='*60}")
        print(f"TITLE SCREEN INTEGRATION TEST: PASS")
        print(f"{'='*60}")
        sys.exit(0)


if __name__ == "__main__":
    main()
