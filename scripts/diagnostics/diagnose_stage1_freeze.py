#!/usr/bin/env python3
"""Print CPU/state receipts for a Stage 1 candidate that stops progressing."""

from __future__ import annotations

import argparse
from collections import Counter
from pathlib import Path

from pyboy import PyBoy


SCHEDULE = (
    (180, 186, "down"),
    (201, 207, "a"),
    (261, 267, "a"),
    (321, 327, "a"),
    (381, 387, "start"),
    (431, 437, "a"),
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("rom", type=Path)
    parser.add_argument("--frames", type=int, default=1800)
    args = parser.parse_args()

    pyboy = PyBoy(str(args.rom.resolve()), window="null", cgb=True)
    pyboy.set_emulation_speed(0)
    memory = pyboy.memory
    registers = pyboy.register_file
    held = None
    pc_histogram: Counter[int] = Counter()
    first_stage1 = -1

    for frame in range(1, args.frames + 1):
        wanted = next(
            (
                button
                for start, end, button in SCHEDULE
                if start <= frame < end
            ),
            None,
        )
        if frame > 700 and memory[0xD880] == 2 and memory[0xFFC1] == 1:
            wanted = "right"
            if first_stage1 < 0:
                first_stage1 = frame
        if wanted != held:
            if held:
                pyboy.button_release(held)
            if wanted:
                pyboy.button_press(wanted)
            held = wanted
        pyboy.tick(1, True)
        if memory[0xD880] == 2:
            pc_histogram[registers.PC] += 1
        if frame % 120 == 0:
            print(
                f"f={frame:4d} PC={registers.PC:04X} SP={registers.SP:04X} "
                f"D880={memory[0xD880]:02X} FFC1={memory[0xFFC1]:02X} "
                f"FFBD={memory[0xFFBD]:02X} SVBK={memory[0xFF70]:02X} "
                f"SCX={memory[0xFF43]:02X} DC00={memory[0xDC00]:02X}"
            )
    if held:
        pyboy.button_release(held)
    print(f"first_stage1={first_stage1}")
    print(
        "stage1_pc_histogram="
        + ",".join(
            f"{pc:04X}:{count}"
            for pc, count in pc_histogram.most_common(20)
        )
    )
    pyboy.stop(save=False)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
