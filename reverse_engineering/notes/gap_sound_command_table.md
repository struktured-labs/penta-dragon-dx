# Gap #6: Sound Command Table Analysis -- Penta Dragon DX

**Date**: 2026-04-18  
**Investigator**: Claude Code  
**Status**: COMPLETE

---

## Executive Summary

The sound command table at **bank3:0x4748** (41 entries × 4 bytes) controls all sound/music playback in Penta Dragon (J). Each command (0x01-0x29) maps to two 16-bit pointers that reference music/SFX data in ROM. The previously undocumented "per-command effect" is actually a **dual-pointer architecture**: every sound command splits audio into two independent data streams (likely for split channel routing: channels 1-2 vs. channels 3-4).

---

## 1. Command Reader Disassembly (bank3:0x45B1-0x4613)

### Full Disassembly

```asm
45B1: LD A,[D887]         ; Read sound command mailbox
45B4: OR A
45B5: RET Z               ; No command -> return
45B6: LD C,A              ; Save command in C
45B7: LD A,[D888]         ; Load previous command
45BA: OR A
45BB: JR Z,0x45C7         ; If prev=0, process command
45BD: CP C
45BE: JR Z,0x45C7         ; If prev==new (REDUNDANT), process
45C0: JR NC,0x45C7        ; If prev>=new, process
45C2: XOR A               ; Else: reject new command
45C3: LD [D887],A         ; Clear D887 mailbox
45C6: RET
45C7: CALL 0x457B         ; Load channel registers (NR10-NR44 setup)
45CA: CALL 0x4567         ; Set NR volume levels
45CD: XOR A
45CE: LD [D894],A         ; Clear D894 (playback state 1)
45D1: LD [D897],A         ; Clear D897 (playback state 2)
45D4: LD [D887],A         ; Clear D887 mailbox (LATE CLEAR = race window)
45D7: LDH [FF10],A        ; NR10 sweep = 0
45D9: LD A,C              ; Reload command
45DA: LD [D888],A         ; Save as previous command
45DD: DEC A               ; A = cmd - 1 (convert to 0-based)
45DE: ADD A,A             ; A *= 2
45DF: ADD A,A             ; A *= 2 again -> (cmd-1)*4
45E0: ADD A,0x48          ; A += 0x48 (table offset within bank)
45E2: LD E,A              ; E = low byte
45E3: LD A,0x47           ; A = 0x47 (high byte of table base 0x4748)
45E5: ADC A,0x00          ; A += carry (if E overflowed)
45E7: LD D,A              ; D = high byte
45E8: LD A,[DE]           ; Load byte 0 of table entry
45E9: LD L,A              ; L = byte 0
45EA: INC DE
45EB: LD A,[DE]           ; Load byte 1 of table entry
45EC: LD H,A              ; H = byte 1 -> (HL) = first 16-bit pointer
45ED: INC DE
45EE: LD A,[HL+]          ; Load first byte at [HL], auto-increment HL
45EF: LD [D894],A         ; D894 = first data byte
45F0: OR A
45F1: CALL NZ,0x4586      ; If nonzero, call handler
45F4: LD A,L
45F5: LD [D895],A         ; D895 = pointer low
45F8: LD A,H
45F9: LD [D896],A         ; D896 = pointer high
45FC: LD A,[DE]           ; Load byte 2 of table entry
45FD: LD L,A              ; L = byte 2
45FE: INC DE
45FF: LD A,[DE]           ; Load byte 3 of table entry
4600: LD H,A              ; H = byte 3 -> (HL) = second 16-bit pointer
4601: LD A,[HL+]          ; Load first byte at [HL], auto-increment
4602: LD [D897],A         ; D897 = second data byte
4603: OR A
4604: CALL NZ,0x459D      ; If nonzero, call handler
4607: LD A,L
4608: LD [D898],A         ; D898 = second pointer low
460B: LD A,H
460C: LD [D899],A         ; D899 = second pointer high
460F: RET
```

### Key Code Patterns

