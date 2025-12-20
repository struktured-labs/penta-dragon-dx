#!/usr/bin/env python3
"""
Automated Palette Patching System
Semi-automates the process of finding and patching game's palette assignment code
"""
import re
import subprocess
import time
from pathlib import Path
from collections import defaultdict
import yaml

def trace_oam_writes(rom_path, duration=5):
    """Run mGBA with Lua script to trace OAM writes"""
    print(f"🔍 Tracing OAM writes for {duration} seconds...")
    
    lua_script = Path("scripts/trace_oam_writes.lua")
    log_file = Path("oam_write_trace.log")
    
    # Clean up old log
    if log_file.exists():
        log_file.unlink()
    
    # Launch mGBA with tracing script
    cmd = [
        "/usr/local/bin/mgba-qt",
        str(rom_path),
        "--script", str(lua_script),
        "--fastforward"
    ]
    
    try:
        import os
        env = os.environ.copy()
        if os.environ.get("XDG_SESSION_TYPE", "").lower() == "wayland":
            from mgba_window_utils import get_mgba_env_for_xwayland
            env = get_mgba_env_for_xwayland()
        
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            env=env
        )
        
        # Wait for duration
        time.sleep(duration)
        
        # Kill mGBA
        try:
            process.terminate()
            time.sleep(0.5)
            if process.poll() is None:
                process.kill()
        except:
            pass
        
        # Force kill
        subprocess.run(["pkill", "-9", "mgba-qt"], stderr=subprocess.DEVNULL, timeout=1)
        
        # Wait for log to be written
        time.sleep(1)
        
        if log_file.exists():
            return log_file
        else:
            print("⚠️  No trace log generated")
            return None
            
    except Exception as e:
        print(f"❌ Error tracing: {e}")
        return None

def analyze_trace_log(log_file):
    """Analyze trace log to find patterns in palette assignments"""
    print(f"📊 Analyzing trace log: {log_file}")
    
    if not log_file.exists():
        print("❌ Trace log not found")
        return None
    
    # Parse log file
    tile_to_palette = defaultdict(set)  # tile -> set of palettes assigned
    palette_to_tiles = defaultdict(set)  # palette -> set of tiles
    write_locations = []  # List of (sprite_index, tile, palette, pc)
    
    with open(log_file, 'r') as f:
        for line in f:
            # Parse: "Write #N: Sprite[X] Flags=0xYY Palette=Z Tile=W PC~0xABCD"
            match = re.search(r'Sprite\[(\d+)\].*Palette=(\d+).*Tile=(\d+).*PC~0x([0-9A-F]+)', line)
            if match:
                sprite_idx = int(match.group(1))
                palette = int(match.group(2))
                tile = int(match.group(3))
                pc = int(match.group(4), 16)
                
                tile_to_palette[tile].add(palette)
                palette_to_tiles[palette].add(tile)
                write_locations.append((sprite_idx, tile, palette, pc))
    
    # Find most common patterns
    print(f"\n📈 Analysis Results:")
    print(f"   Total OAM writes: {len(write_locations)}")
    print(f"   Unique tiles written: {len(tile_to_palette)}")
    print(f"   Unique palettes used: {len(palette_to_tiles)}")
    
    # Find tiles that always use the same palette (good candidates for patching)
    consistent_tiles = {}
    for tile, palettes in tile_to_palette.items():
        if len(palettes) == 1:
            consistent_tiles[tile] = list(palettes)[0]
    
    print(f"\n✅ Consistent tile→palette mappings: {len(consistent_tiles)}")
    for tile, palette in sorted(consistent_tiles.items())[:10]:
        print(f"   Tile {tile} → Palette {palette}")
    
    # Find program counter locations (where code writes to OAM)
    pc_counts = defaultdict(int)
    for _, _, _, pc in write_locations:
        pc_counts[pc] += 1
    
    print(f"\n📍 Most frequent write locations (PC addresses):")
    for pc, count in sorted(pc_counts.items(), key=lambda x: x[1], reverse=True)[:10]:
        print(f"   0x{pc:04X}: {count} writes")
    
    return {
        'tile_to_palette': dict(tile_to_palette),
        'palette_to_tiles': dict(palette_to_tiles),
        'consistent_tiles': consistent_tiles,
        'write_locations': write_locations,
        'pc_counts': dict(pc_counts)
    }

