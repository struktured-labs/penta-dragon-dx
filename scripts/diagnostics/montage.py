#!/usr/bin/env python3
"""Combine per-boss arena screenshots into one labeled grid for quick review.

Usage: python scripts/diagnostics/montage.py <out.png> <label1>=<img1> ...
Each img is upscaled 2x; labels are drawn above each tile. Missing images are
shown as a gray placeholder so the grid stays aligned.
"""
import sys
from PIL import Image, ImageDraw

SCALE = 2
PAD = 6
LABEL_H = 14
COLS = 3


def main():
    out = sys.argv[1]
    items = []
    for arg in sys.argv[2:]:
        label, _, path = arg.partition("=")
        items.append((label, path))
    if not items:
        print("no items")
        return
    tiles = []
    tw = th = 0
    for label, path in items:
        try:
            im = Image.open(path).convert("RGB")
            im = im.resize((im.width * SCALE, im.height * SCALE), Image.NEAREST)
        except Exception:
            im = Image.new("RGB", (160 * SCALE, 144 * SCALE), (40, 40, 40))
        tw = max(tw, im.width)
        th = max(th, im.height)
        tiles.append((label, im))
    cols = min(COLS, len(tiles))
    rows = (len(tiles) + cols - 1) // cols
    cell_w = tw + PAD
    cell_h = th + LABEL_H + PAD
    canvas = Image.new("RGB", (cols * cell_w + PAD, rows * cell_h + PAD), (20, 20, 20))
    d = ImageDraw.Draw(canvas)
    for i, (label, im) in enumerate(tiles):
        cx = PAD + (i % cols) * cell_w
        cy = PAD + (i // cols) * cell_h
        d.text((cx, cy), label, fill=(230, 230, 230))
        canvas.paste(im, (cx, cy + LABEL_H))
    canvas.save(out)
    print(f"wrote {out} ({cols}x{rows}, {len(tiles)} tiles)")


if __name__ == "__main__":
    main()
