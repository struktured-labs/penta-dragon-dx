#!/usr/bin/env python3
"""
One-Command Palette Patching
Run this single script to fully automate the entire patching process
"""
import sys
from pathlib import Path

# Add scripts to path
sys.path.insert(0, str(Path(__file__).parent))

from full_auto_patcher import FullAutoPatcher

def main():
    """One command to rule them all"""
    print("🚀 One-Command Palette Patching")
    print("=" * 60)
    print("This will:")
    print("  1. Trace OAM writes (10s)")
    print("  2. Analyze patterns")
    print("  3. Generate lookup table")
    print("  4. Find functions to patch")
    print("  5. Generate patches")
    print("  6. Apply patches")
    print("  7. Verify results")
    print()
    
    rom_path = Path("rom/working/penta_dragon_cursor_dx.gb")
    yaml_path = Path("palettes/monster_palette_map.yaml")
    
    if not rom_path.exists():
        print(f"❌ ROM not found: {rom_path}")
        print(f"   Please run penta_cursor_dx.py first to create ROM")
        return 1
    
    if not yaml_path.exists():
        print(f"❌ YAML config not found: {yaml_path}")
        return 1
    
    patcher = FullAutoPatcher(rom_path, yaml_path)
    success = patcher.run_full_automation()
    
    if success:
        print("\n🎉 SUCCESS! Patched ROM is ready for testing.")
        print(f"   File: rom/working/penta_dragon_auto_patched.gb")
        return 0
    else:
        print("\n⚠️  Patches applied but verification needs review.")
        print(f"   File: rom/working/penta_dragon_auto_patched.gb")
        print("   Please test manually and verify results.")
        return 1

if __name__ == "__main__":
    sys.exit(main())

