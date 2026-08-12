import sys
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

for boss, name in sorted(boss_names.items()):
    print(f"\n=== Headless Boot & Capture for Boss {boss}: {name} ===")
    pb = PyBoy(rom, window="null", cgb=True)
    pb.set_emulation_speed(0)
    mem = pb.memory

    # 1. Skip Title Screen
    sched = [
        (180, 186, 'down'),
        (201, 207, 'a'),
        (261, 267, 'a'),
        (291, 296, 'a'),
        (341, 346, 'start'),
        (410, 415, 'a')
    ]
    held = None
    for f in range(1, 450):
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

    # 2. Wait for Dungeon
    for f in range(1000):
        if mem[0xD880] == 0x02:
            break
        pb.tick(1, True)
    pb.tick(30, True)

    # 3. Trigger Teleport
    # FFBA target pre-set (INC wraps to target)
    target_ffba = 8 if boss == 0 else (boss - 1)
    mem[0xFFBA] = target_ffba
    mem[0xDF0C] = 0
    mem[0xDF1D] = 0

    pb.button_press('select')
    pb.button_press('start')
    for _ in range(10):
        pb.tick(1, True)
    pb.button_release('select')
    pb.button_release('start')

    # 4. Wait for Arena to Settle
    for f in range(400):
        pb.tick(1, True)
        if 0x0C <= mem[0xD880] <= 0x14:
            if f > 250:
                break

    pb.tick(30, True)

    # 5. Save Screenshot & Scale 8x (Nearest-Neighbor for crisp pixel-art)
    img_path = out_dir / f"boss_{boss}_{name}.png"
    img = pb.screen.image
    from PIL import Image
    img_large = img.resize((img.width * 8, img.height * 8), Image.NEAREST)
    img_large.save(img_path)
    print(f"  Successfully captured and scaled 8x: {img_path}!")
    pb.stop(save=False)

print("\nDone capturing all 9 bosses naturally!")
