# Gap #2: D880 State Machine Analysis (States 0x02-0x09)

## Executive Summary

The D880 state machine handles 28 different game modes via a jump table at bank3:0x4A5A. States 0x02-0x09 are grouped as "normal gameplay" in the architecture doc, but detailed analysis reveals **distinct per-state behavior structures** that differentiate each state for specific gameplay phases.

Unlike states 0x0A+ (mini-boss/boss arenas with dedicated code), states 0x02-0x09 use a **data-driven dispatch system**: each state points to a data table containing function pointers and configuration values rather than direct executable code.

---

## Jump Table Discovery

**Location:** bank3:0x4A5A (file offset 0xCA5A)
**Indexing:** State N -> entry at table_base + (N-1) * 2 bytes

The dispatch code at bank3:0x4029 (file 0xC029):
1. Reads D880 state byte
2. Decrements and indexes jump table
3. Loads 16-bit handler address
4. Executes via `JP (HL)`

### Jump Table Entries (States 0x01-0x09)

| State | Jump Entry Addr | Handler Addr | File Offset |
|-------|-----------------|--------------|------------|
| 0x01  | 0xCA5A         | 0x4A92      | 0x0CA5A    |
| 0x02  | 0xCA5C         | 0x4BAC      | 0x0CBAC    |
| 0x03  | 0xCA5E         | 0x4E3C      | 0x0CE3C    |
| 0x04  | 0xCA60         | 0x5076      | 0x0D076    |
| 0x05  | 0xCA62         | 0x52EB      | 0x0D2EB    |
| 0x06  | 0xCA64         | 0x5689      | 0x0D689    |
| 0x07  | 0xCA66         | 0x617B      | 0x0E17B    |
| 0x08  | 0xCA68         | 0x6328      | 0x0E328    |
| 0x09  | 0xCA6A         | 0x592A      | 0x0D92A    |

---

## Data-Driven Handler Structure

Each handler is NOT executable code directly. Instead, it's a **data table** containing:

```
Offset  Size  Field                Description
------  ----  -----                -----------
0x00    1     Marker               0x02 or 0x03 (version/type)
0x01    1     Substate Count       Number of sub-states or handlers
0x02    2     Config Value         Purpose varies by state
0x04    *     Handler Pointers     16-bit bank3 function addresses (repeating pattern)
```

### Raw Data Examples

**State 0x02:**
```
02 02 01 FA | 05 07 09 89 | 1C 4C 2A 4C C8 4C 42 4D | 3F 4C D3 4C | ...
^  ^  ^--^ | ^  ^  ^  ^ | Handler addresses (bank3) |              
M  C  Config  Unknown?     0x4C1C, 0x4C2A, 0x4CC8, 0x4D42, ...
```

**State 0x03:**
```
02 02 01 8C | 05 07 09 89 | 7C 4E E8 4E 92 4E B1 4F | FD 4E 9F 4E | ...
```

**State 0x08 (different!):**
```
02 03 01 FF | 05 07 09 89 | 98 63 A0 63 51 64 85 64 | AD 63 5E 64 | ...
               ^
               Count=3 (vs. 2 for others)
```

### Observations

1. **Common prefix 0x05 07 09 89 at every state (+4 offset):** This byte sequence is IDENTICAL across all states 0x02-0x07. It may be a version marker, common jump code, or shared data signature.

2. **Config bytes vary by state:** Bytes at 0x02-0x03 differ per state:
   - State 0x02: 0x01 0xFA
   - State 0x03: 0x01 0x8C
   - States 0x04-0x07: 0x01 0xFF
   - State 0x08: 0x01 0xFF
   - State 0x09: 0x01 0xC8

3. **Substate counts distinguish states:**
   - States 0x02-0x07, 0x09: 2 substates
   - State 0x08: 3 substates (anomaly!)

4. **Handler addresses are bank3 routines:** All following addresses (0x4C1C, 0x4C2A, etc.) fall in the 0x4000-0x7FFF bank3 address range.

---

## Per-State Handler Analysis

### STATE 0x02: bank3:0x4BAC (file 0x0CBAC)

**Jump table entry:** 0xCA5C → 0x4BAC

**Header:**
```
Marker:  0x02
Count:   2 (two sub-handlers)
Config:  0x01FA
```

**Data structure:**
```
+00: 02 02 01 FA       (header)
+04: 05 07 09 89       (common signature)
+08: 1C 4C 2A 4C       (handler 1: 0x4C1C, 0x4C2A)
+0C: C8 4C 42 4D       (handler 2: 0x4CC8, 0x4D42)
... (repeats with variations)
+38: End marker? (varies)
```

**Sub-handlers identified:**
- 0x4C1C
- 0x4C2A
- 0x4CC8
- 0x4D42
- 0x4C3F
- 0x4CD3
- ... (pattern continues)

