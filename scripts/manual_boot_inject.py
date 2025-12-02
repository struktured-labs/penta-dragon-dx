#!/usr/bin/env python3
"""Manual boot hook injection with proper banked palette loader."""

import sys
import yaml

sys.path.insert(0, 'src')
from penta_dragon_dx.display_patcher import apply_all_display_patches
from penta_dragon_dx.palette_injector import build_palette_blocks

def create_boot_palette_loader(data_bank: int, data_addr: int, bg_byte_count: int, obj_byte_count: int, original_entry: int) -> bytes:
    """
    Create boot-time palette loader that switches to data bank, loads palettes, then jumps to game.
    
    Args:
        data_bank: Bank number containing palette data (e.g., 13)
        data_addr: Address in that bank (e.g., 0x6C80)
        bg_byte_count: Number of BG palette bytes (typically 64)
        obj_byte_count: Number of OBJ palette bytes (typically 64)
        original_entry: Original game entry point address to jump to after loading
    """
    code = bytearray()
    
    # Save registers (boot code should preserve state)
    code += bytes([0xF5])              # PUSH AF
    code += bytes([0xC5])              # PUSH BC
    code += bytes([0xE5])              # PUSH HL
    
    # Switch to data bank
    code += bytes([0x3E, data_bank])   # LD A, bank
    code += bytes([0xEA, 0x00, 0x20])  # LD [0x2000], A
    
    # Load palette data address
    code += bytes([0x21, data_addr & 0xFF, (data_addr >> 8) & 0xFF])  # LD HL, data_addr
    
    # Load BG palettes
    code += bytes([0x3E, 0x80])        # LD A, 0x80 (auto-increment)
    code += bytes([0xE0, 0x68])        # LDH [FF68], A (BCPS)
    code += bytes([0x0E, bg_byte_count])  # LD C, count
    
    # BG loop
    code += bytes([0x2A])              # LD A, [HL+]
    code += bytes([0xE0, 0x69])        # LDH [FF69], A (BCPD)
    code += bytes([0x0D])              # DEC C
    code += bytes([0x20, 0xFA])        # JR NZ, -6 (loop)
    
    # Load OBJ palettes
    code += bytes([0x3E, 0x80])        # LD A, 0x80
    code += bytes([0xE0, 0x6A])        # LDH [FF6A], A (OCPS)
    code += bytes([0x0E, obj_byte_count])  # LD C, count
    
    # OBJ loop
    code += bytes([0x2A])              # LD A, [HL+]
    code += bytes([0xE0, 0x6B])        # LDH [FF6B], A (OCPD)
    code += bytes([0x0D])              # DEC C
    code += bytes([0x20, 0xFA])        # JR NZ, -6
    
    # Restore bank 1
    code += bytes([0x3E, 0x01])        # LD A, 1
    code += bytes([0xEA, 0x00, 0x20])  # LD [0x2000], A
    
    # Restore registers
    code += bytes([0xE1])              # POP HL
    code += bytes([0xC1])              # POP BC
    code += bytes([0xF1])              # POP AF
    
    # Jump to original entry point
    code += bytes([0xC3, original_entry & 0xFF, (original_entry >> 8) & 0xFF])  # JP original_entry
    
    return bytes(code)


