from pyboy import PyBoy

rom = "rom/working/penta_dragon_dx_teleport.gb"
pb = PyBoy(rom, window="null", cgb=True)
mem = pb.memory

mem[0x2000] = 13

print("Dumping bank 13 bg_sweep (0x6CD0 - 0x6D4F):")
code = [f"{mem[addr]:02X}" for addr in range(0x6CD0, 0x6D50)]
for r in range(8):
    print(f"0x{0x6CD0 + r*16:04X}: " + " ".join(code[r*16:(r+1)*16]))

pb.stop(save=False)
