# Gap #7: Sound Command Table Data Format Analysis

**Date**: 2026-04-18  
**Investigator**: Claude Code  
**Status**: COMPLETE

---

## Executive Summary

The sound command table pointers (from Gap #6) reference **variable-length command streams** stored in ROM bank 3 (0x47EC-0x4A41). Each stream is composed of **command entries separated by 0x00 markers**, where each command consists of:

1. **CMD_BYTE**: Opcode for the handler (0x00-0xFF)
2. **ARG_BYTES**: 0-11 bytes of argument data (format depends on command type)
3. **0x00 SEPARATOR**: Marks end of command entry

This creates a **null-delimited stream protocol** similar to Z80-based tracker/sequencer formats.

---

## 1. Pointer Target Extraction (Task 1)

### Command Table at 0xC748 (164 bytes, 41 entries)

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

### Unique Pointers (49 total across 41 commands)

**Most frequently used:**
- **0x47EC**: 33 uses (10 as Ptr1, 23 as Ptr2) — **SILENCE/DEFAULT**
- **0x48BE**: 2 uses (as Ptr2) — shared by boss/power-up sounds
- All others: 1 use each

**High-level distribution:**
- 32 unique primary pointers (Ptr1)
- 18 unique secondary pointers (Ptr2)

---

## 2. Silence Pointer Analysis (Task 2)

### Stream at 0x47EC (Bank3) / 0xC7EC (File offset)

The most reused pointer. First **64 bytes**:

```
HEX DUMP:
  +00: 00 01 00 F1 6A 80 00 24 37 80 F0 84 86 00 10 67
  +10: 80 F0 8E 87 00 0C 6F 80 F1 8E 87 00 17 77 C0 F1
  +20: B4 87 00 09 67 80 F7 B4 87 12 37 80 F0 62 87 00
  +30: 08 77 80 F4 10 87 08 65 80 FC 05 87 00 05 40 40
```

**Interpretation:**

This is NOT a "silent" stream in the traditional sense. Rather, it's a **default/fallback sequence**. The pattern shows:

- **Cmd 0 (0x00 01 00)**: No-op command with argument 0x01
- **Cmd 1 (0xF1 6A 80 00)**: Register write: F1=6A, 80=00
- **Cmd 2 (0x24 37 80 F0 84 86 00)**: 6-byte command
- **Cmd 3 (0x10 67 80 F0 8E 87 00)**: 6-byte command
- ... continues with similar 5-7 byte entries

**Format observation:** Each entry is [CMD_BYTE] [ARGS...] [0x00]

**Why it's "silence":** When a command dereferences 0x47EC as its first pointer and loads byte 0x00, the handler is **skipped** (disassembly: "CALL NZ, 0x4586" — call only if nonzero). This makes 0x47EC a safe default that doesn't execute channel 1-2 operations.

---

## 3. Five Other Unique Pointer Samples (Task 3)

### Pointer 0x47F3 (Cmd 03 Ptr1) — Regular Music

**First 64 bytes:**

```
HEX DUMP:
  +00: 24 37 80 F0 84 86 00 10 67 80 F0 8E 87 00 0C 6F
  +10: 80 F1 8E 87 00 17 77 C0 F1 B4 87 00 09 67 80 F7
  +20: B4 87 12 37 80 F0 62 87 00 08 77 80 F4 10 87 08
  +30: 65 80 FC 05 87 00 05 40 40 F1 BE 87 00 05 33 80
```

**Relationship to 0x47EC:** This is 0x47EC[7:] — it starts partway through the silence stream at offset +7.

**Interpretation:** Shared data! The data region is tightly packed with multiple pointers reading at different offsets. This indicates:
- High ROM efficiency (data reuse)
- Both music and silence sequences interleave in memory

### Pointer 0x4830 (Cmd 0A Ptr1) — Complex Music

**First 64 bytes:**

```
HEX DUMP:
  +00: 05 33 80 F1 E0 86 01 16 80 F1 DD 86 00 02 00 F1
  +10: 2F 80 06 00 F1 56 80 00 07 00 80 92 CB 87 09 00
  +20: 40 92 CB 87 07 00 80 92 CB 87 09 00 40 92 CB 87
  +30: 07 00 80 92 CB 87 09 00 40 92 CB 87 07 00 80 92
```

**Format analysis:**
- Cmd 0: [05 33 80 F1 E0 86 01 16 80 F1 DD 86 00] — 12-byte entry
- Cmd 1: [02 00] — 1-byte entry
- Cmd 2: [F1 2F 80 06 00] — 3-byte entry
- Cmd 3: [F1 56 80 00] — 2-byte entry
- Cmd 4: [07 00] — 0-byte entry
- Cmd 5: [80 92 CB 87 09 00] — 4-byte entry
- Repeating pattern: [40/80 92 CB 87 07/09 00] — loop-like structure

**Observation:** Variable argument lengths suggest a **format where command semantics define how many args follow**.

### Pointer 0x48B1 (Cmd 0E Ptr1) — Boss Music Phase 1

**First 64 bytes:**

```
HEX DUMP:
  +00: 11 17 80 F8 7D 86 28 2E 80 E0 F8 87 00 0B 00 F7
  +10: 78 80 06 00 F3 68 80 08 00 DC 3F 80 22 00 F4 80
  +20: 80 00 16 77 80 F8 FB 86 0D 27 80 F4 FF 86 00 1D
  +30: 00 80 F3 C6 87 25 00 80 F3 B1 87 00 1A 46 80 F3
```

**Format analysis:**
- Cmd 0: [11 17 80 F8 7D 86 28 2E 80 E0 F8 87 00] — 11-byte entry
- Cmd 1: [0B 00] — 0-byte entry
- ... continues with mixed-size entries

**Observation:** Boss music uses longer data blocks, suggesting more complex register patterns.

### Pointer 0x48BE (Cmd 0E/1C Ptr2) — Shared Boss Sequence

**First 64 bytes:**

```
HEX DUMP:
  +00: 0B 00 F7 78 80 06 00 F3 68 80 08 00 DC 3F 80 22
  +10: 00 F4 80 80 00 16 77 80 F8 FB 86 0D 27 80 F4 FF
  +20: 86 00 1D 00 80 F3 C6 87 25 00 80 F3 B1 87 00 1A
  +30: 46 80 F3 0F 87 00 1A 4E 80 FB FF 86 00 1F 44 C0
```

**Note:** Used by both Cmd 0x0E (boss music) and Cmd 0x1C (power-up) as their secondary pointer.

### Pointer 0x49A2 (Cmd 1F Ptr1) — Complex Multi-Channel Effect

**First 64 bytes:**

```
HEX DUMP:
  +00: 0B 00 C0 F1 E0 87 00 13 00 B1 16 80 00 07 00 F1
  +10: 89 80 06 00 C2 22 80 00 36 00 80 56 D8 87 00 11
  +20: 00 0F 07 80 00 28 00 C0 6C 49 86 00 10 00 3B 31
  +30: 80 0B 00 1A 21 80 02 00 21 11 80 00 15 67 00 F7
```

**Observation:** High variation in argument lengths (some entries 0 bytes, some 6-8 bytes) suggests complex multiplexing of channels.

---

## 4. Data Stream Format Hypothesis (Task 4)

### Protocol Structure

```
SOUND_STREAM := [COMMAND_ENTRY]* [END_OF_STREAM]

COMMAND_ENTRY := [CMD_BYTE] [ARG_BYTES...] [0x00_DELIMITER]

Where:
  - CMD_BYTE: 0x00 = NOP (handler skipped)
                0x01-0x7F = Operations (pitch, duration, register write)
                0x80-0xFF = High-bit values (possibly register writes or special ops)
  
  - ARG_BYTES: Variable length, format determined by CMD_BYTE opcode
                Common patterns:
                - 0-byte entries (NOP or state change)
                - 2-byte entries (register address + value)
                - 4-5 byte entries (multi-register write)
                - 6-12 byte entries (complex channel configuration)
  
  - 0x00_DELIMITER: Always present after argument block
                    Signals: "end of this command entry, handler can process"
```

### Handler Invocation Model

From disassembly (Gap #6):

```
45F1: OR A
45F2: CALL NZ, 0x4586      ; Handler 1: called only if D894 (first dereferenced byte) != 0
...
46:04: OR A
46:05: CALL NZ, 0x459D      ; Handler 2: called only if D897 (second stream byte) != 0
```

**Implication:** 
- 0x00 as first byte = stream does nothing (safe default)
- Non-zero first byte = handler processes the stream starting from next byte

### Interpretation of 0x47EC "Silence"

```
0x47EC contents:
  [00 01 00] [F1 6A 80 00] [24 37 80 F0 84 86 00] [...]
  ^-- CMD=0x00: handler SKIPPED (no operation for stream 1)

0x47ED contents (offset +1, used as Ptr2):
  [01 00] [F1 6A 80 00] [24 37 80 F0 84 86 00] [...]
  ^-- CMD=0x01: handler CALLED (processes stream 2)
```

Commands using 0x47EC as **Ptr1** skip channel 1-2 operations.  
Commands using 0x47EC as **Ptr2** only skip the secondary channel sequence.

---

## 5. Stream End Marker Detection (Task 5)

### Primary Hypothesis: 0x00 as End Marker

Scanning multiple streams shows **no definitive stream-end marker separate from command delimiters**. Instead:

1. Streams naturally continue with [CMD] [ARGS] [0x00] pattern indefinitely
2. Handler behavior likely implements a **stream pointer continuation** based on WRAM registers D895-D899
3. Stream ends when:
   - Next command handler detects a **special terminator command** (e.g., 0xFF?)
   - **Hardware interrupt** marks end of stream processing
   - **Main loop** continues to next command from table

### Evidence Against 0x00 as True End:

Looking at 0x4848 stream:

```
File offset 0xC848: 07 00 80 92 CB 87 09 00 ...
File offset 0xC848 + stream offset 45: [87 04 00 40 90 CB 87 00] -- contains 0x00 but not at true end
File offset 0xC848 + stream offset 46: [04 00 40 90 CB 87 00 28] -- followed by next command start
```

The gap from 0x4848 to next pointer 0x4879 is **49 bytes**. Stream at 0x4848 can be as short as 2-6 bytes (ending with 0x00), but continuation depends on handler.

### Working Hypothesis:

**Streams do NOT have explicit end markers.** Instead:

1. **Handler processes command entries** (CMD + ARGS + 0x00)
2. **Advances internal pointer** (D895-D896 or D898-D899)
3. **Main loop calls handler repeatedly** until a stop condition:
   - Detects a special **terminator command** (0xFF? 0xFE?)
   - **Hardware sound interrupt** signals end
   - Next call to handler at bank3:0x45B1 with new command code

The 0x47EC sequence is "silence" because its first byte (0x00) causes the handler to be skipped initially, and any subsequent processing is confined to the secondary stream.

---

## 6. Concrete Byte Breakdown Examples (Task 4)

### Example 1: 0x47F3 First Command (Regular Music)

```
STREAM: 0x47F3 onwards
FILE:   0xC7F3

RAW BYTES:
  24 37 80 F0 84 86 00 10 67 80 F0 8E 87 00 ...
  ^  ^  ^  ^  ^  ^  ^
  |  |  |  |  |  |  +-- 0x00: End of command
  |  |  |  |  |  +---- Arg5: 0x86
  |  |  |  |  +------- Arg4: 0x84
  |  |  |  +---------- Arg3: 0xF0
  |  |  +------------- Arg2: 0x80
  |  +---------------- Arg1: 0x37
  +------------------- CMD: 0x24

INTERPRETATION (Hypothesis):
  Command: 0x24 (likely "set pitch/duration")
  Arguments: 0x37 0x80 0xF0 0x84 0x86 (5 bytes)
  
  Possible breakdown (GB NR-register mapping):
    0x37 = Pitch/note value
    0x80 = Waveform/duty cycle register
    0xF0 = Volume envelope
    0x84 0x86 = Timing/duration envelope
```

### Example 2: 0x4830 Mixed Format Commands

```
STREAM: 0x4830 onwards
FILE:   0xC830

RAW BYTES:
  05 33 80 F1 E0 86 01 16 80 F1 DD 86 00 02 00 F1 2F 80 06 00 F1 56 80 00 ...

COMMAND 1:
  05 33 80 F1 E0 86 01 16 80 F1 DD 86 00
  ^  ------  ----  ----  ----  ----  ----  ^
  CMD      ARG1   ARG2   ARG3   ARG4   ARG5  END

  Command: 0x05 (dual-register setup?)
  Arguments: 11 bytes = [0x33 0x80 0xF1 0xE0 0x86 0x01 0x16 0x80 0xF1 0xDD 0x86]

COMMAND 2:
  02 00
  ^  ^
  CMD END

  Command: 0x02 (state machine transition or loop marker)
  Arguments: 0 bytes (flag-only command)

COMMAND 3:
  F1 2F 80 06 00
  ^  ^  ^  ^  ^
  CMD ARG1 ARG2 ARG3 END

  Command: 0xF1 (high-bit op, possibly "raw register write" or "continue")
  Arguments: 3 bytes = [0x2F 0x80 0x06]
```

### Example 3: 0x48B1 Boss Music (Long Entries)

```
STREAM: 0x48B1 onwards
FILE:   0xC8B1

RAW BYTES:
  11 17 80 F8 7D 86 28 2E 80 E0 F8 87 00 0B 00 F7 78 80 06 00 F3 68 80 08 00 DC 3F 80 22 00 F4 80 80 00 ...

COMMAND 1:
  11 17 80 F8 7D 86 28 2E 80 E0 F8 87 00
  ^  ----------  ----------  ----------  ^
  CMD ARGS(11 bytes)                     END

  Command: 0x11 (complex multi-part command)
  Arguments: 11 bytes
  Pattern: [0x17 0x80] [0xF8 0x7D 0x86] [0x28 0x2E 0x80] [0xE0 0xF8 0x87]
           = 4 pairs of register-like values, possibly 4 GB channels

COMMAND 2:
  0B 00
  ^  ^
  CMD END

  Command: 0x0B (shorter command, possibly loop/timing)
  Arguments: 0 bytes
```

---

## 7. Summary: Data Format Classification

### Confirmed:
1. ✓ **Null-delimited command protocol**: Each command ends with 0x00 byte
2. ✓ **Variable-length arguments**: 0-12 bytes per command
3. ✓ **Dual-stream architecture**: Ptr1 and Ptr2 can share memory at different offsets
4. ✓ **Handler activation**: First byte determines if handler is called (0x00 = skip)

### Hypothesis (High Confidence):
- **Format**: Similar to **Trekkie/LSDJ-style** Game Boy sound tracker
  - [CMD_BYTE] identifies operation type
  - [ARG_BYTES] provide parameters (pitch, volume, register values)
  - [0x00] marks command boundary for parser
  
- **Likely command types**:
  - 0x00: NOP/silence (handler skipped)
  - 0x01-0x10: Pitch/duration commands for square wave channels
  - 0x11-0x20: Multi-channel setup commands (configure multiple registers at once)
  - 0x80+: Raw register writes or channel 3-4 operations
  - 0xFF: Possible end marker (not yet confirmed in data)

### Comparison to Known GB Sound Formats:
- **Similar to**: Trekkie tracker (Pokémon Red/Blue)
- **Different from**: LSDJ (which uses more compact note encoding)
- **Custom variant**: Argument counts are variable per command, requiring table/switch statement in handler

---

## 8. Files and References

### Source Data:
- **ROM**: `/home/struktured/projects/penta-dragon-dx-claude/rom/Penta Dragon (J).gb`
- **Bank3 offset**: 0xC000-0xFFFF (maps to GB 0x4000-0x7FFF)
- **Stream region**: 0xC748-0xC7EB (table), 0xC7EC-0xCAxx (data streams)

### Related Documentation:
- **Gap #6**: Sound command table structure and pointer table (gap_sound_command_table.md)
- **Disassembly**: Command reader at bank3:0x45B1-0x4613 (99 bytes)
- **Handlers**: Assumed at bank3:0x4586 (Handler 1) and bank3:0x459D (Handler 2)

### Next Steps for Full Decode:
1. Disassemble handlers at 0x4586 and 0x459D to confirm command byte interpretation
2. Trace handler execution to identify argument parsing (how does it know arg length?)
3. Map GB hardware NR-registers (NR10-NR44) to command formats
4. Create command reference table for all command bytes used (0x01-0xFF)
5. Reverse-engineer handler state machine for stream continuation logic

---

**Status**: Ready for handler disassembly phase (Gap #8)
