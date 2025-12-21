#!/usr/bin/env python3
"""
Extract monster names from curated sprite screenshots using OCR
"""
from pathlib import Path
import json
import re
from PIL import Image, ImageEnhance, ImageFilter
import numpy as np

# Try to import OCR libraries
TESSERACT_AVAILABLE = False
EASYOCR_AVAILABLE = False

try:
    import pytesseract
    import subprocess
    # Verify tesseract binary is available
    try:
        subprocess.run(['tesseract', '--version'], capture_output=True, check=True, timeout=1)
        TESSERACT_AVAILABLE = True
    except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired):
        TESSERACT_AVAILABLE = False
except ImportError:
    TESSERACT_AVAILABLE = False

try:
    import easyocr
    EASYOCR_AVAILABLE = True
except ImportError:
    EASYOCR_AVAILABLE = False

def enhance_for_ocr(image):
    """Enhance image for better OCR results - multiple strategies"""
    # Convert to grayscale if needed
    if image.mode != 'L':
        gray = image.convert('L')
    else:
        gray = image
    
    # Strategy 1: High contrast + threshold
    enhancer = ImageEnhance.Contrast(gray)
    enhanced = enhancer.enhance(4.0)
    enhancer = ImageEnhance.Sharpness(enhanced)
    sharp = enhancer.enhance(2.5)
    threshold1 = sharp.point(lambda x: 0 if x < 128 else 255, '1')
    
    # Strategy 2: Adaptive threshold (try different thresholds)
    threshold2 = gray.point(lambda x: 0 if x < 100 else 255, '1')
    threshold3 = gray.point(lambda x: 0 if x < 150 else 255, '1')
    
    # Strategy 3: Inverted (for dark text on light background)
    inverted = Image.eval(gray, lambda x: 255 - x)
    enhancer = ImageEnhance.Contrast(inverted)
    inv_enhanced = enhancer.enhance(4.0)
    threshold4 = inv_enhanced.point(lambda x: 0 if x < 128 else 255, '1')
    
    # Return the first one (can try others if needed)
    return threshold1

def preprocess_image_for_ocr(img_path):
    """Preprocess image to improve OCR accuracy"""
    try:
        img = Image.open(img_path)
    except Exception:
        return []
    
    processed_images = []
    
    # 1. Enhanced (main preprocessing)
    enhanced = enhance_for_ocr(img)
    processed_images.append(('enhanced', enhanced))
    
    # 2. Inverted
    inverted = Image.eval(enhanced, lambda x: 255 - x)
    processed_images.append(('inverted', inverted))
    
    # 3. Original grayscale
    if img.mode != 'L':
        gray = img.convert('L')
    else:
        gray = img
    processed_images.append(('grayscale', gray))
    
    # 4. High contrast original
    contrast = ImageEnhance.Contrast(gray)
    high_contrast = contrast.enhance(2.0)
    processed_images.append(('high_contrast', high_contrast))
    
    return processed_images

def ocr_text_simple(image):
    """Simple OCR using tesseract via subprocess or pytesseract if available"""
    import subprocess
    import tempfile
    
    # Check if tesseract binary is available
    try:
        subprocess.run(['tesseract', '--version'], capture_output=True, check=True, timeout=1)
        tesseract_ok = True
    except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired):
        return None
    
    if not tesseract_ok:
        return None
    
    # Try using subprocess directly (more reliable than pytesseract import)
    enhanced = enhance_for_ocr(image)
    
    # Try different PSM modes - Game Boy text is pixelated, need more lenient modes
    # English only (user confirmed images are NOT Japanese)
    configs = [
        '--psm 11',  # Sparse text (best for Game Boy screenshots)
        '--psm 7',   # Single line
        '--psm 8',   # Single word
        '--psm 6',   # Single block
        '--psm 13',  # Raw line (no layout analysis)
        '--psm 12',  # Sparse text with OSD
    ]
    
    for config in configs:
        try:
            # Save image to temp file
            with tempfile.NamedTemporaryFile(suffix='.png', delete=False) as tmp:
                enhanced.save(tmp.name)
                tmp_path = tmp.name
            
            try:
                # Call tesseract via subprocess
                result = subprocess.run(
                    ['tesseract', tmp_path, 'stdout', config],
                    capture_output=True,
                    text=True,
                    timeout=5
                )
                
                if result.returncode == 0:
                    text = result.stdout.strip()
                    text = re.sub(r'[^\w\s\-]', '', text)
                    text = ' '.join(text.split())
                    if text and len(text) >= 2 and not text.isdigit():
                        return text
            finally:
                # Clean up temp file
                import os
                try:
                    os.unlink(tmp_path)
                except:
                    pass
        except Exception as e:
            continue
    
    # Fallback: try pytesseract if available
    try:
        import pytesseract
        for config in configs:
            try:
                text = pytesseract.image_to_string(enhanced, config=config).strip()
                text = re.sub(r'[^\w\s\-]', '', text)
                text = ' '.join(text.split())
                if text and len(text) >= 2 and not text.isdigit():
                    return text
            except Exception:
                continue
    except ImportError:
        pass
    
    # Try easyocr as fallback
    if EASYOCR_AVAILABLE:
        try:
            reader = easyocr.Reader(['en'], gpu=False)
            enhanced = enhance_for_ocr(image)
            img_array = np.array(enhanced)
            results = reader.readtext(img_array)
            if results:
                best_result = max(results, key=lambda x: x[2])
                text = best_result[1].strip().upper()
                if text and len(text) >= 2:
                    return text
        except Exception:
            pass
    
    return None

