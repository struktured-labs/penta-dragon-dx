#!/usr/bin/env python3
"""Extract tile-ID set for each intro cutscene panel.

Drives ROM through OPENING, samples BG at known panel frames, prints
distinct tile IDs grouped by 16-tile bands (so we can pick palette
overlays by ID range).
"""
from collections import Counter
from pyboy import PyBoy

ROM = "/home/struktured/projects/penta-dragon-dx-claude/rom/working/penta_dragon_dx_teleport.gb"

# (frame, label) — frames where the panel is fully rendered
PANELS = [
    (3000, "TEXT_ONLY_FIRST_BOX"),
    (3600, "TREASURE_SCROLL_INIT"),
    (4200, "TREASURE_SCROLL_FULL"),
    (4800, "TREASURE_SCROLL_TEXT"),
    (5400, "SARA_FACE_INIT"),
    (6000, "SARA_FACE"),
    (6600, "SARA_FACE_TEXT"),
    (7200, "SARA_NAME_TEXT"),
    (7800, "DRAGON_EYES_INIT"),
    (8400, "DRAGON_EYES_FULL"),
]


def sample(p):
    mem = p.memory
    lcdc, scy, scx = mem[0xFF40], mem[0xFF42], mem[0xFF43]
    base = 0x9C00 if (lcdc & 0x08) else 0x9800
    bg_tiles = Counter()
    for r in range(18):
        for c in range(20):
            my = ((scy + r * 8) >> 3) & 0x1F
            mx = ((scx + c * 8) >> 3) & 0x1F
            a = base + my * 32 + mx
            bg_tiles[mem[0, a]] += 1
    return bg_tiles


def band(tid):
    return (tid // 16) * 16


def main():
    p = PyBoy(ROM, window="null", cgb=True, sound=False)
    for _ in range(360): p.tick()
    p.button_press("start"); [p.tick() for _ in range(8)]; p.button_release("start")
    for _ in range(60): p.tick()
    frame = 420
    last_press = 0
    panels_left = list(PANELS)
    while panels_left and frame < 10000:
        p.tick(); frame += 1
        if frame - last_press >= 8:
            p.button_press("a"); [p.tick() for _ in range(2)]; p.button_release("a")
            last_press = frame; frame += 2
        tgt = panels_left[0]
        if frame >= tgt[0]:
            tiles = sample(p)
            # Group by 0x10-band
            bands = Counter()
            for tid, cnt in tiles.items():
                bands[band(tid)] += cnt
            # Distinct non-blank tile IDs
            nonblank = sorted([t for t in tiles if t != 0x00])
            print(f"\n=== {tgt[1]}  @ f={frame} ===")
            print(f"  Bands: {[(f'0x{b:02X}', c) for b,c in sorted(bands.items()) if c>0]}")
            print(f"  Top tiles: {[(f'0x{t:02X}', c) for t,c in tiles.most_common(20) if t!=0]}")
            print(f"  Distinct non-blank IDs ({len(nonblank)}): {[f'0x{t:02X}' for t in nonblank]}")
            panels_left.pop(0)
    p.stop()


if __name__ == "__main__":
    main()
