# Stage Detection - Penta Dragon DX

## Summary

Successfully identified the stage/level address in Penta Dragon's memory through systematic memory scanning using MCP tools. This enables per-stage palette customization and jet form sprite coloring for the bonus stage.

## Key Findings

### Stage Address: 0xFFD0

**Memory Location:** `0xFFD0` (HRAM)

**Values:**
- `0x00` = Level 1 (main dungeon)
- `0x01` = Bonus stage (jet/spaceship stage)
- `0x02-0x04` = Presumably Levels 2-5 (not yet tested)

### Verification Method

Used `mcp__mgba__mgba_read_range` tool (headless emulator) to scan HRAM across multiple save states:

```bash
# Level 1 save state
FFD0: 00 31 1F 14 E0 24 04 0C 02 04 00 04 00 17 00 00

# Bonus stage save state
FFD0: 01 15 FC 08 4B 15 0D 02 01 08 00 08 00 17 01 00
```

First byte at 0xFFD0 shows consistent stage values (0x00 vs 0x01).

## Implementation Plan

### Jet Form Palettes (v0.98 YAML)

Added to `palettes/penta_palettes_v097.yaml`:

```yaml
obj_palettes:
  # Palette 2 (Alt) - SARA W JET (Spaceship form - magenta/purple)
  SaraWitchJet:
    colors: ["0000", "7C1F", "5817", "3010"]  # Trans, Magenta, Purple, Dark purple

  # Palette 1 (Alt) - SARA D JET (Spaceship form - cyan/electric blue)
  SaraDragonJet:
    colors: ["0000", "7FE0", "4EC0", "2D80"]  # Trans, Bright cyan, Blue, Dark blue
```

### Code Integration (Bank 13)

**Palette Loader Pseudocode:**

```asm
; Read stage flag
LDH A, [0xFFD0]
LD B, A              ; Save for later

; Load BG palettes (all 8, 64 bytes)
LD HL, palette_data
LD A, 0x80
LDH [BCPS], A
LD C, 64
bg_loop:
  LD A, [HL+]
  LDH [BCPD], A
  DEC C
  JR NZ, bg_loop

; Load OBJ palette 0 (Effects - always same)
LD A, 0x80
LDH [OCPS], A
; ... load 8 bytes ...

; Load OBJ palette 1 (Sara Dragon - stage-dependent)
LD A, 0x88           ; Palette 1
LDH [OCPS], A
LD HL, sara_dragon_normal
LD A, B              ; Check stage
CP 1
JR NZ, +3
LD HL, sara_dragon_jet
; ... load 8 bytes from HL ...

; Load OBJ palette 2 (Sara Witch - stage-dependent)
LD A, 0x90           ; Palette 2
LDH [OCPS], A
LD HL, sara_witch_normal
LD A, B              ; Check stage
CP 1
JR NZ, +3
LD HL, sara_witch_jet
; ... load 8 bytes from HL ...

; Load OBJ palettes 3-7 (normal)
; ...
```

**Key Implementation Details:**

1. **OCPS Register Must Be Set Explicitly** - Each OBJ palette load must set OCPS with auto-increment bit (0x80) + palette index
   - Palette 0: 0x80
   - Palette 1: 0x88
   - Palette 2: 0x90
   - Palette 3: 0x98
   - Palette 6: 0xB0
   - Palette 7: 0xB8

2. **Address Allocation** - Ensure no overlaps in Bank 13:
   - Palette data: 0x6800 (128 bytes: 64 BG + 64 OBJ)
   - Boss palettes: 0x6880 (16 bytes: Gargoyle + Spider)
   - Jet palettes: 0x6890 (16 bytes: Sara W Jet + Sara D Jet)
   - Palette loader: 0x6900 (~140-150 bytes)
   - Shadow colorizer: 0x6990 (52 bytes)
   - Tile colorizer: 0x69D0 (97 bytes)
   - Combined function: 0x6A80 (13 bytes)
   - BG lookup table: 0x6B00 (256 bytes)
   - BG colorizer: 0x6C00 (53 bytes)

3. **Backwards Compatibility** - Normal levels (stage=0x00) still use standard Sara palettes

## Testing Results

### Save States Used

- **Level 1**: `save_states_for_claude/level1_sara_w_alone.ss0`
  - Stage flag: 0x00 ✓
  - Expected colors: Pink witch, green dragon

- **Bonus stage**: `save_states_for_claude/level1_sara_w_in_jet_form_secret_stage.ss0`
  - Stage flag: 0x01 ✓
  - Expected colors: Magenta jet (W), cyan jet (D)

### MCP Tool Usage

All testing performed with **headless MCP tools** (no GUI windows):

```python
# Memory scanning
mcp__mgba__mgba_read_range(
    rom_path="...",
    savestate_path="...",
    start_address=65488,  # 0xFFD0
    length=16,
    frames=10
)

# Visual verification
mcp__mgba__mgba_run_sequence(
    rom_path="...",
    savestate_path="...",
    frames=180,
    capture_every=60
)
```

## Known Issues

### v2.27 Implementation Bugs

- Code overlaps in Bank 13 (palette loader @ 0x6900 extending into shadow colorizer @ 0x6980)
- OCPS register not set correctly between palette loads
- ROM crashes on boot (white screen)

### Next Steps

1. **Fix v2.27 address overlaps** - Move shadow_colorizer to 0x6990+
2. **Explicit OCPS management** - Set OCPS for each palette load
3. **Test with working v2.26 as base** - Minimal incremental changes
4. **Verify colors visually** - Capture screenshots with both save states
5. **Create regression tests** - Automate color verification

## Future Enhancements

### Per-Stage BG Palettes

Currently all stages use the same 8 BG palettes. Could implement:

```asm
; Load different BG palette sets per stage
LD A, [0xFFD0]       ; Stage flag
CP 1
JR Z, load_bonus_bg
; Level 1: Load dungeon BG palettes
LD HL, dungeon_bg_palettes
JR load_bg
load_bonus_bg:
; Bonus: Load spaceship BG palettes
LD HL, spaceship_bg_palettes
load_bg:
; ... load 64 bytes ...
```

This would allow:
- Level 1: Blue dungeon theme
- Bonus stage: Dark blue spaceship theme
- Level 2-5: Custom themes per level

### Stage-Specific Tile Ranges

Bonus stage uses different tile IDs (0x60-0x7C for spaceship graphics). Could add tileset detection as fallback if stage address is unreliable.

## References

- Original memory scan: 2026-01-21
- YAML v0.98: Added jet form palettes
- MCP tools: `mgba_read_range`, `mgba_run`, `mgba_run_sequence`
- Base implementation: v2.26 (working BG + OBJ colorization)