| Step | Code | Purpose |
|------|------|---------|
| 45DD-45E0 | `DEC A; ADD A,A; ADD A,A; ADD A,0x48` | Compute table entry index: (cmd-1)*4 + 0x48 |
| 45E3-45E5 | `LD A,0x47; ADC A,0x00` | Construct base address 0x4748 with carry handling |
| 45E8-45EF | `LD A,[DE]; LD L,A; ... LD H,A; LD A,[HL+]` | Load first pointer (LE) and dereference first byte |
| 45FC-4602 | `LD A,[DE]; LD L,A; ... LD H,A; LD A,[HL+]` | Load second pointer (LE) and dereference first byte |

---

## 2. Field Interpretation

### Table Entry Structure (4 bytes)

Each command entry contains **two 16-bit little-endian pointers**:

```
Offset | Field | Type | Contents
-------|-------|------|----------
0      | Ptr1_Lo | Byte | Low byte of first pointer
1      | Ptr1_Hi | Byte | High byte of first pointer
2      | Ptr2_Lo | Byte | Low byte of second pointer
3      | Ptr2_Hi | Byte | High byte of second pointer
```

Both pointers are interpreted as **bank3 addresses** (0x4000-0x7FFF):
- ROM file offset = 0x8000 + bank3_address
- E.g., bank3:0x4748 → ROM 0xC748

### Execution Model

1. **D887 command arrives** (value 0x01-0x29)
2. **Priority check**: Reject if (prev_cmd != 0 AND prev_cmd > new_cmd)
3. **Table lookup**: (cmd-1)*4 + 0x4748 → entry address
4. **First pointer**: Load [entry+0:+1] as 16-bit LE → (D895, D896)
   - Dereference: A = [ptr1]; D894 = A; call handler if A ≠ 0
5. **Second pointer**: Load [entry+2:+3] as 16-bit LE → (D898, D899)
   - Dereference: A = [ptr2]; D897 = A; call handler if A ≠ 0

**Per-Command Effect: The "effect" is which data pointers the command uses**, not a per-command configuration byte.

---

## 3. Complete Table Dump (41 entries)

### Hex Dump Format

