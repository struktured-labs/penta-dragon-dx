# Entity Data Structure Analysis

## Overview

This document records findings from reverse engineering the entity data structure at WRAM 0xC200-0xC2FF.

## Key Discovery: Entity Marker Pattern

Entities in the 0xC200 region are marked with a `FE FE FE` header pattern:

```
FE FE FE XX ...
```

Where `XX` is the **entity type ID**.

## Known Entity Types

| Type ID | Hypothesized Identity | Evidence |
|---------|----------------------|----------|
| `0x17` | Regular enemy (common) | Appears multiple times in dumps |
| `0x1D` | Miniboss / Special enemy | Appears less frequently |
| `0x1E` | TBD | |
| `0x1F` | TBD | |

## Entity Structure (Hypothesized)

Based on pattern analysis, entities appear to use **24-byte structures**:

```
Offset  Size  Purpose
------  ----  -------
+0      1     Marker byte 1 (0xFE = active)
+1      1     Marker byte 2 (0xFE)
+2      1     Marker byte 3 (0xFE)
+3      1     Entity Type ID (0x17, 0x1D, etc.)
+4      2     Unknown (possibly position or tile base)
+5-7    3     Unknown (animation/state data?)
+8-15   8     Pattern data (01 02 alternating)
+16-19  4     Unknown
+20-21  2     Terminator or link (00 00)
+22-23  2     Padding
```

## Example Entity Entries

From gamestate_1.txt (0xC200):
```
C200: FE FE FE 17 26 29 22 23 01 02 01 02 01 02 01 02
C210: 01 02 01 05 20 21 00 00
```
- Type: 0x17 (regular enemy)
- Total: 24 bytes

```
C230: FE FE FE 1D 14 15 26 27 01 02 01 02 01 02 01 02
C240: 01 02 03 04 24 25 00 00
```
- Type: 0x1D (possibly miniboss/special)
- Total: 24 bytes

## OAM Slot Correlation

### Hypothesis: Entity Order = OAM Slot Order

Entities at 0xC200+ may map to OAM slots 4+ in order:
- Entity at 0xC200 → OAM slots 4-7 (4 sprites per entity)
- Entity at 0xC218 → OAM slots 8-11
- Entity at 0xC230 → OAM slots 12-15
- etc.

This needs verification via testing.

### Sara's Slots

Sara always uses OAM slots 0-3. Sara's entity data may be stored elsewhere (not at 0xC200+).

## Memory Map Summary

| Address | Purpose |
|---------|---------|
| `0xC000-0xC09F` | Shadow OAM buffer 1 |
| `0xC100-0xC19F` | Shadow OAM buffer 2 |
| `0xC200-0xC2FF` | Entity data (8-10 entities max) |
| `0xFFBF` | Boss flag (confirmed working) |
| `0xFE00-0xFE9F` | Hardware OAM |

## Verification Tasks

1. [ ] Run `analyze_entity_data.lua` during gameplay with different enemy types
2. [ ] Correlate entity type changes with visual enemy changes
3. [ ] Verify 24-byte structure assumption
4. [ ] Find entity-to-OAM-slot mapping
5. [ ] Test boss flag behavior with different boss types

## Usage for Palette Assignment

Once entity types are confirmed, the palette assignment logic will be:

```python
ENTITY_TYPE_TO_PALETTE = {
    0x17: 4,  # Regular enemy -> Blue
    0x1D: 5,  # Miniboss -> Red/Purple
    0x1E: 6,  # Special -> Yellow
    0x1F: 7,  # Boss -> Orange
}
```

The pre-loop scanner will:
1. Scan 0xC200+ for `FE FE FE XX` patterns
2. Extract entity type `XX`
3. Look up palette in mapping table
4. Store in HRAM array for constrained loop to use
