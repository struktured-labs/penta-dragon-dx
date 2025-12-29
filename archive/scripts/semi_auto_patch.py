#!/usr/bin/env python3
"""
Semi-Automated Palette Patching
Combines automated tracing with manual verification and patching
"""
import subprocess
import time
from pathlib import Path
import yaml

def run_workflow():
    """Run the semi-automated workflow"""
    print("🤖 Semi-Automated Palette Patching Workflow")
    print("=" * 60)
    
    rom_path = Path("rom/working/penta_dragon_cursor_dx.gb")
    
    print("\n📋 Step 1: Trace OAM writes")
    print("   This will run mGBA for 10 seconds and trace all OAM palette writes")
    input("   Press Enter to start tracing...")
    
    # Run tracing
    from automated_palette_patcher import trace_oam_writes, analyze_trace_log
    log_file = trace_oam_writes(rom_path, duration=10)
    
    if not log_file:
        print("❌ Tracing failed")
        return
    
    print("\n📊 Step 2: Analyze trace results")
    analysis = analyze_trace_log(log_file)
    
    if not analysis:
        print("❌ Analysis failed")
        return
    
    print("\n📋 Step 3: Review analysis results")
    print("   The analysis shows:")
    print(f"   - {len(analysis['consistent_tiles'])} tiles with consistent palette assignments")
    print(f"   - {len(analysis['pc_counts'])} unique code locations writing to OAM")
    print("\n   Top write locations:")
    for pc, count in sorted(analysis['pc_counts'].items(), key=lambda x: x[1], reverse=True)[:5]:
        print(f"     0x{pc:04X}: {count} writes")
    
    print("\n🔍 Step 4: Disassemble top functions")
    print("   Would you like to disassemble the top write locations?")
    response = input("   (y/n): ")
    
    if response.lower() == 'y':
        from disassemble_function import disassemble_function
        rom = bytearray(rom_path.read_bytes())
        
        top_pcs = sorted(analysis['pc_counts'].items(), key=lambda x: x[1], reverse=True)[:3]
        for pc, count in top_pcs:
            print(f"\n   Disassembling function at 0x{pc:04X} ({count} writes):")
            print("   " + "-" * 56)
            
            # Try to find function start (look backwards)
            func_start = pc
            for offset in range(pc - 0x50, pc, -1):
                if offset < 0 or offset >= len(rom):
                    break
                # Look for PUSH pattern
                if offset < len(rom) - 3:
                    if rom[offset] == 0xF5 and rom[offset+1] == 0xC5:
                        func_start = offset
                        break
            
            instructions = disassemble_function(rom, func_start, 80)
            for inst in instructions[:20]:  # Show first 20 instructions
                bytes_str = " ".join(f"{b:02X}" for b in inst['bytes'])
                marker = " <-- WRITE LOCATION" if inst['addr'] == pc else ""
                print(f"   0x{inst['addr']:04X}: {bytes_str:12} {inst['asm']}{marker}")
    
    print("\n✅ Workflow complete!")
    print("\n📝 Next steps:")
    print("   1. Review the disassembly above")
    print("   2. Identify where palette is assigned (look for AND/E6, OR/F6 patterns)")
    print("   3. Manually create patch to replace with lookup table access")
    print("   4. Test patch incrementally")

if __name__ == "__main__":
    run_workflow()

