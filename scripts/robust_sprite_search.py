#!/usr/bin/env python3
"""
Robust sprite search using timing estimates and gameplay area analysis
T0 -> SARA_W -> SARA_D -> DRAGONFLY sequence
"""
import sys
from pathlib import Path
from PIL import Image
import numpy as np
from collections import defaultdict

sys.path.insert(0, str(Path(__file__).parent))
from verify_palette_injection import load_reference_sprites, extract_sprite_from_screenshot, compare_sprites

def estimate_gameplay_center(screenshot_img):
    """Estimate gameplay center - may be offset from screen center"""
    w, h = screenshot_img.size
    pixels = np.array(screenshot_img.convert('RGBA'))
    
    # Find non-transparent/non-black regions (gameplay area)
    # Avoid top/bottom 20% (UI) and edges
    gameplay_top = int(h * 0.15)
    gameplay_bottom = int(h * 0.85)
    gameplay_left = int(w * 0.1)
    gameplay_right = int(w * 0.9)
    
    # Find center of mass of non-background pixels in gameplay area
    gameplay_region = pixels[gameplay_top:gameplay_bottom, gameplay_left:gameplay_right]
    
    # Find pixels that are not pure black/transparent (likely sprites/objects)
    mask = (gameplay_region[:, :, 3] > 128) & (
        (gameplay_region[:, :, 0] > 10) | 
        (gameplay_region[:, :, 1] > 10) | 
        (gameplay_region[:, :, 2] > 10)
    )
    
    if mask.any():
        y_coords, x_coords = np.where(mask)
        if len(x_coords) > 0:
            center_x = int(np.mean(x_coords)) + gameplay_left
            center_y = int(np.mean(y_coords)) + gameplay_top
            return (center_x, center_y)
    
    # Fallback to screen center
    return (w // 2, h // 2)

def search_around_center(screenshot_img, ref_img, center_estimate, search_radius=40, step=4):
    """Search in a radius around center estimate"""
    w, h = screenshot_img.size
    best_match = None
    best_score = 0
    best_pos = None
    
    cx, cy = center_estimate
    
    # Search in expanding circles
    for radius in range(step, search_radius, step):
        for angle in range(0, 360, 15):  # Every 15 degrees
            import math
            x = int(cx + radius * math.cos(math.radians(angle)))
            y = int(cy + radius * math.sin(math.radians(angle)))
            
            # Bounds check
            if x < 12 or x >= w - 12 or y < 12 or y >= h - 12:
                continue
            
            sprite = extract_sprite_from_screenshot(screenshot_img, x, y)
            stats = compare_sprites(ref_img, sprite, threshold=50)
            
            if stats['total_pixels'] > 20:
                score = stats['accuracy'] * (stats['total_pixels'] / 100.0)
                if score > best_score:
                    best_score = score
                    best_match = sprite
                    best_pos = (x, y)
    
    return best_pos, best_score, best_match

def analyze_frame_sequence(screenshot_dir, sprite_name='SARA_W'):
    """Analyze multiple frames to find consistent sprite positions"""
    project_root = Path(__file__).parent.parent
    references = load_reference_sprites()
    ref_img = references[sprite_name]
    
    # Focus on frames 206-234 (SARA_W range)
    frames_to_check = list(range(206, 235))
    
    positions = []
    scores = []
    
    for frame_num in frames_to_check:
        screenshot_path = screenshot_dir / f'verify_frame_{frame_num:05d}.png'
        if not screenshot_path.exists():
            continue
        
        screenshot_img = Image.open(screenshot_path).convert('RGBA')
        
        # Estimate gameplay center for this frame
        center_estimate = estimate_gameplay_center(screenshot_img)
        
        # Search around center
        pos, score, match = search_around_center(screenshot_img, ref_img, center_estimate, search_radius=50)
        
        if pos and score > 30:  # Reasonable threshold
            positions.append(pos)
            scores.append(score)
            print(f"Frame {frame_num}: Found at {pos} with score {score:.1f}")
    
    if positions:
        # Find mean position
        mean_x = int(np.mean([p[0] for p in positions]))
        mean_y = int(np.mean([p[1] for p in positions]))
        mean_pos = (mean_x, mean_y)
        
        # Find best frame (highest score)
        best_idx = np.argmax(scores)
        best_frame = frames_to_check[best_idx]
        best_pos = positions[best_idx]
        
        print(f"\n📊 Analysis Results:")
        print(f"   Mean position across frames: ({mean_x}, {mean_y})")
        print(f"   Best frame: {best_frame} at {best_pos} (score: {scores[best_idx]:.1f})")
        print(f"   Found {len(positions)}/{len(frames_to_check)} frames with matches")
        
        return mean_pos, best_pos, best_frame
    else:
        print("❌ No matches found in frame sequence")
        return None, None, None

def main():
    project_root = Path(__file__).parent.parent
    screenshot_dir = project_root / 'test_verification_output'
    
    print("🔍 Robust sprite search for SARA_W")
    print("=" * 60)
    
    # Analyze frame sequence
    mean_pos, best_pos, best_frame = analyze_frame_sequence(screenshot_dir, 'SARA_W')
    
    if best_pos:
        # Load best frame and create comparison
        screenshot_path = screenshot_dir / f'verify_frame_{best_frame:05d}.png'
        screenshot_img = Image.open(screenshot_path).convert('RGBA')
        
        references = load_reference_sprites()
        ref_img = references['SARA_W']
        
        sprite = extract_sprite_from_screenshot(screenshot_img, best_pos[0], best_pos[1])
        stats = compare_sprites(ref_img, sprite, threshold=50)
        
        print(f"\n✅ Best match from frame {best_frame}:")
        print(f"   Position: {best_pos}")
        print(f"   Accuracy: {stats['accuracy']:.1f}%")
        print(f"   Avg Distance: {stats['avg_color_distance']:.1f}")
        print(f"   Total Pixels: {stats['total_pixels']}")
        
        # Save
        sprite.save(project_root / 'sara_w_robust_extraction.png')
        print(f"\n💾 Saved: sara_w_robust_extraction.png")
        
        return best_pos, best_frame
    else:
        print("❌ Could not find SARA_W")
        return None, None

if __name__ == "__main__":
    main()

