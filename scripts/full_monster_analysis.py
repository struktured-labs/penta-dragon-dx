#!/usr/bin/env python3
"""Full workflow: Capture screenshots for 100 seconds, then extract sprites and OCR names"""
import subprocess
import sys
from pathlib import Path

def main():
    print("=" * 80)
    print("🎮 FULL MONSTER ANALYSIS WORKFLOW")
    print("=" * 80)
    print()
    
    # Step 1: Run verification script to capture screenshots for 100 seconds
    print("📸 Step 1: Capturing screenshots for 100 seconds...")
    print("   (This will take ~5-10 seconds real time with fast forward)")
    print()
    
    verify_script = Path("scripts/quick_verify_rom.py")
    if not verify_script.exists():
        print(f"❌ Verification script not found: {verify_script}")
        return False
    
    result = subprocess.run(
        [sys.executable, str(verify_script)],
        capture_output=False,
        text=True
    )
    
    if result.returncode != 0:
        print("⚠️  Verification script had issues, but continuing...")
    
    print()
    print("=" * 80)
    
    # Step 2: Analyze monsters and extract sprites
    print("🔍 Step 2: Analyzing monsters and extracting sprites...")
    print()
    
    analyze_script = Path("scripts/analyze_monsters.py")
    if not analyze_script.exists():
        print(f"❌ Analysis script not found: {analyze_script}")
        return False
    
    result = subprocess.run(
        [sys.executable, str(analyze_script)],
        capture_output=False,
        text=True
    )
    
    if result.returncode != 0:
        print("⚠️  Analysis script had issues")
        return False
    
    print()
    print("=" * 80)
    print("✅ WORKFLOW COMPLETE!")
    print("=" * 80)
    print()
    print("📁 Results:")
    print("   - Screenshots: rom/working/verify_screenshot_*.png")
    print("   - Extracted sprites: rom/working/extracted_sprites/")
    print("   - Monster mapping: palettes/monster_palette_map.yaml")
    print()
    print("💡 Note: Monster names are left empty - you can fill them in manually later")
    print()
    
    return True

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)