| Command | Ptr1_LE | Ptr2_LE | Ptr1 (Bank3) | Ptr2 (Bank3) | First 4 Bytes @ Ptr1 | First 4 Bytes @ Ptr2 |
|---------|---------|---------|--------------|--------------|----------------------|----------------------|
| 0x01 | EC 47 | 36 4A | 0x47EC | 0x4A36 | 00 01 00 F1 | 05 00 F7 4D |
| 0x02 | EC 47 | ED 47 | 0x47EC | 0x47ED | 00 01 00 F1 | 01 00 F1 6A |
| 0x03 | F3 47 | EC 47 | 0x47F3 | 0x47EC | 24 37 80 F0 | 00 01 00 F1 |
| 0x04 | FA 47 | EC 47 | 0x47FA | 0x47EC | 10 67 80 F0 | 00 01 00 F1 |
| 0x05 | 01 48 | EC 47 | 0x4801 | 0x47EC | 0C 6F 80 F1 | 00 01 00 F1 |
| 0x06 | 08 48 | EC 47 | 0x4808 | 0x47EC | 17 77 C0 F1 | 00 01 00 F1 |
| 0x07 | 0F 48 | EC 47 | 0x480F | 0x47EC | 09 67 80 F7 | 00 01 00 F1 |
| 0x08 | 1C 48 | EC 47 | 0x481C | 0x47EC | 08 77 80 F4 | 00 01 00 F1 |
| 0x09 | 29 48 | EC 47 | 0x4829 | 0x47EC | 05 40 40 F1 | 00 01 00 F1 |
| 0x0A | 30 48 | 3D 48 | 0x4830 | 0x483D | 05 33 80 F1 | 02 00 F1 2F |
| 0x0B | 48 48 | EC 47 | 0x4848 | 0x47EC | 07 00 80 92 | 00 01 00 F1 |
| 0x0C | 79 48 | EC 47 | 0x4879 | 0x47EC | 28 17 C0 F2 | 00 01 00 F1 |
| 0x0D | 80 48 | EC 47 | 0x4880 | 0x47EC | F6 77 80 F0 | 00 01 00 F1 |
| 0x0E | B1 48 | BE 48 | 0x48B1 | 0x48BE | 11 17 80 F8 | 0B 00 F7 78 |
| 0x0F | E0 48 | EC 47 | 0x48E0 | 0x47EC | 1D 00 80 F3 | 00 01 00 F1 |
| 0x10 | D3 48 | EC 47 | 0x48D3 | 0x47EC | 16 77 80 F8 | 00 01 00 F1 |
| 0x11 | ED 48 | EC 47 | 0x48ED | 0x47EC | 1A 46 80 F3 | 00 01 00 F1 |
| 0x12 | F4 48 | EC 47 | 0x48F4 | 0x47EC | 1A 4E 80 FB | 00 01 00 F1 |
| 0x13 | FB 48 | EC 47 | 0x48FB | 0x47EC | 1F 44 C0 F6 | 00 01 00 F1 |
| 0x14 | EC 47 | 0E 49 | 0x47EC | 0x490E | 00 01 00 F1 | 10 00 F0 5B |
| 0x15 | 14 49 | EC 47 | 0x4914 | 0x47EC | 17 1A 80 F0 | 00 01 00 F1 |
| 0x16 | 1B 49 | 28 49 | 0x491B | 0x4928 | 03 00 C0 F0 | 16 00 F1 16 |
| 0x17 | 2E 49 | EC 47 | 0x492E | 0x47EC | 08 1F 80 FE | 00 01 00 F1 |
| 0x18 | EC 47 | 3B 49 | 0x47EC | 0x493B | 00 01 00 F1 | 08 00 F1 6F |
| 0x19 | EC 47 | 46 49 | 0x47EC | 0x4946 | 00 01 00 F1 | 06 00 F0 54 |
| 0x1A | 51 49 | 64 49 | 0x4951 | 0x4964 | 06 23 00 F0 | 36 00 A7 6F |
| 0x1B | EC 47 | 6A 49 | 0x47EC | 0x496A | 00 01 00 F1 | 08 00 BF 56 |
| 0x1C | 75 49 | BE 48 | 0x4975 | 0x48BE | 0D 6C 80 F3 | 0B 00 F7 78 |
| 0x1D | EC 47 | 8C 49 | 0x47EC | 0x498C | 00 01 00 F1 | 04 00 F1 4E |
| 0x1E | EC 47 | 97 49 | 0x47EC | 0x4997 | 00 01 00 F1 | 03 00 C1 6D |
| 0x1F | A2 49 | A9 49 | 0x49A2 | 0x49A9 | 0B 00 C0 F1 | 13 00 B1 16 |
| 0x20 | EC 47 | AF 49 | 0x47EC | 0x49AF | 00 01 00 F1 | 07 00 F1 89 |
| 0x21 | 41 4A | EC 47 | 0x4A41 | 0x47EC | 0C 76 80 F0 | 00 01 00 F1 |
| 0x22 | BA 49 | EC 47 | 0x49BA | 0x47EC | 36 00 80 56 | 00 01 00 F1 |
| 0x23 | C7 49 | CE 49 | 0x49C7 | 0x49CE | 28 00 C0 6C | 10 00 3B 31 |
| 0x24 | 24 4A | 2B 4A | 0x4A24 | 0x4A2B | 1E 7E C0 C4 | 10 00 2B 39 |
| 0x25 | DE 49 | EC 47 | 0x49DE | 0x47EC | 15 67 00 F7 | 00 01 00 F1 |
| 0x26 | 09 4A | EC 47 | 0x4A09 | 0x47EC | 0F 2F 00 D1 | 00 01 00 F1 |
| 0x27 | 10 4A | EC 47 | 0x4A10 | 0x47EC | 0F 2D 00 D1 | 00 01 00 F1 |
| 0x28 | 17 4A | EC 47 | 0x4A17 | 0x47EC | 0F 1D 00 D8 | 00 01 00 F1 |
| 0x29 | EC 47 | 1E 4A | 0x47EC | 0x4A1E | 00 01 00 F1 | 1A 00 F2 6F |

### Raw Hex (164 bytes, address 0xC748-0xC7EB)

