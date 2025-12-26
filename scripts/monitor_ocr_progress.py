#!/usr/bin/env python3
"""Crude progress bar for OCR extraction"""
import time
import sys
from pathlib import Path
import re
from datetime import datetime

def get_progress():
    sprite_dir = Path("rom/working/extracted_sprites")
    yaml_path = Path("palettes/monster_palette_map.yaml")
    
    # Count files
    all_files = list(sprite_dir.glob("*_text_*_*.png"))
    enhanced_files = list(sprite_dir.glob("*_enhanced.png"))
    
    # Get latest screenshot
    if all_files:
        latest_file = max(all_files, key=lambda x: x.stat().st_mtime)
        # Try multiple patterns to extract screenshot number
        match = re.search(r'_(\d{4,5})\.png$', latest_file.name)
        if not match:
            match = re.search(r'_(\d{3,5})_', latest_file.name)
        latest_screenshot = int(match.group(1)) if match else 0
        latest_time = datetime.fromtimestamp(latest_file.stat().st_mtime)
    else:
        latest_screenshot = 0
        latest_time = None
    
    # Check YAML
    yaml_stat = yaml_path.stat()
    yaml_mtime = datetime.fromtimestamp(yaml_stat.st_mtime)
    
    # Count total screenshots
    total_screenshots = len(list(Path("rom/working").glob("verify_screenshot_*.png")))
    
    return {
        'total_files': len(all_files),
        'enhanced_files': len(enhanced_files),
        'latest_screenshot': latest_screenshot,
        'total_screenshots': total_screenshots,
        'latest_time': latest_time,
        'yaml_mtime': yaml_mtime,
    }

def draw_progress_bar(current, total, width=50):
    """Draw a simple progress bar"""
    if total == 0:
        return "[" + " " * width + "]"
    
    filled = int((current / total) * width)
    bar = "█" * filled + "░" * (width - filled)
    pct = (current / total) * 100 if total > 0 else 0
    return f"[{bar}] {pct:.1f}%"

def main():
    print("OCR Extraction Progress Monitor")
    print("=" * 70)
    print("Press Ctrl+C to exit\n")
    
    initial_state = get_progress()
    start_time = time.time()
    last_file_count = initial_state['total_files']
    
    try:
        while True:
            state = get_progress()
            elapsed = time.time() - start_time
            
            # Calculate rate
            files_added = state['total_files'] - last_file_count
            last_file_count = state['total_files']
            
            # Clear screen (crude)
            print("\033[2J\033[H", end="")  # ANSI clear screen
            
            print("=" * 70)
            print("OCR EXTRACTION PROGRESS")
            print("=" * 70)
            print()
            
            # File progress
            print(f"📁 Files Created: {state['total_files']:,}")
            print(f"   └─ Successful OCR: {state['enhanced_files']:,} ({state['enhanced_files']/state['total_files']*100:.1f}%)" if state['total_files'] > 0 else "   └─ Successful OCR: 0")
            print()
            
            # Screenshot progress (based on files, not screenshot numbers)
            # Since script only processes screenshots with sprites, use file count as progress
            # Estimate: ~1-5 files per sprite processed (depending on OCR success)
            estimated_sprites_processed = state['total_files'] // 3  # Rough estimate
            estimated_total_sprites = 50000  # Rough estimate based on log file
            
            if state['latest_screenshot'] > 0:
                print(f"📸 Current Screenshot: #{state['latest_screenshot']:,}")
            print(f"📊 Files Progress: {state['total_files']:,} files created")
            print(f"   {draw_progress_bar(state['total_files'], 50000, 50)} (estimated)")
            print(f"   └─ Based on file count (screenshots processed out of order)")
            print()
            
            # Activity status
            if state['latest_time']:
                age = (datetime.now() - state['latest_time']).total_seconds()
                if age < 5:
                    status = "🟢 ACTIVE"
                elif age < 30:
                    status = "🟡 SLOW"
                else:
                    status = "🔴 IDLE"
                print(f"⚡ Status: {status} (last file: {age:.0f}s ago)")
            else:
                print("⚡ Status: 🔴 WAITING")
            print()
            
            # Rate
            if elapsed > 0:
                rate = state['total_files'] / elapsed
                recent_rate = files_added / 10 if files_added > 0 else 0
                print(f"📊 Rate: {rate:.1f} files/sec (avg) | {recent_rate:.1f} files/sec (recent)")
            print()
            
            # YAML status
            yaml_age = (datetime.now() - state['yaml_mtime']).total_seconds()
            if yaml_age < 60:
                print("✅ YAML: UPDATED - Script finished!")
                print("=" * 70)
                break
            else:
                print(f"⏳ YAML: Not updated yet ({yaml_age/60:.1f} min ago)")
            
            print("=" * 70)
            print(f"Runtime: {elapsed/60:.1f} minutes | Press Ctrl+C to exit")
            
            time.sleep(2)  # Update every 2 seconds
            
    except KeyboardInterrupt:
        print("\n\nMonitor stopped.")

if __name__ == "__main__":
    main()

