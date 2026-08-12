#!/usr/bin/env python3
"""Cutscene D880 probe — DRIVES past title to capture intro cutscenes.

Cold-boots penta_dragon_dx_teleport.gb. After ~2000 frames (past PyBoy boot
+ YANOMAN), presses START to launch OPENING. Samples (frame, D880, FFC1,
FFBA, FFBF, FFD0) every 30 frames for 12000 frames. On every D880 change,
saves a screenshot and dumps the BG (tile, palette) histogram (top 10).
"""
import sys
from collections import Counter
from pathlib import Path

from pyboy import PyBoy

ROM = "/home/struktured/projects/penta-dragon-dx-claude/rom/working/penta_dragon_dx_teleport.gb"
OUT = Path("/home/struktured/projects/penta-dragon-dx-claude/tmp")
OUT.mkdir(parents=True, exist_ok=True)

LCDC = 0xFF40
SCY = 0xFF42
SCX = 0xFF43

D880 = 0xD880
FFC1 = 0xFFC1
FFBA = 0xFFBA
FFBF = 0xFFBF
FFD0 = 0xFFD0

BG_MAP_LO = 0x9800
BG_MAP_HI = 0x9C00


def sample_screen_bg(pyboy):
    mem = pyboy.memory
    lcdc = mem[LCDC]
    scy = mem[SCY]
    scx = mem[SCX]
    map_base = BG_MAP_HI if (lcdc & 0x08) else BG_MAP_LO
    hist = Counter()
    for r in range(18):
        for col in range(20):
            map_y = ((scy + r * 8) >> 3) & 0x1F
            map_x = ((scx + col * 8) >> 3) & 0x1F
            addr = map_base + map_y * 32 + map_x
            tid = mem[0, addr]
            attr = mem[1, addr]
            hist[(tid, attr & 0x07)] += 1
    return hist


def hist_top(h, n=10):
    return [f"(t=0x{t:02X},p{p})x{c}" for (t, p), c in h.most_common(n)]


def press(pyboy, btn, hold=4, gap=4):
    pyboy.button_press(btn)
    for _ in range(hold):
        pyboy.tick()
    pyboy.button_release(btn)
    for _ in range(gap):
        pyboy.tick()


def main():
    pyboy = PyBoy(ROM, window="null", cgb=True, sound=False)
    print(f"Loaded {ROM}")

    # Boot past PyBoy splash (~60f) and YANOMAN/title intro
    INTRO_HOLD = 360
    for _ in range(INTRO_HOLD):
        pyboy.tick()

    # Press START to begin OPENING
    print(f"@ f={INTRO_HOLD}: pressing START (OPENING)")
    press(pyboy, "start", hold=8, gap=8)
    # Possibly need a second confirm
    for _ in range(60):
        pyboy.tick()
    press(pyboy, "a", hold=4, gap=4)

    prev = None
    samples = []
    transitions = []

    frame = INTRO_HOLD + 24
    TOTAL = 12000
    SAMPLE = 30
    last_input = 0
    while frame < TOTAL:
        pyboy.tick()
        frame += 1

        # Every ~600 frames, press A in case a textbox is waiting
        if frame - last_input > 240:
            press(pyboy, "a", hold=2, gap=2)
            last_input = frame
            frame += 4

        if frame % SAMPLE:
            continue

        mem = pyboy.memory
        d = mem[D880]
        c1 = mem[FFC1]
        ba = mem[FFBA]
        bf = mem[FFBF]
        d0 = mem[FFD0]
        line = (
            f"f={frame:5d}  D880=0x{d:02X}  FFC1=0x{c1:02X}  "
            f"FFBA=0x{ba:02X}  FFBF=0x{bf:02X}  FFD0=0x{d0:02X}"
        )
        samples.append(line)

        if d != prev:
            shot = OUT / f"cutscene_d880_{d:02X}_f{frame:05d}.png"
            try:
                pyboy.screen.image.save(shot)
            except Exception as e:
                print(f"  screenshot fail: {e}")
            hist = sample_screen_bg(pyboy)
            top = hist_top(hist, 10)
            msg = (
                f"--- D880 0x{(prev if prev is not None else 0):02X} -> "
                f"0x{d:02X} @ f={frame} ({shot.name})\n    {line}\n"
                f"    BG top10: {top}"
            )
            transitions.append(msg)
            print(msg)
            prev = d

    pyboy.stop()

    log = OUT / "cutscene_d880_intro_log.txt"
    with open(log, "w") as f:
        f.write("# Per-sample log (every 30 frames)\n")
        for s in samples:
            f.write(s + "\n")
        f.write("\n# D880 transitions\n")
        for t in transitions:
            f.write(t + "\n")
    distinct = sorted({int(s.split("D880=0x")[1][:2], 16) for s in samples})
    print(f"\nWrote {log}")
    print(f"Distinct D880 values seen: {[hex(x) for x in distinct]}")


if __name__ == "__main__":
    main()