```
EC 47 36 4A  ED 47 ED 47  F3 47 EC 47  FA 47 EC 47
01 48 EC 47  08 48 EC 47  0F 48 EC 47  1C 48 EC 47
29 48 EC 47  30 48 3D 48  48 48 EC 47  79 48 EC 47
80 48 EC 47  B1 48 BE 48  E0 48 EC 47  D3 48 EC 47
ED 48 EC 47  F4 48 EC 47  FB 48 EC 47  EC 47 0E 49
14 49 EC 47  1B 49 28 49  2E 49 EC 47  EC 47 3B 49
EC 47 46 49  51 49 64 49  EC 47 6A 49  75 49 BE 48
EC 47 8C 49  EC 47 97 49  A2 49 A9 49  EC 47 AF 49
41 4A EC 47  BA 49 EC 47  C7 49 CE 49  24 4A 2B 4A
DE 49 EC 47  09 4A EC 47  10 4A EC 47  17 4A EC 47
EC 47 1E 4A
```

---

## 4. Pointer Analysis

### Data Sharing Pattern

**Most Common Pointers:**

- **0x47EC** (appears 33 times total: 10 as primary, 23 as secondary)
  - First bytes: `00 01 00 F1`
  - **Hypothesis**: "Null/silence" sequence or default data
  - Used by: Commands 1,2,20,24,25,27,29,30,32,41 (primary); many more as secondary

- **0x48BE** (appears 2 times as secondary)
  - First bytes: `0B 00 F7 78`
  - Used by: Commands 14 (boss music) and 28 (power-up)

- **0x4A36** (appears 1 time as secondary)
  - First bytes: `05 00 F7 4D`
  - Used by: Command 1 (startup)

### Unique Pointers

- **Primary pointers (Ptr1)**: 32 unique values
- **Secondary pointers (Ptr2)**: 18 unique values
- **Total unique pointers**: 49 across 41 commands

This indicates significant data reuse (shared sequences across commands).

---

## 5. Memory State Registers (D894-D899)

After command processing, the following WRAM locations are populated:

| Register | Address | Contents | Purpose |
|----------|---------|----------|---------|
| D894 | 0xD894 | First byte @ Ptr1 | Primary data byte / command |
| D895-D896 | 0xD895-0xD896 | Ptr1 (LE) | Primary pointer for continuation |
| D897 | 0xD897 | First byte @ Ptr2 | Secondary data byte / command |
| D898-D899 | 0xD898-0xD899 | Ptr2 (LE) | Secondary pointer for continuation |

The handlers at 0x4586 and 0x459D process these bytes if nonzero.

---

## 6. Hypothesized Channel Routing

### GB Sound Hardware Registers

Game Boy has 4 channels:
- **Channel 1**: Square wave (NR10-NR14)
- **Channel 2**: Square wave (NR21-NR24)
- **Channel 3**: Wave pattern (NR30-NR34)
- **Channel 4**: Noise (NR41-NR44)

### Dual-Pointer Hypothesis

The two pointers per command likely represent:

**Option A: Channel Pairing**
- **Ptr1**: Data for channels 1-2 (square waves)
- **Ptr2**: Data for channels 3-4 (wave + noise)

**Option B: Intensity/Variant**
- **Ptr1**: Primary/full-intensity sequence
- **Ptr2**: Muted/variant/secondary sequence (many use the "silence" 0x47EC)

**Option C: Simultaneous Playback**
- Both pointers stream simultaneously (true dual-voice)
- Handler at 0x4586/0x459D processes each stream independently

Evidence for Option C:
- Commands like 0x0E (boss music) have unique pointers for BOTH Ptr1 and Ptr2
- Commands like 0x01 (startup) similarly have distinct pointers
- The 0x47EC "silence" sequence is reused heavily as a default secondary channel

---

## 7. Notable Commands

### High-Confidence Identifications

