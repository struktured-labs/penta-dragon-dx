#!/usr/bin/env python3
"""Create pixel-by-pixel comparison for SARA_W"""
import sys
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont
import numpy as np

sys.path.insert(0, str(Path(__file__).parent))
from verify_palette_injection import (
    load_reference_sprites, extract_sprite_from_screenshot,
    compare_sprites, color_distance
)

def find_sprite_in_screenshot(reference_img, screenshot_img, search_region=None, threshold=0.3):
    """Find sprite position in screenshot using template matching"""
    
    ref_array = np.array(reference_img.convert('RGBA'))
    screen_array = np.array(screenshot_img.convert('RGBA'))
    
    # Extract non-transparent region from reference
    ref_mask = ref_array[:, :, 3] > 128
    if not ref_mask.any():
        return None
    
    # Get bounding box of reference sprite
    rows = np.any(ref_mask, axis=1)
    cols = np.any(ref_mask, axis=0)
    if not rows.any() or not cols.any():
        return None
    
    ref_h, ref_w = ref_array.shape[:2]
    screen_h, screen_w = screen_array.shape[:2]
    
    # Limit search region if specified
    if search_region:
        x1, y1, x2, y2 = search_region
        screen_array = screen_array[y1:y2, x1:x2]
        offset_x, offset_y = x1, y1
    else:
        offset_x, offset_y = 0, 0
    
    # Simple approach: search for similar color patterns
    # Look for regions with similar color distribution
    best_match = None
    best_score = 0
    best_pos = None
    
    # Search in a grid pattern (every 4 pixels for speed)
    step = 4
    for y in range(0, max(1, screen_h - ref_h + 1), step):
        for x in range(0, max(1, screen_w - ref_w + 1), step):
            # Extract candidate region (ensure we don't go out of bounds)
            y_end = min(y + ref_h, screen_h)
            x_end = min(x + ref_w, screen_w)
            candidate = screen_array[y:y_end, x:x_end]
            
            # Actual size of candidate region
            cand_h, cand_w = candidate.shape[:2]
            min_h = min(ref_h, cand_h)
            min_w = min(ref_w, cand_w)
            
            # Compare non-transparent pixels
            match_count = 0
            total_count = 0
            color_similarity = 0
            
            for ry in range(min_h):
                for rx in range(min_w):
                    if ref_mask[ry, rx]:  # Only compare non-transparent pixels
                        total_count += 1
                        ref_rgb = ref_array[ry, rx, :3]
                        cand_rgb = candidate[ry, rx, :3]
                        
                        # Check if candidate pixel is also non-transparent
                        if candidate[ry, rx, 3] > 128:
                            # Calculate color similarity (inverse distance)
                            dist = color_distance(ref_rgb, cand_rgb)
                            max_dist = np.sqrt(3 * 255**2)  # Max possible distance
                            similarity = 1.0 - (dist / max_dist)
                            color_similarity += similarity
                            match_count += 1
            
            if total_count > 0:
                # Score combines shape match (transparency) and color similarity
                shape_score = match_count / total_count if total_count > 0 else 0
                color_score = color_similarity / total_count if total_count > 0 else 0
                
                # Penalize text-like patterns: text usually has less transparency variation
                # Check transparency variation in candidate
                cand_alpha = candidate[:, :, 3]
                alpha_variance = np.var(cand_alpha[cand_alpha > 128]) if np.any(cand_alpha > 128) else 0
                # Text usually has low alpha variance (mostly solid), sprites have more variation
                text_penalty = 1.0 - min(1.0, alpha_variance / 10000.0)  # Normalize variance
                
                # Also check if candidate has too many solid horizontal lines (text characteristic)
                # This is a simple heuristic - sprites have more varied shapes
                score = shape_score * 0.4 + color_score * 0.6
                score = score * (1.0 - text_penalty * 0.3)  # Reduce score if looks like text
                
                if score > best_score:
                    best_score = score
                    best_pos = (x + offset_x + ref_w // 2, y + offset_y + ref_h // 2)
                    best_match = candidate
    
    if best_score > threshold and best_pos:
        return best_pos, best_score
    return None

def create_comparison_image(reference_img, candidate_img, comparison_stats, output_path, frame_num=None):
    """Create a side-by-side comparison image with difference map and improvement suggestions"""
    
    # Ensure both images are the same size
    ref_array = np.array(reference_img)
    cand_array = np.array(candidate_img)
    
    min_h = min(ref_array.shape[0], cand_array.shape[0])
    min_w = min(ref_array.shape[1], cand_array.shape[1])
    
    ref_cropped = ref_array[:min_h, :min_w]
    cand_cropped = cand_array[:min_h, :min_w]
    
    # Create difference map
    diff_map = np.zeros((min_h, min_w, 3), dtype=np.uint8)
    threshold = 50
    
    for y in range(min_h):
        for x in range(min_w):
            ref_r, ref_g, ref_b, ref_a = ref_cropped[y, x]
            cand_r, cand_g, cand_b, cand_a = cand_cropped[y, x]
            
            if ref_a > 128 and cand_a > 128:
                ref_rgb = (ref_r, ref_g, ref_b)
                cand_rgb = (cand_r, cand_g, cand_b)
                dist = color_distance(ref_rgb, cand_rgb)
                
                if dist < threshold:
                    # Match - green
                    diff_map[y, x] = [0, 255, 0]
                else:
                    # Mismatch - red
                    diff_map[y, x] = [255, 0, 0]
            else:
                # Transparent - black
                diff_map[y, x] = [0, 0, 0]
    
    # Convert back to PIL Images
    ref_pil = Image.fromarray(ref_cropped, 'RGBA')
    cand_pil = Image.fromarray(cand_cropped, 'RGBA')
    diff_pil = Image.fromarray(diff_map, 'RGB')
    
    # Create composite image - make it much wider for wide monitors
    padding = 60  # More padding for wide layout
    label_height = 80  # More space for labels
    img_width = min_w * 4  # Make sprites 4x larger for better visibility
    img_height = min_h * 4
    stats_height = 220  # More space for stats and suggestions
    
    # Scale up the images
    ref_pil = ref_pil.resize((img_width, img_height), Image.NEAREST)
    cand_pil = cand_pil.resize((img_width, img_height), Image.NEAREST)
    diff_pil = diff_pil.resize((img_width, img_height), Image.NEAREST)
    
    total_width = img_width * 3 + padding * 4
    total_height = img_height + label_height + padding * 3 + stats_height
    
    composite = Image.new('RGB', (total_width, total_height), color=(30, 30, 30))
    draw = ImageDraw.Draw(composite)
    
    # Try to load fonts - make them larger for readability
    try:
        font_title = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 24)
        font_label = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 18)
        font_text = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 14)
        font_small = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 12)
    except:
        font_title = ImageFont.load_default()
        font_label = font_title
        font_text = font_title
        font_small = font_title
    
    # Title - at the top with more space
    title_y = 20
    title_text = "SARA_W Color Comparison"
    if frame_num:
        title_text += f" (Frame {frame_num})"
    draw.text((total_width // 2, title_y), title_text, fill=(255, 255, 255), anchor="mt", font=font_title)
    
    # Draw reference - ensure labels are above images
    x_offset = padding
    y_offset = label_height + padding + 10  # More space below labels
    composite.paste(ref_pil, (x_offset, y_offset), ref_pil)
    draw.text((x_offset + img_width // 2, label_height + 5), 
              "Reference Sprite", fill=(200, 255, 200), anchor="mm", font=font_label)
    draw.text((x_offset + img_width // 2, label_height + 25), 
              "(Expected Colors)", fill=(150, 200, 150), anchor="mm", font=font_small)
    
    # Draw candidate
    x_offset = padding * 2 + img_width
    composite.paste(cand_pil, (x_offset, y_offset), cand_pil)
    draw.text((x_offset + img_width // 2, label_height + 5), 
              "ROM Screenshot", fill=(200, 200, 255), anchor="mm", font=font_label)
    draw.text((x_offset + img_width // 2, label_height + 25), 
              "(Actual Colors)", fill=(150, 150, 200), anchor="mm", font=font_small)
    
    # Draw difference map
    x_offset = padding * 3 + img_width * 2
    composite.paste(diff_pil, (x_offset, y_offset))
    draw.text((x_offset + img_width // 2, label_height + 5), 
              "Difference Map", fill=(255, 200, 200), anchor="mm", font=font_label)
    draw.text((x_offset + img_width // 2, label_height + 25), 
              "(Green=Match, Red=Mismatch)", fill=(200, 150, 150), anchor="mm", font=font_small)
    
    # Statistics section (below images) - ensure enough space
    stats_y = y_offset + img_height + padding + 30  # More space after images
    
    # Draw separator line
    draw.line([padding, stats_y - 10, total_width - padding, stats_y - 10], fill=(100, 100, 100), width=2)
    
    # Statistics - two column layout for wide screens
    stats_title = "Comparison Statistics:"
    draw.text((padding, stats_y), stats_title, fill=(255, 255, 200), font=font_label)
    
    stats_text = [
        f"• Accuracy: {comparison_stats['accuracy']:.1f}% ({comparison_stats['matching_pixels']}/{comparison_stats['total_pixels']} pixels match)",
        f"• Average Color Distance: {comparison_stats['avg_color_distance']:.1f} (lower is better)",
        f"• Total Pixels Compared: {comparison_stats['total_pixels']}"
    ]
    
    stats_y += 30
    line_height = 22  # More line spacing
    for i, text in enumerate(stats_text):
        draw.text((padding + 15, stats_y + i * line_height), text, fill=(220, 220, 220), font=font_text)
    
    # Improvement suggestions - ensure enough space
    suggestions_y = stats_y + len(stats_text) * line_height + 25
    draw.text((padding, suggestions_y), "Next Steps to Improve Colors:", fill=(255, 200, 100), font=font_label)
    
    suggestions = []
    if comparison_stats['accuracy'] < 50:
        suggestions.append("1. Update palette values in palettes/monster_palettes.yaml")
        suggestions.append("2. Convert expected RGB colors to BGR555 hex format")
        suggestions.append("3. Rebuild ROM: python3 scripts/penta_cursor_dx_gbc_native.py")
        suggestions.append("4. Re-run verification: python3 scripts/verify_palette_injection.py")
    
    if comparison_stats['avg_color_distance'] > 100:
        suggestions.append("5. Check that orange color (#FF8400) maps to BGR555: 021F")
        suggestions.append("6. Verify green color (#00FF00) maps to BGR555: 03E0")
    
    suggestions.append("7. Run automated iteration: python3 scripts/auto_verify_color_match.py")
    
    suggestions_y += 30
    suggestion_line_height = 18  # More spacing for suggestions
    for i, suggestion in enumerate(suggestions):
        draw.text((padding + 15, suggestions_y + i * suggestion_line_height), suggestion, fill=(200, 220, 255), font=font_text)
    
    # Add legend for difference map (top right, larger for visibility)
    legend_x = padding * 3 + img_width * 2 + 10
    legend_y = y_offset + 10
    legend_size = 20
    draw.rectangle([legend_x, legend_y, legend_x + legend_size, legend_y + legend_size], fill=(0, 255, 0))
    draw.text((legend_x + legend_size + 8, legend_y + 4), "Match", fill=(255, 255, 255), font=font_text)
    
    legend_y += 28
    draw.rectangle([legend_x, legend_y, legend_x + legend_size, legend_y + legend_size], fill=(255, 0, 0))
    draw.text((legend_x + legend_size + 8, legend_y + 4), "Mismatch", fill=(255, 255, 255), font=font_text)
    
    composite.save(output_path)
    print(f"✅ Saved comparison to: {output_path}")

def main():
    project_root = Path(__file__).parent.parent
    
    # Load reference
    print("📸 Loading reference SARA_W sprite...")
    references = load_reference_sprites()
    if 'SARA_W' not in references:
        print("❌ SARA_W reference not found!")
        return
    
    ref_img = references['SARA_W']
    
    # Find the best centered frame (SARA_W doing twirl in center)
    print("   Finding best centered frame (SARA_W twirl sequence)...")
    from find_centered_sara_w import find_centered_frames
    
    screenshot_dir = project_root / 'test_verification_output'
    # User said frame 206 is already off-center, so check 3-5 frames before (201-205)
    frames_to_check = list(range(201, 206))
    screen_center_x, screen_center_y = 80, 72  # Game Boy screen center
    
    centered_frames = find_centered_frames(screenshot_dir, frames_to_check, screen_center_x, screen_center_y)
    
    if centered_frames:
        # Filter out frame 205 (too late - she turned left)
        good_frames = [f for f in centered_frames if f['frame'] <= 204]
        
        if good_frames:
            # Sort by frame number and use frame 203 (index 2) as primary
            good_frames.sort(key=lambda x: x['frame'])
            if len(good_frames) > 2:
                best_centered = good_frames[2]  # Index 2 = frame 203
            else:
                best_centered = good_frames[-1]  # Fallback to last good frame
            
            frame_num = best_centered['frame']
            sprite_pos = best_centered['position']
            print(f"   ✅ Using frame {frame_num} at center ({sprite_pos[0]}, {sprite_pos[1]}) - Accuracy: {best_centered['accuracy']:.1f}%")
            screenshot_path = screenshot_dir / f'verify_frame_{frame_num:05d}.png'
            candidate_sprite = best_centered['sprite']
        else:
            # Fallback: use frame 203 directly
            frame_num = 203
            screenshot_path = screenshot_dir / f'verify_frame_{frame_num:05d}.png'
            if not screenshot_path.exists():
                print(f"❌ Screenshot not found: {screenshot_path}")
                return
            sprite_pos = (80, 72)  # Exact center
            print(f"   Using frame {frame_num} at exact center ({sprite_pos[0]}, {sprite_pos[1]})")
    else:
        # Fallback: try frame 203 directly
        frame_num = 203
        screenshot_path = project_root / 'test_verification_output' / f'verify_frame_{frame_num:05d}.png'
        if not screenshot_path.exists():
            print(f"❌ Screenshot not found: {screenshot_path}")
            return
        sprite_pos = (80, 72)  # Exact center
        print(f"   Using frame {frame_num} at exact center ({sprite_pos[0]}, {sprite_pos[1]})")
    
    # If we didn't get candidate_sprite from centered frames search, extract it now
    if 'candidate_sprite' not in locals():
        print(f"📸 Loading screenshot: {screenshot_path.name}")
        screenshot_img = Image.open(screenshot_path).convert('RGBA')
        # Extract from exact center (80, 72) - focus 100% on center
        sprite_pos = (80, 72)  # Exact screen center
        candidate_sprite = extract_sprite_from_screenshot(screenshot_img, sprite_pos[0], sprite_pos[1])
        print(f"   Extracted from exact center ({sprite_pos[0]}, {sprite_pos[1]})")
    
    # Compare
    print("🔍 Comparing sprites...")
    stats = compare_sprites(ref_img, candidate_sprite, threshold=50)
    print(f"   Accuracy: {stats['accuracy']:.1f}%")
    print(f"   Avg Distance: {stats['avg_color_distance']:.1f}")
    print(f"   Total Pixels: {stats['total_pixels']}")
    
    # Create comparison image
    output_path = project_root / 'sara_w_pixel_comparison.png'
    print(f"🎨 Creating comparison image...")
    create_comparison_image(ref_img, candidate_sprite, stats, output_path, frame_num=frame_num if 'frame_num' in locals() else None)
    
    print(f"\n✅ Done! View: {output_path}")

if __name__ == "__main__":
    main()

