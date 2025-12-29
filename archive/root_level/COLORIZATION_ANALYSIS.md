# Penta Dragon Colorization Analysis

## Problem Summary

Penta Dragon (J) is a DMG-only Game Boy game that cannot be trivially colorized through simple palette injection. Setting the CGB flag (0x143 = 0x80) causes the game to freeze with a white screen, though audio continues to play.

## Root Cause

The game's display initialization code is incompatible with CGB mode. When the GBC BIOS initializes the system in CGB mode, the LCD hardware state differs from what the game expects, causing the display to hang even though the CPU continues running.

## What We Tried

### 1. VBlank Interrupt Hook (0x0040)
- **Problem**: Requires stub in bank 0, no space available
- **Result**: Immediate freeze due to cross-bank calling

### 2. Boot Entry Hook (0x0100)  
- **Problem**: Redirects to bank 13 before banking is initialized
- **Result**: Crash at boot as bank 1 is mapped, not bank 13

### 3. Late Init Hook (0x015F)
- **Problem**: Requires trampoline for bank switching, no space in bank 0
- **Result**: Can't place 19-byte trampoline

### 4. CGB Flag Only (No Code Injection)
- **Test**: Set 0x143 = 0x80, no other changes
- **Result**: White screen freeze, music plays
- **Analysis**: Display init code breaks in CGB mode

## Key Technical Constraints

1. **No Bank 0 Free Space**: ROM is tightly packed, no room for trampolines
2. **Bank Switching Required**: All free space is in bank 13, requires MBC1 switching
3. **Display Init Incompatibility**: Game's LCD setup doesn't work in CGB mode

## Why Official "DX" Versions Work

Games like Link's Awakening DX, Tetris DX, etc. had **developer support**:
- Display init code was patched for CGB compatibility
- Palette switching logic added throughout the game
- Save data format updated for color preferences
- Extensive playtesting and bug fixes

## Path Forward

### Option 1: Full Reverse Engineering (Recommended for DX-quality result)
1. Disassemble the display init code (0x0067, 0x00C8, 0x015F area)
2. Identify what breaks in CGB mode (likely LCDC timing or register assumptions)
3. Patch the display init to work in both DMG and CGB modes
4. Add proper palette initialization after LCD is stable
5. Implement scene-specific palette switching

**Tools needed**: 
- GB disassembler (RGBDS, mgbdis)
- GBC hardware documentation
- Emulator with step debugging (BGB, Emulicious)

### Option 2: Static Colorization (Simpler, limited)
Keep ROM as DMG mode, create external palette files for emulators that support custom palettes for DMG games (like BGB or some flash carts).

### Option 3: Emulator-Specific Patch
Create a patch specifically for emulators that can force CGB hardware mode without the CGB flag, bypassing the BIOS init issues.

## Current Tool Status

The `penta-colorize` CLI we built can:
- ✅ Parse GB ROM headers
- ✅ Find free space in ROMs
- ✅ Generate GBZ80 palette init stubs
- ✅ Convert YAML palettes to BGR555 format
- ✅ Build IPS patches
- ⚠️  Inject palettes (but game freezes due to display init issues)

The infrastructure is solid and could work for games with better CGB compatibility or more free space.

## Comparison: Why Some Games are Easier

**Easy to colorize:**
- Have free space in bank 0 for hooks
- Display init code is CGB-compatible
- Simple memory mappers (MBC1/MBC3)
- Examples: Simple puzzle games, some platformers

**Hard to colorize (like Penta Dragon):**
- Tight ROM packing, no bank 0 space
- Display init breaks in CGB mode
- Requires trampolines for bank switching
- Needs display code patching

## Recommendation

For a proper "Penta Dragon DX", invest in reverse engineering the display init code. This is a weekend project for someone with GB ASM experience and debugging tools. The colorization infrastructure we built will work once the display compatibility is fixed.

Alternatively, if you just want to play with colors, use an emulator with custom DMG palette support (BGB) and keep the ROM in DMG mode.
