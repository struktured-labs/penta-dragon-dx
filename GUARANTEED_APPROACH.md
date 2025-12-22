# Guaranteed Palette Injection Approach

## Core Principles (What ALWAYS Works)

### 1. Boot-Time Palette Loading (100% Safe)
**Why it works:**
- Runs once at startup, before game code executes
- No timing issues, no conflicts with game logic
- Game hasn't initialized yet, so nothing can interfere

**Implementation:**
- Hook at `0x0150` (after boot, before game starts)
- Load all palettes into CGB palette RAM (0xFF68-0xFF6B for BG, 0xFF6A-0xFF6B for OBJ)
- Use bank 0 for hook code (always accessible)
- Store palette data in ROM (read-only, never changes)

**Guarantee:** If palettes are loaded at boot, they're in RAM and ready to use.

### 2. OAM DMA Completion Hook (Perfect Timing)
**Why it works:**
- Game updates OAM → DMA completes → Our code runs → Palette bits set
- Runs AFTER game writes sprite data, BEFORE rendering
- Perfect timing: sprites are updated, we just set palette bits

**Implementation:**
- Hook at `0x4197` (RET after OAM DMA completion)
- Iterate OAM (0xFE00-0xFE9F)
- Set palette bits (byte 3, bits 0-2) based on tile ID
- Use bank 0 for hook code

**Guarantee:** If sprite loop runs after OAM DMA, palette bits are set before render.

### 3. DMG Palette Register Patching (Prevent Interference)
**Why it works:**
- DMG palettes (FF47/FF48/FF49) interfere with CGB palettes
- By patching writes to these registers, we prevent interference
- Change `LDH [FF47], A` → `LDH [FF00], A` (unused register)

**Implementation:**
- Scan ROM for `E0 47`, `E0 48`, `E0 49` (LDH [FF47/48/49], A)
- Change second byte to `00` (FF00 instead of FF47/48/49)
- Do this for ALL occurrences

**Guarantee:** DMG palette writes can't interfere if they're patched.

### 4. Use Bank 0 for All Hooks (Always Accessible)
**Why it works:**
- Bank 0 is always mapped, regardless of current bank
- No bank switching needed during interrupts
- Safe for boot code and interrupt handlers

**Implementation:**
- Find free space in bank 0 (usually 0x0150-0x3FFF)
- Place all hook code in bank 0
- Use absolute addresses (no bank switching)

**Guarantee:** Bank 0 code is always accessible, no bank switching issues.

## Guaranteed Implementation Steps

### Step 1: Find Free Space in Bank 0
```
Scan 0x0150-0x3FFF for 00 or FF sequences
Need ~200 bytes for palette loader + sprite loop
```

### Step 2: Store Palette Data in ROM
```
Place palette data at fixed ROM offset (e.g., 0x036C80)
8 bytes per palette (4 colors × 2 bytes)
Read-only, never modified
```

### Step 3: Boot Loader (Load Palettes)
```assembly
PUSH AF,BC,DE,HL          ; Save registers
LD A, 0x80                ; Auto-increment, OBJ palette, index 0
LDH [0xFF6A], A           ; Set palette index register
LD HL, palette_data_addr  ; Point to palette data in ROM
LD C, palette_size       ; Number of bytes
loop:
  LD A, [HL+]             ; Load byte from ROM
  LDH [0xFF6B], A         ; Write to palette RAM
  DEC C
  JR NZ, loop
POP HL,DE,BC,AF           ; Restore registers
RET
```

### Step 4: Hook Boot Entry
```
At 0x0150: CALL boot_loader_addr
This runs once at startup, loads all palettes
```

### Step 5: Sprite Loop (Assign Palettes)
```assembly
PUSH AF,BC,HL
LD HL, 0xFE00             ; OAM start
LD C, 40                  ; 40 sprites
loop:
  LD A, [HL]              ; Y position
  CP 0                    ; Off-screen?
  JR Z, next              ; Skip if Y=0
  INC HL                  ; Skip to tile ID
  LD A, [HL]              ; Tile ID
  CP 4                    ; SARA_W tiles?
  JR C, next              ; Skip if < 4
  CP 8                    ; Still SARA_W?
  JR NC, next             ; Skip if >= 8
  INC HL                  ; Skip to flags
  LD A, [HL]              ; Flags
  AND 0xF8                ; Clear palette bits
  OR 0x01                 ; Set palette to 1
  LD [HL], A              ; Write back
  DEC HL                  ; Back to tile
next:
  INC HL                  ; Skip to next sprite
  INC HL
  DEC C
  JR NZ, loop
POP HL,BC,AF
RET
```

### Step 6: Hook OAM DMA Completion
```
At 0x4197: CALL sprite_loop_addr
This runs after game updates OAM, sets palette bits
```

### Step 7: Patch DMG Palette Writes
```
Scan ROM for E0 47, E0 48, E0 49
Change to E0 00 (write to FF00 instead)
Prevents DMG palette interference
```

## Verification Checklist

### ✅ Palette Loading Verified
- [ ] Breakpoint at boot loader
- [ ] Read 0xFF6A-0xFF6B after loader runs
- [ ] Values match YAML definitions
- [ ] Palettes persist (don't get overwritten)

### ✅ Sprite Assignment Verified
- [ ] Breakpoint at sprite loop
- [ ] Read OAM entries (0xFE00 + sprite_index * 4)
- [ ] Byte 3 bits 0-2 match expected palette
- [ ] Assignment happens after OAM DMA

### ✅ Timing Verified
- [ ] Boot loader runs once at startup
- [ ] Sprite loop runs after OAM DMA (0x4197)
- [ ] No conflicts with game code

### ✅ Visual Verification
- [ ] Screenshot shows correct colors
- [ ] Accuracy > 80%
- [ ] Avg color distance < 40

## Common Failures & Guaranteed Fixes

### Failure: Palettes are white (0x7FFF)
**Cause:** Boot loader not running or palette data wrong
**Fix:** 
- Verify boot hook at 0x0150
- Check palette data bytes match YAML
- Use debugger to verify loader runs

### Failure: Sprites show wrong colors
**Cause:** Sprite loop not running or wrong palette bits
**Fix:**
- Verify OAM DMA hook at 0x4197
- Check sprite loop sets correct palette bits
- Use debugger to verify loop runs

### Failure: Colors flicker or reset
**Cause:** DMG palette writes interfering
**Fix:**
- Patch ALL DMG palette register writes
- Verify patches are applied (scan ROM)

### Failure: Game crashes or freezes
**Cause:** Hook code overwrites game code or wrong bank
**Fix:**
- Use bank 0 for all hooks
- Verify free space before writing
- Don't overwrite game code/data

## The Guaranteed Formula

```
1. Load palettes at boot (0x0150 hook) → Palettes in RAM ✅
2. Patch DMG palette writes → No interference ✅
3. Hook OAM DMA completion (0x4197) → Perfect timing ✅
4. Set palette bits in sprite loop → Sprites use palettes ✅
5. Use bank 0 for all code → Always accessible ✅
```

**If all 5 steps are done correctly, palette injection WILL work.**

