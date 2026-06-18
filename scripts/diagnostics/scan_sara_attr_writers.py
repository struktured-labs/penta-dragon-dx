#!/usr/bin/env python3
"""Static ROM scan for code that writes attr=0x01 to Sara OAM slots.

Background: the spider miniboss fight forces all 4 Sara OAM slots to
pal 1 (green) even though FFBE=0 (Sara is in Witch form). Per
docs/audit/oam_read_timing.md, the colorize chain writes pal 2 to Sara
slots every frame, but something writes pal 1 hundreds of times per frame
and wins. Identifying that writer needs PC access during the fight, which
mGBA Lua doesn't expose (iter 21 / docs/mgba_lua_api_capabilities.md).

This script does a static scan of the ROM instead. It finds:

  1. DIRECT writes:
     `EA xx FE` (LD [0xFExx], A) where xx in {0x03, 0x07, 0x0B, 0x0F}
     — these write directly to real OAM Sara slot flag bytes.
  2. SHADOW DIRECT writes:
     `EA xx C0` (LD [0xC0xx], A) or `EA xx C1` where xx in the same set
     — writes to shadow OAM Sara slots (buffer A or B).
  3. STRIDED HL writes:
     `21 xx C0` / `21 xx C1` (LD HL,0xC0xx/0xC1xx) followed within ~8
     bytes by `3E 01` (LD A,1) then `77` (LD [HL],A) — typical
     "load HL, store value 1" pattern.

Outputs a structured report: bank, file offset, instruction window,
target address, immediate-preceding value-load (looking for LD A,1).

Run:
  uv run python scripts/diagnostics/scan_sara_attr_writers.py
"""
import sys
from pathlib import Path

ROM = Path("rom/working/penta_dragon_dx_teleport.gb")
SARA_FLAG_OFFSETS = {0x03, 0x07, 0x0B, 0x0F}
WINDOW = 16


def disasm_window(rom: bytes, off: int, n: int = 12) -> str:
    """Hex-dump a small window around an instruction site."""
    lo = max(0, off - 4)
    hi = min(len(rom), off + n)
    return " ".join(f"{b:02X}" for b in rom[lo:hi])


def bank_for(file_off: int) -> int:
    """ROM bank for a file offset."""
    return file_off >> 14


def cpu_addr_for(file_off: int) -> int:
    """CPU address that maps to this file offset when its bank is in."""
    bank_off = file_off & 0x3FFF
    if file_off < 0x4000:
        return file_off  # bank 0 → 0x0000
    return 0x4000 + bank_off  # bank N → 0x4000


def find_direct(rom: bytes, hi_byte: int) -> list:
    """Find `EA xx HI` direct writes for xx in SARA_FLAG_OFFSETS."""
    hits = []
    for i in range(len(rom) - 2):
        if rom[i] == 0xEA and rom[i + 1] in SARA_FLAG_OFFSETS and rom[i + 2] == hi_byte:
            preceding_a = None
            # look back up to 8 bytes for `3E vv` (LD A,vv)
            for j in range(max(0, i - 8), i):
                if rom[j] == 0x3E and j + 1 < i:
                    preceding_a = rom[j + 1]
            hits.append({
                "file_off": i,
                "bank": bank_for(i),
                "cpu_addr": cpu_addr_for(i),
                "target": (hi_byte << 8) | rom[i + 1],
                "preceding_a": preceding_a,
                "context": disasm_window(rom, i),
            })
    return hits


def find_strided(rom: bytes, hi_byte: int) -> list:
    """Find `21 xx HI` (LD HL,HIxx) where xx in SARA_FLAG_OFFSETS.

    Looks for `3E 01` (LD A,1) and `77` (LD [HL],A) within WINDOW bytes
    after. The pattern is common for OAM init / clear loops.
    """
    hits = []
    for i in range(len(rom) - 2):
        if rom[i] == 0x21 and rom[i + 1] in SARA_FLAG_OFFSETS and rom[i + 2] == hi_byte:
            window = rom[i:i + WINDOW]
            has_load_1 = False
            has_store = False
            for j in range(len(window) - 1):
                if window[j] == 0x3E and window[j + 1] == 0x01:
                    has_load_1 = True
                if window[j] == 0x77:
                    has_store = True
            if has_load_1 and has_store:
                hits.append({
                    "file_off": i,
                    "bank": bank_for(i),
                    "cpu_addr": cpu_addr_for(i),
                    "target": (hi_byte << 8) | rom[i + 1],
                    "context": disasm_window(rom, i),
                })
    return hits


