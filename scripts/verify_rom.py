#!/usr/bin/env python3
import subprocess
import time
import sys
from pathlib import Path

def run_test(rom_path):
    print(f"🚀 Testing ROM: {rom_path}")
    
    # Check if mGBA is available
    mgba_path = "/usr/local/bin/mgba-qt"
    if not Path(mgba_path).exists():
        mgba_path = subprocess.getoutput("which mgba-qt")
    
    if not mgba_path:
        print("❌ mGBA not found!")
        return False

    # Launch mGBA
    # We use a timeout to see if it crashes/freezes
    try:
        proc = subprocess.Popen([mgba_path, rom_path], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        print("⏱️ Running for 10 seconds...")
        time.sleep(10)
        
        if proc.poll() is not None:
            print("❌ mGBA exited early! Possible crash.")
            return False
        else:
            print("✅ ROM still running after 10 seconds.")
            proc.terminate()
            return True
    except Exception as e:
        print(f"❌ Error: {e}")
        return False

if __name__ == "__main__":
    rom = "rom/working/penta_dragon_cursor_dx.gb"
    if len(sys.argv) > 1:
        rom = sys.argv[1]
    
    success = run_test(rom)
    if success:
        print("\n✨ Verification successful (Preliminary)")
        sys.exit(0)
    else:
        print("\n💥 Verification failed")
        sys.exit(1)

