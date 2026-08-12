#!/usr/bin/env python3
"""Cold-boot cutscene enumeration probe.

Boots penta_dragon_dx_teleport.gb and samples (frame, D880, FFC1, FFBA, FFBF, FFD0)
every 60 frames for 6000 frames. On each D880 change vs the previous sample, takes
a screenshot to tmp/cutscene_d880_<value>_f<frame>.png and dumps the on-screen
BG (tile_id, palette) histogram (top 10).

Usage:
    .venv/bin/python scripts/probe_cutscene_d880.py
"""
import sys
from collections import Counter
from pathlib import Path

from pyboy import PyBoy

ROM = "/home/struktured/projects/penta-dragon-dx-claude/rom/working/penta_dragon_dx_teleport.gb"
OUT = Path("/home/struktured/projects/penta-dragon-dx-claude/tmp")
OUT.mkdir(parents=True, exist_ok=True)

# Scroll registers
LCDC = 0xFF40
SCY = 0xFF42
SCX = 0xFF43

# Game flags
D880 = 0xD880
FFC1 = 0xFFC1
FFBA = 0xFFBA
FFBF = 0xFFBF
FFD0 = 0xFFD0

BG_MAP_LO = 0x9800  # selected by LCDC bit3 (0)
BG_MAP_HI = 0x9C00  # selected by LCDC bit3 (1)


def sample_screen_bg(pyboy):
    """Return Counter of (tile_id, pal) for the 20x18 visible BG tiles.

    Reads VRAM directly using SCY/SCX + LCDC.bit3 (BG map base).
    Bank 0 holds tile IDs; bank 1 holds attribute bytes (palette = low 3 bits).
    """
    mem = pyboy.memory
    lcdc = mem[LCDC]
    scy = mem[SCY]
    scx = mem[SCX]
    map_base = BG_MAP_HI if (lcdc & 0x08) else BG_MAP_LO

    hist = Counter()
    for screen_row in range(18):
        for screen_col in range(20):
            map_y = ((scy + screen_row * 8) >> 3) & 0x1F
            map_x = ((scx + screen_col * 8) >> 3) & 0x1F
            addr = map_base + map_y * 32 + map_x
            tid = mem[0, addr]
            attr = mem[1, addr]
            pal = attr & 0x07
            hist[(tid, pal)] += 1
    return hist


def hist_top(hist, n=10):
    return [
        f"(t=0x{tid:02X},p{pal})x{cnt}"
        for (tid, pal), cnt in hist.most_common(n)
    ]


def main():
    pyboy = PyBoy(ROM, window="null", cgb=True, sound=False)
    print(f"Loaded {ROM}")

    prev_d880 = None
    samples = []
    transitions = []

    SAMPLE_EVERY = 60
    TOTAL_FRAMES = 6000

    for frame in range(1, TOTAL_FRAMES + 1):
        pyboy.tick()
        if frame % SAMPLE_EVERY != 0:
            continue
        mem = pyboy.memory
        d = mem[D880]
        c1 = mem[FFC1]
        ba = mem[FFBA]
        bf = mem[FFBF]
        d0 = mem[FFD0]
        lcdc = mem[LCDC]
        scy = mem[SCY]
        scx = mem[SCX]

        line = (
            f"f={frame:5d}  D880=0x{d:02X}  FFC1=0x{c1:02X}  "
            f"FFBA=0x{ba:02X}  FFBF=0x{bf:02X}  FFD0=0x{d0:02X}  "
            f"LCDC=0x{lcdc:02X}  SCY=0x{scy:02X}  SCX=0x{scx:02X}"
        )
        samples.append(line)

        if d != prev_d880:
            # D880 changed: capture screenshot + histogram
            shot = OUT / f"cutscene_d880_{d:02X}_f{frame:04d}.png"
            try:
                pyboy.screen.image.save(shot)
            except Exception as e:
                print(f"  screenshot fail: {e}")
            hist = sample_screen_bg(pyboy)
            top = hist_top(hist, 10)
            transitions.append(
                f"--- D880 0x{prev_d880 if prev_d880 is not None else 0:02X} "
                f"-> 0x{d:02X} @ f={frame}  ({shot.name})\n"
                f"    {line}\n"
                f"    BG top10: {top}"
            )
            print(transitions[-1])
            prev_d880 = d

    pyboy.stop()

    log = OUT / "cutscene_d880_log.txt"
    with open(log, "w") as f:
        f.write("# Per-sample log (every 60 frames)\n")
        for s in samples:
            f.write(s + "\n")
        f.write("\n# D880 transitions\n")
        for t in transitions:
            f.write(t + "\n")
    print(f"\nWrote {log}")
    print(f"Distinct D880 values seen: {sorted({int(s.split('D880=0x')[1][:2],16) for s in samples})}")


if __name__ == "__main__":
    main()
