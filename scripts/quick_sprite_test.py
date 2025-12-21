#!/usr/bin/env python3
"""
Quick sprite test - manual verification helper
Launches ROM and provides instructions for manual color checking
"""
import subprocess
import sys
from pathlib import Path

def main():
    rom_path = Path("rom/working/penta_dragon_cursor_dx.gb")
    
    if not rom_path.exists():
        print(f"❌ ROM not found: {rom_path}")
        return
    
    print("=" * 80)
    print("QUICK SPRITE COLOR TEST")
    print("=" * 80)
    print()
    print("🎮 Launching ROM for manual verification...")
    print()
    print("📋 What to look for:")
    print("   ✅ Sara W (playable character): Should be GREEN/ORANGE (Palette 1)")
    print("   ✅ Dragonfly: Should be RED/BLACK (Palette 0)")
    print("   ⚠️  Other monsters: May have various colors")
    print()
    print("🔍 Focus on:")
    print("   - Sara W appearing consistently in green/orange")
    print("   - Dragonfly appearing consistently in red/black")
    print("   - No flickering or color fighting")
    print("   - Game speed should be acceptable (not too slow)")
    print()
    print("=" * 80)
    
    import os
    cmd = ["/usr/local/bin/mgba-qt", str(rom_path), "--fastforward"]
    env = os.environ.copy()
    env["QT_QPA_PLATFORM"] = "xcb"
    env["__GLX_VENDOR_LIBRARY_NAME"] = "nvidia"
    subprocess.Popen(cmd, env=env)
    print("✅ ROM launched - please verify colors manually")
    print("   Close mgba-qt when done testing")

if __name__ == "__main__":
    main()

