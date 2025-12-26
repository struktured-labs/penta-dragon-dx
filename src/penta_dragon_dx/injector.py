"""Assembly code generation and injection for GBC palette initialization."""
from typing import Tuple


def generate_palette_stub_bytes(bg_data: bytes, obj_data: bytes) -> Tuple[bytes, int | None, int | None]:
    """Generate Z80 machine code for palette initialization.
    
    Returns (code_bytes, bg_addr_offset, obj_addr_offset) for patching data pointers.
    """
    # Hand-assembled Z80 opcodes for palette init routine
    code = bytearray()
    
    bg_addr_offset: int | None = None
    obj_addr_offset: int | None = None
    
    # Check if running on CGB (KEY1 register test)
    # ld a, [$FF4D]   ; KEY1 register (CGB-only)
    # and $80         ; check bit 7
    # ret z           ; return if DMG (register reads as 0xFF on DMG, 0x7E/0xFE on CGB)
    # Actually, better: check header at 0x143 already parsed at boot
    # For now, always run (we'll set CGB flag in header when patching)
    
    # --- Write BG palettes ---
    # ld a, $80       ; BCPS: auto-increment, start at index 0
    code.extend([0x3E, 0x80])
    # ld [$FF68], a
    code.extend([0xE0, 0x68])
    
    if bg_data:
        # ld hl, <bg_data_addr>  (will be patched with actual address)
        code.extend([0x21, 0x00, 0x00])  # placeholder for LD HL, nn
        bg_addr_offset = len(code) - 2  # remember where to patch address
        
        # ld b, <bg_data_len>
        code.extend([0x06, len(bg_data)])
        
        # .bg_loop:
        bg_loop_start = len(code)
        # ld a, [hl+]
        code.append(0x2A)
        # ld [$FF69], a   ; BCPD
        code.extend([0xE0, 0x69])
        # dec b
        code.append(0x05)
        # jr nz, .bg_loop
        offset = bg_loop_start - (len(code) + 2)
        code.extend([0x20, offset & 0xFF])
    
    # --- Write OBJ palettes ---
    # ld a, $80       ; OCPS: auto-increment, start at index 0
    code.extend([0x3E, 0x80])
    # ld [$FF6A], a
    code.extend([0xE0, 0x6A])
    
    if obj_data:
        # ld hl, <obj_data_addr>
        code.extend([0x21, 0x00, 0x00])
        obj_addr_offset = len(code) - 2
        
        # ld b, <obj_data_len>
        code.extend([0x06, len(obj_data)])
        
        # .obj_loop:
        obj_loop_start = len(code)
        # ld a, [hl+]
        code.append(0x2A)
        # ld [$FF6B], a   ; OCPD
        code.extend([0xE0, 0x6B])
        # dec b
        code.append(0x05)
        # jr nz, .obj_loop
        offset = obj_loop_start - (len(code) + 2)
        code.extend([0x20, offset & 0xFF])
    
    # ret
    code.append(0xC9)
    
    return bytes(code), bg_addr_offset, obj_addr_offset


def inject_palette_system(
    rom: bytes,
    bg_palette_data: bytes,
    obj_palette_data: bytes,
    free_region_offset: int,
) -> Tuple[bytes, dict[str, int]]:
    """Inject palette data and initialization stub into ROM.
    
    Returns (modified_rom, injection_info).
    """
    rom = bytearray(rom)
    
    # Generate stub code
    stub_code, bg_addr_off, obj_addr_off = generate_palette_stub_bytes(bg_palette_data, obj_palette_data)
    
    # Layout in free space:
    # [stub_code][bg_palette_data][obj_palette_data]
    stub_start = free_region_offset
    bg_data_start = stub_start + len(stub_code)
    obj_data_start = bg_data_start + len(bg_palette_data)
    total_size = len(stub_code) + len(bg_palette_data) + len(obj_palette_data)
    
    # Patch stub code with actual data addresses
    stub_bytes = bytearray(stub_code)
    if bg_addr_off is not None:
        # Convert file offset to Game Boy address
        bg_gb_addr = _file_offset_to_gb_addr(bg_data_start)
        stub_bytes[bg_addr_off:bg_addr_off+2] = bg_gb_addr.to_bytes(2, "little")
    if obj_addr_off is not None:
        obj_gb_addr = _file_offset_to_gb_addr(obj_data_start)
        # Find obj address offset in stub (second LD HL)
        # Search for second 0x21 opcode after bg one
        second_ld_hl = None
        count = 0
        for i in range(len(stub_bytes)):
            if stub_bytes[i] == 0x21:
                count += 1
                if count == 2:
                    second_ld_hl = i + 1
                    break
        if second_ld_hl:
            stub_bytes[second_ld_hl:second_ld_hl+2] = obj_gb_addr.to_bytes(2, "little")
    
    # Write everything to ROM
    rom[stub_start:stub_start+len(stub_bytes)] = stub_bytes
    rom[bg_data_start:bg_data_start+len(bg_palette_data)] = bg_palette_data
    rom[obj_data_start:obj_data_start+len(obj_palette_data)] = obj_palette_data
    
    info = {
        "stub_offset": stub_start,
        "stub_size": len(stub_bytes),
        "stub_gb_addr": _file_offset_to_gb_addr(stub_start),
        "bg_data_offset": bg_data_start,
        "bg_data_size": len(bg_palette_data),
        "obj_data_offset": obj_data_start,
        "obj_data_size": len(obj_palette_data),
        "total_size": total_size,
        "bank": stub_start // 0x4000,
    }
    
    return bytes(rom), info


def _file_offset_to_gb_addr(offset: int) -> int:
    """Convert ROM file offset to Game Boy address space.
    
    Bank 0: 0x0000-0x3FFF (file 0x0000-0x3FFF)
    Bank N: 0x4000-0x7FFF (file N*0x4000 - N*0x4000+0x3FFF)
    """
    if offset < 0x4000:
        return offset
    else:
        # Banked address is always 0x4000-0x7FFF range
        return 0x4000 + (offset % 0x4000)


def find_init_hook_location(rom: bytes) -> int | None:
    """Find a suitable location in early init to place CALL to palette stub.
    
    Looks for:
    - Area after header (past 0x0150)
    - Before main loop starts (heuristic: before first large loop/jump back)
    - Ideally in a sequence of predictable init code
    
    Returns file offset or None if no safe location found.
    """
    # Simple heuristic: look for NOP sequences or end of init code block
    # For now, return None - user will need to manually identify hook point
    # or we can search for specific patterns after disassembly
    return None


def patch_cgb_flag(rom: bytes) -> bytes:
    """Set CGB compatibility flag in ROM header to enable color mode.
    
    Byte 0x143: 0x80 = CGB-compatible, 0xC0 = CGB-only
    We use 0x80 to maintain DMG compatibility (though our stub won't run).
    """
    rom = bytearray(rom)
    rom[0x0143] = 0x80  # CGB support flag
    
    # Recalculate header checksum
    x = 0
    for i in range(0x0134, 0x014D):
        x = (x - rom[i] - 1) & 0xFF
    rom[0x014D] = x
    
    return bytes(rom)
