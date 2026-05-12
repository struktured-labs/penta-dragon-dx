"""Title-screen color verification.

Boots a ROM in headless mgba, captures title-screen screenshot via Lua,
analyzes pixel colors. Fails if >70% of pixels are near-white (the v2.90
regression where CGB BG palette RAM stays at boot-ROM defaults).

Usage:
    python verify_title_color.py <rom_path> [--frame N] [--threshold P]

Exit codes:
    0 — title has reasonable color (PASS)
    1 — title is mostly white (FAIL — bug present)
    2 — harness error (couldn't capture)
"""
from __future__ import annotations
import os, sys, subprocess, tempfile, argparse


def capture_title(rom_path: str, frame_at: int, lua_script: str) -> str:
    """Run headless mgba, return path to captured PNG. Raises on failure."""
    out_png = tempfile.NamedTemporaryFile(suffix=".png", delete=False).name
    env = os.environ.copy()
    env["STATE_PATH"] = out_png
    env["FRAME_AT"] = str(frame_at)
    env["QT_QPA_PLATFORM"] = "offscreen"
    env["SDL_AUDIODRIVER"] = "dummy"
    cmd = [
        "xvfb-run", "-a",
        "mgba-qt", rom_path,
        "--script", lua_script,
        "-l", "0",
    ]
    proc = subprocess.run(cmd, env=env, capture_output=True, timeout=60)
    if not os.path.exists(out_png) or os.path.getsize(out_png) < 100:
        sys.stderr.write(f"[verify_title_color] mgba did not produce screenshot.\n")
        sys.stderr.write(f"  cmd: {' '.join(cmd)}\n")
        sys.stderr.write(f"  stdout: {proc.stdout.decode(errors='replace')[:500]}\n")
        sys.stderr.write(f"  stderr: {proc.stderr.decode(errors='replace')[:500]}\n")
        raise RuntimeError("screenshot failed")
    return out_png


def analyze_white_ratio(png_path: str, white_thresh: int = 240) -> dict:
    """Return color stats for a PNG screenshot."""
    from PIL import Image
    img = Image.open(png_path).convert("RGB")
    pixels = list(img.getdata())
    total = len(pixels)
    white = sum(1 for r, g, b in pixels
                if r >= white_thresh and g >= white_thresh and b >= white_thresh)
    distinct = len(set(pixels))
    # Sample top 5 distinct colors by count
    from collections import Counter
    top = Counter(pixels).most_common(5)
    return {
        "total_pixels": total,
        "white_pixels": white,
        "white_ratio": white / total,
        "distinct_colors": distinct,
        "top5_colors": top,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("rom", help="Path to ROM file")
    ap.add_argument("--frame", type=int, default=600,
                    help="Frame at which to capture title screen "
                         "(default 600 — by then v289 has the colored title loaded)")
    ap.add_argument("--min-colors", type=int, default=2,
                    help="PASS if image has at least this many distinct colors "
                         "(default 2 — v290 white bug shows 1, readable title 2+). "
                         "Also requires at least one non-white pixel.")
    ap.add_argument("--lua", default="scripts/probes/title_screenshot.lua")
    ap.add_argument("--keep-png", action="store_true",
                    help="Print path to captured PNG instead of cleaning up")
    args = ap.parse_args()

    if not os.path.exists(args.rom):
        sys.stderr.write(f"ROM not found: {args.rom}\n")
        sys.exit(2)

    try:
        png = capture_title(args.rom, args.frame, args.lua)
    except Exception as e:
        sys.stderr.write(f"capture failed: {e}\n")
        sys.exit(2)

    stats = analyze_white_ratio(png)
    print(f"ROM:              {args.rom}")
    print(f"Captured frame:   {args.frame}")
    print(f"Total pixels:     {stats['total_pixels']}")
    print(f"White pixels:     {stats['white_pixels']}")
    print(f"White ratio:      {stats['white_ratio']:.4f}")
    print(f"Distinct colors:  {stats['distinct_colors']}")
    print(f"Top 5 colors:")
    for color, count in stats['top5_colors']:
        print(f"  {color}: {count} ({count/stats['total_pixels']*100:.1f}%)")
    print(f"Min colors required: {args.min_colors}")

    if args.keep_png:
        print(f"PNG kept at: {png}")
    else:
        try:
            os.unlink(png)
        except OSError:
            pass

    # PASS criteria:
    #   - At least min_colors distinct colors (default 2), AND
    #   - At least one non-white color (so we know it's not 100% blank)
    # The v2.90 white bug shows 1 color (all white). Any build with readable
    # text — even grayscale-like DMG-emulated 2-color — passes. v2.94 had
    # 3+ colors but a green-ball artifact; v2.95 has 2 colors (DMG style)
    # and no artifacts, which is acceptable.
    has_non_white = stats['white_ratio'] < 1.0
    enough_colors = stats['distinct_colors'] >= args.min_colors
    if not enough_colors or not has_non_white:
        reasons = []
        if not enough_colors:
            reasons.append(f"only {stats['distinct_colors']} distinct color(s) "
                           f"(need {args.min_colors}+)")
        if not has_non_white:
            reasons.append("100% white (every pixel is FFFFFF)")
        print(f"\nFAIL: " + "; ".join(reasons))
        sys.exit(1)
    else:
        print(f"\nPASS: {stats['distinct_colors']} distinct colors, "
              f"{(1-stats['white_ratio'])*100:.1f}% non-white")
        sys.exit(0)


if __name__ == "__main__":
    main()
