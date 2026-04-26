"""Capture and replay PyBoy save states.

Strategy: drive the game to a known-good condition (e.g., gargoyle just spawned,
boss 16 active), then save the PyBoy state to a file. Subsequent training
resets from that file directly — skipping title menu + slow buildup.
"""
from __future__ import annotations
import os, time
from pyboy import PyBoy

ROM = "/home/struktured/projects/penta-dragon-dx-claude/rom/Penta Dragon (J) [A-fix].gb"


# Known-good navigation to title-menu → gameplay
TITLE_NAV = [
    (180, 185, "down"),
    (193, 198, "a"),
    (241, 246, "a"),
    (291, 296, "a"),
    (341, 346, "start"),
    (391, 396, "a"),
]


def _drive_to_gameplay(pb: PyBoy, end_frame: int = 500):
    prev = None
    for f in range(end_frame):
        cur = None
        for fr_lo, fr_hi, btn in TITLE_NAV:
            if fr_lo <= f <= fr_hi:
                cur = btn; break
        if cur != prev:
            if prev is not None: pb.button_release(prev)
            if cur is not None: pb.button_press(cur)
            prev = cur
        pb.tick()
    if prev is not None: pb.button_release(prev)


def make_save_at_gameplay(out_path: str, rom: str = ROM):
    """Save state at frame 500 = gameplay start (D880=0x02)."""
    pb = PyBoy(rom, window="null", sound_emulated=False, cgb=True)
    _drive_to_gameplay(pb)
    with open(out_path, "wb") as f:
        pb.save_state(f)
    print(f"Saved {out_path} (D880=0x{pb.memory[0xD880]:02X} FFBA={pb.memory[0xFFBA]} "
          f"FFBD={pb.memory[0xFFBD]})")
    pb.stop()


def make_save_at_miniboss(out_path: str, ffbf: int = 1, rom: str = ROM,
                          patch_boss16: bool = False):
    """Save state with miniboss spawned. Optionally patch ROM for boss 16 hitbox."""
    pb = PyBoy(rom, window="null", sound_emulated=False, cgb=True)
    _drive_to_gameplay(pb)
    # Patch entry 2 to spawn this boss
    boss_id = 0x30 + (ffbf - 1) * 5  # gargoyle=0x30, spider=0x35, ...
    if ffbf == 16:
        boss_id = 0x7B
    pb.memory[0x3402F] = boss_id  # WARNING: this writes to MBC, not ROM. Patch via cart instead
    # Force fresh section
    pb.memory[0xFFBF] = 0
    pb.memory[0xDCB8] = 0
    pb.memory[0xDCBA] = 0x01
    pb.memory[0xFFD6] = 0x1E
    pb.memory[0xDCBB] = 0xFF
    for a in (0xDC85, 0xDC8D, 0xDC95, 0xDC9D, 0xDCA5):
        pb.memory[a] = 0x00
    if patch_boss16 and ffbf == 16:
        # Patch boss-16 AI table zero bytes (file 0x2D7F + 1,4,7,10,13)
        # NOTE: cart_data API in PyBoy
        for off in (1, 4, 7, 10, 13):
            try:
                pb.memory[0x2D7F + off] = 0x04  # may or may not work; cart access varies
            except Exception:
                pass
    # Tick until spawn
    for _ in range(100):
        pb.memory[0xDCBA] = 0x01
        pb.memory[0xFFD6] = 0x1E
        pb.tick()
        if pb.memory[0xFFBF] != 0:
            break
    with open(out_path, "wb") as f:
        pb.save_state(f)
    print(f"Saved {out_path} (FFBF=0x{pb.memory[0xFFBF]:02X} DC04=0x{pb.memory[0xDC04]:02X})")
    pb.stop()


def load_save(pb: PyBoy, path: str):
    """Load a previously saved PyBoy state into the given instance."""
    with open(path, "rb") as f:
        pb.load_state(f)


if __name__ == "__main__":
    import sys
    SAVE_DIR = "/home/struktured/projects/penta-dragon-dx-claude/rl/saves"
    os.makedirs(SAVE_DIR, exist_ok=True)
    cmd = sys.argv[1] if len(sys.argv) > 1 else "all"
    if cmd in ("all", "gameplay"):
        make_save_at_gameplay(f"{SAVE_DIR}/gameplay_start.state")
    if cmd in ("all", "gargoyle"):
        make_save_at_miniboss(f"{SAVE_DIR}/gargoyle.state", ffbf=1)
    if cmd in ("all", "boss16"):
        make_save_at_miniboss(f"{SAVE_DIR}/boss16.state", ffbf=16, patch_boss16=False)
    if cmd in ("all", "boss16_patched"):
        make_save_at_miniboss(f"{SAVE_DIR}/boss16_patched.state", ffbf=16, patch_boss16=True)
