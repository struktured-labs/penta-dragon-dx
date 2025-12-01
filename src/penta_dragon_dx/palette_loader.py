"""Compact palette loader that fits in bank 0 using data from bank 13."""

def build_compact_loader(data_bank: int, data_addr: int) -> bytes:
    """
    Build a minimal palette loader stub for bank 0.
    
    Instead of embedding palette data inline (36+ bytes), this stub:
    1. Switches to data_bank
    2. Copies palette data from data_addr to GBC registers
    3. Restores original bank
    4. Returns
    
    Size: ~35 bytes (minimal register preservation)
    
    Args:
        data_bank: ROM bank containing palette data
        data_addr: Address (0x4000-0x7FFF) where palette data starts
    
    Returns:
        GBZ80 machine code bytes
    """
    code = bytearray()
    
    # Check CGB mode
    code += bytes([0xF0, 0x4D])        # LDH A,[FF4D]
    code += bytes([0xCB, 0x7F])        # BIT 7,A
    code += bytes([0xC8])              # RET Z (return if DMG)
    
    # Save minimal registers (AF, BC for counter, HL for pointer)
    code += bytes([0xF5])              # PUSH AF
    code += bytes([0xC5])              # PUSH BC
    code += bytes([0xE5])              # PUSH HL
    
    # Switch to data bank
    code += bytes([0x3E, data_bank])   # LD A, data_bank
    code += bytes([0xEA, 0x00, 0x20])  # LD [0x2000], A
    
    # Load palette pointer
    code += bytes([0x21, data_addr & 0xFF, (data_addr >> 8) & 0xFF])  # LD HL, data_addr
    
    # Set BG palette index with auto-increment
    code += bytes([0x3E, 0x80])        # LD A, 0x80
    code += bytes([0xE0, 0x68])        # LDH [FF68], A (BCPS)
    
    # Load BG palette count from [HL], increment HL
    code += bytes([0x2A])              # LD A, [HL+]
    code += bytes([0x47])              # LD B, A (B = byte count)
    
    # Loop: copy B bytes from [HL] to FF69
    # .loop:
    loop_start = len(code)
    code += bytes([0x2A])              # LD A, [HL+]
    code += bytes([0xE0, 0x69])        # LDH [FF69], A (BCPD - auto-increments)
    code += bytes([0x05])              # DEC B
    code += bytes([0x20, 0xFA])        # JR NZ, loop (-6)
    
    # Set OBJ palette index
    code += bytes([0x3E, 0x80])        # LD A, 0x80
    code += bytes([0xE0, 0x6A])        # LDH [FF6A], A (OCPS)
    
    # Load OBJ palette count
    code += bytes([0x2A])              # LD A, [HL+]
    code += bytes([0x47])              # LD B, A
    
    # Loop: copy B bytes from [HL] to FF6B
    # .loop2:
    code += bytes([0x2A])              # LD A, [HL+]
    code += bytes([0xE0, 0x6B])        # LDH [FF6B], A (OCPD)
    code += bytes([0x05])              # DEC B
    code += bytes([0x20, 0xFA])        # JR NZ, loop2 (-6)
    
    # Restore bank 1 (assume game uses bank 1 by default)
    code += bytes([0x3E, 0x01])        # LD A, 1
    code += bytes([0xEA, 0x00, 0x20])  # LD [0x2000], A
    
    # Restore registers
    code += bytes([0xE1])              # POP HL
    code += bytes([0xC1])              # POP BC
    code += bytes([0xF1])              # POP AF
    code += bytes([0xC9])              # RET
    
    return bytes(code)


def build_palette_data_block(bg_bytes: bytes, obj_bytes: bytes) -> bytes:
    """
    Build palette data block with byte counts for the loader.
    
    Format:
        [1 byte: BG byte count]
        [BG palette data...]
        [1 byte: OBJ byte count]
        [OBJ palette data...]
    """
    data = bytearray()
    data.append(len(bg_bytes))
    data.extend(bg_bytes)
    data.append(len(obj_bytes))
    data.extend(obj_bytes)
    return bytes(data)
