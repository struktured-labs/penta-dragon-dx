#!/usr/bin/env python3
"""
Disassemble Game Boy function to understand palette assignment code
"""
import sys
from pathlib import Path

# Simple Game Boy opcode disassembler
OPCODES = {
    0x21: "LD HL, {imm16}",
    0x3E: "LD A, {imm8}",
    0x77: "LD [HL], A",
    0x7E: "LD A, [HL]",
    0xE6: "AND {imm8}",
    0xF6: "OR {imm8}",
    0x06: "LD B, {imm8}",
    0x0E: "LD C, {imm8}",
    0x79: "LD A, C",
    0x87: "ADD A, A",
    0x85: "ADD A, L",
    0x6F: "LD L, A",
    0x23: "INC HL",
    0x0C: "INC C",
    0x05: "DEC B",
    0x20: "JR NZ, {rel8}",
    0x28: "JR Z, {rel8}",
    0x30: "JR NC, {rel8}",
    0x38: "JR C, {rel8}",
    0x18: "JR {rel8}",
    0xFE: "CP {imm8}",
    0xF5: "PUSH AF",
    0xC5: "PUSH BC",
    0xD5: "PUSH DE",
    0xE5: "PUSH HL",
    0xF1: "POP AF",
    0xC1: "POP BC",
    0xD1: "POP DE",
    0xE1: "POP HL",
    0xC9: "RET",
    0xCD: "CALL {imm16}",
    0xEA: "LD [{imm16}], A",
    0xE0: "LDH [{imm8}], A",
}

def disassemble_function(rom, start_addr, max_bytes=100):
    """Disassemble function starting at address"""
    addr = start_addr
    bytes_read = 0
    instructions = []
    
    while bytes_read < max_bytes and addr < len(rom):
        opcode = rom[addr]
        bytes_read += 1
        
        if opcode in OPCODES:
            fmt = OPCODES[opcode]
            inst_bytes = [opcode]
            
            # Handle immediate values
            if "{imm16}" in fmt:
                if addr + 2 < len(rom):
                    imm16 = rom[addr+1] | (rom[addr+2] << 8)
                    fmt = fmt.replace("{imm16}", f"0x{imm16:04X}")
                    inst_bytes.extend([rom[addr+1], rom[addr+2]])
                    bytes_read += 2
                    addr += 2
            elif "{imm8}" in fmt:
                if addr + 1 < len(rom):
                    imm8 = rom[addr+1]
                    fmt = fmt.replace("{imm8}", f"0x{imm8:02X}")
                    inst_bytes.append(imm8)
                    bytes_read += 1
                    addr += 1
            elif "{rel8}" in fmt:
                if addr + 1 < len(rom):
                    rel8 = rom[addr+1]
                    if rel8 > 127:
                        rel8 = rel8 - 256
                    target = addr + 2 + rel8
                    fmt = fmt.replace("{rel8}", f"0x{target:04X}")
                    inst_bytes.append(rom[addr+1])
                    bytes_read += 1
                    addr += 1
            
            instructions.append({
                'addr': addr - bytes_read + 1,
                'bytes': bytes(inst_bytes),
                'asm': fmt
            })
            
            addr += 1
            
            # Stop at RET
            if opcode == 0xC9:
                break
        else:
            # Unknown opcode
            instructions.append({
                'addr': addr,
                'bytes': bytes([opcode]),
                'asm': f"DB 0x{opcode:02X}"
            })
            addr += 1
    
    return instructions

def main():
    if len(sys.argv) < 3:
        print("Usage: python3 disassemble_function.py <rom_path> <address> [max_bytes]")
        print("Example: python3 disassemble_function.py rom.gb 0x0824 100")
        sys.exit(1)
    
    rom_path = Path(sys.argv[1])
    addr_str = sys.argv[2]
    max_bytes = int(sys.argv[3]) if len(sys.argv) > 3 else 100
    
    # Parse address
    if addr_str.startswith("0x"):
        addr = int(addr_str, 16)
    else:
        addr = int(addr_str)
    
    # Load ROM
    rom = bytearray(rom_path.read_bytes())
    
    # Handle bank switching (simplified)
    if addr >= 0x4000:
        # Banked address - would need proper bank switching
        print(f"⚠️  Warning: Address 0x{addr:04X} is in banked memory")
        print(f"   Disassembling from file offset...")
        file_offset = addr
    else:
        file_offset = addr
    
    if file_offset >= len(rom):
        print(f"❌ Address 0x{addr:04X} (file offset 0x{file_offset:06X}) out of range")
        sys.exit(1)
    
    # Disassemble
    print(f"Disassembling function at 0x{addr:04X} (file offset 0x{file_offset:06X}):")
    print("=" * 60)
    
    instructions = disassemble_function(rom, file_offset, max_bytes)
    
    for inst in instructions:
        bytes_str = " ".join(f"{b:02X}" for b in inst['bytes'])
        print(f"0x{inst['addr']:04X}: {bytes_str:12} {inst['asm']}")

if __name__ == "__main__":
    main()

