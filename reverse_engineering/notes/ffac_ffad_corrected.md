# FFAC/FFAD Per-Level Pointer Table — CORRECTED

## Earlier Claim (WRONG)

In `runtime_probe_findings.md` I stated: "FFAC/FFAD = constant $4000 at game start; not per-level."

That conclusion was **wrong** — derived from a probe that wrote FFBA without triggering a level transition. FFBA alone doesn't update FFAC/FFAD; the game only refreshes the pointer pair on actual level entry.

## Correct Behavior (verified via existing autoplay_full_game.lua)

FFAC/FFAD IS the per-level spawn-table pointer. The autoplay script empirically maps:

| Level | FFAC | FFAD | GB Pointer | File Offset | Bosses |
|-------|------|------|------------|-------------|--------|
| 1 | 0x00 | 0x40 | $4000 | 0x34000 | Gargoyle, Spider |
| 2 | 0xC8 | 0x43 | $43C8 | 0x343C8 | Crimson, Ice |
| 3 | 0x3F | 0x46 | $463F | 0x3463F | Void, Poison |
| 4 | 0x42 | 0x4C | $4C42 | 0x34C42 | All 8 (Knight + Angela debut) |
| 5 | 0xF2 | 0x4C | $4CF2 | 0x34CF2 | Boss9, Boss10 |
| 6 | 0xFD | 0x4D | $4DFD | 0x34DFD | Boss11, Boss12 |
| 7 | 0x10 | 0x50 | $5010 | 0x35010 | Boss13, Boss14, all prior |
| 8 | 0xEF | 0x50 | $50EF | 0x350EF | Boss15, Boss16 |

All pointers land in bank 13 (0x34000-0x37FFF), confirming bank 13's role as the spawn-table data bank.

## Spawn Table Format (more complex than originally documented)

The 5-byte spawn entries we documented earlier (at file 0x34024 onward) are still valid. But the FFAC/FFAD pointer references a **different** data structure that level-switching code consumes.

Reading raw bytes at L1's pointer (file 0x34000):
```
24 40 22 40 43 40 4B 40 23 40 4C 40 4D 40 4E 40 ...
```

These look like 16-bit LE pointers: `$4024, $4022, $4043, $404B, $4023, ...`. But dereferencing `idx 2 = $4043` does NOT yield the gargoyle entry (which lives at $402F per memory). So the format is more sophisticated than a simple pointer list — possibly:

- A list of slot-pointers PLUS inline data
- A list of room-or-section pointers separate from spawn entries
- DCB8 indexes a SUB-table reached through one of the FFAC pointers

The autoplay script just resets `DCB8=0` after switching FFAC/FFAD and lets the game's own logic figure out spawn order from the pointer-table contents. That works empirically.

## Why My Earlier Probe Failed to Detect This

In `runtime_probe.lua` Round 1, I cycled FFBA values (0..8) without triggering an actual level transition. FFAC/FFAD were never updated by the game because the transition code (likely in bank 0 or 12) only runs on legitimate level entry — not on raw FFBA writes.

## Lessons

1. **Static probes that write but don't trigger control flow miss data refreshes.** Need to either drive game-side transitions or manually invoke the update routine.
2. **Existing infrastructure is gold.** The autoplay scripts already encoded this knowledge. Should have searched harder before declaring something "constant."
3. **FFAD:FFAC = $4000 IS correct for level 1.** That's where it sits at game start. The "constant" observation was correct in scope; the error was generalizing to "not per-level."

## Suggested Architecture Doc Update

Section 12.5 (FFAC/FFAD) should note: per-level pointer pair, table mapping verified, value at game start = $4000 for level 1.
