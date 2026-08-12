from pyboy import PyBoy

rom = "rom/working/penta_dragon_dx_teleport.gb"
pb = PyBoy(rom, window="null", cgb=True)
mem = pb.memory

# Switch ROM bank to 13
# In PyBoy, to read bank 13 ROM, we can read from 0x4000 to 0x7FFF
# when MBC is set to bank 13 (via mem[0x2000] = 13).
mem[0x2000] = 13

print("Dumping bank 13 colorize handler (0x6E00 - 0x6E7F):")
code = [f"{mem[addr]:02X}" for addr in range(0x6E00, 0x6E80)]
for r in range(8):
    print(f"0x{0x6E00 + r*16:04X}: " + " ".join(code[r*16:(r+1)*16]))

pb.stop(save=False)
