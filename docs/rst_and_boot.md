# Penta Dragon RST Vectors + Boot Init

The 8 RST vectors at 0x0000-0x003F act as the game's "supercalls" — common
operations packed into 1-byte calls. Documents each vector and the boot
init routine at bank 1:0x4000.

## RST vector summary

| RST | Addr  | Target / inline                                     | Purpose                                  |
|-----|-------|-----------------------------------------------------|------------------------------------------|
| 00  | 0x0000| `D0 63 FB EF FE F1 ...` (junk)                      | Unused (would fall into 0x0008)          |
| 08  | 0x0008| `JP 0x0000`                                         | Soft reset (unused in normal play)       |
| 10  | 0x0010| `JP 0x09DE`                                         | **HUD/text print** — caller sets `HL=FFC4` (text buffer) then `RST 10` |
| 18  | 0x0018| `JP 0x0000`                                         | Soft reset (unused)                      |
| 20  | 0x0020| `LD (D880), A; RETI`                                | **Fast scene change** — write A to D880 master-scene and RETI (returns from interrupt). Likely fired from STAT/Timer to change scene atomically. |
| 28  | 0x0028| `JP 0x099A`                                         | **Death-cinematic trigger** — paired with `FFE4=1; RST 28` pattern in death code |
| 30  | 0x0030| `JP 0x42A5` (bank 1)                                | Bank-1 dependent — likely tile/sprite related |
| 38  | 0x0038| `LD (D887), A; RETI` (vanilla) / `RET` (v2.88+ patched) | **Phantom-sound trampoline** — original would write A to D887 sound-cmd then RETI (re-enable IME mid-VBlank → races with Timer ISR). Our v2.88 fix patches 0x003B `RETI → RET` to disable IME re-enable. |

Notes:
- `RST 20` is **2 bytes inline** (`EA 80 D8 D9` = LD (nn),A; RETI). Fits
  exactly in the 8-byte RST slot. Common pattern for state-change-via-IRQ.
- `RST 38` is the famous v2.88 phantom-sound fix. Vanilla `RETI` at 0x003B
  re-enabled IME inside our extended VBlank handler, letting Timer ISR
  fire mid-VBlank and double-consume D887 → phantom sounds.
- `RST 10` is the most-called RST — used everywhere the score / health /
  text needs updating. Always paired with `LD HL, FFC4` (or similar
  HUD buffer pointer) before the call.

## Boot init at bank 1:0x4000

This is where the game starts initializing after the post-Nintendo-logo
copyright check. Disassembly:

```asm
bank1:0x4000:
    XOR A; LDH (FF0F), A         ; IF = 0 (clear pending IRQs)

    LD HL, 0x9800; LD BC, 0x1000 ; VRAM block (4KB tilemap area)
    CALL 0x09A8                  ; bank-0 memset routine

    CALL 0x4422                  ; bank-1 subroutine (TBD)

    LD BC, 0x1F00; LD HL, 0xC000 ; WRAM 0xC000-DEFF (7936 bytes)
    CALL 0x09A8                  ; clear WRAM

    LD BC, 0x007D; LD HL, 0xFF80 ; HRAM (125 bytes — FF80-FFFC)
    CALL 0x09A8                  ; clear HRAM

    LD HL, 0xD700; LD BC, 0x0200 ; D700-D8FF range (512 bytes)
    CALL 0x09A8                  ; clear (this overlaps with WRAM clear above)

    LD A, 1; LD (D889), A        ; D889 = 1
    CALL 0x52B6                  ; bank-1 init phase 2

    LD A, 7; LDH (FFFF), A       ; IE = 0x07 (VBlank | STAT | Timer enabled)

    CALL 0x09CE                  ; bank-0 routine

    LD BC, 0x19FF; LD HL, 0xA000 ; SRAM A000-B9FF (~6656 bytes)
    XOR A; CALL 0x09A8           ; clear SRAM

    CALL 0x09D6                  ; bank-0 routine
    CALL 0x4179                  ; bank-1

    LD A, 3; LDH (FF9A), A       ; FF9A = 3
    CALL 0x0088                  ; bank-0
    ; ... continues to game loop dispatch ...
```

### What the boot tells us about the memory map

| Region            | Range            | Purpose                          |
|-------------------|------------------|----------------------------------|
| VRAM tilemap      | 0x9800-0xA7FF    | 4KB cleared at boot              |
| WRAM (bank 0)     | 0xC000-0xDEFF    | Main game state, ~8KB            |
| HRAM              | 0xFF80-0xFFFC    | 125 bytes — cleared at boot      |
| SRAM (cart RAM)   | 0xA000-0xB9FF    | ~6.5KB cleared at boot           |
| D700-D8FF block   | 0xD700-0xD8FF    | Second clear — possibly sound state init zone |

The clears tell us where the game's state actually lives. The 0xD700-D8FF
re-clear immediately after main WRAM clear suggests this is a known
"state zone" the engine wants in a specific clean state.

### IE = 0x07 at boot

Bit 0 = VBlank, Bit 1 = STAT, Bit 2 = Timer. Bits 3 (Serial) and 4 (Joypad)
are NOT enabled. That matches the disassembly of vectors 0x58 (Serial)
and 0x60 (Joypad), both of which start with `D9` (RETI) — they're empty
handlers.

## RST 28 + FFE4 = death cinematic

Pattern seen throughout combat / death code:

```asm
... game condition ...
LD A, 1; LD (FFE4), A
RST 28              ; → JP 0x099A → death-handling chain
```

`0x099A` is in bank 0 (always mapped). Per the project memory's
"0x4A44 cinematic" note, the death cinematic ultimately runs at
bank 0:0x4A44, after a chain through 0x099A. The cinematic sets
`D880=0x17` and reads `FFE4=1` to know it's a death event vs
something else.

## RST 10 + FFC4 = HUD text routine

Pattern:
```asm
LD HL, FFC4         ; HUD text buffer start
LD A, <string ID>   ; or other parameter
RST 10              ; → JP 0x09DE
```

The HUD buffer at FFC4 extends through to ~FFE3 (~32 bytes), enough for
a stylized HUD line.

## RST 30 + 0x42A5 = ?

`0x42A5` is in bank 1, right before our tile-copy modification at 0x42A7.
This is suspicious — RST 30 lands at a point IMMEDIATELY before our
patched inline tile copy. Worth a closer trace: this might be the
tile-copy entry that *callers* use, where 0x42A5 sets up `H=0x9C` or
`H=0x98` for the tilemap target.

Looking at vanilla bytes at 0x42A0-0x42A7 (per build_v301_gdma assertion):
```
0x42A0:  26 9C       LD H, 0x9C       ; 1st tilemap target
0x42A2:  C3 A7 42    JP 0x42A7        ; jump to copy code
0x42A5:  26 98       LD H, 0x98       ; 2nd tilemap target
0x42A7:  ... inline tile copy starts here ...
```

So `RST 30` (0x42A5) selects "copy to tilemap 0 (0x9800)" by setting
H=0x98 then falling through to 0x42A7. `JP 0x42A2` selects "copy to
tilemap 1 (0x9C00)". Game uses these as a 1-byte shortcut for the
two tilemap-copy variants.
