"""Patches display initialization code for CGB compatibility."""

def patch_vblank_wait_for_cgb(rom_data: bytearray) -> tuple[bytearray, list[tuple[int, bytes, bytes]]]:
    """
    Patch the VBlank wait function at 0x0067 to work in CGB mode.
    
    Original code at 0x0067:
        F0 FF       LDH A,[FFFF]    ; Save interrupt enable
        E0 98       LDH [FF98],A    ; Store it
        CB 87       RES 0,A         ; Clear bit 0
        F0 44       LDH A,[FF44]    ; Read LY (scanline)
        FE 91       CP 91h          ; Compare with 145 (VBlank)
        38 FA       JR C,006Dh      ; Loop if < 145
        F0 40       LDH A,[FF40]    ; Read LCDC
        E6 7F       AND 7Fh         ; Clear bit 7 (LCD off)
        E0 40       LDH [FF40],A    ; Write LCDC
        F0 98       LDH A,[FF98]    ; Restore interrupt enable
        E0 FF       LDH [FFFF],A
        C9          RET
    
    Problem: In CGB mode, the LY register timing differs and LCD off/on sequence
    can cause white screen. The game expects DMG behavior.
    
    Solution: Make LCD operations CGB-aware or skip them entirely in CGB mode.
    We'll patch to detect CGB mode and skip the problematic LCD off operation.
    """
    # Ensure we have a mutable bytearray
    if not isinstance(rom_data, bytearray):
        rom_data = bytearray(rom_data)
    
    patches = []
    
    # Strategy: Replace the function with CGB-detection version
    # New code:
    #   Check if CGB mode (KEY1 register bit 7)
    #   If CGB: skip LCD operations, just return
    #   If DMG: run original code
    
    original_addr = 0x0067
    original_code = rom_data[original_addr:original_addr + 23]  # Full function
    
    # New code for 0x0067:
    new_code = bytearray([
        # Check CGB mode
        0xF0, 0x4D,        # LDH A,[FF4D]  ; Read KEY1 (CGB double-speed register)
        0xCB, 0x7F,        # BIT 7,A       ; Check bit 7 (1 = CGB mode)
        0x20, 0x01,        # JR NZ,skip    ; If CGB, skip to RET
        0xC9,              # RET           ; Early return for CGB
        
        # Original DMG code (starting from LDH A,[FFFF])
        0xF0, 0xFF,        # LDH A,[FFFF]
        0xE0, 0x98,        # LDH [FF98],A
        0xCB, 0x87,        # RES 0,A (CB 87 actually means RES 0,A)
        0xF0, 0x44,        # LDH A,[FF44]  ; @006D in original
        0xFE, 0x91,        # CP 91h
        0x38, 0xFA,        # JR C,-6 (loop back to 006D equivalent)
        0xF0, 0x40,        # LDH A,[FF40]
        0xE6, 0x7F,        # AND 7Fh
        0xE0, 0x40,        # LDH [FF40],A
        0xF0, 0x98,        # LDH A,[FF98]
        0xE0, 0xFF,        # LDH [FFFF],A
        0xC9,              # RET
    ])
    
    # Verify size matches (original is 23 bytes, new is 7 + 23 = 30 bytes)
    # Wait, that's too long. Let me recalculate...
    # Actually, we need to fit in same space or find free space
    
    # Better approach: Just NOP out the LCD operations for CGB
    # Even simpler: Make the function just RET in CGB mode
    
    # Simplest patch: At 0x0067, add CGB check and early return
    # But we only have 23 bytes total. Let's be surgical:
    
    # Replace LCD off sequence (0x0073-0x0077) with NOPs in CGB mode
    # Actually, let's just patch the LCDC write itself
    
    # New strategy: Conditional LCD operations
    # At 0x0073 (before "LDH A,[FF40]"), insert CGB check
    
    # Even simpler: Just make the entire function a NOP in CGB mode
    # Replace first few bytes with:
    #   F0 4D        LDH A,[FF4D]
    #   CB 7F        BIT 7,A
    #   C8           RET Z (return if not CGB - wait, reversed)
    #   C9           RET (return if CGB)
    # That's only 5 bytes, then continue with original code
    
    # Let me think... BIT 7,A sets Z flag if bit is 0
    # In CGB mode, bit 7 of KEY1 should be 1, so Z will be clear
    # RET NZ would return if CGB mode
    
    # FIXED APPROACH: NOP out the LCD off instructions directly.
    # We're building a CGB-only ROM, so LCD off during VBlank is unnecessary
    # and can corrupt VRAM bank 1 attributes.
    #
    # Original layout (23 bytes at 0x0067):
    #   0x0067: F0 FF  LDH A,[FFFF]   ; Save IE
    #   0x0069: E0 98  LDH [FF98],A   ; Store IE
    #   0x006B: CB 87  RES 0,A        ; (unused side effect)
    #   0x006D: F0 44  LDH A,[FF44]   ; Read LY
    #   0x006F: FE 91  CP 91h         ; Compare 145
    #   0x0071: 38 FA  JR C,-6        ; Loop if < VBlank
    #   0x0073: F0 40  LDH A,[FF40]   ; ← LCD OFF starts here
    #   0x0075: E6 7F  AND 7Fh        ; ← Clear LCD enable bit
    #   0x0077: E0 40  LDH [FF40],A   ; ← LCD OFF write
    #   0x0079: F0 98  LDH A,[FF98]   ; Restore IE
    #   0x007B: E0 FF  LDH [FFFF],A
    #   0x007D: C9     RET
    #
    # Fix: NOP out the 6 bytes at 0x0073-0x0078 (LCD off sequence)
    # This preserves VBlank wait + interrupt restore + RET

    lcd_off_addr = 0x0073
    lcd_off_original = bytes(rom_data[lcd_off_addr:lcd_off_addr + 6])
    lcd_off_nops = bytes([0x00] * 6)  # 6 NOPs

    rom_data[lcd_off_addr:lcd_off_addr + 6] = lcd_off_nops
    patches.append((lcd_off_addr, lcd_off_original, lcd_off_nops))
    
    return rom_data, patches


def patch_lcd_enable_for_cgb(rom_data: bytearray) -> tuple[bytearray, list[tuple[int, bytes, bytes]]]:
    """
    Patch the LCD enable function at 0x00C8 to work in CGB mode.
    
    Original:
        00C8: F0 40       LDH A,[FF40]
        00CA: F6 80       OR 80h
        00CC: E0 40       LDH [FF40],A
        00CE: C9          RET
    
    This turns LCD on (bit 7 of LCDC). In CGB mode, we may need different
    initialization or timing. For now, keep it but add CGB awareness.
    """
    patches = []
    
    # For now, this function seems less problematic. The issue is more with
    # the VBlank wait function. Let's leave this alone for first test.
    
    return rom_data, patches


def apply_all_display_patches(rom_data: bytearray) -> tuple[bytearray, list[tuple[int, bytes, bytes]]]:
    """Apply all display compatibility patches for CGB mode."""
    all_patches = []
    
    # Patch VBlank wait (critical)
    rom_data, patches = patch_vblank_wait_for_cgb(rom_data)
    all_patches.extend(patches)
    
    # Patch LCD enable (if needed)
    rom_data, patches = patch_lcd_enable_for_cgb(rom_data)
    all_patches.extend(patches)
    
    return rom_data, all_patches
