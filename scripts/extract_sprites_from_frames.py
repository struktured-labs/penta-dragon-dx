#!/usr/bin/env python3
"""Extract centered sprites from curated frames with transparent backgrounds"""
import json
from pathlib import Path
from PIL import Image
import numpy as np

def extract_sprite_with_transparency(img_path, output_path, sprite_size=24):
    """Extract sprite from frame and make background transparent
    
    Uses a fixed-size region centered on the image to extract the sprite.
    Game Boy sprites are typically 8x8 or 16x16, so 24x24 should capture them.
    """
    img = Image.open(img_path)
    w, h = img.size
    
    # Center of image (where the sprite should be)
    center_x = w // 2
    center_y = h // 2
    
    # Extract fixed-size region around center
    half_size = sprite_size // 2
    left = max(0, center_x - half_size)
    top = max(0, center_y - half_size)
    right = min(w, center_x + half_size)
    bottom = min(h, center_y + half_size)
    
    # Crop to sprite region
    sprite_img = img.crop((left, top, right, bottom))
    
    # Convert to RGBA for transparency
    sprite_rgba = sprite_img.convert('RGBA')
    pixels = np.array(sprite_rgba)
    
    # Make black background transparent
    # Use a threshold to handle slight variations
    bg_mask = (pixels[:, :, 0] < 10) & (pixels[:, :, 1] < 10) & (pixels[:, :, 2] < 10)
    pixels[bg_mask, 3] = 0  # Set alpha to 0 for black pixels
    
    # Also make very dark gray transparent (common in Game Boy screenshots)
    dark_mask = (pixels[:, :, 0] < 30) & (pixels[:, :, 1] < 30) & (pixels[:, :, 2] < 30)
    pixels[dark_mask, 3] = 0
    
    result_img = Image.fromarray(pixels)
    
    # Save with transparency
    result_img.save(output_path, 'PNG')
    return result_img

def main():
    script_dir = Path(__file__).parent
    project_root = script_dir.parent
    curated_dir = project_root / 'sprite-curated'
    output_dir = project_root / 'sprites-extracted'
    output_dir.mkdir(exist_ok=True)
    
    # Load monster names mapping
    json_path = project_root / 'monster_names_extracted.json'
    with open(json_path) as f:
        monster_data = json.load(f)
    
    # Process each frame
    frame_files = sorted(curated_dir.glob('frame_*.png'))
    
    print(f"Extracting sprites from {len(frame_files)} frames...")
    
    for frame_path in frame_files:
        frame_name = frame_path.name
        monster_name = monster_data.get(frame_name, {}).get('monster_name', 'UNKNOWN')
        
        # Create output filename: sprite_<monster_name>.png
        safe_name = monster_name.replace(' ', '_').upper()
        output_filename = f"sprite_{safe_name}.png"
        output_path = output_dir / output_filename
        
        try:
            sprite_img = extract_sprite_with_transparency(frame_path, output_path)
            print(f"✓ {frame_name} -> {output_filename} ({sprite_img.size[0]}x{sprite_img.size[1]})")
        except Exception as e:
            print(f"✗ {frame_name} -> ERROR: {e}")
    
    print(f"\n✅ Extracted {len(list(output_dir.glob('sprite_*.png')))} sprites to {output_dir}/")

if __name__ == '__main__':
    main()

