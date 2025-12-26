#!/usr/bin/env python3
"""Map tile IDs to sprite types by analyzing tile logs and screenshots"""
import re
from pathlib import Path
from collections import defaultdict

def parse_tile_log(log_path):
    """Parse tile log and group sprites by tile ID ranges"""
    if not log_path.exists():
        return {}
    
    tile_groups = defaultdict(list)
    
    with open(log_path, 'r') as f:
        current_screenshot = None
        for line in f:
            # Match screenshot header
            match = re.match(r'Screenshot (\d+) \(frame (\d+)\):', line)
            if match:
                current_screenshot = int(match.group(1))
                continue
            
            # Match sprite data
            match = re.match(r'\s+Sprite\[(\d+)\]: tile=0x([0-9A-Fa-f]+) \((\d+)\) palette=(\d+) pos=\((\d+),(\d+)\)', line)
            if match:
                sprite_idx = int(match.group(1))
                tile_hex = match.group(2)
                tile_id = int(match.group(3))
                palette = int(match.group(4))
                x = int(match.group(5))
                y = int(match.group(6))
                
                tile_groups[tile_id].append({
                    'sprite_idx': sprite_idx,
                    'palette': palette,
                    'x': x,
                    'y': y,
                    'screenshot': current_screenshot
                })
    
    return tile_groups

def analyze_tile_usage(tile_groups):
    """Analyze tile usage patterns to identify character types"""
    # Group tiles by position patterns
    # Sara D: ground character (Y typically 100-140)
    # Sara W: ground character (Y typically 100-140) 
    # Dragon Fly: flying (Y typically 20-80)
    
    ground_tiles = defaultdict(list)
    flying_tiles = defaultdict(list)
    
    for tile_id, sprites in tile_groups.items():
        avg_y = sum(s['y'] for s in sprites) / len(sprites) if sprites else 0
        
        if avg_y < 80:
            flying_tiles[tile_id] = sprites
        else:
            ground_tiles[tile_id] = sprites
    
    # Most common tiles
    ground_tile_ids = sorted(ground_tiles.keys(), key=lambda t: len(ground_tiles[t]), reverse=True)
    flying_tile_ids = sorted(flying_tiles.keys(), key=lambda t: len(flying_tiles[t]), reverse=True)
    
    print("=== Tile ID Analysis ===")
    print(f"\nGround sprites (Y >= 80): {len(ground_tile_ids)} unique tiles")
    for tile_id in ground_tile_ids[:10]:
        sprites = ground_tiles[tile_id]
        palettes = [s['palette'] for s in sprites]
        palette_counts = {p: palettes.count(p) for p in set(palettes)}
        print(f"  Tile {tile_id:3d} (0x{tile_id:02X}): {len(sprites)} occurrences, palettes: {palette_counts}")
    
    print(f"\nFlying sprites (Y < 80): {len(flying_tile_ids)} unique tiles")
    for tile_id in flying_tile_ids[:10]:
        sprites = flying_tiles[tile_id]
        palettes = [s['palette'] for s in sprites]
        palette_counts = {p: palettes.count(p) for p in set(palettes)}
        print(f"  Tile {tile_id:3d} (0x{tile_id:02X}): {len(sprites)} occurrences, palettes: {palette_counts}")
    
    return {
        'ground': ground_tile_ids,
        'flying': flying_tile_ids,
        'ground_tiles': ground_tiles,
        'flying_tiles': flying_tiles
    }

def suggest_palette_ranges(analysis):
    """Suggest tile ranges for each character based on analysis"""
    ground = analysis['ground']
    flying = analysis['flying']
    
    # Sara D and Sara W are both ground characters
    # Dragon Fly is flying
    
    suggestions = {
        'sara_d': [],
        'sara_w': [],
        'dragon_fly': []
    }
    
    # Dragon Fly: flying tiles (most common)
    if flying:
        suggestions['dragon_fly'] = flying[:4]  # Top 4 flying tiles
    
    # Sara D and Sara W: split ground tiles
    # Typically Sara D appears first, Sara W appears later
    if ground:
        mid = len(ground) // 2
        suggestions['sara_d'] = ground[:mid] if mid > 0 else ground[:2]
        suggestions['sara_w'] = ground[mid:] if mid > 0 else ground[2:4]
    
    print("\n=== Suggested Tile Ranges ===")
    print(f"Sara D (red/black): tiles {suggestions['sara_d']}")
    print(f"Sara W (green/orange): tiles {suggestions['sara_w']}")
    print(f"Dragon Fly (white/blue): tiles {suggestions['dragon_fly']}")
    
    return suggestions

def main():
    log_path = Path("rom/working/verify_screenshot_tile_ids.txt")
    
    if not log_path.exists():
        print(f"❌ Tile log not found: {log_path}")
        print("   Run quick_verify_rom.py first to capture tile IDs")
        return
    
    print(f"📖 Parsing tile log: {log_path}")
    tile_groups = parse_tile_log(log_path)
    
    if not tile_groups:
        print("❌ No tile data found in log")
        return
    
    print(f"✓ Found {len(tile_groups)} unique tile IDs")
    
    analysis = analyze_tile_usage(tile_groups)
    suggestions = suggest_palette_ranges(analysis)
    
    # Write suggestions to file
    output_path = Path("rom/working/tile_id_suggestions.txt")
    with open(output_path, 'w') as f:
        f.write("=== Tile ID to Palette Mapping Suggestions ===\n\n")
        f.write(f"Sara D (Palette 0 - red/black):\n")
        f.write(f"  Tiles: {suggestions['sara_d']}\n\n")
        f.write(f"Sara W (Palette 1 - green/orange):\n")
        f.write(f"  Tiles: {suggestions['sara_w']}\n\n")
        f.write(f"Dragon Fly (Palette 7 - white/blue):\n")
        f.write(f"  Tiles: {suggestions['dragon_fly']}\n\n")
    
    print(f"\n✓ Suggestions written to: {output_path}")
    return suggestions

if __name__ == "__main__":
    main()

