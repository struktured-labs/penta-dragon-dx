#!/usr/bin/env python3
"""Create weighted average sprite from frames 201-204 (excluding 205)"""
import sys
from pathlib import Path
from PIL import Image
import numpy as np

sys.path.insert(0, str(Path(__file__).parent))
from verify_palette_injection import extract_sprite_from_screenshot

def create_weighted_average(frames, weights=None):
    """Create weighted average of sprites from multiple frames"""
    if not frames:
        return None
    
    if weights is None:
        # Equal weights
        weights = [1.0 / len(frames)] * len(frames)
    
    # Ensure weights sum to 1
    total_weight = sum(weights)
    weights = [w / total_weight for w in weights]
    
    # Convert to numpy arrays
    arrays = []
    for frame_img in frames:
        arr = np.array(frame_img.convert('RGBA')).astype(np.float32)
        arrays.append(arr)
    
    # Weighted average
    result = np.zeros_like(arrays[0])
    for arr, weight in zip(arrays, weights):
        result += arr * weight
    
    # Convert back to uint8
    result = np.clip(result, 0, 255).astype(np.uint8)
    
    return Image.fromarray(result, 'RGBA')

def main():
    project_root = Path(__file__).parent.parent
    screenshot_dir = project_root / 'test_verification_output'
    
    # Frames 201-204 (indices 0-3), exclude 205
    frames_to_use = [201, 202, 203, 204]
    center_x, center_y = 80, 72
    
    sprites = []
    for frame_num in frames_to_use:
        screenshot_path = screenshot_dir / f'verify_frame_{frame_num:05d}.png'
        if screenshot_path.exists():
            screenshot = Image.open(screenshot_path).convert('RGBA')
            sprite = extract_sprite_from_screenshot(screenshot, center_x, center_y)
            sprites.append(sprite)
            print(f"Loaded frame {frame_num}")
    
    if sprites:
        # Create weighted average (can adjust weights if needed)
        # Equal weights for now, but could weight frame 203 more heavily
        weights = [0.2, 0.3, 0.4, 0.1]  # Slightly favor frame 203 (index 2)
        avg_sprite = create_weighted_average(sprites, weights)
        
        output_path = project_root / 'sara_w_weighted_average.png'
        avg_sprite.save(output_path)
        print(f"\n✅ Saved weighted average: {output_path}")
        print(f"   Using frames: {frames_to_use}")
        print(f"   Weights: {weights}")
        
        return avg_sprite
    else:
        print("❌ No frames found")
        return None

if __name__ == "__main__":
    main()

