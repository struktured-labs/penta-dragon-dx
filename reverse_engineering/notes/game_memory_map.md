# Penta Dragon — Complete Game Memory Map

## Confirmed HRAM Addresses (FF80-FFFF)

### Game State

| Address | Name | Values | Confirmed | Notes |
|---------|------|--------|-----------|-------|
| `FFBA` | Level progress / difficulty tier | 0=normal, 2=mid, 7=bonus | Partial | At 0x03A6: controls damage multiplier (0→10, 2→5, else→20). Inc/dec at bank1:0x73EB. Bonus stage=7. |
| `FFBD` | Room/section counter | 0=title/menu, 1-7=rooms | **Yes** | Jump table at bank1:0x4481 dispatches to 7 room handlers. Increases as you progress through level. |
| `FFBE` | Sara form | 0=Witch, 1=Dragon | **Yes** | Used for palette selection |
| `FFBF` | Boss/mini-boss flag | 0=normal, 1-2=mini-boss, 3-8=boss | **Yes** | Mini-bosses: 1=Gargoyle, 2=Spider. Bosses: 3=Crimson, 4=Ice, 5=Void, 6=Poison, 7=Knight, 8=Angela. Forces boss palette on enemies. |
| `FFC0` | Powerup state | 0=none, 1=spiral, 2=shield, 3=turbo | **Yes** | Selects projectile palette |
| `FFC1` | Gameplay active | 0=menu/title, 1=gameplay | **Yes** | Guards all coloring code |
| `FFCE` | Next room | Room number | **Yes** | Set by room transition table at 0x0BBF, copied to FFBD on room change. Checked before FFBD read at 0x0AD9. |
| `FFCF` | Scroll position / section index | 0x12-0x15+ | **Yes** | Probe-verified. Changes with room transitions. Was previously misidentified as DD04. High nibble may index room transition table at 0x0BBF. |
| `FFD0` | Tilemap pointer high byte | 0=normal, 1=bonus | **Yes** | High byte of tilemap source pointer. 0=standard tilemap, 1=alternate/bonus phase (when FFEB=1). NOT a level counter — game has only one continuous dungeon with 7 rooms. Controls jet form palettes. |
| `FFD6` | Room progress counter | 0-15+ | **Yes** | Cleared (=0) on level load at 0x2260. Increments during gameplay. |
| `FFD9` | Kill/action counter | 0-8+ | Partial | Incremented via pattern at 0x2ACD. Resets periodically. |
| `FFE5` | Copy of FFBD | Mirrors FFBD | **Yes** | Written at 0x0ADB |
| `FFE6` | Invincibility/status timer | Inc/dec | Partial | Incremented at bank1:0x7A72, decremented at bank1:0x4AD9 |
| `FFEB` | Bonus phase flag | 0=normal, 1=bonus | **Yes** | When set, FFD0 becomes 1 (alternate tilemap). Controls bonus stage entry. |
| `FFFD` | Sub-counter (0-99) | 0-99, resets at 100 | **Yes** | Compared to 100 (0x64) at 0x0ADF, reset to 0 when reached |

### DMA / VBlank System (our colorizer uses these)

| Address | Name | Values | Notes |
|---------|------|--------|-------|
| `FF91` | Hook flag | 0 or 0x5A | Suppresses BG sweep during enhanced copy |
| `FF99` | Bank save | ROM bank number | Saved/restored around bank switches |
| `FFA5` | BG sweep counter | 0-47 | Phase 1: 0-23, Phase 2: 24-47 |
| `FFA9` | Prev SCX/8 | 0-31 | Scroll-edge detection |
| `FFCB` | DMA buffer toggle | 0 or 1 | Alternates each frame |
| `FFEE` | Tilemap base hi | 0x98 or 0x9C | Protected by hook flag |

## Confirmed WRAM Addresses (C000-DFFF)

### Sprite Data

| Address | Name | Notes |
|---------|------|-------|
| `C000-C09F` | Shadow OAM buffer 1 | 40 sprites × 4 bytes |
| `C100-C19F` | Shadow OAM buffer 2 | Alternate buffer |
| `C1A0-C2FF` | Tilemap copy buffer | Source for enhanced tilemap copy |
| `C200-C2FF` | Entity type data | Entity markers (FE FE FE XX pattern) |

### Game Variables

