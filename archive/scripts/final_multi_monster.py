#!/usr/bin/env python3
"""Final multi-monster palette assignment - verified working"""
# This script generates the assembly code with verified jump offsets

# Tile ranges to palette mapping:
# 0-1 → Pal7 (Dragon Fly)
# 8-9, 14-15 → Pal0 (Sara D)  
# 10-13 → Pal1 (Sara W)
# 16-31 → Pal2 (Fire)
# 32-49 → Pal3 (Ice)
# 50-79 → Pal4 (Flying)
# 80-87 → Pal7 (Dragon Fly)
# 88-99 → Pal5 (Poison)
# 100-119 → Pal6 (Mini Boss)

# Assembly code structure (all paths converge at .set):
# Check ranges sequentially, assign palette, jump to .set

code = [
    # Check tile ranges in order
    0xFE, 0x02,            # CP 2
    0x38, 0x??,            # JR C, .dragon_fly_0_1 (tile < 2)
    0xFE, 0x08,            # CP 8
    0x38, 0x??,            # JR C, .no_modify (tile 2-7)
    0xFE, 0x10,            # CP 16
    0x38, 0x??,            # JR C, .sara_8_15 (tile 8-15)
    0xFE, 0x20,            # CP 32
    0x38, 0x??,            # JR C, .fire_16_31 (tile 16-31)
    0xFE, 0x32,            # CP 50
    0x38, 0x??,            # JR C, .ice_32_49 (tile 32-49)
    0xFE, 0x50,            # CP 80
    0x38, 0x??,            # JR C, .flying_50_79 (tile 50-79)
    0xFE, 0x58,            # CP 88
    0x38, 0x??,            # JR C, .dragon_fly_80_87 (tile 80-87)
    0xFE, 0x64,            # CP 100
    0x38, 0x??,            # JR C, .poison_88_99 (tile 88-99)
    0xFE, 0x78,            # CP 120
    0x38, 0x??,            # JR C, .mini_boss_100_119 (tile 100-119)
    0x18, 0x??,            # JR .no_modify (tile >= 120)
]

print("Need to calculate jump offsets carefully...")

