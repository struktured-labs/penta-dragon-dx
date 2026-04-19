# SRAM Checkpoint Slot Validity Flag Mechanism

## Overview
Penta Dragon DX uses a simple but effective slot validity mechanism stored at byte 0 of each SRAM checkpoint slot.

## Slot Layout
- **Location**: SRAM 0xBF00 - 0xC017
- **Slot Count**: 7 slots
- **Slot Size**: 0x28 bytes each
- **Validity Byte**: Offset 0x00 within each slot

## Validity Flag Definition

### Mechanism Type: **MAGIC BYTE**
The validity flag is a simple magic byte check - NOT a counter or checksum.

### Valid Slot Indicator
```
Byte Value: 0x01
Meaning: Slot contains valid checkpoint data
```

### Empty Slot Indicator
```
Byte Value: 0xFF
Meaning: Slot has never been written (SRAM uninitialized state)
```

## Validation Check Location

### Load-Side Validation: ROM 0x8757-0x875A

```z80
0x8757: 7E              LD A,(HL)          ; Load byte 0 of slot
0x8758: FE 01           CP 0x01            ; Compare with 0x01
0x875A: 20 38           JR NZ,+56          ; If not 0x01, skip slot (empty)
```

The code performs a strict equality check: only slots with byte 0 = 0x01 are considered valid.

### Context: Save Loop Structure (ROM 0x86FD-0x8724)

```z80
0x86FD: 3E 07           LD A,0x07          ; Load slot count (7 slots)
0x86FF: D7              [SRAM enable]
0x8700: 06 07           LD B,0x07
0x8702: C5              PUSH BC
0x8703: CD 5F 06        CALL 0x065F        ; Per-slot save operation
0x8706: C1              POP BC
0x8707: 0D              DEC C
0x8708: 20 F8           JR NZ,-8 (0x8702) ; Loop for each slot

;; ... later in sequence ...

0x8714: AF              XOR A              ; Clear A
0x8715: 12              LD (DE),A          ; Write to SRAM address
0x8716: D1              POP DE
```

For **each slot**, the first byte written to SRAM is **0x01** (set at save time).

## SRAM Control Functions

### Enable SRAM (0x09CE-0x09D5)
```z80
0x09CE: F5              PUSH AF
0x09CF: 3E 0A           LD A,0x0A          ; MBC1 SRAM enable value
0x09D1: EA FF 1F        LD (0x1FFF),A      ; Write to MBC1 RAM enable register
0x09D4: F1              POP AF
0x09D5: C9              RET
```

### Disable SRAM (0x09D6-0x09DD)
```z80
0x09D6: F5              PUSH AF
0x09D7: 3E 00           LD A,0x00          ; MBC1 SRAM disable value
0x09D9: EA FF 1F        LD (0x1FFF),A      ; Write to MBC1 RAM enable register
0x09DC: F1              POP AF
0x09DD: C9              RET
```

## Level Select Slot Display (0x7393-0x7401)

The level select menu uses a similar check to determine which slots to display:

```z80
0x73C9: F0 94           LDH A,(0x94)       ; Read joystick input
0x73CB: CB 7F           BIT 7,A            ; Test Up button
0x73CD: 20 17           JR NZ,+23 (0x73E6); If pressed, change slot

[... button checking for Left/Right/Down ...]

0x73DB: CB 47           BIT 0,A            ; Test A button
0x73DD: 20 34           JR NZ,+52 (0x7413); If pressed, load/confirm slot
0x73DF: CB 4F           BIT 1,A            ; Test B button
0x73E1: C2 5A 74        JP NZ,0x745A       ; If pressed, cancel/exit
0x73E4: 18 DD           JR -35 (0x73C3)   ; Otherwise loop back
```

The slot counter is stored at **SRAM 0xBA** and incremented/decremented based on D-pad input.

## Test Case: Empty Cartridge

When a cartridge is first inserted (SRAM uninitialized), all bytes are 0xFF:

### .sav File Offset 0x1F00-0x1F27 (Slot 0)
```
00 01 02 03 04 05 06 07 08 09 0A 0B 0C 0D 0E 0F
FF FF FF FF FF FF FF FF FF FF FF FF FF FF FF FF  <- All 0xFF
FF FF FF FF FF FF FF FF                          <- Rest of slot

[Same pattern repeats for Slots 1-6]
```

When the player saves at slot 0:
```
00 01 02 03 04 05 06 07 08 09 0A 0B 0C 0D 0E 0F
01 XX XX XX XX XX XX XX XX XX XX XX XX XX XX XX  <- Byte 0 = 0x01
XX XX XX XX XX XX XX XX                          <- Rest filled with data

[Remaining slots stay 0xFF if not used]
```

## Conclusion

**The validity mechanism is a simple magic byte (0x01 = valid, 0xFF = empty).**

- **Type**: Magic byte (NOT a counter, NOT a checksum)
- **Valid Value**: 0x01
- **Empty Value**: 0xFF
- **Location**: Byte 0 of each slot (0xBF00, 0xBF28, 0xBF50, etc.)
- **Validation**: Strict equality check (`CP 0x01; JR NZ,skip`)
- **No secondary validation**: No CRC, checksum, or byte-swapping involved

This is a robust design for a Game Boy cartridge since:
1. Simple to implement
2. Fast to check
3. Unlikely to occur accidentally (0x01 is specific marker)
4. Works with SRAM initialization (0xFF default)