| Address | Name | Values | Confirmed | Notes |
|---------|------|--------|-----------|-------|
| `DCBB` | Countdown timer | Decrements every ~8 frames | **Yes** | At bank1:0x4200. Tied to DCDF/DCE0 cascade. Triggers events at 0. |
| `DCDC` | Health sub-counter | 0-255 | **Yes** | At 0x1F3C: `SUB 16` each tick. When underflows → DCDD decrements. |
| `DCDD` | Health/HP main | 0-23+ | **Yes** | At 0x1F46: decremented when DCDC underflows. 0=death state. Varies: sara_d=4, extra_life=2, boss_states=0 |
| `DCDF` | Timer cascade 1 | Checked at 0x41F6 | Partial | When 0, stops DCBB decrement |
| `DCE0` | Timer cascade 2 | | Partial | Linked to DCDF |
| `DCB8` | Section cycle counter | 0-5 (wraps at max from level table) | **Yes** | Controls which enemy/boss section loads next. Incremented at 0x224F when all entities defeated. Reset to 0 at bank1:0x40BC on level init/death. Level 1: 0=normal, 1=normal, 2=Gargoyle, 3=normal, 4=normal, 5=Spider. |
| `DC85` | Entity base pointer | Referenced at 0x226C | Partial | Used as HL source for entity loading |
| `DCFF` | Damage timer 1 | Decremented at 0x0786 | Partial | |
| `DCF7` | Damage timer 2 | Decremented at 0x07A0 | Partial | |
| `DCF6` | Damage timer 3 | Decremented at 0x07B6 | Partial | |
| `DCF9` | Damage timer 4 | Decremented at 0x07F9 | Partial | |
| `DC81` | Section scroll counter | Init 0xC8, counts down by 4 | **Yes** | Probe-verified. Initialized to 200 (0xC8) at section start. Decrements by 4 per scroll tick. DC82=0xC8 is the constant initial value. |
| `DC82` | Section scroll max value | Constant 0xC8 | **Yes** | Reference copy of DC81 initial value |
| `DD01:DD02` | Tilemap source pointer | 16-bit address | Partial | Points to current tilemap data in ROM. Always 0 during gameplay — may only be set transiently during level load. |
| `DD03` | Status timer 1 | Decremented at 0x0B39 | Partial | |
| `DC04` | Section descriptor byte 0 | 0x00-0x57 | **Yes** | First of 5 bytes loaded from level data table (bank 13). If >= 0x30, triggers boss: `boss_number = (DC04-0x30)/5+1`. Values 0x30-0x34=Gargoyle, 0x35-0x39=Spider, etc. Written transiently at 0x0C02 during section advance; the HRAM probe sees 0 because it's read+consumed in the same routine. |
| `DC04:DC08` | Section descriptor (5 bytes) | varies | **Yes** | 5-byte section descriptor copied from level data in bank 13. DC04 determines boss/enemy type. DC05-DC08 contain enemy pattern/positioning data. |
| `DD04` | ~~Scroll position~~ | **UNUSED** | ~~Yes~~ | **WRONG**: Probe v3 confirmed always 0x00 during all gameplay including room transitions. The real scroll position index is FFCF (HRAM). |
| `DD05` | ~~Section scroll counter~~ | **UNUSED** | ~~Yes~~ | **WRONG**: Probe v3 confirmed always 0x00. The real section scroll counter is DC81 (WRAM). |
| `DD06` | ~~Enemy spawn counter~~ | **UNUSED** | ~~Partial~~ | **Suspect**: Likely also wrong. Entity data lives in DC84-DCAF range. |
| `DD09` | Input blocking flag | 0 or 1 | **Yes** | Probe-verified. Briefly set to 1 during transitions, then back to 0. When ≠0, all input zeroed. |
| `DDAE` | Global timer | Decremented at 0x0710 | Partial | |

## Cheat Codes (for testing)

### Level/Room Warp
Write to `FFBD` and `FFE5` simultaneously:
```
FFBD = room_number (1-7)
FFE5 = room_number (mirror)
```
**Note:** This changes room behavior (enemy patterns, events) but does NOT reload the tilemap. The game is one continuous dungeon with 7 interconnected rooms — there are no separate "levels 2-5".

### Boss / Mini-Boss Mode
Write to `FFBF`:
```
FFBF = boss_index (1-8)
```
**Mini-bosses** (mid-level encounters):
- 1=Gargoyle, 2=Spider

**Bosses** (major/end-of-level encounters):
- 3=Crimson, 4=Ice, 5=Void, 6=Poison, 7=Knight, 8=Angela

Forces all enemy sprites to the selected boss palette slot.
**Verified working** — changes enemy colors immediately.

### Infinite Health
Freeze `DCDD` and `DCDC`:
```
DCDD = 0x17 (23 HP)
DCDC = 0xFF (max sub-counter)
```
Must be refreshed periodically (game will decrement them).

### Sara Form Toggle
```
FFBE = 0  (Witch)
FFBE = 1  (Dragon)
```

### Powerup Select
```
FFC0 = 0  (None)
FFC0 = 1  (Spiral)
FFC0 = 2  (Shield)
FFC0 = 3  (Turbo)
```

## ROM Code References

### Level Load (bank0:0x2260)
```
0x2260: XOR A; LDH [FFD6],A     ; clear room progress
0x2262: LDH A,[FFBF]; OR A      ; check boss flag
0x2265: JP NZ, 0x27F4           ; boss path
0x226C: LD HL, 0xDC85           ; entity data base
```

### Room Dispatch (bank1:0x4481)
```
0x4481: LDH A,[FFBD]  ; load room counter
0x4483: DEC A; JP Z, room1_handler
0x4487: DEC A; JP Z, room2_handler
... (7 rooms total)
0x449F: LD A, 1 → default handler
```

