#!/usr/bin/env python3
"""
Compare two game state dumps to find memory locations that changed.
Useful for finding boss/enemy flags.
"""
import sys
from pathlib import Path

def compare_dumps(file1: Path, file2: Path):
    """Compare two binary dumps and show differences."""
    data1 = file1.read_bytes()
    data2 = file2.read_bytes()

    if len(data1) != len(data2):
        print(f"Warning: file sizes differ ({len(data1)} vs {len(data2)})")

    # WRAM is 0xC000-0xDFFF (8KB = 8192 bytes)
    # HRAM is 0xFF80-0xFFFE (127 bytes)
    # Total: 8319 bytes

    wram_size = 0x2000  # 8KB
    hram_size = 127

    print("=== MEMORY DIFFERENCES ===\n")
    print("Looking for bytes that changed between dumps...")
    print("(Likely candidates for boss/enemy state flags)\n")

    differences = []

    # Check WRAM
    for i in range(min(wram_size, len(data1), len(data2))):
        if data1[i] != data2[i]:
            addr = 0xC000 + i
            differences.append((addr, data1[i], data2[i]))

    # Check HRAM
    for i in range(min(hram_size, len(data1) - wram_size, len(data2) - wram_size)):
        idx = wram_size + i
        if idx < len(data1) and idx < len(data2) and data1[idx] != data2[idx]:
            addr = 0xFF80 + i
            differences.append((addr, data1[idx], data2[idx]))

    if not differences:
        print("No differences found!")
        return

    print(f"Found {len(differences)} differences:\n")

    # Group by region
    regions = {
        "0xC000-0xC0FF (game vars)": [],
        "0xC100-0xC1FF (shadow OAM?)": [],
        "0xC200-0xC2FF (enemy data?)": [],
        "0xC300-0xC3FF": [],
        "0xD000-0xDFFF (other WRAM)": [],
        "0xFF80-0xFFFE (HRAM)": [],
    }

    for addr, v1, v2 in differences:
        if 0xC000 <= addr <= 0xC0FF:
            regions["0xC000-0xC0FF (game vars)"].append((addr, v1, v2))
        elif 0xC100 <= addr <= 0xC1FF:
            regions["0xC100-0xC1FF (shadow OAM?)"].append((addr, v1, v2))
        elif 0xC200 <= addr <= 0xC2FF:
            regions["0xC200-0xC2FF (enemy data?)"].append((addr, v1, v2))
        elif 0xC300 <= addr <= 0xC3FF:
            regions["0xC300-0xC3FF"].append((addr, v1, v2))
        elif 0xD000 <= addr <= 0xDFFF:
            regions["0xD000-0xDFFF (other WRAM)"].append((addr, v1, v2))
        elif 0xFF80 <= addr <= 0xFFFE:
            regions["0xFF80-0xFFFE (HRAM)"].append((addr, v1, v2))

    # Look for "flag-like" changes (e.g., non-zero to zero, or 1 to 0)
    print("=== LIKELY FLAG CANDIDATES (changed to/from 0) ===\n")
    for addr, v1, v2 in differences:
        if v1 == 0 or v2 == 0:
            direction = "appeared" if v1 == 0 else "cleared"
            print(f"  0x{addr:04X}: 0x{v1:02X} -> 0x{v2:02X}  ({direction})")

    print("\n=== ALL DIFFERENCES BY REGION ===\n")
    for region, diffs in regions.items():
        if diffs:
            print(f"{region}: {len(diffs)} changes")
            for addr, v1, v2 in diffs[:20]:  # Show first 20
                print(f"  0x{addr:04X}: 0x{v1:02X} -> 0x{v2:02X}")
            if len(diffs) > 20:
                print(f"  ... and {len(diffs) - 20} more")
            print()

def main():
    if len(sys.argv) < 3:
        # Default: compare gamestate_1.bin and gamestate_2.bin
        file1 = Path("tmp/gamestate_1.bin")
        file2 = Path("tmp/gamestate_2.bin")
        if not file1.exists() or not file2.exists():
            print("Usage: python compare_game_states.py <dump1.bin> <dump2.bin>")
            print("Or run with default files tmp/gamestate_1.bin and tmp/gamestate_2.bin")
            sys.exit(1)
    else:
        file1 = Path(sys.argv[1])
        file2 = Path(sys.argv[2])

    print(f"Comparing: {file1} vs {file2}\n")
    compare_dumps(file1, file2)

if __name__ == "__main__":
    main()
