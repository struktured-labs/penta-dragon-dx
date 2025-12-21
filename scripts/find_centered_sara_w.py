#!/usr/bin/env python3
"""
Find the ~5 frames where SARA_W is centered (doing twirl)
Focus 100% on screen center, ignore green background
"""
import sys
from pathlib import Path
from PIL import Image
import numpy as np

sys.path.insert(0, str(Path(__file__).parent))
from verify_palette_injection import load_reference_sprites, extract_sprite_from_screenshot, compare_sprites

def is_green_background(sprite_img, threshold=0.9):
    """Check if extracted region is mostly green background"""
    pixels = np.array(sprite_img.convert('RGBA'))
    
    # Count green pixels (high green, low red/blue)
    green_count = 0
    total_pixels = 0
    
    for row in pixels:
        for pixel in row:
            r, g, b, a = pixel
            if a > 128:  # Non-transparent
                total_pixels += 1
                # Check if it's green (high green, low red/blue)
                if g > 200 and r < 50 and b < 50:
                    green_count += 1
    
    if total_pixels == 0:
        return True  # All transparent = likely background
    
    green_ratio = green_count / total_pixels if total_pixels > 0 else 0
    return green_ratio > threshold

def has_sprite_content(sprite_img, min_non_transparent=10):
    """Check if sprite has actual content (not just background)"""
    pixels = np.array(sprite_img.convert('RGBA'))
    
    non_transparent = 0
    non_green = 0
    
    for row in pixels:
        for pixel in row:
            r, g, b, a = pixel
            if a > 128:  # Non-transparent
                non_transparent += 1
                # Check if it's NOT pure green background
                if not (g > 200 and r < 50 and b < 50):
                    non_green += 1
    
    return non_transparent >= min_non_transparent and non_green >= 5

def find_centered_frames(screenshot_dir, frames_to_check, center_x, center_y):
    """Find frames where SARA_W is centered"""
    references = load_reference_sprites()
    ref_img = references['SARA_W']
    
    centered_frames = []
    
    for frame_num in frames_to_check:
        screenshot_path = screenshot_dir / f'verify_frame_{frame_num:05d}.png'
        if not screenshot_path.exists():
            continue
        
        screenshot_img = Image.open(screenshot_path).convert('RGBA')
        
        # Extract from exact center
        sprite = extract_sprite_from_screenshot(screenshot_img, center_x, center_y)
        
        # Skip if it's just green background
        if is_green_background(sprite):
            continue
        
        # Check if it has actual sprite content
        if not has_sprite_content(sprite):
            continue
        
        # Compare with reference
        stats = compare_sprites(ref_img, sprite, threshold=50)
        
        # Only consider if we have enough pixels and reasonable match
        if stats['total_pixels'] > 20:
            centered_frames.append({
                'frame': frame_num,
                'position': (center_x, center_y),
                'accuracy': stats['accuracy'],
                'avg_distance': stats['avg_color_distance'],
                'total_pixels': stats['total_pixels'],
                'sprite': sprite
            })
            print(f"Frame {frame_num}: Found at center ({center_x}, {center_y}) - "
                  f"Accuracy: {stats['accuracy']:.1f}%, Pixels: {stats['total_pixels']}")
    
    return centered_frames

def main():
    project_root = Path(__file__).parent.parent
    screenshot_dir = project_root / 'test_verification_output'
    
    # Screen center for 160x144 Game Boy screen
    screen_center_x = 80
    screen_center_y = 72
    
    print("🔍 Finding frames where SARA_W is centered (doing twirl)")
    print("=" * 60)
    print(f"Screen center: ({screen_center_x}, {screen_center_y})")
    print(f"Searching frames 201-205 (3-5 frames before 206 where she starts moving left)...")
    print()
    
    # User said frame 206 is already off-center, so check 3-5 frames before (201-205)
    frames_to_check = list(range(201, 206))
    centered_frames = find_centered_frames(screenshot_dir, frames_to_check, screen_center_x, screen_center_y)
    
    if centered_frames:
        # Sort by accuracy
        centered_frames.sort(key=lambda x: x['accuracy'], reverse=True)
        
        print(f"\n✅ Found {len(centered_frames)} frames with SARA_W at center:")
        print()
        
        # Show top frames
        for i, frame_data in enumerate(centered_frames[:10], 1):
            print(f"{i}. Frame {frame_data['frame']:03d}: "
                  f"Accuracy: {frame_data['accuracy']:.1f}%, "
                  f"Distance: {frame_data['avg_distance']:.1f}, "
                  f"Pixels: {frame_data['total_pixels']}")
        
        # User said frames 0-3 (201-204) are good, frame 4 (205) is too late (turned left)
        # Use frame index 2 (frame 203) as primary, or weighted average of [0-3]
        good_frames = [f for f in centered_frames if f['frame'] <= 204]  # Exclude 205
        
        if good_frames:
            # Sort by frame number to ensure order
            good_frames.sort(key=lambda x: x['frame'])
            
            # Primary choice: frame 203 (index 2)
            if len(good_frames) > 2:
                primary_frame = good_frames[2]  # Index 2 = frame 203
            else:
                primary_frame = good_frames[-1]  # Fallback to last good frame
            
            print(f"\n🎯 Best frame for comparison:")
            print(f"   Frame {primary_frame['frame']:03d} (accuracy: {primary_frame['accuracy']:.1f}%)")
            print(f"\n📊 Good frames (excluding 205 which is too late):")
            for frame_data in good_frames:
                marker = " ← PRIMARY" if frame_data['frame'] == primary_frame['frame'] else ""
                print(f"   Frame {frame_data['frame']:03d} (accuracy: {frame_data['accuracy']:.1f}%){marker}")
            
            # Save primary frame
            primary_frame['sprite'].save(project_root / 'sara_w_centered_best.png')
            print(f"\n💾 Saved best centered frame: sara_w_centered_best.png (frame {primary_frame['frame']})")
            
            # Save all good frames
            for i, frame_data in enumerate(good_frames, 1):
                frame_data['sprite'].save(project_root / f'sara_w_centered_{i:02d}_frame{frame_data["frame"]:03d}.png')
            
            print(f"💾 Saved {len(good_frames)} good centered frames")
            
            return [primary_frame]  # Return primary frame as best
        else:
            # Fallback to all frames
            best_frames = centered_frames[:5]
            return best_frames
    else:
        print("❌ No frames found with SARA_W at center")
        print("   (All extractions were green background or had no sprite content)")
        return None

if __name__ == "__main__":
    main()

