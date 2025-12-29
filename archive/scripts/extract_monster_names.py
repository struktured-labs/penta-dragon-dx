#!/usr/bin/env python3
"""
Extract monster names from screenshots in rom/working.bak directory.
Monster names are:
- Centered horizontally
- All capitalized
- Positioned slightly below midpoint
- Not "PENTA DRAGON"
"""

import os
from pathlib import Path
from PIL import Image, ImageEnhance
import pytesseract
from collections import Counter
import re

def extract_text_from_image(image_path):
    """Extract text from an image using OCR."""
    try:
        img = Image.open(image_path)
        
        # Convert to RGB if needed
        if img.mode != 'RGB':
            img = img.convert('RGB')
        
        # Get image dimensions
        width, height = img.size
        
        # For Game Boy screenshots, upscale first for better OCR
        scale_factor = 4
        img = img.resize((width * scale_factor, height * scale_factor), Image.Resampling.NEAREST)
        
        # Enhance contrast
        enhancer = ImageEnhance.Contrast(img)
        img = enhancer.enhance(2.0)
        
        # Get new dimensions after scaling
        width, height = img.size
        
        # Focus on the area slightly below midpoint (45-65% of height)
        # where monster names typically appear
        crop_top = int(height * 0.45)
        crop_bottom = int(height * 0.65)
        
        # Crop to the region of interest
        cropped = img.crop((0, crop_top, width, crop_bottom))
        
        # Extract text using pytesseract with better config for uppercase
        # PSM 7 = single line of text
        text = pytesseract.image_to_string(
            cropped, 
            config='--psm 7 -c tessedit_char_whitelist=ABCDEFGHIJKLMNOPQRSTUVWXYZ '
        )
        
        return text.strip()
    except Exception as e:
        # Silently skip errors
        return ""

def is_monster_name(text):
    """
    Check if text is likely a monster name.
    - All uppercase (or mostly uppercase)
    - Not "PENTA DRAGON" or "GAME START" or "OPENING"
    - Has letters (not just symbols)
    - Reasonable length (3-15 chars)
    - Not common menu words
    """
    if not text:
        return False
    
    # Remove whitespace and check
    text = text.strip()
    
    # Ignore common menu/UI text
    ignore_list = [
        "PENTA", "DRAGON", "GAME", "START", "OPENING", "POPENING",
        "NEW", "CONTINUE", "OPTION", "SOUND", "STEREO", "MONO"
    ]
    
    for ignore_word in ignore_list:
        if ignore_word in text:
            return False
    
    # Check if mostly uppercase letters
    letters = [c for c in text if c.isalpha()]
    if not letters:
        return False
    
    uppercase_ratio = sum(1 for c in letters if c.isupper()) / len(letters)
    if uppercase_ratio < 0.8:  # At least 80% uppercase
        return False
    
    # Check length
    if len(text) < 3 or len(text) > 15:
        return False
    
    # Should contain mostly letters (at least 70%)
    alpha_ratio = sum(1 for c in text if c.isalpha()) / len(text)
    if alpha_ratio < 0.7:
        return False
    
    return True

def extract_monster_names_from_screenshots(directory):
    """Process all screenshots and extract unique monster names."""
    directory = Path(directory)
    
    if not directory.exists():
        print(f"Directory not found: {directory}")
        return []
    
    # Get all PNG files
    png_files = sorted(directory.glob("*.png"))
    print(f"Found {len(png_files)} PNG files")
    
    all_names = []
    
    # Process each screenshot
    for i, png_file in enumerate(png_files):
        if i % 100 == 0:
            print(f"Processing {i}/{len(png_files)}...")
        
        text = extract_text_from_image(png_file)
        
        # Split into lines and check each line
        lines = text.split('\n')
        for line in lines:
            # Clean up the line
            line = line.strip()
            
            # Check if it looks like a monster name
            if is_monster_name(line):
                # Clean up further - remove extra spaces and special chars at edges
                cleaned = re.sub(r'^\W+|\W+$', '', line)
                if cleaned and is_monster_name(cleaned):
                    all_names.append(cleaned)
    
    # Count occurrences
    name_counts = Counter(all_names)
    
    # Get unique names sorted by frequency
    unique_names = sorted(name_counts.items(), key=lambda x: (-x[1], x[0]))
    
    print(f"\nFound {len(unique_names)} unique monster names")
    print(f"Total occurrences: {sum(name_counts.values())}")
    
    return unique_names

def main():
    # Path to the screenshot directory
    screenshot_dir = Path(__file__).parent.parent / "rom" / "working.bak"
    
    print(f"Extracting monster names from: {screenshot_dir}")
    print("=" * 60)
    
    # Extract monster names
    unique_names = extract_monster_names_from_screenshots(screenshot_dir)
    
    # Print results
    print("\n" + "=" * 60)
    print("UNIQUE MONSTER NAMES:")
    print("=" * 60)
    
    for name, count in unique_names:
        print(f"{name:<30} (appears {count} times)")
    
    # Also save to a file
    output_file = Path(__file__).parent.parent / "monster_names_extracted.txt"
    with open(output_file, 'w') as f:
        f.write("Unique Monster Names from Screenshots\n")
        f.write("=" * 60 + "\n\n")
        for name, count in unique_names:
            f.write(f"{name} ({count} occurrences)\n")
    
    print(f"\nResults saved to: {output_file}")

if __name__ == "__main__":
    main()