def main() -> int:
    if not ROM.exists():
        print(f"ROM not found: {ROM}")
        return 1
    rom = ROM.read_bytes()
    print(f"Scanning {ROM} ({len(rom)} bytes, {len(rom) >> 14} banks)")
    print()

    print("== Pattern 1: EA xx FE (direct write to real OAM Sara flag) ==")
    direct_real = find_direct(rom, 0xFE)
    for h in direct_real:
        print(f"  bank {h['bank']:02X} file=0x{h['file_off']:05X} cpu=0x{h['cpu_addr']:04X} "
              f"target=0x{h['target']:04X} preceding_A={h['preceding_a']} "
              f"context: {h['context']}")
    if not direct_real:
        print("  (none — game uses shadow OAM via DMA, as expected)")
    print()

    print("== Pattern 2a: EA xx C0 (direct write to shadow OAM buffer A) ==")
    direct_a = find_direct(rom, 0xC0)
    for h in direct_a:
        print(f"  bank {h['bank']:02X} file=0x{h['file_off']:05X} cpu=0x{h['cpu_addr']:04X} "
              f"target=0x{h['target']:04X} preceding_A={h['preceding_a']} "
              f"context: {h['context']}")
    if not direct_a:
        print("  (none)")
    print()

    print("== Pattern 2b: EA xx C1 (direct write to shadow OAM buffer B) ==")
    direct_b = find_direct(rom, 0xC1)
    for h in direct_b:
        print(f"  bank {h['bank']:02X} file=0x{h['file_off']:05X} cpu=0x{h['cpu_addr']:04X} "
              f"target=0x{h['target']:04X} preceding_A={h['preceding_a']} "
              f"context: {h['context']}")
    if not direct_b:
        print("  (none)")
    print()

    print("== Pattern 3a: LD HL, 0xC0xx + LD A,1 + LD [HL],A (within 16 bytes) ==")
    strided_a = find_strided(rom, 0xC0)
    for h in strided_a:
        print(f"  bank {h['bank']:02X} file=0x{h['file_off']:05X} cpu=0x{h['cpu_addr']:04X} "
              f"target=0x{h['target']:04X} context: {h['context']}")
    if not strided_a:
        print("  (none)")
    print()

    print("== Pattern 3b: LD HL, 0xC1xx + LD A,1 + LD [HL],A (within 16 bytes) ==")
    strided_b = find_strided(rom, 0xC1)
    for h in strided_b:
        print(f"  bank {h['bank']:02X} file=0x{h['file_off']:05X} cpu=0x{h['cpu_addr']:04X} "
              f"target=0x{h['target']:04X} context: {h['context']}")
    if not strided_b:
        print("  (none)")
    print()

    total = len(direct_real) + len(direct_a) + len(direct_b) + len(strided_a) + len(strided_b)
    print(f"Total candidates: {total}")
    print()
    print("Note: false positives include game code that writes attr=1 to NON-Sara")
    print("entities sharing flag-byte offsets (e.g., other sprite slot 1 in another")
    print("entity group). The spider-specific writer is the subset of these that")
    print("(a) only runs in bank 13 or similar boss-banks, AND (b) is gated on")
    print("FFBF=2. Cross-reference with a runtime probe (mGBA debugger UI / GDB stub)")
    print("to confirm. See docs/mgba_lua_api_capabilities.md for blockers.")
    if "--broad" in sys.argv:
        broad_scan(rom)
    return 0


def find_all_hl_setup(rom: bytes, hi_byte: int) -> list:
    """Find ALL `21 xx HI` (LD HL,HIxx) regardless of subsequent A value."""
    hits = []
    for i in range(len(rom) - 2):
        if rom[i] == 0x21 and rom[i + 2] == hi_byte:
            hits.append({
                "file_off": i,
                "bank": bank_for(i),
                "cpu_addr": cpu_addr_for(i),
                "target": (hi_byte << 8) | rom[i + 1],
                "context": disasm_window(rom, i, 16),
            })
    return hits


def broad_scan(rom: bytes) -> None:
    print("\n=== BROAD SCAN: every `LD HL, 0xC0xx` / `LD HL, 0xC1xx` ===")
    print("(includes ALL targets, not just Sara flag offsets)")
    for hi in (0xC0, 0xC1):
        print(f"\n--- LD HL, 0x{hi:02X}xx ---")
        hits = find_all_hl_setup(rom, hi)
        by_bank = {}
        for h in hits:
            by_bank.setdefault(h["bank"], []).append(h)
        for bank in sorted(by_bank):
            print(f"  bank {bank:02X}: {len(by_bank[bank])} sites")
            for h in by_bank[bank][:5]:
                print(f"    file=0x{h['file_off']:05X} cpu=0x{h['cpu_addr']:04X} "
                      f"target=0x{h['target']:04X} ctx: {h['context']}")


if __name__ == "__main__":
    sys.exit(main())
