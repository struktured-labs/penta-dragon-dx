#!/usr/bin/env python3
"""OPENING cutscene probe — captures BG content changes within D880=0x15.

Drives ROM past title (START), then mashes A every 30 frames to step through
the OPENING text + cutscene panels. Logs D880 every 30f. Saves a screenshot
+ histogram whenever EITHER D880 changes OR a distinct "scene signature"
(top-3 (tile,pal) tuple) emerges — to capture each cutscene panel.
"""
from collections import Counter
from pathlib import Path

from pyboy import PyBoy

ROM = "/home/struktured/projects/penta-dragon-dx-claude/rom/working/penta_dragon_dx_teleport.gb"
OUT = Path("/home/struktured/projects/penta-dragon-dx-claude/tmp/cutscene_intro_v2")
OUT.mkdir(parents=True, exist_ok=True)

LCDC, SCY, SCX = 0xFF40, 0xFF42, 0xFF43
D880, FFC1, FFBA, FFBF, FFD0 = 0xD880, 0xFFC1, 0xFFBA, 0xFFBF, 0xFFD0


def sample_bg(pyboy):
    mem = pyboy.memory
    lcdc, scy, scx = mem[LCDC], mem[SCY], mem[SCX]
    base = 0x9C00 if (lcdc & 0x08) else 0x9800
    hist = Counter()
    for r in range(18):
        for c in range(20):
            my = ((scy + r * 8) >> 3) & 0x1F
            mx = ((scx + c * 8) >> 3) & 0x1F
            a = base + my * 32 + mx
            hist[(mem[0, a], mem[1, a] & 0x07)] += 1
    return hist


def sig(hist):
    # First 4 non-blank (tile,pal) pairs as the scene signature
    nonblank = [k for k, _ in hist.most_common(20) if k[0] != 0x00][:4]
    return tuple(sorted(nonblank))


def main():
    pyboy = PyBoy(ROM, window="null", cgb=True, sound=False)
    # Boot
    for _ in range(360):
        pyboy.tick()
    # START -> OPENING
    pyboy.button_press("start"); [pyboy.tick() for _ in range(8)]; pyboy.button_release("start")
    for _ in range(60): pyboy.tick()

    log = []
    seen_sigs = {}
    seen_d880 = {}
    frame = 360 + 60

    INTERVAL = 8   # press A every N frames to keep cutscene advancing
    TOTAL = 8000
    last_press = 0

    while frame < TOTAL:
        pyboy.tick()
        frame += 1

        if frame - last_press >= INTERVAL:
            pyboy.button_press("a"); [pyboy.tick() for _ in range(2)]; pyboy.button_release("a")
            last_press = frame
            frame += 2

        if frame % 6 != 0:
            continue

        mem = pyboy.memory
        d = mem[D880]
        hist = sample_bg(pyboy)
        s = sig(hist)

        new_d = d not in seen_d880
        new_s = s not in seen_sigs

        if new_d or new_s:
            shot_name = f"d880_{d:02X}_f{frame:05d}_sig{abs(hash(s))%10000:04d}.png"
            shot = OUT / shot_name
            try: pyboy.screen.image.save(shot)
            except Exception as e: print("save fail", e)
            top = [(f"0x{t:02X}", f"p{p}", c) for (t, p), c in hist.most_common(10)]
            msg = (
                f"f={frame:5d}  D880=0x{d:02X}  FFC1=0x{mem[FFC1]:02X} "
                f"FFBA=0x{mem[FFBA]:02X} FFBF=0x{mem[FFBF]:02X} FFD0=0x{mem[FFD0]:02X} "
                f"NEW_D={new_d} NEW_S={new_s}\n"
                f"  shot={shot_name}\n  BG top10={top}"
            )
            print(msg)
            log.append(msg)
            seen_d880.setdefault(d, frame)
            seen_sigs[s] = frame

    pyboy.stop()
    out = OUT / "log.txt"
    out.write_text("\n".join(log))
    print(f"\nWrote {out}\nDistinct D880: {sorted(seen_d880.keys())}\nDistinct sigs: {len(seen_sigs)}")


if __name__ == "__main__":
    main()
