"""Diagnostic: forcibly write DCBB=0 and trace what game does after.

If kill detection is broken on cheat ROM, we'll see: boss_hp goes to 0 but
section never advances and miniboss flag never clears.
"""
import sys, os
sys.path.insert(0, "/home/struktured/projects/penta-dragon-dx-claude/rl")
from pyboy import PyBoy
from penta_rl.state import read_state

CHEAT = "/home/struktured/projects/penta-dragon-dx-claude/rom/Penta Dragon (J) [A-fix-cheat-noPhase].gb"
REAL  = "/home/struktured/projects/penta-dragon-dx-claude/rom/Penta Dragon (J) [A-fix].gb"
SAVES = "/home/struktured/projects/penta-dragon-dx-claude/rl/saves"

def force_kill_test(rom_path, save_name, label):
    print(f"\n=== {label} ===")
    pb = PyBoy(rom_path, window="null", sound_emulated=False, cgb=True)
    with open(os.path.join(SAVES, save_name), "rb") as fh:
        pb.load_state(fh)
    # Tick a couple to settle
    for _ in range(4):
        pb.tick()
    s = read_state(pb)
    print(f"start: scene={hex(s.scene)} sect={s.section} mb={s.miniboss} boss_hp={hex(s.boss_hp)} ply_hp={s.player_hp} lvl={s.level}")
    # FORCE DCBB=0
    pb.memory[0xDCBB] = 0x00
    print(f"forced DCBB=0; ticking 240 frames...")
    last_log = None
    for i in range(240):
        pb.tick()
        s = read_state(pb)
        sig = (hex(s.scene), s.section, s.miniboss, hex(s.boss_hp))
        if sig != last_log:
            print(f"  frame {i}: scene={sig[0]} sect={sig[1]} mb={sig[2]} boss_hp={sig[3]} ply_hp={s.player_hp}")
            last_log = sig
    pb.stop()

force_kill_test(CHEAT, "cheat_gargoyle.state", "CHEAT ROM + cheat_gargoyle (DCBB=0x10 init)")
force_kill_test(REAL,  "gargoyle.state",       "REAL  ROM + gargoyle (DCBB=0xFF init)")
