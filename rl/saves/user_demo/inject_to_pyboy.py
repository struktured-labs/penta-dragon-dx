"""Inject mgba state dumps into PyBoy and save as PyBoy state.

Pipeline:
1. Boot PyBoy from gameplay_start (sets up CPU registers, MBC banking, etc.)
2. Write WRAM (0xC000-0xDFFF), HRAM (0xFF80-0xFFFE), OAM (0xFE00-0xFE9F) from mgba dumps
3. Tick a few frames to let game populate sprite positions and re-render
4. Save as PyBoy save state

Usage:
    python inject_to_pyboy.py <prefix> <output.state>

Where <prefix> is the basename of the mgba dumps (e.g., /tmp/pdragon_dump_BOSS1)
expecting <prefix>_wram.bin, _hram.bin, _oam.bin, _meta.txt
"""
from __future__ import annotations
import os, sys
sys.path.insert(0, "/home/struktured/projects/penta-dragon-dx-claude/rl")

ROM = "/home/struktured/projects/penta-dragon-dx-claude/rom/Penta Dragon (J) [A-fix].gb"
GAMEPLAY_START = "/home/struktured/projects/penta-dragon-dx-claude/rl/saves/gameplay_start.state"


def inject_state(prefix: str, output: str, settle_frames: int = 30):
    from pyboy import PyBoy
    pb = PyBoy(ROM, window="null", sound_emulated=False, cgb=True)
    # Bootstrap from gameplay_start to set up MBC banking, registers
    with open(GAMEPLAY_START, "rb") as fh:
        pb.load_state(fh)
    print(f"[init] FFBA={pb.memory[0xFFBA]} FFBD={pb.memory[0xFFBD]} D880=0x{pb.memory[0xD880]:02x}")

    # Inject WRAM (0xC000-0xDFFF, 8192 bytes)
    with open(f"{prefix}_wram.bin", "rb") as fh:
        wram = fh.read()
    assert len(wram) == 0x2000, f"WRAM size mismatch: {len(wram)} vs 0x2000"
    for i, b in enumerate(wram):
        pb.memory[0xC000 + i] = b

    # Inject HRAM (0xFF80-0xFFFE, 127 bytes)
    with open(f"{prefix}_hram.bin", "rb") as fh:
        hram = fh.read()
    assert len(hram) == 0x7F, f"HRAM size mismatch: {len(hram)} vs 0x7F"
    for i, b in enumerate(hram):
        pb.memory[0xFF80 + i] = b

    # Inject OAM (0xFE00-0xFE9F, 160 bytes)
    with open(f"{prefix}_oam.bin", "rb") as fh:
        oam = fh.read()
    assert len(oam) == 0xA0, f"OAM size mismatch: {len(oam)} vs 0xA0"
    for i, b in enumerate(oam):
        pb.memory[0xFE00 + i] = b

    # Verify injected state
    print(f"[after-inject] FFBA={pb.memory[0xFFBA]} FFBD={pb.memory[0xFFBD]} "
          f"FFBF={pb.memory[0xFFBF]} FFC0={pb.memory[0xFFC0]} "
          f"D880=0x{pb.memory[0xD880]:02x} DCB8={pb.memory[0xDCB8]} "
          f"DCBB=0x{pb.memory[0xDCBB]:02x}")

    # Settle: tick frames so the game can re-render sprites and stabilize
    for _ in range(settle_frames):
        pb.tick()
    print(f"[settled] FFBA={pb.memory[0xFFBA]} FFBD={pb.memory[0xFFBD]} "
          f"FFBF={pb.memory[0xFFBF]} D880=0x{pb.memory[0xD880]:02x} "
          f"DCB8={pb.memory[0xDCB8]} FE04={pb.memory[0xFE04]} FE05={pb.memory[0xFE05]}")

    # Save state
    with open(output, "wb") as fh:
        pb.save_state(fh)
    print(f"[saved] {output}")
    pb.stop()


if __name__ == "__main__":
    prefix = sys.argv[1]
    output = sys.argv[2]
    settle = int(sys.argv[3]) if len(sys.argv) > 3 else 30
    inject_state(prefix, output, settle)
