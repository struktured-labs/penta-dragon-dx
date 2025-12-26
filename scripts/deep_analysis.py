#!/usr/bin/env python3
"""Deep analysis of sprite palette assignment issues"""
from pathlib import Path

def analyze_rom_hook():
    """Analyze if the input handler hook is correctly installed"""
    rom_path = Path("rom/working/penta_dragon_cursor_dx.gb")
    if not rom_path.exists():
        print("❌ ROM not found")
        return
    
    rom = bytearray(rom_path.read_bytes())
    
    print("=" * 60)
    print("DEEP ANALYSIS: Sprite Palette Assignment")
    print("=" * 60)
    
    # 1. Check input handler hook
    input_handler_addr = 0x0824
    print(f"\n1. INPUT HANDLER HOOK ANALYSIS (0x{input_handler_addr:04X})")
    print(f"   Original ROM bytes: {rom[input_handler_addr]:02X} {rom[input_handler_addr+1]:02X} {rom[input_handler_addr+2]:02X}")
    
    if rom[input_handler_addr] == 0xCD:  # CALL instruction
        trampoline_low = rom[input_handler_addr + 1]
        trampoline_high = rom[input_handler_addr + 2]
        trampoline_addr = (trampoline_high << 8) | trampoline_low
        print(f"   ✅ Hooked: CALL 0x{trampoline_addr:04X}")
        
        # Check trampoline content
        print(f"\n   Trampoline at 0x{trampoline_addr:04X}:")
        trampoline_bytes = rom[trampoline_addr:trampoline_addr+20]
        print(f"   Bytes: {' '.join(f'{b:02X}' for b in trampoline_bytes)}")
        
        # Check if it calls sprite function
        sprite_func_addr = 0x7E00 + 0x150  # base + 0x150
        sprite_call_pattern = [0xCD, sprite_func_addr & 0xFF, (sprite_func_addr >> 8) & 0xFF]
        
        found_call = False
        for i in range(len(trampoline_bytes) - 2):
            if (trampoline_bytes[i] == sprite_call_pattern[0] and
                trampoline_bytes[i+1] == sprite_call_pattern[1] and
                trampoline_bytes[i+2] == sprite_call_pattern[2]):
                print(f"   ✅ Found CALL to sprite function at offset {i}")
                found_call = True
                break
        
        if not found_call:
            print(f"   ❌ Sprite function call NOT found in trampoline!")
            print(f"   Expected: CALL 0x{sprite_func_addr:04X}")
    else:
        print(f"   ❌ Input handler NOT hooked (first byte: 0x{rom[input_handler_addr]:02X})")
    
    # 2. Check sprite function
    sprite_func_addr = 0x7E00 + 0x150
    print(f"\n2. SPRITE FUNCTION ANALYSIS (0x{sprite_func_addr:04X})")
    sprite_func_bytes = rom[sprite_func_addr:sprite_func_addr+50]
    print(f"   First 20 bytes: {' '.join(f'{b:02X}' for b in sprite_func_bytes[:20])}")
    
    # Check if it uses FE00 (real OAM) or C000 (shadow OAM)
    if sprite_func_bytes[1] == 0x00 and sprite_func_bytes[2] == 0xFE:
        print("   ✅ Uses FE00 (real OAM)")
    elif sprite_func_bytes[1] == 0x00 and sprite_func_bytes[2] == 0xC0:
        print("   ✅ Uses C000 (shadow OAM)")
    else:
        print(f"   ⚠️  Unknown OAM base: {sprite_func_bytes[1]:02X} {sprite_func_bytes[2]:02X}")
    
    # 3. Check palettes
    print(f"\n3. PALETTE DATA ANALYSIS")
    palette_base = 0x7E00 + 64  # OBJ palettes start at base + 64
    pal0_bytes = rom[palette_base:palette_base+8]
    pal1_bytes = rom[palette_base+8:palette_base+16]
    pal7_bytes = rom[palette_base+56:palette_base+64]
    
    print(f"   Pal0 (Sara D): {' '.join(f'{b:02X}' for b in pal0_bytes)}")
    print(f"   Pal1 (Sara W): {' '.join(f'{b:02X}' for b in pal1_bytes)}")
    print(f"   Pal7 (Dragon Fly): {' '.join(f'{b:02X}' for b in pal7_bytes)}")
    
    # 4. Check original input handler
    original_input_addr = 0x7E00 + 0x350
    print(f"\n4. ORIGINAL INPUT HANDLER BACKUP (0x{original_input_addr:04X})")
    original_bytes = rom[original_input_addr:original_input_addr+10]
    print(f"   First 10 bytes: {' '.join(f'{b:02X}' for b in original_bytes)}")
    
    # 5. Analysis summary
    print(f"\n5. ANALYSIS SUMMARY")
    print(f"   Issues identified:")
    
    issues = []
    if rom[input_handler_addr] != 0xCD:
        issues.append("Input handler not hooked")
    
    # Check if sprite function modifies real OAM but game uses DMA
    if sprite_func_bytes[1] == 0x00 and sprite_func_bytes[2] == 0xFE:
        issues.append("Modifying real OAM (FE00) - game may overwrite via DMA")
        issues.append("Should modify shadow OAM (C000) before DMA transfer")
    
    if issues:
        for issue in issues:
            print(f"   ⚠️  {issue}")
    else:
        print(f"   ✅ Hook appears correctly installed")
    
    print(f"\n6. RECOMMENDATIONS")
    print(f"   1. Modify shadow OAM (C000) instead of real OAM (FE00)")
    print(f"   2. Hook OAM DMA transfer (0xFF46) to modify shadow OAM before transfer")
    print(f"   3. Or modify real OAM AFTER DMA transfer completes")
    print(f"   4. Verify hook is actually being called (add debug output)")

if __name__ == "__main__":
    analyze_rom_hook()

