# Gap: D880 State 0x08 — Unique 3-Substate Combat State

## Structure

State 0x08 is the only state in 0x02-0x09 with **3 substate handler pairs** (others have 2). Data table at file offset 0xE328 (bank3:0x6328):

```
+0x00: 02            marker
+0x01: 03            substate count = 3
+0x02-0x03: FF 01    config
+0x04-0x07: 05 07 09 89   common signature
+0x08+: 6 handler pointers (3 substates × 2 handlers each)
```

| Substate | Handler A | Handler B | Purpose |
|----------|-----------|-----------|---------|
| 0 | 0x6398 | 0x63A0 | Arena setup / first-frame render |
| 1 | 0x6451 | 0x6485 | Active combat (input/AI/damage) |
| 2 | 0x63AD | 0x645E | Post-combat finalize / cleanup / state transition |

## Substate Counter

Sub-counter at WRAM 0xDDA8 (read by all substate dispatchers). Increments through 0→1→2 as combat progresses.

## Per-Substate Behavior

### Substate 0 (Arena Setup) — 0x6398 / 0x63A0

- Calls `0x068F` (likely arena/tilemap init)
- Multiple `0x5809` writes to WRAM state vars
- Reads from (DE) entity reference
- Pushes/pops AF, BC, DE, HL (full register save)

### Substate 1 (Active Combat) — 0x6451 / 0x6485

- Calls `0x5804` (read helper) and `0x5809` (write helper)
- Calls `0x0671` (entity AI / collision)
- Calls `0x53A5` (animation/sprite update)
- Heavy conditional branching (B7 OR A; JR Z/NZ)
- Loops via `JP NZ, 0x63F4`
- RST $10 trigger at end

### Substate 2 (Cleanup) — 0x63AD / 0x645E

- Reads game state pointer at 0xDE48
- Reads outcome counter at 0xDDA8
- Conditional early return (RET Z) if no outcome
- Two `0x0671` calls for entity cleanup
- `LD DE,$01B0` for secondary WRAM cleanup
- RST $10 + D880 transition

## Why 3 Substates Instead of 2

Combat is a 3-phase encounter (setup → fight → cleanup). With 2 substates, each handler would need internal branching for "is_arena_ready" / "is_combat_active" / "is_combat_done." The 3-substate structure cleanly separates:

- **Setup**: arena init runs exactly once
- **Combat**: input/AI/damage loop runs N frames
- **Cleanup**: victory/defeat animation + reward + transition runs once

This avoids race conditions where cleanup might fire mid-combat and matches the same N=3 phase pattern visible in the boss-defeat sequence.

## Common Helpers

| Address | Purpose |
|---------|---------|
| 0x068F | Arena initialization |
| 0x0671 | Entity / combat logic dispatcher |
| 0x5804 | WRAM read helper |
| 0x5809 | WRAM write helper |
| 0x53A5 | Animation / sprite update |
| 0x63DF | Render / sprite setup |

## State Transitions

- **Entry**: from state 0x07 (AI/collision) when combat condition met
- **Exit**: from substate 2 handler B → state 0x09 (finalize) or state 0x02 (gameplay)
- Mechanism: RST $10 + D880 write at end of 0x645E

## Caveat

Some opcode interpretations from the agent's disassembly (e.g., `04 CD 09 58` at start of 0x6398) read as `INC B; CALL 0x5809` which is plausible but the surrounding bytes need verification against actual ROM. The substate split (3 vs 2) is structurally confirmed by the data-table marker at 0x6328.