def main():
    # Load ROM
    with open("rom/Penta Dragon (J).gb", "rb") as f:
        rom = bytearray(f.read())
    
    # Apply CGB compatibility patches
    rom, patches = apply_all_display_patches(rom)
    print(f"✓ Applied {len(patches)} CGB compatibility patches")
    
    # Load palette YAML
    with open("palettes/penta_palettes.yaml", "r") as f:
        palettes = yaml.safe_load(f)
    
    # Build palette data blocks
    bg_bytes, obj_bytes, manifest = build_palette_blocks(palettes)
    print(f"✓ Built palette data: {len(bg_bytes)} BG bytes, {len(obj_bytes)} OBJ bytes")
    
    # Write palette DATA to bank 13 at 0x6C80
    data_offset = 0x036C80  # File offset for bank 13, addr 0x6C80
    rom[data_offset:data_offset+len(bg_bytes)] = bg_bytes
    rom[data_offset+len(bg_bytes):data_offset+len(bg_bytes)+len(obj_bytes)] = obj_bytes
    print(f"✓ Wrote palette data to bank 13 @0x6C80 (file 0x{data_offset:06X})")
    
    # The original game entry point is always at 0x0150 (after BIOS)
    # We'll save the code at 0x0150 and replace it with a jump to our loader
    original_entry = 0x0150
    
    # Save the first 3 bytes at 0x0150 (we'll replace with JP instruction)
    saved_0150_bytes = bytes(rom[0x0150:0x0153])
    print(f"✓ Original entry point: 0x{original_entry:04X}")
    print(f"✓ Saved bytes at 0x0150: {saved_0150_bytes.hex()}")
    
    # Put loader in bank 13 right after palette data
    # Palette data: bank 13 @0x6C80 (128 bytes)
    # Loader code: bank 13 @0x6D00 (right after palette data)
    # Loader will execute the saved 0x0150 bytes, then jump to 0x0153
    loader = create_boot_palette_loader(
        data_bank=13,
        data_addr=0x6C80,
        bg_byte_count=len(bg_bytes),
        obj_byte_count=len(obj_bytes),
        original_entry=0x0153  # Jump past our JP instruction at 0x0150
    )
    
    # Prepend the saved bytes from 0x0150 so they still execute
    loader_with_saved = bytes(saved_0150_bytes) + loader
    
    print(f"✓ Boot loader size: {len(loader)} bytes (+{len(saved_0150_bytes)} saved bytes)")
    
    # Write loader to bank 13 at 0x6D00
    loader_file_offset = 0x036D00  # Bank 13, addr 0x6D00
    loader_bank_addr = 0x6D00
    rom[loader_file_offset:loader_file_offset+len(loader_with_saved)] = loader_with_saved
    print(f"✓ Wrote boot loader to bank 13 @0x6D00 (file 0x{loader_file_offset:06X})")
    
    # Replace entry at 0x0150 with: switch to bank 13, call loader, return
    entry_hook = bytearray()
    entry_hook += bytes([0x3E, 13])                     # LD A, 13
    entry_hook += bytes([0xEA, 0x00, 0x20])             # LD [0x2000], A
    entry_hook += bytes([0xCD, 0x00, 0x6D])             # CALL 0x6D00 (loader in bank 13)
    entry_hook += bytes([0x3E, 0x01])                   # LD A, 1
    entry_hook += bytes([0xEA, 0x00, 0x20])             # LD [0x2000], A
    entry_hook += bytes([0xC3, 0x53, 0x01])             # JP 0x0153 (skip this hook)
    
    rom[0x0150:0x0150+len(entry_hook)] = entry_hook
    print(f"✓ Patched entry @0x0150: Switch to bank 13, CALL 0x6D00, restore bank, JP 0x0153 ({len(entry_hook)} bytes)")
    
    # Keep 0x0100 as standard boot entry (NOP + JP 0x0150)
    rom[0x0100] = 0x00  # NOP
    rom[0x0101:0x0104] = bytes([0xC3, 0x50, 0x01])  # JP 0x0150
    print(f"✓ Set boot entry @0x0100: NOP, JP 0x0150")
    
    # Set CGB compatibility flag
    rom[0x143] = 0x80  # CGB compatible
    print(f"✓ Set CGB flag at 0x143: 0x80")
    
    # Fix header checksum
    chk = 0
    for i in range(0x134, 0x14D):
        chk = (chk - rom[i] - 1) & 0xFF
    rom[0x14D] = chk
    print(f"✓ Fixed header checksum: 0x{chk:02X}")
    
    # Write output ROM
    with open("rom/working/penta_dx.gb", "wb") as f:
        f.write(rom)
    
    print(f"✓ Wrote rom/working/penta_dx.gb")
    print()
    print("Boot sequence:")
    print(f"  1. Nintendo BIOS runs, displays logo")
    print(f"  2. BIOS jumps to 0x0100")
    print(f"  3. 0x0100 contains: NOP, JP 0x0150")
    print(f"  4. 0x0150 switches to bank 13 and CALLs loader at 0x6D00")
    print(f"  5. Loader executes saved original 0x0150 bytes: {saved_0150_bytes.hex()}")
    print(f"  6. Loader reads {len(bg_bytes) + len(obj_bytes)} bytes from 0x6C80")
    print(f"  7. Loader writes palettes to CGB registers")
    print(f"  8. Loader restores bank 1")
    print(f"  9. Loader jumps to 0x0153 (continues game code)")



if __name__ == "__main__":
    main()
