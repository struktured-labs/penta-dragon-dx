"""Wrapper for DMG palette writes that also sets CGB palettes."""

def create_palette_wrapper(data_bank: int, data_addr: int) -> bytes:
    """
    Create a function that writes BOTH DMG and CGB palettes.
    
    This function will be called by patched DMG palette code.
    Input: A = DMG palette value (for FF47/BGP)
    
    The wrapper:
    1. Writes A to FF47 (DMG BGP) as original code expects
    2. If CGB mode, also loads CGB palettes from data_bank:data_addr
    3. Returns
    
    Size: ~40 bytes
    """
    code = bytearray()
    
    # First, do the original DMG write
    code += bytes([0xE0, 0x47])        # LDH [FF47], A
    
    # Check CGB mode
    code += bytes([0xF0, 0x4D])        # LDH A, [FF4D]
    code += bytes([0xCB, 0x7F])        # BIT 7, A
    code += bytes([0xC8])              # RET Z (return if DMG)
    
    # Save registers
    code += bytes([0xF5])              # PUSH AF
    code += bytes([0xC5])              # PUSH BC
    code += bytes([0xE5])              # PUSH HL
    
    # Switch to data bank
    code += bytes([0x3E, data_bank])   # LD A, data_bank
    code += bytes([0xEA, 0x00, 0x20])  # LD [0x2000], A
    
    # Load palette data pointer
    code += bytes([0x21, data_addr & 0xFF, (data_addr >> 8) & 0xFF])  # LD HL, data_addr
    
    # Set BG palette index with auto-increment
    code += bytes([0x3E, 0x80])        # LD A, 0x80
    code += bytes([0xE0, 0x68])        # LDH [FF68], A (BCPS)
    
    # Load BG palette byte count
    code += bytes([0x2A])              # LD A, [HL+]
    code += bytes([0x47])              # LD B, A
    
    # Loop: copy B bytes from [HL] to FF69
    code += bytes([0x2A])              # LD A, [HL+]
    code += bytes([0xE0, 0x69])        # LDH [FF69], A
    code += bytes([0x05])              # DEC B
    code += bytes([0x20, 0xFA])        # JR NZ, -6 (loop)
    
    # Set OBJ palette index
    code += bytes([0x3E, 0x80])        # LD A, 0x80
    code += bytes([0xE0, 0x6A])        # LDH [FF6A], A (OCPS)
    
    # Load OBJ palette byte count
    code += bytes([0x2A])              # LD A, [HL+]
    code += bytes([0x47])              # LD B, A
    
    # Loop: copy B bytes from [HL] to FF6B
    code += bytes([0x2A])              # LD A, [HL+]
    code += bytes([0xE0, 0x6B])        # LDH [FF6B], A
    code += bytes([0x05])              # DEC B
    code += bytes([0x20, 0xFA])        # JR NZ, -6 (loop)
    
    # Restore bank 1
    code += bytes([0x3E, 0x01])        # LD A, 1
    code += bytes([0xEA, 0x00, 0x20])  # LD [0x2000], A
    
    # Restore registers
    code += bytes([0xE1])              # POP HL
    code += bytes([0xC1])              # POP BC
    code += bytes([0xF1])              # POP AF
    code += bytes([0xC9])              # RET
    
    return bytes(code)


def patch_dmg_palette_writes(rom_data: bytearray, wrapper_addr: int) -> list[tuple[int, bytes, bytes]]:
    """
    Patch DMG palette writes (LD A, xx; LDH [FF47], A) to call wrapper instead.
    
    Original: 3E xx E0 47 (4 bytes)
    Patched:  3E xx CD xx xx (5 bytes) - need 1 extra byte, so requires careful placement
    
    Better approach: Replace the whole sequence with CALL wrapper, padding with NOP
    Patched:  CD xx xx 00 (4 bytes: CALL + NOP)
    But then A register doesn't have the palette value...
    
    Best approach: Hook at known palette functions that are called from many places.
    Replace their first instruction with JP wrapper.
    """
    patches = []
    
    # Find palette write sequences
    # Pattern: 3E xx E0 47 (LD A, value; LDH [FF47], A)
    i = 0
    while i < len(rom_data) - 3:
        if rom_data[i] == 0x3E and rom_data[i+2] == 0xE0 and rom_data[i+3] == 0x47:
            original = bytes(rom_data[i:i+4])
            palette_value = rom_data[i+1]
            
            # Replace with: LD A, value; CALL wrapper; NOP
            # But CALL is 3 bytes, so: 3E xx CD addr addr = 5 bytes (need 1 more)
            # Check if next byte is safe to overwrite
            if i + 4 < len(rom_data):
                next_byte = rom_data[i+4]
                if next_byte in [0x00, 0xAF, 0xC9]:  # NOP, XOR A, or RET (safe-ish)
                    patched = bytearray([
                        0x3E, palette_value,                    # LD A, value
                        0xCD, wrapper_addr & 0xFF, (wrapper_addr >> 8) & 0xFF  # CALL wrapper
                    ])
                    
                    rom_data[i:i+5] = patched
                    patches.append((i, original + bytes([next_byte]), bytes(patched)))
                    
                    i += 5
                    continue
        
        i += 1
    
    return patches
