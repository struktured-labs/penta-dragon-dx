#!/usr/bin/env python3
"""
Automated palette verification using mgba-headless.
Runs the ROM, captures palette data, and compares to YAML definitions.
"""

import subprocess
import sys
import time
from pathlib import Path

try:
    import yaml
except ImportError:
    # Fallback if yaml not in path
    sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))
    import yaml

# Paths
ROM_PATH = "rom/working/penta_dragon_dx_WORKING.gb"
LUA_SCRIPT = "scripts/verify_palettes.lua"
PALETTE_YAML = "palettes/penta_palettes.yaml"
OUTPUT_FILE = "rom/working/palette_verification.txt"
SCREENSHOT = "rom/working/palette_verification.png"
SAVE_STATE = "rom/working/lvl1.ss0"  # Optional: load save state for faster verification


def run_mgba_verification():
    """Launch mgba with Lua script to capture palette data."""
    
    print("🎮 Launching mGBA headless to verify palette injection...")
    
    cmd = [
        "mgba",  # Use mgba (not mgba-qt) for true headless
        "--script", LUA_SCRIPT,
        ROM_PATH
    ]
    
    # If save state exists, use it to skip intro
    if Path(SAVE_STATE).exists():
        print(f"   Loading save state: {SAVE_STATE}")
        cmd.extend(["-l", SAVE_STATE])
    
    try:
        result = subprocess.run(
            cmd,
            timeout=10,  # 10 seconds should be plenty
            capture_output=True,
            text=True
        )
        
        if result.returncode != 0:
            print(f"⚠️  mGBA exited with code {result.returncode}")
            if result.stderr:
                print(f"   stderr: {result.stderr}")
        else:
            print("✓ mGBA completed successfully")
            
    except subprocess.TimeoutExpired:
        print("⚠️  mGBA timed out (script may not have called emu:stop())")
    except FileNotFoundError:
        print("❌ mgba binary not found. Trying mgba-qt as fallback...")
        # Fallback to mgba-qt
        cmd[0] = "mgba-qt"
        subprocess.run(cmd, timeout=10)


def parse_palette_data():
    """Parse the captured palette data from mGBA output."""
    
    if not Path(OUTPUT_FILE).exists():
        print(f"❌ Output file not found: {OUTPUT_FILE}")
        print("   mGBA script may have failed to write data.")
        return None
    
    print(f"\n📄 Reading captured palette data from {OUTPUT_FILE}...")
    
    with open(OUTPUT_FILE, 'r') as f:
        content = f.read()
    
    print(content)
    
    return content


def load_expected_palettes():
    """Load expected palette definitions from YAML."""
    
    print(f"\n📋 Loading expected palettes from {PALETTE_YAML}...")
    
    with open(PALETTE_YAML, 'r') as f:
        config = yaml.safe_load(f)
    
    obj_palettes = config['obj_palettes']
    
    print("\n🎨 Expected OBJ Palettes:")
    for name, pal in obj_palettes.items():
        colors = ' '.join(pal['colors'])
        print(f"   {name}: {colors}")
    
    return obj_palettes


def compare_palettes(captured_content, expected_palettes):
    """Compare captured palette data to expected YAML definitions."""
    
    print("\n🔍 Comparison Analysis:")
    
    # Extract OBJ Palette 0 from captured data
    lines = captured_content.split('\n')
    for line in lines:
        if line.startswith("OBJ Palette 0:"):
            captured_pal0 = line.split(": ")[1].strip().split()
            expected_pal0 = expected_palettes['MainCharacter']['colors']
            
            print(f"\n   OBJ Palette 0 (MainCharacter):")
            print(f"      Expected: {' '.join(expected_pal0)}")
            print(f"      Captured: {' '.join(captured_pal0)}")
            
            if [c.upper() for c in expected_pal0] == [c.upper() for c in captured_pal0]:
                print(f"      ✅ MATCH!")
            else:
                print(f"      ❌ MISMATCH!")
                
            break
    
    # Analyze sprite assignments
    print("\n   Sprite Palette Usage:")
    sprite_palettes = {}
    for line in lines:
        if line.startswith("Sprite "):
            parts = line.split()
            sprite_idx = parts[1].rstrip(':')
            palette_num = None
            for part in parts:
                if part.startswith("Palette="):
                    palette_num = int(part.split('=')[1])
                    break
            if palette_num is not None:
                sprite_palettes.setdefault(palette_num, []).append(sprite_idx)
    
    for pal_num in sorted(sprite_palettes.keys()):
        sprites = sprite_palettes[pal_num]
        pal_names = ['MainCharacter', 'EnemyBasic', 'EnemyFire', 'EnemyIce', 
                     'EnemyFlying', 'EnemyPoison', 'MiniBoss', 'MainBoss']
        pal_name = pal_names[pal_num] if pal_num < len(pal_names) else f"Unknown{pal_num}"
        print(f"      Palette {pal_num} ({pal_name}): Sprites {', '.join(sprites)}")


def main():
    print("=" * 60)
    print("Penta Dragon DX - Palette Injection Verification")
    print("=" * 60)
    
    # Step 1: Run mGBA to capture data
    run_mgba_verification()
    
    # Give it a moment to finish writing
    time.sleep(0.5)
    
    # Step 2: Parse captured data
    captured = parse_palette_data()
    
    if captured is None:
        print("\n❌ Failed to capture palette data. Exiting.")
        sys.exit(1)
    
    # Step 3: Load expected palettes
    expected = load_expected_palettes()
    
    # Step 4: Compare
    compare_palettes(captured, expected)
    
    # Step 5: Show screenshot path
    if Path(SCREENSHOT).exists():
        print(f"\n📸 Screenshot saved: {SCREENSHOT}")
    
    print("\n" + "=" * 60)
    print("✓ Verification complete!")
    print("=" * 60)


if __name__ == "__main__":
    main()
