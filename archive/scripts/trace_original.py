#!/usr/bin/env python3
import subprocess
from pathlib import Path

def main():
    rom_path = Path("rom/Penta Dragon (J).gb")
    print(f"Running Trace on ORIGINAL ROM: {rom_path}")
    try:
        result = subprocess.run(
            ["mgba-headless", "-p", "scripts/mgba_verify.lua", str(rom_path)],
            capture_output=True, text=True, timeout=5
        )
        print(result.stdout)
    except subprocess.TimeoutExpired:
        print("TRACE TIMEOUT")
    except Exception as e:
        print(f"TRACE ERROR: {e}")

if __name__ == "__main__":
    main()