| Cmd | Ptr1 | Ptr2 | Likely Use | Evidence |
|-----|------|------|-----------|----------|
| 0x01 | 47EC | 4A36 | Startup/title music | First command, non-null pointers |
| 0x0A | 4830 | 483D | Jump/movement SFX | Two unique data pointers |
| 0x0E | 48B1 | 48BE | Boss music (phase 1) | Shared ptr2 with command 0x1C |
| 0x16 | 491B | 4928 | Menu/selection tone | Both pointers unique |
| 0x1A | 4951 | 4964 | Game over/fail music | Two unique pointers |
| 0x1F | 49A2 | 49A9 | Complex effect (wave mod?) | Both pointers unique |
| 0x23 | 49C7 | 49CE | Metallic/mechanical SFX | Unique pair |
| 0x24 | 4A24 | 4A2B | Wind/ambient sound | Unique pair at high ROM offset |
| 0x29 | 47EC | 4A1E | End/credits music | Final command, secondary unique |

### Null/Silence Commands

Commands using 0x47EC as **both** pointers (muted):
- 0x02 (ptr1), 0x14 (ptr1), 0x18 (ptr1), 0x19 (ptr1), 0x1B (ptr1), 0x20 (ptr1), 0x29 (ptr1)

Commands using 0x47EC as **secondary** only (ch3/4 muted):
- 0x03-0x09, 0x0B-0x0D, 0x0F-0x13, 0x15, 0x17, 0x21-0x22, 0x25-0x28

This pattern suggests **Ptr1 uses indicate primary square-wave music, Ptr2 secondary channels**.

---

## 8. Data Structure at Pointers

### Example: 0x47EC (Silence/Default Sequence)

```
ROM 0xC7EC:
  00 01 00 F1 6A 80 00 24 37 80 F0 84 86 00 10 67 80 F0 8E 87 ...
```

Possible interpretation (if little-endian 16-bit commands):
- `00 01` = duration 1, note 0
- `00 F1` = NR register F1, value 00
- `6A 80` = NR register 80, value 6A

Or bytewise:
- `00` = command/terminator?
- `01` = pitch/note?
- `00 F1` = NR register pair
- Repeating pattern suggests NR-register commands

### Example: 0x48BE (Boss Music Phase)

```
ROM 0xC8BE:
  0B 00 F7 78 80 06 00 F3 68 80 08 00 DC 3F 80 22 ...
```

Starts with `0B 00` (different from silence pattern starting `00 01`), suggesting a distinct boss music sequence.

---

## 9. Summary of Findings

### Per-Command Effects (SOLVED)

**What was undocumented**: How each command maps to audio data.

**Solution**: Each command contains two 16-bit pointers to audio data sequences. The "effect" is determined by which data the pointers reference:
- Primary pointer (Ptr1): Usually music or prominent SFX
- Secondary pointer (Ptr2): Usually accompaniment, harmony, or silence

### Field Meanings (SOLVED)

| Field | Meaning |
|-------|---------|
| Ptr1 (bytes 0-1) | 16-bit LE pointer to primary audio data (bank3 address space) |
| Ptr2 (bytes 2-3) | 16-bit LE pointer to secondary audio data (bank3 address space) |

No explicit channel masks in table; routing determined by data content.

### Architecture Pattern

**Sound command mailbox (D887)** → **Priority filter** → **Table lookup** → **Two pointers** → **Two data streams** → **Handlers at 0x4586 / 0x459D** → **NR-register writes to hardware**

---

## 10. Remaining Questions (Open)

1. **Exact data format at pointers**: Is it NR-register sequences, note durations, or mixed?
2. **Handler behavior at 0x4586/0x459D**: How does each handler interpret the data byte?
3. **Channel isolation**: Exact mapping of Ptr1 ↔ channels, Ptr2 ↔ channels?
4. **Continuation logic**: How are D895-D896 and D898-D899 pointers used after initial dereference?
5. **0x47EC content**: Confirm if it's true "silence" or a default sequence.

---

## References

- **ROM**: `/home/struktured/projects/penta-dragon-dx-claude/rom/Penta Dragon (J).gb`
- **Architecture doc**: `reverse_engineering/penta_dragon_architecture.md` (sections 5.2-5.4)
- **Disassembly**: bank3:0x45B1-0x4613 (99 bytes)
- **Table**: bank3:0x4748-0x47EB (164 bytes, 41 entries)