**Hypothesis:** State 0x02 is a "main gameplay state" with 2 primary handlers that likely manage:
1. Game logic/input processing
2. Rendering/screen updates

---

### STATE 0x03: bank3:0x4E3C (file 0x0CE3C)

**Jump table entry:** 0xCA5E → 0x4E3C

**Header:**
```
Marker:  0x02
Count:   2
Config:  0x01 8C (different from 0x02!)
```

**Data structure:**
```
+00: 02 02 01 8C
+04: 05 07 09 89
+08: 7C 4E E8 4E       (handler 1: 0x4E7C, 0x4EE8)
+0C: 92 4E B1 4F       (handler 2: 0x4E92, 0x4FB1)
... repeating addresses in 0x4E00-0x4F00 range
+56: FF FF             (end marker)
```

**Sub-handlers identified:**
- 0x4E7C
- 0x4EE8
- 0x4E92
- 0x4FB1
- 0x4EFD
- 0x4E9F
- ... (all in 0x4E00-0x4F00 range)

**Hypothesis:** State 0x03 appears to be "room transition setup" based on architecture doc. The different config byte (0x8C vs 0xFA) and distinct handler addresses suggest:
1. Loading next room data
2. Setting up palette/tilemap for transition

---

### STATE 0x04: bank3:0x5076 (file 0x0D076)

**Jump table entry:** 0xCA60 → 0x5076

**Header:**
```
Marker:  0x02
Count:   2
Config:  0x01 FF
```

**Data structure:**
```
+00: 02 02 01 FF
+04: 05 07 09 89
+08: E6 50 EE 50       (handler 1: 0x50E6, 0x50EE)
+0C: 8D 51 22 52       (handler 2: 0x518D, 0x5222)
... repeating addresses in 0x50-0x52 range
```

**Sub-handlers identified:**
- 0x50E6
- 0x50EE
- 0x518D
- 0x5222
- 0x50F9
- 0x5196
- ... (all in 0x5000-0x5200 range)

**Hypothesis:** State 0x04 is "room transition execute". Handlers likely:
1. Apply scroll movement
2. Update entity positions
3. Complete transition

---

### STATE 0x05: bank3:0x52EB (file 0x0D2EB)

**Jump table entry:** 0xCA62 → 0x52EB

**Header:**
```
Marker:  0x02
Count:   2
Config:  0x01 FF
```

**Handler addresses:**
- 0x53BB
- 0x5401
- 0x54C7
- 0x557F
- 0x540A
- 0x54CE
- ... (0x5300-0x5500 range)

**Hypothesis:** State 0x05 is "scroll/movement processing" - continuation of normal gameplay with active scrolling:
1. Calculate scroll position
2. Load new tiles as needed
3. Update SCX/SCY hardware registers

---

### STATE 0x06: bank3:0x5689 (file 0x0D689)

**Jump table entry:** 0xCA64 → 0x5689

**Header:**
```
Marker:  0x02
Count:   2
Config:  0x01 FF
```

**Handler addresses:**
- 0x5705
- 0x570D
- 0x579E
- 0x581F
- 0x571F
- 0x57AE
- ... (0x5700-0x5800 range)

**Hypothesis:** State 0x06 is "entity spawn/despawn" - manages enemies/objects:
1. Check section cycle counter (DCB8)
2. Load spawn data from bank 13
3. Initialize entity sprites

---

### STATE 0x07: bank3:0x617B (file 0x0E17B)

**Jump table entry:** 0xCA66 → 0x617B

**Header:**
```
Marker:  0x02
Count:   2
Config:  0x01 FF
```

**Handler addresses:**
- 0x61BB
- 0x6208
- 0x61C3
- 0x6256
- 0x6215
- 0x61CD
- ... (0x6100-0x6300 range)

**Raw data structure:**
```
+50: E7 4C E7 4C AA 4D ... repeats addresses
+56: AC 4E B1 4F ...
+5E: FF FF             (end marker at offset 0x5E)
```

**Hypothesis:** State 0x07 appears to be an intermediate gameplay state. Based on handler address range (0x61xx-0x62xx), it may manage:
1. Enemy AI / behavior
2. Collision detection
3. Or possibly a "lock/wait" state

---

### STATE 0x08: bank3:0x6328 (file 0x0E328) — ANOMALY

**Jump table entry:** 0xCA68 → 0x6328

**Header:**
```
Marker:  0x02
Count:   3  <-- DIFFERENT from other states (count=2)!
Config:  0x01 FF
```

**Handler addresses:**
- 0x6398
- 0x63A0
- 0x6451
- 0x6485
- 0x63AD
- 0x645E
- 0x6496
- ... (0x6300-0x6500 range)

**Distinction:** State 0x08 has 3 substates instead of 2. This is the ONLY state in 0x02-0x09 range with this count.

