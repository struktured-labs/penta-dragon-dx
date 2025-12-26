#!/usr/bin/env python3
"""
Trace CALL and JP instructions to build initialization call graph.
This helps identify safe vs unsafe hook points.
"""

def disassemble_region(rom, start, end, name):
    """Disassemble a region and find all CALL/JP targets."""
    print(f"\n{'='*70}")
    print(f"REGION: {name} (0x{start:04X}-0x{end:04X})")
    print(f"{'='*70}\n")
    
    calls = []
    jumps = []
    
    addr = start
    while addr < end and addr < len(rom):
        opcode = rom[addr]
        
        # CD nn nn = CALL nn
        if opcode == 0xCD and addr + 2 < len(rom):
            target = rom[addr+1] | (rom[addr+2] << 8)
            calls.append((addr, target))
            print(f"  {addr:04X}: CALL {target:04X}")
            addr += 3
            
        # C3 nn nn = JP nn
        elif opcode == 0xC3 and addr + 2 < len(rom):
            target = rom[addr+1] | (rom[addr+2] << 8)
            jumps.append((addr, target))
            print(f"  {addr:04X}: JP   {target:04X}")
            addr += 3
            
        # C4/CC/D4/DC = conditional CALL
        elif opcode in [0xC4, 0xCC, 0xD4, 0xDC] and addr + 2 < len(rom):
            target = rom[addr+1] | (rom[addr+2] << 8)
            cond = ["NZ", "Z", "NC", "C"][opcode // 8 - 24]
            calls.append((addr, target))
            print(f"  {addr:04X}: CALL {cond},{target:04X}")
            addr += 3
            
        # C2/CA/D2/DA = conditional JP
        elif opcode in [0xC2, 0xCA, 0xD2, 0xDA] and addr + 2 < len(rom):
            target = rom[addr+1] | (rom[addr+2] << 8)
            cond = ["NZ", "Z", "NC", "C"][opcode // 8 - 24]
            jumps.append((addr, target))
            print(f"  {addr:04X}: JP   {cond},{target:04X}")
            addr += 3
            
        # C9 = RET
        elif opcode == 0xC9:
            print(f"  {addr:04X}: RET")
            addr += 1
            
        else:
            addr += 1
    
    return calls, jumps


def analyze_initialization(rom):
    """Analyze the initialization sequence to build call graph."""
    
    print("\n" + "="*70)
    print("INITIALIZATION SEQUENCE ANALYSIS")
    print("="*70)
    
    # Key regions to analyze
    regions = [
        (0x0150, 0x01B0, "Boot Entry"),
        (0x0190, 0x0200, "Main Init"),
        (0x0824, 0x0870, "Input Handler"),
        (0x06D6, 0x0700, "VBlank Handler"),
        (0x0A0F, 0x0A60, "Init Function (0x0A0F)"),
        (0x5021, 0x5070, "Palette Init (0x5021)"),
    ]
    
    all_calls = []
    all_jumps = []
    
    for start, end, name in regions:
        calls, jumps = disassemble_region(rom, start, end, name)
        all_calls.extend(calls)
        all_jumps.extend(jumps)
    
    # Build call graph
    print("\n" + "="*70)
    print("CALL GRAPH SUMMARY")
    print("="*70)
    
    # Group by target
    targets = {}
    for source, target in all_calls:
        if target not in targets:
            targets[target] = []
        targets[target].append(source)
    
    print("\nMost Called Functions:")
    for target, sources in sorted(targets.items(), key=lambda x: -len(x[1]))[:20]:
        print(f"  0x{target:04X}: called from {len(sources)} places")
        for source in sources[:5]:  # Show first 5 callers
            print(f"    ← 0x{source:04X}")
        if len(sources) > 5:
            print(f"    ... and {len(sources)-5} more")
    
    return all_calls, all_jumps


def main():
    rom = open("rom/Penta Dragon (J).gb", "rb").read()
    
    print("PENTA DRAGON - CALL GRAPH ANALYSIS")
    print("This will help identify safe injection points\n")
    
    calls, jumps = analyze_initialization(rom)
    
    # Save results
    with open("reverse_engineering/analysis/call_graph.txt", "w") as f:
        f.write("PENTA DRAGON - CALL GRAPH\n")
        f.write("="*70 + "\n\n")
        f.write(f"Total CALLs found: {len(calls)}\n")
        f.write(f"Total JPs found: {len(jumps)}\n\n")
        
        f.write("CALL TARGETS:\n")
        for source, target in sorted(calls):
            f.write(f"  {source:04X} → {target:04X}\n")
        
        f.write("\nJP TARGETS:\n")
        for source, target in sorted(jumps):
            f.write(f"  {source:04X} → {target:04X}\n")
    
    print(f"\n✓ Call graph saved to reverse_engineering/analysis/call_graph.txt")
    print(f"  Found {len(calls)} CALL instructions")
    print(f"  Found {len(jumps)} JP instructions")


if __name__ == "__main__":
    main()
