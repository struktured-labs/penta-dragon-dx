#!/usr/bin/env python3
"""
Simple, reliable mgba-qt launcher
No fancy window positioning - just launches the ROM
"""
import subprocess
import sys
from pathlib import Path

def launch_mgba(rom_path, fastforward=True, script=None):
    """Launch mgba-qt with ROM - simple and reliable"""
    rom_path = Path(rom_path)
    
    if not rom_path.exists():
        print(f"❌ ROM not found: {rom_path}")
        return False
    
    cmd = ["/usr/local/bin/mgba-qt", str(rom_path)]
    
    if fastforward:
        cmd.append("--fastforward")
    
    if script:
        cmd.extend(["--script", str(script)])
    
    print(f"🚀 Launching mgba-qt: {' '.join(cmd)}")
    
    try:
        # Simple launch - no window management, no environment tricks
        subprocess.Popen(cmd)
        print(f"✅ mgba-qt launched")
        return True
    except Exception as e:
        print(f"❌ Failed to launch: {e}")
        return False

def main():
    """Main entry point"""
    if len(sys.argv) < 2:
        # Default to current ROM
        rom_path = Path("rom/working/penta_dragon_cursor_dx.gb")
        if not rom_path.exists():
            rom_path = Path("rom/working/penta_dragon_auto_patched.gb")
    else:
        rom_path = Path(sys.argv[1])
    
    fastforward = "--no-fastforward" not in sys.argv
    script = None
    if "--script" in sys.argv:
        idx = sys.argv.index("--script")
        if idx + 1 < len(sys.argv):
            script = Path(sys.argv[idx + 1])
    
    success = launch_mgba(rom_path, fastforward=fastforward, script=script)
    sys.exit(0 if success else 1)

if __name__ == "__main__":
    main()

