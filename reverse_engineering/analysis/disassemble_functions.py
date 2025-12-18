#!/usr/bin/env python3
"""
Disassemble specific functions from Penta Dragon ROM.
Focus on: 0x3B69 (level load), 0x495D (most-called), 0x40A0 (VRAM clear)
"""

import sys

# Simple Z80 disassembler for Game Boy
def disassemble_instruction(rom, addr):
    """Returns (mnemonic, operands, byte_length)"""
    b = rom[addr]
    
    # Common instructions
    opcodes = {
        0x00: ("NOP", "", 1),
        0x01: ("LD", "BC,{:04X}h", 3),
        0x03: ("INC", "BC", 1),
        0x06: ("LD", "B,{:02X}h", 2),
        0x0D: ("DEC", "C", 1),
        0x0E: ("LD", "C,{:02X}h", 2),
        0x11: ("LD", "DE,{:04X}h", 3),
        0x20: ("JR", "NZ,{:+d}", 2),
        0x21: ("LD", "HL,{:04X}h", 3),
        0x28: ("JR", "Z,{:+d}", 2),
        0x2A: ("LD", "A,[HL+]", 1),
        0x3E: ("LD", "A,{:02X}h", 2),
        0xC1: ("POP", "BC", 1),
        0xC3: ("JP", "{:04X}h", 3),
        0xC5: ("PUSH", "BC", 1),
        0xC9: ("RET", "", 1),
        0xCD: ("CALL", "{:04X}h", 3),
        0xE0: ("LDH", "[FF{:02X}],A", 2),
        0xE1: ("POP", "HL", 1),
        0xE5: ("PUSH", "HL", 1),
        0xEA: ("LD", "[{:04X}],A", 3),
        0xF1: ("POP", "AF", 1),
        0xF3: ("DI", "", 1),
        0xF5: ("PUSH", "AF", 1),
        0xFA: ("LD", "A,[{:04X}]", 3),
        0xFE: ("CP", "{:02X}h", 2),
    }
    
    if b in opcodes:
        mnemonic, operand_fmt, length = opcodes[b]
        
        if length == 1:
            return mnemonic, operand_fmt, length
        elif length == 2:
            val = rom[addr + 1]
            if "{:+d}" in operand_fmt:  # Relative jump
                offset = val if val < 128 else val - 256
                target = addr + 2 + offset
                return mnemonic, f"${target:04X}", length
            else:
                return mnemonic, operand_fmt.format(val), length
        elif length == 3:
            val = rom[addr + 1] | (rom[addr + 2] << 8)
            return mnemonic, operand_fmt.format(val), length
    
    return f"DB", f"{b:02X}h", 1


def disassemble_function(rom, start_addr, max_bytes=200):
    """Disassemble a function starting at start_addr"""
    print(f"\n{'='*60}")
    print(f"Function at 0x{start_addr:04X}")
    print(f"{'='*60}")
    
    addr = start_addr
    end_addr = start_addr + max_bytes
    
    while addr < end_addr:
        mnemonic, operands, length = disassemble_instruction(rom, addr)
        
        # Show hex bytes
        hex_bytes = " ".join(f"{rom[addr+i]:02X}" for i in range(length))
        
        print(f"  {addr:04X}: {hex_bytes:<12} {mnemonic:<8} {operands}")
        
        addr += length
        
        # Stop at RET or unconditional JP
        if mnemonic in ["RET", "RETI"] or (mnemonic == "JP" and not operands.startswith("Z,") and not operands.startswith("NZ,")):
            break
    
    print()
    return addr - start_addr


if __name__ == "__main__":
    rom_path = "rom/Penta Dragon (J).gb"
    
    with open(rom_path, "rb") as f:
        rom = f.read()
    
    print("🔍 Disassembling Key Functions")
    print(f"ROM: {rom_path} ({len(rom)} bytes)")
    
    # Function 1: Level load (candidate for safe hook)
    size = disassemble_function(rom, 0x3B69, max_bytes=300)
    print(f"Function size: {size} bytes")
    
    # Function 2: Most-called function (9 times)
    size = disassemble_function(rom, 0x495D, max_bytes=200)
    print(f"Function size: {size} bytes")
    
    # Function 3: VRAM clear (called from init)
    size = disassemble_function(rom, 0x40A0, max_bytes=200)
    print(f"Function size: {size} bytes")
    
    print("\n✅ Analysis complete")
    print("Next: Check call_graph.txt to see who calls these functions")
