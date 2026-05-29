"""Map bank 3 (so 0x1A2B's CALL 0x759B works), then enter via 0x1A2B.
Proves the boss arena renders. MBC1 bank select = write 0x2000-0x3FFF."""
import sys
from pyboy import PyBoy
rom="rom/working/penta_dragon_dx_FIXED.gb"
boss=int(sys.argv[1]) if len(sys.argv)>1 else 0
pb=PyBoy(rom, window="null", cgb=True); pb.set_emulation_speed(0)
mem=pb.memory; rf=pb.register_file
sched=[(180,186,'down'),(201,207,'a'),(261,267,'a'),(321,327,'a'),(381,387,'start'),(431,437,'a')]
held=None
for f in range(1,640):
    want=None
    for s,e,b in sched:
        if s<=f<e: want=b; break
    if want!=held:
        if held: pb.button_release(held)
        if want: pb.button_press(want)
        held=want
    pb.tick(1,True)
if held: pb.button_release(held)
for f in range(1400):
    if mem[0xD880]==0x02: break
    if f%40<8: pb.button_press('right')
    else: pb.button_release('right')
    pb.tick(1,True)
pb.button_release('right')
print(f"dungeon: D880=0x{mem[0xD880]:02X} FFC1={mem[0xFFC1]}")
if mem[0xD880]!=0x02:
    print("FAIL"); pb.stop(save=False); sys.exit(1)
pb.tick(10,True)
# Map bank 3, DISABLE interrupts (so VBlank can't corrupt bank mid-init),
# then simulate a CALL to 0x1A2B
mem[0xFFBA]=boss; mem[0xFFBF]=0
mem[0x2000]=3
mem[0xFF99]=3
ie_save=mem[0xFFFF]
mem[0xFFFF]=0                 # IE=0: disable all interrupts during arena init
ret=rf.PC
sp=rf.SP-2
mem[sp]=ret & 0xFF; mem[sp+1]=(ret>>8)&0xFF
rf.SP=sp
rf.PC=0x1A2B
print(f"bank3 mapped, IE=0, FFBA={boss}, CALL 0x1A2B (ret=0x{ret:04X})")
for i in range(300):
    pb.tick(1,True)
    if i in (0,1,3,7,15,39,99,199,299):
        print(f"  +{i+1}f: PC=0x{rf.PC:04X} D880=0x{mem[0xD880]:02X} FFB7=0x{mem[0xFFB7]:02X} FFBA={mem[0xFFBA]}")
expect=0x0C+boss
print(f"FINAL D880=0x{mem[0xD880]:02X} (want 0x{expect:02X}) FFBA={mem[0xFFBA]} -> {'PASS' if mem[0xD880]==expect else 'no'}")
pb.screen.image.save(f"/tmp/tp_bank3map_boss{boss}.png")
pb.stop(save=False)