### Damage System (bank0:0x1F3C-0x1F52)
```
0x1F3C: LD A,[DCDC]; SUB 16    ; health sub -= 16
0x1F41: JR C, skip             ; if underflow, skip
0x1F43: LD [DCDC],A
0x1F46: LD A,[DCDD]; DEC A     ; health main -= 1
0x1F4A: LD [DCDD],A
0x1F4E: LD A, 0x09; RST 0x38  ; play damage sound
```

### FFBA Difficulty Check (bank0:0x03A6)
```
0x03A6: LDH A,[FFBA]; CP 2
0x03AA: JR NZ → check_zero
0x03AC: LD A, 5 → multiplier=5
0x03B0: LDH A,[FFBA]; OR A
0x03B3: JR NZ → A=20 (high)
0x03B5: LD A, 10 → multiplier=10
```

### Room Transition (bank0:0x0BBF)
```
0x0BBF: Room transition table (likely indexed by FFCF, NOT DD04 which is unused)
        Maps current scroll position → next room number (stored in FFCE)
        FFCE → FFBD on room change
        DC81 initialized to 0xC8 (200) for section scroll countdown
```

### Boss Detection (bank0:0x0C07-0x0C18) -- FULLY SOLVED
```
; DC04 is loaded with section descriptor from level data table (bank 13)
; The section table is indexed by DCB8 (section cycle counter)
; Level 1 table at bank13:0x4024 has 6 entries (max index = 6):
;   DCB8=0: DC04=0x04 (normal enemies)
;   DCB8=1: DC04=0x22 (normal enemies)
;   DCB8=2: DC04=0x30 (Gargoyle mini-boss)
;   DCB8=3: DC04=0x04 (normal enemies)
;   DCB8=4: DC04=0x22 (normal enemies)
;   DCB8=5: DC04=0x35 (Spider mini-boss)

0x0C07: LD A, [DC04]      ; load section type
0x0C0A: ADD A, 0x40        ;
0x0C0C: SUB 0x70           ; effectively: A = DC04 - 0x30
0x0C0E: JR C, no_boss      ; if DC04 < 0x30 -> no boss
0x0C10: LD B, 0x00         ; B = 0 (boss counter)
0x0C12: INC B              ; B++ (loop: divide by 5)
0x0C13: SUB 0x05           ;
0x0C15: JR NC, 0x0C12      ;
0x0C17: LD A, B            ; A = boss_number
0x0C18: LDH [FFBF], A      ; store boss flag

boss_number = (DC04 - 0x30) / 5 + 1
```
**Section advance trigger** (bank0:0x2248):
- When all 5 entity slots at DC85+ are zero (all enemies defeated)
- DCB8 is incremented at 0x224F, new 5-byte section loaded from bank 13 table
- FFD6 reset to 0 at 0x2260
- If new section has DC04 >= 0x30, FFBF set; game jumps to boss handler at 0x27F4

**Section cycle reset** (bank1:0x40B7):
- DCB8 reset to 0 on death/game-over/level init
- This is why the auto-play bot always sees Gargoyle (DCB8=2) and never Spider (DCB8=5)
- To reach Spider, must survive through sections 0,1,2(Gargoyle),3,4 without dying

**NOTE**: DC04 is written transiently (copied from ROM, read immediately, then value
persists until next section advance). Frame-based probes may see it as the section
descriptor value during gameplay, not always 0. DD04 (different address) IS always 0.

Result stored in FFBF (1-8):
- Mini-bosses: 1=Gargoyle, 2=Spider
- Bosses: 3=Crimson, 4=Ice, 5=Void, 6=Poison, 7=Knight, 8=Angela
- After defeating Angela (boss 8), game returns to title screen.

## Game Structure

**There are no separate levels 2-5.** The game is one continuous dungeon with 7 interconnected rooms. The "level select" screen loads checkpoint data from SRAM (0xBF00-0xBFC8) but always initializes FFBD=5, FFD0=0. FFD0 is NOT a level counter — it only takes values 0 (normal) and 1 (alternate/bonus phase when FFEB=1).

## What We Still Need

1. **Lives address**: FFBA doesn't appear to be simple lives. May need to trace the death/game-over sequence to find the actual lives counter. Could be in the DC80-DCFF range.
2. **Item inventory**: Haven't found item slot addresses yet. Need to test with item pickup states.
3. **Score**: No score address identified yet (game may use BCD in WRAM).
4. ~~**Boss detection mechanism**~~: **SOLVED** -- see "Boss Detection" section above. DC04 (loaded from ROM bank 13 level data table, indexed by DCB8) determines boss type via `boss = (DC04 - 0x30) / 5 + 1`.
5. ~~**Spider mini-boss trigger**~~: **SOLVED** -- Spider appears at DCB8=5 in the section cycle. The autoplay bot never reaches it because DCB8 resets to 0 on death. Must survive through Gargoyle (DCB8=2) + sections 3,4 to reach Spider at DCB8=5.
