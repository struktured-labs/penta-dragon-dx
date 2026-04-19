# Gap #9: SRAM Checkpoint Slot Layout

## Verified Structure

- **7 slots × 0x28 bytes (40 bytes each)** = 0x118 total = 280 bytes
- SRAM addresses: 0xBF00 — 0xC017 (slots 5-6 cross 0xC000 boundary)
- 7-iteration save loop confirmed at ROM 0x86FD-0x8724
- Level-select code at 0x7393 reads checkpoint via input loop at 0x73C3

## Per-Byte Field Map (best inference, needs runtime confirmation)

| Offset | Size | Field | WRAM Source | Notes |
|--------|------|-------|-------------|-------|
| 0x00 | 1 | Validity flag | — | Likely magic byte / checksum |
| 0x01-0x02 | 2 | Scroll X (16-bit) | DC00-DC01 | Coarse scroll position |
| 0x03-0x04 | 2 | Scroll Y (16-bit) | DC02-DC03 | Coarse scroll position |
| 0x05 | 1 | Level/boss index | FFBA | 0-8 |
| 0x06 | 1 | Room | FFBD | 1-7 |
| 0x07 | 1 | Sara form | FFBE | 0=Witch, 1=Dragon |
| 0x08 | 1 | Powerup | FFC0 | 0/1/2/3 |
| 0x09 | 1 | Mini-boss flag | FFBF | 0=normal, 1-16 |
| 0x0A | 1 | HP main | DCDD | 0-23 |
| 0x0B | 1 | HP sub | DCDC | 0-255 decay |
| 0x0C | 1 | Timer sec | FFF5 | BCD |
| 0x0D | 1 | Timer min | FFF6 | BCD |
| 0x0E-0x12 | 5 | Section data | DC04-DC08 | Spawn-id + descriptor |
| 0x13-0x27 | 21 | Spawn/state | DCB8 + entity flags | Entity counter, scroll state |

## ROM Code Locations

- 49 LDI A,(HL) / LDI (DE),A copy patterns indicating bulk save/load transfers
- SRAM base loaded at ROM offsets 0x30DBE, 0x252DF, 0x3824F
- SRAM bank-switch sequences at 0x09CF-0x09D1 and 0x1B49

## Sample SRAM State

The shipped `.sav` is all 0xFF (no checkpoints saved yet — fresh ROM).

## Open Questions

- Exact validity-flag mechanism at offset 0x00 (magic byte vs. checksum vs. counter)
- Whether 0x13-0x27 includes RNG seed for deterministic re-entry
- Whether slot 6 truly straddles the 0xC000 SRAM boundary or is in an unused page

## Verification Plan

1. Use mgba Lua: dump 0xBF00-0xC017 before and after save-on-checkpoint
2. Diff against the known WRAM/HRAM addresses at save time
3. Manually corrupt offset 0x00 in .sav and check whether level select rejects the slot (validates "validity flag" theory)
