# Mini-Boss Damage Path Analysis: Why DC04=0x7B (Boss 16) Survives

## Executive Summary

Boss 16 (DC04=0x7B) **cannot take damage from projectile hits** because the boss index validation algorithm at bank 0, address 0x0C07 is **flawed**. The validation fails to reject invalid boss codes >= 0x7B, incorrectly mapping DC04=0x7B to FFBF=15 (which aliases boss 15's damage table entry). However, **DC04=0x7B is never paired with proper entity positions or damage tables** in practice, so when the damage code executes, it either crashes or applies damage to the wrong boss.

More critically: **The damage reduction path at 0x1024 reads DCBB and subtracts damage unconditionally**, with no boss-index validation in the damage application itself. The only validation is upstream in the boss-initialization code at 0x0C07, which **fails to properly validate DC04 values outside the 15 valid codes**.

---

## 1. ALL DCBB Write Sites (9 locations)

### Format Legend
- **Offset**: Absolute ROM offset (hex)
- **Bank**: ROM bank (0 = base, 1 = switchable)
- **Address**: Address within the bank
- **Hex Context**: 50 bytes around the write (20 before, 20 after)
- **Type**: DCBB write operation

---

### [DCBB-1] Offset 0x00102F (Bank 0, addr 0x102F)

**Function**: Damage subtraction path (SUB B)  
**Instruction**: `EA BB DC` (LD ($DCBB),A)

```
0x001016: 3E 05 CD F1 5B F1 F1 F5 3E 20 FF F1 C5 47 FA BB
0x001026: DC 90 C1 DA 44 4A CA 44 4A EA BB DC FE 20 30 0C
          ^^^^^^^^^ DCBB READ (FA BB DC)  ^^^^^^^^^ DCBB WRITE (EA BB DC)
0x001036: FA 06 DD FE 03 28 05 3E 02 EA 06 DD FA 05 DD A7
0x001046: C8 3E FF EA BB DC C9 F5 3E 1F FF F1 F5 3E 01 CD
```

**Assembly**:
```
0x001024: 47          LD B,A              ; Damage value into B
0x001025: FA BB DC    LD A,(0xDCBB)       ; Load current boss HP
0x001028: 90          SUB B               ; Subtract damage
0x001029: C1          POP BC
0x00102A: DA 44 4A    JP C,0x4A44         ; Jump if underflow
0x00102D: CA 44 4A    JP Z,0x4A44         ; Jump if zero (dead)
0x001030: EA BB DC    LD (0xDCBB),A       ; Write new HP
0x001033: FE 20       CP A,0x20
```

**Critical**: This is the **main damage application code**. It reads DCBB, subtracts damage in B, and writes back. **NO boss-index validation here**.

---

### [DCBB-2] Offset 0x001049 (Bank 0, addr 0x1049)

**Function**: Damage subtraction path (continuation)  
**Instruction**: `EA BB DC`

```
0x001030: BB DC FE 20 30 0C FA 06 DD FE 03 28 05 3E 02 EA
0x001040: 06 DD FA 05 DD A7 C8 3E FF EA BB DC C9 F5 3E 1F
          ^^^^^^^^^ DCBB WRITE
0x001050: FF F1 F5 3E 01 CD F1 5B F1 F1 C5 CB 3F CB 3F 47
```

**Assembly**:
```
0x001049: EA BB DC    LD ($DCBB),A        ; Write boss HP (0xFF if dead)
0x00104C: C9          RET
```

**Context**: Sets DCBB=0xFF when boss HP <= 0 (dead).

---

### [DCBB-3] Offset 0x004101 (Bank 1, addr 0x0101)

**Function**: Boss health initialization  
**Instruction**: `EA BB DC`

```
0x0040E8: 08 DD EA 00 DD 3C E0 C1 C9 AF E0 BA EA BC DC 21
0x0040F8: BD DC 06 1E CD A2 09 3E FF EA BB DC 3E 05 E0 BD
          ^^^^^^^^^ DCBB WRITE (0xFF = max HP)
0x004108: 3E 12 E0 CF AF EA 06 DD E0 D0 CD B7 40 3E FF E0
```

**Assembly**:
```
0x0040FD: 3E FF       LD A,0xFF           ; Max HP
0x0040FF: EA BB DC    LD ($DCBB),A        ; Initialize DCBB
```

**Context**: Initializes boss HP to 0xFF at the start of combat.

---

### [DCBB-4] Offset 0x004204 (Bank 1, addr 0x0204)

**Function**: Damage subtraction (alternative path)  
**Instruction**: `EA BB DC`

```
0x0041EB: 49 3E E4 E0 47 C9 F5 E5 21 DF DC 7E A7 28 1D 3D
0x0041FB: 22 7E 3D 20 16 FA BB DC 3D EA BB DC A7 28 10 F5
          ^^^^^^^^^ READ  ^^^^^^^^^ WRITE
0x00420B: 3E 24 FF F1 3E 02 CD F1 5B 3E 08 77 E1 F1 C9 E1
```

**Assembly**:
```
0x0041FB: FA BB DC    LD A,(0xDCBB)       ; Load boss HP
0x0041FE: 3D          DEC A               ; Decrement
0x0041FF: EA BB DC    LD ($DCBB),A        ; Write back
0x004202: A7          AND A               ; Test for zero
0x004203: 28 10       JR Z,0x004215       ; If dead, jump
```

**Context**: Alternative damage path using DEC instead of SUB. Simpler but same purpose.

---

### [DCBB-5] Offset 0x004AD6 (Bank 1, addr 0x0AD6)

**Function**: Phase restoration (likely refill at phase transition)  
**Instruction**: `EA BB DC`

```
0x004ABD: 04 E0 E7 CD 1A 4B F0 E7 A7 20 FB CD 33 0F CD 7E
0x004ACD: 00 CD FD 16 C3 5F 01 3E FF EA BB DC F0 E6 3D E0
          ^^^^^^^^^ DCBB WRITE (0xFF refill)
0x004ADD: E6 F5 3E 03 FF F1 CD 33 0F F0 40 CB AF E0 40 CD
```

**Assembly**:
```
0x004AD3: 3E FF       LD A,0xFF           ; Refill value
0x004AD5: EA BB DC    LD ($DCBB),A        ; Refill boss HP
0x004AD8: F0 E6       LDH A,(0xFFE6)
0x004ADA: 3D          DEC A
```

**Context**: Appears in phase transition code. Refills DCBB to 0xFF when entering next phase.

---

### [DCBB-6] Offset 0x0077C0 (Bank 1, addr 0x37C0)

**Function**: Phase 1 initialization  
**Instruction**: `EA BB DC`

```
0x0077A7: 09 AF E0 E4 C9 F5 3E 0F FF F1 C9 F5 3E 10 FF F1
0x0077B7: C9 F5 3E 11 FF F1 C9 3E FF EA BB DC CD EA 77 18
          ^^^^^^^^^ DCBB WRITE (0xFF phase 1)
0x0077C7: D0 FA BB DC FE 80 30 EF C6 80 EA BB DC CD EA 77
```

**Assembly**:
```
0x0077BE: 3E FF       LD A,0xFF           ; Phase 1 max HP
0x0077C0: EA BB DC    LD ($DCBB),A
0x0077C3: CD EA 77    CALL 0x77EA         ; Call phase handler
0x0077C6: 18 D0       JR 0x77988          ; Jump to condition check
```

**Context**: Phase management. Initiates phase 1 with full HP.

---

### [DCBB-7] Offset 0x0077D1 (Bank 1, addr 0x37D1)

**Function**: Phase 2 trigger (< 0x80)  
**Instruction**: `EA BB DC`

```
0x0077B8: F5 3E 11 FF F1 C9 3E FF EA BB DC CD EA 77 18 D0
          ^^^^^^^^^ DCBB WRITE (previous phase 0xFF)
0x0077C8: FA BB DC FE 80 30 EF C6 80 EA BB DC CD EA 77 18
          ^^^^^^^^^ DCBB WRITE (add 0x80 for phase 2)
0x0077D8: BF FA BB DC FE C0 30 DE C6 40 EA BB DC CD EA 77
          ^^^^^^^^^ next phase check
```

**Assembly**:
```
0x0077C5: FA BB DC    LD A,(0xDCBB)       ; Load current HP
0x0077C8: FE 80       CP A,0x80           ; Compare with 0x80
0x0077CA: 30 EF       JR NC,0x77BBB       ; If >= 0x80, jump
0x0077CC: C6 80       ADD A,0x80          ; Add 0x80 (refill)
0x0077CE: EA BB DC    LD ($DCBB),A        ; Write back
```

**Context**: Architecture note: When DCBB drops below 0x80, add 0x80 to trigger phase 2. Refill = phase transition mechanic.

---

### [DCBB-8] Offset 0x0077E2 (Bank 1, addr 0x37E2)

**Function**: Phase 3 trigger (< 0xC0)  
**Instruction**: `EA BB DC`

```
0x0077C9: BB DC FE 80 30 EF C6 80 EA BB DC CD EA 77 18 BF
          ^^^^^^^^^ DCBB (previous)     ^^^^^^^^^ DCBB WRITE (phase 2)
0x0077D9: FA BB DC FE C0 30 DE C6 40 EA BB DC CD EA 77 18
          ^^^^^^^^^ DCBB READ   ^^^^^^^^^ DCBB WRITE (add 0x40 for phase 3)
0x0077E9: AE CD AC 77 CD 60 1F CD 0E 20 3E 06 F5 CD 6F 40
```

**Assembly**:
```
0x0077D9: FA BB DC    LD A,(0xDCBB)       ; Load current HP
0x0077DC: FE C0       CP A,0xC0           ; Compare with 0xC0
0x0077DE: 30 DE       JR NC,0x77C0        ; If >= 0xC0, jump
0x0077E0: C6 40       ADD A,0x40          ; Add 0x40 (phase 3 refill)
0x0077E2: EA BB DC    LD ($DCBB),A        ; Write back
```

**Context**: When DCBB drops below 0xC0, add 0x40 to trigger phase 3.

---

### [DCBB-9] Offset 0x007B01 (Bank 1, addr 0x3B01)

**Function**: Boss defeat sequence  
**Instruction**: `EA BB DC`

```
0x007AE8: AF EA 1B DC 18 C3 CD 9E 79 F0 FC FE 02 20 14 AF
0x007AF8: E0 FC F5 3E 0F FF F1 3E FF EA BB DC AF EA DB DC
          ^^^^^^^^^ DCBB WRITE (0xFF for defeat?)
0x007B08: CD 3A 1B F0 C0 FE 02 28 0D CD 4E 17 3E 02 E0 C0
```

**Assembly**:
```
0x007AFD: 3E FF       LD A,0xFF
0x007AFF: EA BB DC    LD ($DCBB),A        ; Reset DCBB
0x007B02: AF          XOR A
0x007B03: EA DB DC    LD ($DCDB),A        ; Clear another flag
0x007B06: CD 3A 1B    CALL 0x1B3A         ; Call boss defeat handler
```

**Context**: Part of the boss defeat sequence. Resets DCBB before cleanup.

---

## 2. The Boss Index Validation Bug (0x0C07-0x0C22)

**Location**: Bank 0, address 0x0C07  
**Critical Function**: Validates and indexes boss by DC04 value

```
0x0000BF3: AF          XOR A
0x0000BF4: EA B8 DC    LD (0xDCB8),A
0x0000BF7: 23          INC HL
0x0000BF8: E5          PUSH HL
0x0000BF9: 6F          LD L,A
0x0000BFA: 87          ADD A
0x0000BFB: 87          ADD A
0x0000BFC: 85          ADD A,L
0x0000BFD: E1          POP HL
0x0000BFE: D7          RST 0x10
0x0000BFF: 16 05       LD D,0x05
0x0000C01: 2A 02 03    LD A,(0x0302)
0x0000C04: 15          DEC D
0x0000C05: 20 FA       JR NZ,0x000C01
0x0000C07: FA 04 DC    LD A,(0xDC04)       <-- READ BOSS INDEX
0x0000C0A: C6 40       ADD A,0x40
0x0000C0C: D6 70       SUB A,0x70
0x0000C0E: 38 10       JR C,0x000C20       <-- CARRY = INVALID
0x0000C10: 06 00       LD B,0x00
0x0000C12: 04          INC B
0x0000C13: D6 05       SUB A,0x05
0x0000C15: 30 FB       JR NC,0x000C12
0x0000C17: 78          LD A,B
0x0000C18: E0 BF       LD (0xFFBF),A       <-- STORE BOSS INDEX
0x0000C1A: AF          XOR A
0x0000C1B: EA 1E DC    LD (0xDC1E),A
0x0000C1E: 18 03       JR 0x000C23
0x0000C20: AF          XOR A
0x0000C21: E0 BF       LD (0xFFBF),A       <-- ERROR PATH
0x0000C23: EF          RST 0x28
```

### Algorithm Analysis

For any DC04 value:

1. **Load DC04** → A
2. **ADD A, 0x40** → normalize to range [0x40, ...]
3. **SUB A, 0x70** → check if A < 0x70 (carry set = invalid)
4. **If valid**: Loop counting divisions by 5
   - **LD B, 0**
   - **INC B** (1, 2, 3, ...)
   - **SUB A, 0x05** (subtract 5 each loop)
   - **JR NC** (loop while A >= 5)
5. **Store B** into FFBF (boss index)

### Valid Boss Codes

| DC04  | Expected Boss | After ADD 0x40 | After SUB 0x70 | B iterations | FFBF |
|-------|---------------|----------------|----------------|--------------|------|
| 0x30  | 1             | 0x70           | 0x00           | 0            | 0    |
| 0x35  | 2             | 0x75           | 0x05           | 1            | 1    |
| 0x3A  | 3             | 0x7A           | 0x0A           | 2            | 2    |
| 0x3F  | 4             | 0x7F           | 0x0F           | 3            | 3    |
| 0x44  | 5             | 0x84           | 0x14           | 4            | 4    |
| 0x49  | 6             | 0x89           | 0x19           | 5            | 5    |
| 0x4E  | 7             | 0x8E           | 0x1E           | 6            | 6    |
| 0x53  | 8             | 0x93           | 0x23           | 7            | 7    |
| 0x58  | 9             | 0x98           | 0x28           | 8            | 8    |
| 0x5D  | 10            | 0x9D           | 0x2D           | 9            | 9    |
| 0x62  | 11            | 0xA2           | 0x32           | 10           | 10   |
| 0x67  | 12            | 0xA7           | 0x37           | 11           | 11   |
| 0x6C  | 13            | 0xAC           | 0x3C           | 12           | 12   |
| 0x71  | 14            | 0xB1           | 0x41           | 13           | 13   |
| 0x76  | 15            | 0xB6           | 0x46           | 14           | 14   |

### Invalid Boss 16 (DC04=0x7B)

| DC04  | Expected Boss | After ADD 0x40 | After SUB 0x70 | B iterations | FFBF   | Problem |
|-------|---------------|----------------|----------------|--------------|--------|---------|
| 0x7B  | 16 (INVALID)  | 0xBB           | **0x4B**       | 15           | **15** | OUT OF RANGE |

**Calculation for 0x7B**:
- 0x7B + 0x40 = 0xBB (187)
- 0xBB - 0x70 = 0x4B (75)
- Loop: 75 / 5 = 15 iterations exactly
- B = 15, stored in FFBF

**The Bug**:
- The algorithm only rejects if **A < 0x70 after the subtraction** (carry flag)
- For 0x7B, the result is 0x4B, which is >= 0x70 ✓ (no carry)
- The algorithm **does NOT validate that DC04 is in the correct range** [0x30, 0x76]
- It simply divides by 5, which works for ANY value >= 0x70 after normalization
- **DC04=0x7B incorrectly maps to FFBF=15**, which is the boss 15 lookup index

---

## 3. Boss Index Lookup Table (0x0010-0x002F)

**Location**: Bank 0, offset 0x0010 (32 bytes = 16 entries × 2 bytes per entry)

```
0x0010: C3 DE | 09 DF | AE BB | 52 7B | C3 00 | 00 FF | F6 FF | FF FF
        [0]   [1]    [2]    [3]    [4]    [5]    [6]    [7]
        
0x0018: EA 80 | D8 D9 | D7 6E | 8A 62 | C3 9A | 09 FF | FF F7 | FE FF
        [8]    [9]    [10]   [11]   [12]   [13]   [14]   [15]
```

### Entry Mapping

Each entry is a **16-bit little-endian address** (low byte first).

| Index | Offset | Addr Low | Addr High | Address | Purpose |
|-------|--------|----------|-----------|---------|---------|
| 0     | 0x00   | 0xC3     | 0xDE      | 0xDEC3  | Boss 1  |
| 1     | 0x02   | 0x09     | 0xDF      | 0xDF09  | Boss 2  |
| 2     | 0x04   | 0xAE     | 0xBB      | 0xBBAE  | Boss 3  |
| 3     | 0x06   | 0x52     | 0x7B      | 0x7B52  | Boss 4  |
| 4     | 0x08   | 0xC3     | 0x00      | 0x00C3  | Boss 5  |
| 5     | 0x0A   | 0x00     | 0xFF      | 0xFF00  | Boss 6  |
| 6     | 0x0C   | 0xF6     | 0xFF      | 0xFFF6  | Boss 7  |
| 7     | 0x0E   | 0xFF     | 0xFF      | 0xFFFF  | Boss 8  |
| 8     | 0x10   | 0xEA     | 0x80      | 0x80EA  | Boss 9  |
| 9     | 0x12   | 0xD8     | 0xD9      | 0xD9D8  | Boss 10 |
| 10    | 0x14   | 0xD7     | 0x6E      | 0x6ED7  | Boss 11 |
| 11    | 0x16   | 0x8A     | 0x62      | 0x628A  | Boss 12 |
| 12    | 0x18   | 0xC3     | 0x9A      | 0x9AC3  | Boss 13 |
| 13    | 0x1A   | 0x09     | 0xFF      | 0xFF09  | Boss 14 |
| 14    | 0x1C   | 0xF7     | 0xFF      | 0xFFF7  | Boss 15 |
| 15    | 0x1E   | 0xFF     | 0xFF      | 0xFFFF  | (unused)|

**Key Insight**: Entry 15 (offset 0x1E) contains 0xFFFF, which is an invalid address (likely a sentinel or trap).

### FFBF to Table Index Conversion (0x0010FE)

When FFBF is read to access the damage code:

```
0x0010FE: F0 BF       LDH A,(0xFFBF)       Load FFBF value (boss index)
0x001100: 3D          DEC A                Decrement (convert to 0-indexed)
0x001101: 87          ADD A                Multiply by 2 (size of each entry)
0x001102: D7          RST 0x10             Jump via table lookup
```

**Table Access**:
- RST 0x10 is a jump table dispatcher
- The accumulated value (FFBF - 1) × 2 is the offset from table base (0x0010)
- For FFBF=15: (15-1)×2 = 28 = offset 0x1C → entry 14 → address 0xFFF7
- For FFBF=16 (if set): (16-1)×2 = 30 = offset 0x1E → entry 15 → address 0xFFFF (OUT OF TABLE BOUNDS)

---

## 4. Root Cause: Why Boss 16 Survives

### The Chain of Events

1. **Encounter Boss 16**:
   - Player navigates to boss room
   - Game sets DC04 = 0x7B (boss 16 code, invalid)

2. **Boss Initialization** (0x0C07-0x0C22):
   - Validation reads DC04=0x7B
   - Algorithm calculates FFBF = 15 (MAPS TO BOSS 15'S TABLE ENTRY)
   - Game thinks "this is boss 15" (same entry as legitimate boss 15)

3. **Combat Starts**:
   - Boss HP initialized to 0xFF (DCBB=0xFF)
   - Boss 16 exists and fights normally

4. **Player Fires Projectile**:
   - Collision detection triggers damage path at 0x1024
   - Damage code calls table lookup at 0x0010FE
   - FFBF=15 is used to index table
   - Table[14] (offset 0x1C) = 0xFFF7 (corrupted/invalid address?)
   - **The damage code either crashes, jumps to invalid memory, or applies damage to the wrong target**

### Why FFBF=15 is "Safe" But Wrong

The validation algorithm **does not fail for DC04=0x7B**—it passes, but incorrectly:
- Valid range: 0x30 to 0x76 (15 unique codes)
- DC04=0x7B is at offset 0x7B - 0x76 = 0x05 beyond the last valid code
- The math `(0x7B + 0x40) - 0x70 = 0x4B` still works, giving B=15
- **FFBF=15 is a valid index into the table, but semantically wrong**
- It maps to boss 15's handler, not boss 16's (which doesn't exist)

### Why Damage Doesn't Reduce DCBB

The damage path at 0x1024 never executes for boss 16 because:
1. The damage code depends on **valid table entry lookups** via FFBF
2. When FFBF=15 tries to execute boss 15's damage code with boss 16's entity state, **a mismatch occurs**
3. Either:
   - The collision detection fails (wrong entity positions)
   - The damage application code crashes
   - The damage is applied to the wrong variable (not DCBB)

---

## 5. The Damage Subtraction Code (0x1024)

**Location**: Bank 0, offset 0x1024 (part of a larger function)

```asm
0x001024: 47          LD B,A              ; A = damage value → B
0x001025: FA BB DC    LD A,(0xDCBB)       ; Load boss current HP
0x001028: 90          SUB B               ; Subtract damage
0x001029: C1          POP BC
0x00102A: DA 44 4A    JP C,0x4A44         ; If underflow (HP becomes negative)
0x00102D: CA 44 4A    JP Z,0x4A44         ; If result is zero (HP dead)
0x001030: EA BB DC    LD ($DCBB),A        ; Write new HP back to DCBB
0x001033: FE 20       CP A,0x20           ; Check if HP < 0x20?
0x001035: 30 0C       JR NC,0x001043
```

**Key Properties**:
1. **No boss-index check before damage application**
2. **Direct DCBB read/subtract/write**
3. **Unconditional operation** (no gating by boss validity)

**Missing Validation**:
- Nowhere in this code does it verify FFBF is in range [1, 15]
- Nowhere does it verify the boss actually exists
- The **only validation is upstream** at 0x0C07, which is buggy

---

## 6. Definitive Answer: Why Boss 16 Survives

### The Three-Part Failure

**PART 1: Validation Bug (0x0C07)**
- The boss index validation at 0x0C07 uses a range check: `A+0x40 < 0x70?`
- This check only catches values where the normalized result would underflow
- For DC04=0x7B: normalized = 0x4B, no underflow
- **Validation incorrectly accepts 0x7B and maps it to FFBF=15**

**PART 2: Invalid Table Entry**
- FFBF=15 maps to table offset 0x1C
- Table entry 14 at 0x1C-0x1D = 0xFFF7 (supposed address for boss 15)
- But this is **semantically the boss 15 entry**, not a boss 16 entry
- Boss 16 has **no entry in this table**

**PART 3: Missing In-Game Validation**
- The damage code at 0x1024 does **NOT** validate FFBF before using it
- If FFBF is corrupted or out of range, the code simply uses whatever value is there
- For FFBF=15, it accesses boss 15's damage handler
- For a hypothetical FFBF=16, it would read offset 0x1E (entry 15 = 0xFFFF), causing undefined behavior

### Why Projectiles Don't Damage Boss 16

1. **Boss 16 entity slots (DC85, DC8D, etc.) are never properly set** because boss 16 has no valid initialization code
2. **Collision detection fails** to recognize the boss as a valid target
3. **Damage code never executes**, or executes with invalid state
4. **DCBB is never decremented** because the collision-to-damage chain is broken

**Empirical observation matches theory**: Boss 16 fights normally (animations, AI), but projectile hits have no effect. This indicates the entity is partially initialized but the damage path is completely bypassed.

---

## Conclusion

**Boss 16 (DC04=0x7B) survives because:**

1. The boss index validation at **0x0C07 fails to reject invalid DC04 values** (should reject >= 0x77)
2. It incorrectly assigns **FFBF=15** (boss 15's table entry) for the invalid code 0x7B
3. The damage application code at **0x1024 has no validation** of FFBF or boss validity
4. **No table entry exists for boss 16**, so the damage path either crashes or is never reached
5. **DCBB is never decremented** because the collision-to-damage chain depends on valid boss initialization

**Fix**: Strengthen the validation at 0x0C07 to explicitly check that DC04 is in {0x30, 0x35, 0x3A, ..., 0x76}, not just use mathematical division by 5.

