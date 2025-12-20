# Automated Palette Patching System

## Overview

This system semi-automates the process of finding and patching the game's palette assignment code, making it less tedious while maintaining reliability.

## Tools

### 1. `automated_palette_patcher.py`
**Fully automated workflow** - traces OAM writes, analyzes patterns, and generates patches.

**Usage:**
```bash
python3 scripts/automated_palette_patcher.py
```

**What it does:**
1. Runs mGBA with tracing script for 10 seconds
2. Analyzes trace log to find patterns
3. Identifies consistent tile→palette mappings
4. Finds code locations that write to OAM
5. Generates lookup table from YAML config
6. Creates patch suggestions

**Output:**
- `oam_write_trace.log` - Detailed trace of OAM writes
- `rom/working/penta_dragon_auto_patched.gb` - Patched ROM (needs manual verification)

### 2. `semi_auto_patch.py`
**Interactive workflow** - guides you through the process with manual verification steps.

**Usage:**
```bash
python3 scripts/semi_auto_patch.py
```

**What it does:**
1. Traces OAM writes (with your approval)
2. Shows analysis results
3. Offers to disassemble top functions
4. Shows disassembly for manual review
5. Guides you through manual patching

**Best for:** First-time use, learning the process

### 3. `disassemble_function.py`
**Standalone disassembler** - disassemble any function in the ROM.

**Usage:**
```bash
python3 scripts/disassemble_function.py <rom_path> <address> [max_bytes]
python3 scripts/disassemble_function.py rom.gb 0x0824 100
```

**What it does:**
- Disassembles Game Boy assembly code
- Shows opcodes and instructions
- Helps understand game's code structure

### 4. `trace_oam_writes.lua` / `improved_trace_oam_writes.lua`
**mGBA Lua scripts** - trace OAM writes during gameplay.

**What they log:**
- Frame number
- Sprite index
- Tile ID
- Palette assigned
- Program counter (approximate)

## Workflow

### Quick Start (Fully Automated)

```bash
# 1. Run automated patcher
python3 scripts/automated_palette_patcher.py

# 2. Review generated patches
# 3. Manually verify and refine patches
# 4. Test patched ROM
```

### Recommended (Semi-Automated)

```bash
# 1. Run interactive workflow
python3 scripts/semi_auto_patch.py

# 2. Follow prompts to:
#    - Trace OAM writes
#    - Review analysis
#    - Disassemble functions
#    - Create patches manually

# 3. Test patches incrementally
```

### Manual (Most Control)

```bash
# 1. Trace OAM writes
mgba-qt rom.gb --script scripts/improved_trace_oam_writes.lua

# 2. Analyze trace log manually
cat oam_write_trace.log

# 3. Disassemble specific functions
python3 scripts/disassemble_function.py rom.gb 0x0824 100

# 4. Create patches manually
# 5. Test incrementally
```

## Understanding the Output

### Trace Log Format
```
--- Frame 42 ---
Sprite[0]: Tile=4 Palette=1 Flags=0x01 PC=0x0824
Sprite[1]: Tile=5 Palette=1 Flags=0x01 PC=0x0824
```

- **Frame**: Game frame number
- **Sprite**: OAM sprite index (0-39)
- **Tile**: Sprite tile ID
- **Palette**: Palette assigned (0-7)
- **Flags**: Full flags byte
- **PC**: Program counter (where code was executing)

### Analysis Results

**Consistent tiles**: Tiles that always use the same palette - these are good candidates for patching.

**PC counts**: Code locations that write to OAM frequently - these are functions we should patch.

**Write locations**: All OAM writes with context - helps understand patterns.

## Creating Patches

Once you've identified a function to patch:

1. **Disassemble the function**:
   ```bash
   python3 scripts/disassemble_function.py rom.gb 0x0824 100
   ```

2. **Find palette assignment code**:
   - Look for `AND 0xF8` (clears palette bits)
   - Look for `OR 0xXX` (sets palette)
   - Look for `LD [HL], A` (writes to OAM)

3. **Replace with lookup table access**:
   ```assembly
   ; Original:
   LD A, [HL]      ; Get tile ID
   AND 0xF8        ; Clear palette
   OR 0x01         ; Set palette 1
   LD [HL], A      ; Write back
   
   ; Patched:
   LD A, [HL]      ; Get tile ID
   LD HL, 0x6E00   ; Lookup table base
   ADD HL, A       ; HL = table[tile]
   LD A, [HL]      ; Get palette from table
   CP 0xFF         ; Check if modify
   JR Z, skip      ; Skip if 0xFF
   ; ... apply palette ...
   ```

4. **Test incrementally**: Patch one function at a time, test, then move to next.

## Tips

- **Start small**: Patch one function first, test thoroughly
- **Keep backups**: Save working ROMs before patching
- **Test frequently**: Test after each patch
- **Use consistent tiles**: Focus on tiles that always use same palette first
- **Document patches**: Keep notes on what each patch does

## Troubleshooting

**Trace log empty?**
- Make sure mGBA ran long enough
- Check that ROM has sprites visible
- Verify Lua script is working

**No consistent tiles found?**
- Game may use dynamic palettes
- Try longer trace duration
- Look for patterns in specific frames

**Disassembly looks wrong?**
- Address might be in wrong bank
- Try different starting addresses
- Check if function uses bank switching

