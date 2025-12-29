#!/usr/bin/env python3
"""Create tile-to-palette lookup table for scalable monster type mapping"""
import yaml
from pathlib import Path

def create_tile_palette_table():
    """Create a 256-byte lookup table mapping tile IDs to palette IDs"""
    
    # Initialize table: all tiles default to palette 0 (or keep original)
    # Use 0xFF to mean "don't modify" (keep game's original palette)
    table = [0xFF] * 256  # 0xFF = don't modify
    
    # Based on current mappings and future expansion:
    # Current known mappings:
    # - Tiles 8-9, 14-15 → Palette 0 (Sara D)
    # - Tiles 10-13 → Palette 1 (Sara W)
    # - Tiles 0-1, 80-87 → Palette 7 (Dragon Fly) - when we add it
    
    # Sara D (Palette 0 - red/black)
    for tile in [8, 9, 14, 15, 32]:
        table[tile] = 0
    
    # Sara W (Palette 1 - green/orange)
    for tile in [10, 11, 12, 13, 33]:
        table[tile] = 1
    
    # Dragon Fly (Palette 7 - white/blue) - ready for when we add it
    for tile in [0, 1, 80, 81, 82, 83, 84, 85, 86, 87]:
        table[tile] = 7
    
    # Future monster types (ready to expand):
    # Fire enemies (Palette 2 - red/blue)
    # for tile in range(16, 32):
    #     table[tile] = 2
    
    # Ice enemies (Palette 3 - cyan/white)
    # for tile in range(34, 50):
    #     table[tile] = 3
    
    # Flying enemies (Palette 4 - green/yellow)
    # for tile in range(50, 80):
    #     table[tile] = 4
    
    # Poison enemies (Palette 5 - blue/purple)
    # for tile in range(88, 100):
    #     table[tile] = 5
    
    # Mini Boss (Palette 6 - white/yellow/purple)
    # for tile in range(100, 120):
    #     table[tile] = 6
    
    return bytes(table)

def create_yaml_mapping():
    """Create YAML file documenting tile-to-palette mappings"""
    mapping = {
        'tile_palette_table': {
            'description': '256-byte lookup table mapping tile IDs (0-255) to palette IDs (0-7)',
            'location': 'Bank 13 @ 0x6E00',
            'format': 'Each byte: tile_id → palette_id (0xFF = don\'t modify)',
            'current_mappings': {
                'sara_d': {
                    'tiles': [8, 9, 14, 15, 32],
                    'palette': 0,
                    'colors': ['red', 'black']
                },
                'sara_w': {
                    'tiles': [10, 11, 12, 13, 33],
                    'palette': 1,
                    'colors': ['green', 'orange']
                },
                'dragon_fly': {
                    'tiles': [0, 1, 80, 81, 82, 83, 84, 85, 86, 87],
                    'palette': 7,
                    'colors': ['white', 'blue']
                }
            },
            'ready_for_expansion': {
                'fire_enemies': {'tiles': '16-31', 'palette': 2},
                'ice_enemies': {'tiles': '34-49', 'palette': 3},
                'flying_enemies': {'tiles': '50-79', 'palette': 4},
                'poison_enemies': {'tiles': '88-99', 'palette': 5},
                'mini_boss': {'tiles': '100-119', 'palette': 6}
            }
        }
    }
    
    output_path = Path('rom/working/tile_palette_mapping.yaml')
    with open(output_path, 'w') as f:
        yaml.dump(mapping, f, default_flow_style=False)
    
    return output_path

if __name__ == "__main__":
    table = create_tile_palette_table()
    
    # Save table as binary file for inspection
    table_path = Path('rom/working/tile_palette_table.bin')
    table_path.parent.mkdir(parents=True, exist_ok=True)
    table_path.write_bytes(table)
    
    print(f"✓ Created tile-to-palette lookup table ({len(table)} bytes)")
    print(f"  Saved to: {table_path}")
    
    # Show current mappings
    print("\nCurrent mappings:")
    for tile_id, palette_id in enumerate(table):
        if palette_id != 0xFF:
            print(f"  Tile {tile_id:3d} → Palette {palette_id}")
    
    # Create YAML documentation
    yaml_path = create_yaml_mapping()
    print(f"\n✓ Created mapping documentation: {yaml_path}")