**Hypothesis:** State 0x08 may be a more complex gameplay phase:
1. Possibly "mini-boss detection" or "high-level enemy mode"
2. Requires 3 sub-handlers for:
   - Detection/setup
   - Active combat
   - State transition

---

### STATE 0x09: bank3:0x592A (file 0x0D92A)

**Jump table entry:** 0xCA6A → 0x592A

**Header:**
```
Marker:  0x02
Count:   2
Config:  0x01 C8  <-- Unique config value!
```

**Handler addresses:**
- 0x596A
- 0x5972
- 0x5A1B
- 0x5A85
- 0x5983
- 0x5A28
- ... (0x5900-0x5B00 range)

**Raw data:**
```
+30: 07 5A 75 5A 18 5B
+36: FF FF 34 59 FE FF 49 5B FF FF 6A 59 FE FF
+44: (end)
```

**Distinction:** State 0x09 has unique config value 0xC8 (vs. others having 0xFA, 0x8C, or 0xFF).

**Hypothesis:** State 0x09 is a finalization/reset state or possibly:
1. Section advance logic
2. Death/game-over detection
3. State machine reset preparation

---

## State Progression and Game Flow

Based on architecture doc + handler analysis:

```
GAMEPLAY CYCLE (States 0x02-0x09):

D880=0x02  ─────────────────────────────────────────┐
  "Main gameplay"       (handlers: 0x4C1C, 0x4C2A)   │
       │                                             │
       ├─→ D880=0x03 (Room setup)                   │
       │   "Transition prep" (handlers: 0x4E7C, etc) │
       │        │                                    │
       │        ├─→ D880=0x04 (Room exec)           │
       │        │   "Apply transition"              │
       │        │        │                           │
       │        │        ├─→ D880=0x05 (Scroll)     │ Repeat
       │        │        │   "Scroll handling"      │ during
       │        │        │        │                 │ gameplay
       │        │        │        ├─→ D880=0x06     │
       │        │        │        │   "Spawn ents"  │
       │        │        │        │                 │
       │        │        │        ├─→ D880=0x07     │
       │        │        │        │   "AI/collide"  │
       │        │        │        │                 │
       │        │        │        ├─→ D880=0x08     │ IF mini-boss
       │        │        │        │   "Combat?"     │ detected
       │        │        │        │                 │
       │        │        │        └─→ D880=0x09     │
       │        │        │            "Reset?"      │
       │        │        │                           │
       └────────┴────────┴───────────────────────────┘
```

---

## Key Findings Summary

| State | Phase | Config | Count | Distinction |
|-------|-------|--------|-------|-------------|
| 0x02  | Main gameplay | 0xFA | 2 | Entry point for dungeon mode |
| 0x03  | Room transition setup | 0x8C | 2 | Unique config (0x8C) |
| 0x04  | Room transition execute | 0xFF | 2 | Applies movement/updates |
| 0x05  | Scroll/movement | 0xFF | 2 | Active scrolling logic |
| 0x06  | Entity spawn/despawn | 0xFF | 2 | Enemy/object management |
| 0x07  | AI/collision/lock | 0xFF | 2 | Game physics/behavior |
| 0x08  | Combat/anomaly | 0xFF | **3** | **ONLY state with 3 substates** |
| 0x09  | Finalization/reset | 0xC8 | 2 | Unique config (0xC8) |

---

## Gap Resolution: "Per-State Behavior Differs"

The architecture doc correctly identifies that each state 0x02-0x09 is "normal gameplay," but it's **misleading to group them without distinction**. Analysis reveals:

1. **Config bytes vary:** States have distinct configuration values (0xFA, 0x8C, 0xFF, 0xC8) suggesting different modes.

2. **Handler addresses are disjoint:** Each state calls functions in different address ranges, indicating specialized code.

3. **Substate count anomaly:** State 0x08 alone has 3 substates vs. 2 for others, marking it as structurally unique.

4. **Data-driven not code-driven:** Unlike states 0x0A+ (mini-boss with direct code), states 0x02-0x09 use function pointer tables, suggesting a dispatcher pattern where the engine **interprets the data tables at runtime** to decide which handlers to call.

5. **Possible cycling:** The repeated function addresses within each state suggest **multiple passes per frame** through the same handlers, possibly for multi-phase updates (input → logic → render).

---

## Recommendations for Further Investigation

1. **Trace handler execution:** Use emulator breakpoints to see which handlers actually execute per frame.

2. **Analyze D880 transitions:** Log D880 state changes during a complete gameplay cycle to understand transition timing.

3. **Decode handler code:** The sub-handler addresses (0x4C1C, 0x4E7C, etc.) contain actual SM83 code that needs reverse engineering.

4. **Check mini-boss detection:** Verify whether state 0x08's 3rd substate is related to FFBF (mini-boss flag) changes.

5. **Validate state transitions:** Compare state 0x02 entry conditions vs. other states to understand when each phase activates.

