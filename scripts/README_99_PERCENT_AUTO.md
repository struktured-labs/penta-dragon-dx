# 99% Automated Palette Patching

## One Command Solution

```bash
python3 scripts/one_command_patch.py
```

That's it! This single command will:

1. ✅ Trace OAM writes automatically (10 seconds)
2. ✅ Analyze patterns to find consistent mappings
3. ✅ Generate lookup table from YAML config
4. ✅ Find functions that assign palettes
5. ✅ Generate assembly code patches automatically
6. ✅ Apply patches to ROM automatically
7. ✅ Verify results automatically

## What Gets Automated

### Fully Automated (99%)
- **Tracing**: Runs mGBA, traces OAM writes, saves logs
- **Analysis**: Finds patterns, identifies consistent mappings
- **Function Discovery**: Finds code locations to patch
- **Code Generation**: Generates assembly code patches
- **Patch Application**: Applies patches to ROM
- **Verification**: Runs automated tests

### Manual (1% - Verification Only)
- **Review Results**: Check if patches work correctly
- **Test ROM**: Play game to verify colors

## Output

After running, you'll get:

- `rom/working/penta_dragon_auto_patched.gb` - Fully patched ROM
- `oam_write_trace.log` - Detailed trace of OAM writes
- Console output showing all steps and results

## How It Works

### Step 1: Tracing
- Launches mGBA with Lua tracing script
- Captures all OAM palette writes for 10 seconds
- Logs tile IDs, palettes, and code locations

### Step 2: Analysis
- Parses trace log
- Finds tiles that consistently use same palette
- Identifies code locations (PC addresses) that write to OAM
- Ranks locations by frequency

### Step 3: Lookup Table Generation
- Reads `palettes/monster_palette_map.yaml`
- Creates 256-byte lookup table
- Maps tile IDs → palette IDs
- Stores at Bank 13 @ 0x6E00

### Step 4: Function Discovery
- Finds function starts (looks for PUSH patterns)
- Locates palette assignment code (AND 0xF8, OR X patterns)
- Identifies insertion points for patches

### Step 5: Code Generation
- Generates assembly code to:
  - Read tile ID from OAM
  - Lookup palette from table
  - Check if should apply (0xFF = skip)
  - Apply palette to OAM flags byte
- Calculates jump offsets automatically

### Step 6: Patch Application
- Writes lookup table to ROM
- Injects patch code at identified locations
- Preserves original code structure
- Handles bank switching

### Step 7: Verification
- Runs automated ROM verification
- Checks for distinct colors
- Verifies ROM stability
- Reports results

## Example Output

```
🤖 99% Automated Palette Patching System
============================================================
🔍 Step 1/6: Tracing OAM writes (10s)...
   ✓ Trace complete
📊 Step 2/6: Analyzing trace log...
   ✓ Found 15 consistent tile→palette mappings
   ✓ Found 8 code locations writing to OAM
📋 Step 3/6: Generating lookup table...
   ✓ Generated 256-byte lookup table
   ✓ Mapped 15 tiles
🔎 Step 4/6: Finding functions to patch...
   ✓ Found 3 functions to patch
🔧 Step 5/6: Generating patches...
   ✓ Generated 3 patches
⚙️  Step 6/6: Applying patches...
   ✓ Wrote lookup table to 0x6E00
   ✓ Patch 1: Applied at 0x0824 (25 bytes)
   ✓ Patch 2: Applied at 0x0950 (25 bytes)
   ✓ Patch 3: Applied at 0x0A10 (25 bytes)
   ✓ Saved patched ROM to rom/working/penta_dragon_auto_patched.gb

✅ Verification: Running automated test...
   ✓ Verification PASSED

✅ Automation complete!
   Patched ROM: rom/working/penta_dragon_auto_patched.gb
   Verification: PASSED
```

## Troubleshooting

### "ROM not found"
- Run `python3 scripts/penta_cursor_dx.py` first to create base ROM

### "No functions found to patch"
- Game may use different code patterns
- Try longer trace duration
- Check trace log manually

### "Verification failed"
- Patches may need adjustment
- Review generated patches
- Test ROM manually

### "Not enough space"
- Function may be too small
- Try patching fewer functions
- Use different insertion point

## Advanced Usage

### Custom Trace Duration
```python
patcher = FullAutoPatcher(rom_path, yaml_path)
log_file = patcher.trace_oam_writes(duration=20)  # 20 seconds
```

### Manual Patch Review
```python
patcher = FullAutoPatcher(rom_path, yaml_path)
# ... run steps 1-5 ...
patches = patcher.generate_patches(functions)

# Review patches before applying
for patch in patches:
    print(f"Function: 0x{patch['function']['start']:04X}")
    print(f"Code: {patch['code'].hex()}")
    
# Then apply
patcher.apply_patches(patches, output_path)
```

## Files Generated

- `rom/working/penta_dragon_auto_patched.gb` - Patched ROM
- `oam_write_trace.log` - OAM write trace
- Console output with full details

## Next Steps After Automation

1. **Test ROM**: Load in mGBA and play
2. **Verify Colors**: Check if Sara W is green/orange
3. **Check Stability**: Ensure no crashes
4. **Review Patches**: If issues, review generated code
5. **Iterate**: Adjust YAML config and re-run

## Success Criteria

✅ ROM loads without crashes
✅ Sara W appears green/orange (not red/black)
✅ Other sprites maintain distinct colors
✅ Game runs at normal speed
✅ No visual glitches