def find_palette_assignment_functions(rom_path, analysis):
    """Use disassembly to find functions that assign palettes"""
    print(f"\n🔎 Finding palette assignment functions...")
    
    # Load ROM
    rom = bytearray(Path(rom_path).read_bytes())
    
    # Get most frequent PC addresses
    top_pcs = sorted(analysis['pc_counts'].items(), key=lambda x: x[1], reverse=True)[:5]
    
    functions = []
    for pc, count in top_pcs:
        # Try to find function start (look backwards for CALL or JP)
        # This is a heuristic - real disassembly would be better
        func_start = None
        for offset in range(pc - 0x100, pc, -1):
            if offset < 0:
                break
            # Look for common function prologues
            if offset < len(rom) - 1:
                # PUSH AF, BC, DE, HL pattern
                if rom[offset] == 0xF5 and offset + 3 < len(rom):
                    if rom[offset+1] == 0xC5 and rom[offset+2] == 0xD5 and rom[offset+3] == 0xE5:
                        func_start = offset
                        break
        
        if func_start:
            functions.append({
                'pc': pc,
                'start': func_start,
                'write_count': count,
                'bank': 0 if pc < 0x4000 else (pc // 0x4000)
            })
    
    print(f"   Found {len(functions)} potential functions")
    for func in functions:
        print(f"   Function at 0x{func['start']:04X} (called from 0x{func['pc']:04X}, {func['write_count']} writes)")
    
    return functions

def generate_lookup_table(yaml_path):
    """Generate tile-to-palette lookup table from YAML config"""
    print(f"\n📋 Generating lookup table from {yaml_path}...")
    
    with open(yaml_path, 'r') as f:
        config = yaml.safe_load(f)
    
    # Initialize table: 0xFF = don't modify
    table = [0xFF] * 256
    
    # Load mappings from monster_palette_map
    if 'monster_palette_map' in config:
        for monster_name, data in config['monster_palette_map'].items():
            palette = data.get('palette', 0)
            tile_range = data.get('tile_range', [])
            
            for tile in tile_range:
                if 0 <= tile < 256:
                    table[tile] = palette
                    print(f"   Tile {tile} → Palette {palette} ({monster_name})")
    
    return bytes(table)

def generate_patch_code(rom_path, functions, lookup_table_addr):
    """Generate assembly code to patch functions with lookup table"""
    print(f"\n🔧 Generating patch code...")
    
    # This is a simplified version - real implementation would need
    # proper disassembly and code generation
    
    patches = []
    
    for func in functions:
        # Generate patch that replaces palette assignment with lookup table access
        # This is pseudo-code - real implementation needs proper assembly generation
        
        patch = {
            'address': func['start'],
            'original_pc': func['pc'],
            'type': 'palette_assignment',
            'lookup_table_addr': lookup_table_addr
        }
        
        patches.append(patch)
        print(f"   Patch at 0x{patch['address']:04X}: Replace palette assignment with lookup table")
    
    return patches

def apply_patches(rom_path, patches, lookup_table, output_path):
    """Apply patches to ROM"""
    print(f"\n⚙️  Applying patches to ROM...")
    
    rom = bytearray(Path(rom_path).read_bytes())
    
    # Write lookup table to Bank 13 @ 0x6E00
    lookup_table_addr = 0x036E00  # File offset
    rom[lookup_table_addr:lookup_table_addr+256] = lookup_table
    print(f"   ✓ Wrote lookup table to 0x6E00 (file: 0x{lookup_table_addr:06X})")
    
    # Apply patches (simplified - real implementation needs proper code generation)
    for patch in patches:
        print(f"   ⚠️  Patch at 0x{patch['address']:04X}: Manual implementation needed")
        # TODO: Generate proper assembly code to:
        # 1. Read tile ID
        # 2. Look up palette from table
        # 3. Apply palette
    
    # Save patched ROM
    Path(output_path).write_bytes(rom)
    print(f"   ✓ Saved patched ROM to {output_path}")
    
    return output_path

def main():
    """Main automation workflow"""
    print("🤖 Automated Palette Patching System")
    print("=" * 50)
    
    rom_path = Path("rom/working/penta_dragon_cursor_dx.gb")
    yaml_path = Path("palettes/monster_palette_map.yaml")
    output_path = Path("rom/working/penta_dragon_auto_patched.gb")
    
    if not rom_path.exists():
        print(f"❌ ROM not found: {rom_path}")
        return
    
    # Step 1: Trace OAM writes
    log_file = trace_oam_writes(rom_path, duration=10)
    if not log_file:
        print("❌ Failed to generate trace log")
        return
    
    # Step 2: Analyze trace log
    analysis = analyze_trace_log(log_file)
    if not analysis:
        print("❌ Failed to analyze trace log")
        return
    
    # Step 3: Find palette assignment functions
    functions = find_palette_assignment_functions(rom_path, analysis)
    
    # Step 4: Generate lookup table
    lookup_table = generate_lookup_table(yaml_path)
    
    # Step 5: Generate patches
    lookup_table_addr = 0x6E00  # Bank 13 address
    patches = generate_patch_code(rom_path, functions, lookup_table_addr)
    
    # Step 6: Apply patches
    patched_rom = apply_patches(rom_path, patches, lookup_table, output_path)
    
    print(f"\n✅ Automation complete!")
    print(f"   Patched ROM: {patched_rom}")
    print(f"\n⚠️  Note: Generated patches need manual verification and proper assembly code generation")
    print(f"   Review patches and implement proper code injection")

if __name__ == "__main__":
    main()

