"""Quick: print player HP and boss state for each save state."""
import sys, os
sys.path.insert(0, "/home/struktured/projects/penta-dragon-dx-claude/rl")
from pyboy import PyBoy
from penta_rl.state import read_state

CHEAT = "/home/struktured/projects/penta-dragon-dx-claude/rom/Penta Dragon (J) [A-fix-cheat-noPhase].gb"
REAL = "/home/struktured/projects/penta-dragon-dx-claude/rom/Penta Dragon (J) [A-fix].gb"
SAVES = "/home/struktured/projects/penta-dragon-dx-claude/rl/saves"

for rom_label, rom_path in [("real", REAL), ("cheat", CHEAT)]:
    for f in sorted(os.listdir(SAVES)):
        if not f.endswith(".state"):
            continue
        path = os.path.join(SAVES, f)
        try:
            pb = PyBoy(rom_path, window="null", sound_emulated=False, cgb=True)
            with open(path, "rb") as fh:
                pb.load_state(fh)
            for _ in range(2):
                pb.tick()
            s = read_state(pb)
            print(f"  [{rom_label}] {f}: scene={hex(s.scene)} sect={s.section} mb={s.miniboss} "
                  f"boss_hp={hex(s.boss_hp)} player_hp={s.player_hp} lvl={s.level}")
            pb.stop()
        except Exception as e:
            print(f"  [{rom_label}] {f}: ERROR {e}")