def extract_text_from_regions(img_path):
    """Extract text from multiple regions of the image"""
    try:
        img = Image.open(img_path)
    except Exception:
        return []
    
    w, h = img.size
    
    # Scale up the entire image first for better OCR (Game Boy screenshots are tiny)
    scale_factor = 4
    img_large = img.resize((w * scale_factor, h * scale_factor), Image.NEAREST)
    w_large, h_large = img_large.size
    
    # Define text regions where monster names might appear (on scaled image)
    regions = [
        # Top HUD area (full width, top 30 pixels)
        ('top_hud', (0, 0, w_large, min(30 * scale_factor, h_large))),
        # Center-top (name might be above sprite)
        ('center_top', (0, 0, w_large, min(50 * scale_factor, h_large))),
        # Center (around sprite - wider area)
        ('center', (0, h_large//2 - 30 * scale_factor, w_large, h_large//2 + 30 * scale_factor)),
        # Center-bottom (name might be below sprite)
        ('center_bottom', (0, h_large//2 + 20 * scale_factor, w_large, min(h_large, h_large//2 + 60 * scale_factor))),
        # Bottom HUD
        ('bottom_hud', (0, max(0, h_large - 30 * scale_factor), w_large, h_large)),
        # Full image (fallback)
        ('full', (0, 0, w_large, h_large)),
    ]
    
    results = []
    
    for region_name, (x1, y1, x2, y2) in regions:
        if x2 <= x1 or y2 <= y1:
            continue
        
        region_img = img_large.crop((x1, y1, x2, y2))
        
        if region_img.size[0] == 0 or region_img.size[1] == 0:
            continue
        
        # Try OCR on this region
        text = ocr_text_simple(region_img)
        
        if text and len(text) >= 2:
            # Clean up text
            text = re.sub(r'[^\w\s\-]', '', text)
            text = ' '.join(text.split())
            # Filter out obvious OCR garbage
            if len(text) >= 2 and not text.isdigit() and len([c for c in text if c.isalpha()]) >= 2:
                results.append({
                    'region': region_name,
                    'text': text
                })
    
    return results

def extract_monster_names_from_curated():
    """Extract monster names from all curated sprite screenshots"""
    base_dir = Path(__file__).parent.parent
    curated_dir = base_dir / "sprite-curated"
    output_file = base_dir / "monster_names_extracted.json"
    debug_dir = base_dir / "sprite-curated" / "debug_ocr"
    debug_dir.mkdir(exist_ok=True)
    
    if not curated_dir.exists():
        print(f"❌ Directory not found: {curated_dir}")
        return
    
    png_files = sorted(curated_dir.glob("*.png"))
    print(f"📸 Found {len(png_files)} curated sprite screenshots")
    print(f"🐛 Debug images will be saved to: {debug_dir}")
    print("=" * 80)
    
    all_results = {}
    
    for i, img_path in enumerate(png_files, 1):
        print(f"\n[{i}/{len(png_files)}] Processing: {img_path.name}")
        
        # Initialize text_results list
        text_results = []
        
        # Also try OCR on the full image with very aggressive preprocessing
        full_image_text = None
        try:
            img = Image.open(img_path)
            # Scale up 8x for better OCR (Game Boy is 160x144, so 8x = 1280x1152)
            img_huge = img.resize((img.size[0] * 8, img.size[1] * 8), Image.NEAREST)
            enhanced = enhance_for_ocr(img_huge)
            # Save debug image
            debug_path = debug_dir / f"{img_path.stem}_enhanced.png"
            enhanced.save(debug_path)
            
            # Try OCR on full enhanced image with multiple configs using subprocess
            import subprocess
            import tempfile
            try:
                # Verify tesseract is available
                subprocess.run(['tesseract', '--version'], capture_output=True, check=True, timeout=1)
                
                # Save enhanced image to temp file
                with tempfile.NamedTemporaryFile(suffix='.png', delete=False) as tmp:
                    enhanced.save(tmp.name)
                    tmp_path = tmp.name
                
                try:
                    # Try multiple PSM modes on full image
                    for psm in [11, 7, 8, 6, 13]:
                        try:
                            result = subprocess.run(
                                ['tesseract', tmp_path, 'stdout', f'--psm', str(psm)],
                                capture_output=True,
                                text=True,
                                timeout=5
                            )
                            
                            if result.returncode == 0:
                                full_text = result.stdout.strip()
                                if full_text and len(full_text) > 2:
                                    # Clean up
                                    clean_text = re.sub(r'[^\w\s\-]', '', full_text)
                                    clean_text = ' '.join(clean_text.split())
                                    if len(clean_text) >= 2 and not clean_text.isdigit() and len([c for c in clean_text if c.isalpha()]) >= 2:
                                        print(f"   🔍 Full image OCR (PSM {psm}): '{clean_text[:60]}...'")
                                        full_image_text = clean_text
                                        
                                        # Extract potential monster names from the text
                                        # Look for words that might be monster names (skip common OCR artifacts)
                                        words = clean_text.split()
                                        monster_candidates = []
                                        skip_words = {'PERCH', 'DRABOD', 'DRASOD', 'theF', 'are', 'Fil', 'PENTA', 'DRAGON', 'THEY', 'FILL', 'UW', 'nPpwRnK', 'io', 'rn', 'Le', 'F', 'Den', 'Wat', 'y', 'oF', 'in', 'ca', 'el', 'yy', 'is', 'ra', 'soLo', 'IER', 'a', 'nS', 'at', 'i', 'HMHAAITTH'}
                                        
                                        for word in words:
                                            word_upper = word.upper()
                                            # Skip if it's a known artifact or too short
                                            if word_upper in skip_words or len(word) < 3:
                                                continue
                                            # Must have at least 2 letters and not be mostly numbers
                                            alpha_count = len([c for c in word if c.isalpha()])
                                            if alpha_count >= 2 and alpha_count >= len(word) * 0.5:
                                                monster_candidates.append(word_upper)
                                        
                                        # Add all candidates to results
                                        for candidate in monster_candidates:
                                            text_results.append({
                                                'region': 'full_image',
                                                'text': candidate
                                            })
                                        
                                        if monster_candidates:
                                            break
                        except Exception as e:
                            continue
                finally:
                    # Clean up temp file
                    import os
                    try:
                        os.unlink(tmp_path)
                    except:
                        pass
            except Exception as e:
                pass
        except Exception as e:
            pass
        
        # Also try region-based extraction and merge results
        region_results = extract_text_from_regions(img_path)
        text_results.extend(region_results)
        
        if text_results:
            # Group by text content (most common is likely the name)
            text_counts = {}
            for result in text_results:
                text = result['text']
                if text not in text_counts:
                    text_counts[text] = []
                text_counts[text].append(result)
            
            # Get most common text (likely the monster name)
            if text_counts:
                most_common = max(text_counts.items(), key=lambda x: len(x[1]))
                best_text = most_common[0]
                best_results = most_common[1]
                
                print(f"   ✅ Extracted: '{best_text}' ({len(best_results)} matches)")
                print(f"      Best region: {best_results[0]['region']}")
                
                all_results[img_path.name] = {
                    'monster_name': best_text,
                    'all_texts': list(text_counts.keys()),
                    'best_result': best_results[0],
                    'all_results': text_results
                }
            else:
                print(f"   ⚠️  No text extracted")
                all_results[img_path.name] = {'monster_name': None, 'all_texts': []}
        else:
            print(f"   ⚠️  No text found")
            all_results[img_path.name] = {'monster_name': None, 'all_texts': []}
    
    # Save results
    with open(output_file, 'w') as f:
        json.dump(all_results, f, indent=2)
    
    print("\n" + "=" * 80)
    print("📊 EXTRACTION SUMMARY")
    print("=" * 80)
    
    # Count unique monster names
    unique_names = {}
    for filename, data in all_results.items():
        name = data.get('monster_name')
        if name:
            if name not in unique_names:
                unique_names[name] = []
            unique_names[name].append(filename)
    
    print(f"\n✅ Extracted {len([x for x in all_results.values() if x.get('monster_name')])} names from {len(png_files)} images")
    print(f"📝 Found {len(unique_names)} unique monster names:")
    
    for name, files in sorted(unique_names.items()):
        print(f"   • {name}: {len(files)} sprite(s)")
        for f in files[:3]:
            print(f"     - {f}")
        if len(files) > 3:
            print(f"     ... and {len(files) - 3} more")
    
    print(f"\n💾 Results saved to: {output_file}")
    
    # Also create a simple text file with just names
    txt_file = base_dir / "monster_names_list.txt"
    with open(txt_file, 'w') as f:
        for name in sorted(unique_names.keys()):
            f.write(f"{name}\n")
    print(f"📄 Simple list saved to: {txt_file}")

if __name__ == "__main__":
    extract_monster_names_from_curated()

