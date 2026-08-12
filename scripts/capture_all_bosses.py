import sys
import os
from pathlib import Path
from pyboy import PyBoy

rom = "rom/working/penta_dragon_dx_teleport.gb"
out_dir = Path("tmp/boss_captures")
out_dir.mkdir(parents=True, exist_ok=True)

boss_names = {
    0: "Shalamar",
    1: "Riff",
    2: "Crystal_Dragon",
    3: "Cameo",
    4: "Ted",
    5: "Troop",
    6: "Faze",
    7: "Angela",
    8: "Penta_Dragon",
}

for boss, name in boss_names.items():
    print(f"=== Teleporting to Boss {boss}: {name} ===")
    pb = PyBoy(rom, window="null", cgb=True)
    pb.set_emulation_speed(0)
    mem = pb.memory
    rf = pb.register_file
    
    # Standard intro navigation
    sched = [
        (180, 186, 'down'),
        (201, 207, 'a'),
        (261, 267, 'a'),
        (321, 327, 'a'),
        (381, 387, 'start'),
        (431, 437, 'a')
    ]
    held = None
    for f in range(1, 640):
        want = None
        for s, e, b in sched:
            if s <= f < e:
                want = b
                break
        if want != held:
            if held: pb.button_release(held)
            if want: pb.button_press(want)
            held = want
        pb.tick(1, True)
    if held:
        pb.button_release(held)
        
    for f in range(1400):
        if mem[0xD880] == 0x02:
            break
        if f % 40 < 8:
            pb.button_press('right')
        else:
            pb.button_release('right')
        pb.tick(1, True)
    pb.button_release('right')
    
    pb.tick(10, True)
    
    # Inject teleport to the boss arena!
    mem[0xFFBA] = boss
    mem[0xFFBF] = 0
    mem[0x2000] = 3
    mem[0xFF99] = 3
    mem[0xFFFF] = 0  # Disable interrupts for arena load
    
    ret = rf.PC
    sp = rf.SP - 2
    mem[sp] = ret & 0xFF
    mem[sp+1] = (ret >> 8) & 0xFF
    rf.SP = sp
    rf.PC = 0x1A2B
    
    # Let the game transition and settle (about 300-400 frames to fade in)
    for _ in range(350):
        pb.tick(1, True)
        
    img_path = out_dir / f"boss_{boss}_{name}.png"
    pb.screen.image.save(img_path)
    print(f"  Saved screenshot to {img_path}")
    pb.stop(save=False)

print("Done capturing all bosses!")
