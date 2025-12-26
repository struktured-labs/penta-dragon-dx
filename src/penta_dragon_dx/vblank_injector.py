"""Create ultra-compact VBlank palette loader for bank 0."""

def create_vblank_palette_injector(bg_bytes: bytes, obj_bytes: bytes) -> bytes:
    """
    Create minimal palette loader that fits in ~46 bytes.
    
    Uses loop to copy from embedded data, not inline LD A instructions.
    
    Structure:
        [code: ~25 bytes]
        [bg_data: 8 bytes]
        [obj_data: 8 bytes]
        Total: ~41 bytes
    """
    code = bytearray()
    
    # CGB check - skip for max space (assume always CGB)
    # code += bytes([0xF0, 0x4D])        # LDH A,[FF4D]
    # code += bytes([0xCB, 0x7F])        # BIT 7,A
    # code += bytes([0xC8])              # RET Z
    
    # HL = address of BG data (PC-relative)
    # We'll place data right after code
    # For now, calculate manually
    code_start = 0x0824  # Where this will be placed
    data_offset_from_start = 18  # Updated - no CGB check
    bg_data_addr = code_start + data_offset_from_start
    
    code += bytes([0x21, bg_data_addr & 0xFF, (bg_data_addr >> 8) & 0xFF])  # LD HL, bg_data
    code += bytes([0x3E, 0x80])        # LD A, 0x80
    code += bytes([0xE0, 0x68])        # LDH [FF68], A
    code += bytes([0x0E, len(bg_bytes)])  # LD C, byte_count
    
    # Loop
    loop1_start = len(code)
    code += bytes([0x2A])              # LD A, [HL+]
    code += bytes([0xE0, 0x69])        # LDH [FF69], A
    code += bytes([0x0D])              # DEC C
    code += bytes([0x20, 0xFA])        # JR NZ, -6 (loop)
    
    # OBJ palettes (HL already advanced)
    code += bytes([0x3E, 0x80])        # LD A, 0x80
    code += bytes([0xE0, 0x6A])        # LDH [FF6A], A
    code += bytes([0x0E, len(obj_bytes)])  # LD C, byte_count
    
    # Loop 2
    code += bytes([0x2A])              # LD A, [HL+]
    code += bytes([0xE0, 0x6B])        # LDH [FF6B], A
    code += bytes([0x0D])              # DEC C
    code += bytes([0x20, 0xFA])        # JR NZ, -6
    
    code += bytes([0xC9])              # RET
    
    # Append palette data
    code.extend(bg_bytes)
    code.extend(obj_bytes)
    
    return bytes(code)


def create_banked_vblank_loader(data_bank: int, data_addr: int, bg_byte_count: int, obj_byte_count: int) -> bytes:
    """
    Create bank-switching palette loader for VBlank.
    
    Loads palette data from a different ROM bank.
    Must fit in 46 bytes.
    
    Args:
        data_bank: Bank number containing palette data (e.g., 13)
        data_addr: Address in that bank (0x4000-0x7FFF range)
        bg_byte_count: Number of BG palette bytes
        obj_byte_count: Number of OBJ palette bytes
    """
    code = bytearray()
    
    # Save registers
    code += bytes([0xF5])              # PUSH AF
    code += bytes([0xC5])              # PUSH BC
    code += bytes([0xE5])              # PUSH HL
    
    # Switch to data bank
    code += bytes([0x3E, data_bank])   # LD A, bank
    code += bytes([0xEA, 0x00, 0x20])  # LD [0x2000], A
    
    # Load from data bank
    code += bytes([0x21, data_addr & 0xFF, (data_addr >> 8) & 0xFF])  # LD HL, data_addr
    
    # BG palettes
    code += bytes([0x3E, 0x80])        # LD A, 0x80
    code += bytes([0xE0, 0x68])        # LDH [FF68], A
    code += bytes([0x0E, bg_byte_count])  # LD C, count
    
    # Loop
    code += bytes([0x2A])              # LD A, [HL+]
    code += bytes([0xE0, 0x69])        # LDH [FF69], A
    code += bytes([0x0D])              # DEC C
    code += bytes([0x20, 0xFA])        # JR NZ, -6
    
    # OBJ palettes
    code += bytes([0x3E, 0x80])        # LD A, 0x80
    code += bytes([0xE0, 0x6A])        # LDH [FF6A], A
    code += bytes([0x0E, obj_byte_count])  # LD C, count
    
    # Loop 2
    code += bytes([0x2A])              # LD A, [HL+]
    code += bytes([0xE0, 0x6B])        # LDH [FF6B], A
    code += bytes([0x0D])              # DEC C
    code += bytes([0x20, 0xFA])        # JR NZ, -6
    
    # Restore bank 1
    code += bytes([0x3E, 0x01])        # LD A, 1
    code += bytes([0xEA, 0x00, 0x20])  # LD [0x2000], A
    
    # Restore registers
    code += bytes([0xE1])              # POP HL
    code += bytes([0xC1])              # POP BC
    code += bytes([0xF1])              # POP AF
    code += bytes([0xC9])              # RET
    
    return bytes(code)


if __name__ == "__main__":
    # Test with 1 palette each
    bg = bytes([0xFF, 0x7F, 0x00, 0x56, 0xE0, 0x03, 0x00, 0x00])  # 4 colors
    obj = bytes([0x1F, 0x7C, 0x00, 0x50, 0x00, 0x28, 0x00, 0x00])
    
    loader = create_vblank_palette_injector(bg, obj)
    print(f"Total size: {len(loader)} bytes")
    print(f"Code: {len(loader) - len(bg) - len(obj)} bytes")
    print(f"Data: {len(bg) + len(obj)} bytes")
    print()
    print("Hex:", " ".join(f"{b:02X}" for b in loader))
