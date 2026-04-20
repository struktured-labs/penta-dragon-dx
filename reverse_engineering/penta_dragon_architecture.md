# Penta Dragon (J) -- Complete Reverse Engineering Architecture Reference

Developer: Japan Art Media (JAM)
Publisher: Yanoman
Platform: Game Boy (DMG), CGB-enhanced for DX colorization
Genre: Top-down scrolling dungeon crawler
English translation: HTI (fan translation exists)
Physical cart release target: July 2026 retro game conference


---

## 1. Game Overview

Penta Dragon is a top-down scrolling dungeon crawler (NOT side-scrolling). The player controls Sara, who has two forms: Witch (FFBE=0) and Dragon (FFBE=1). The game features powerups (none/spiral/shield/turbo via FFC0), a health system (DCDD/DCDC), and a level timer (DCBB).

### Structure

- **7 stages**, each a scrolling dungeon with 7 interconnected rooms (FFBD=1-7)
- Rooms are continuous -- there are no separate "level 2-5" maps
- "Level select" at 0x7393 loads checkpoint data from SRAM
- 7 checkpoint slots in SRAM at 0xBF00-0xBFC8 (0x28 bytes each) store game state

### Boss System (Dual-Layer)

Two completely independent boss systems exist:

**16 Mini-Bosses** (DCB8/spawn table system):
- Spawned via section cycle counter DCB8 and level data tables in bank 13
- 2 recurring types: Haunt Dragon (Gargoyle/FFBF=1) and The Arachnid (Spider/FFBF=2)
- 8 difficulty tiers, 2 mini-bosses per tier = 16 total unique mini-bosses
- D880 state = 0x0A during mini-boss fights

**8 Stage Bosses** (event sequence system):
- Triggered by Event 0x29 in the event sequence system
- Run entirely in ROM Bank 2 under their own rendering/game logic
- D880 states 0x0C-0x14 (one per boss)
- Named: Shalamar, Riff, Crystal Dragon, Cameo, Ted, Troop, Faze, Angela, Penta Dragon

### A-Fix ROM

File: `rom/Penta Dragon (J) [A-fix].gb` -- 2-byte patch at 0x0A65.

Original game has a developer bug: `AND 0x00; JR Z,+0` causes the A button handler (0x5050) to be called EVERY frame. The A-fix patches this to `AND 0x01; JR Z,+3` so the handler only fires on actual A press. Pattern matches the B button handler (`AND 0x02; JR Z,+3`).

Does NOT affect the title menu (separate input handler at 0x3BF6).


---

## 2. Memory Map

### HRAM Addresses (FF80-FFFF)

#### Game State

| Address | Name | Values | Verified | Notes |
|---------|------|--------|----------|-------|
| `FF91` | Hook flag | 0 or 0x5A | Yes | Suppresses BG sweep during enhanced copy |
| `FF93` | Raw joypad | Bitmask | Yes | Written by 0x0824 in VBlank |
| `FF94` | Edge-detected joypad | Bitmask | Yes | Written by 0x00A8, used by game logic |
| `FF95` | Previous joypad | Bitmask | Yes | Previous FF93, for edge detection |
| `FF96` | Joypad mask | 0xFF | Yes | AND mask for edge detection |
| `FF99` | Bank save/restore | ROM bank# | Yes | Timer ISR uses to restore bank after sound engine |
| `FF9A` | Rendering mode | Various | Partial | Set to 4 during boss arenas |
| `FF9F` | Zone boundary low | Coord | Yes | Entity zone gatekeeper uses FFD3 = entity_coord - FF9F |
| `FFA2` | Zone boundary high | Coord | Yes | Defines active zone upper bound |
| `FFA5` | BG sweep counter | 0-47 | Yes | Phase 1: 0-23, Phase 2: 24-47 |
| `FFA9` | Prev SCX/8 | 0-31 | Yes | For scroll-edge palette detection |
| `FFAC` | Spawn table ptr low | Low byte | Yes | Points to current level's spawn table in bank 13 |
| `FFAD` | Spawn table ptr high | High byte | Yes | High byte of spawn table pointer |
| `FFBA` | Level/boss counter | 0-8 | Yes | Indexes stage boss name table + arena setup; also controls damage multiplier at 0x03A6 |
| `FFBD` | Room/section counter | 0=title, 1-7=rooms | Yes | Jump table at bank1:0x4481 dispatches to 7 room handlers |
| `FFBE` | Sara form | 0=Witch, 1=Dragon | Yes | Used for palette selection |
| `FFBF` | Mini-boss flag | 0=normal, 1-16 | Yes | Set by boss detection at 0x0C07-0x0C18 |
| `FFC0` | Powerup state | 0-3 | Yes | 0=none, 1=spiral, 2=shield, 3=turbo |
| `FFC1` | Gameplay active flag | 0=menu, 1=gameplay | Yes | Guards all colorization code |
| `FFCB` | DMA buffer toggle | 0 or 1 | Yes | Alternates each frame for double-buffered OAM |
| `FFCE` | Next room value | Room number | Yes | Set from room transition table at 0x0BBF, consumed at 0x0B78 -> written to FFBD |
| `FFCF` | Scroll position / section index | 0x10-0x16 | Yes | High nibble indexes room transition table |
| `FFD0` | Tilemap pointer high byte | 0 or 1 | Yes | 0=normal (FFEB=0), 1=alternate/bonus (FFEB=1). NOT a level counter! |
| `FFD3` | Event sequence index | 0-27+ | Yes | Within current FFBA level; computed by gatekeeper at 0x797B each frame |
| `FFD6` | Room progress counter | 0-30+ | Yes | Cleared at 0x2260 on level load; DCBA armed when FFD6 >= 0x1E |
| `FFD9` | Kill/action counter | 0-8+ | Partial | Incremented via pattern at 0x2ACD |
| `FFDA` | Gameplay flag | 0 or 1 | Yes | Set during boss arena |
| `FFE4` | Cinematic mode flag | 0 or 1 | Yes | Set during boss splash and death/timeout |
| `FFE5` | Copy of FFBD | Mirrors FFBD | Yes | Written at 0x0ADB |
| `FFE6` | Invincibility timer | Inc/dec | Partial | Inc at bank1:0x7A72, dec at bank1:0x4AD9 |
| `FFEB` | Bonus phase flag | 0 or 1 | Yes | When set, FFD0=1 (alternate tilemap) |
| `FFEE` | Tilemap base hi | 0x98 or 0x9C | Yes | Protected by hook flag FF91 |
| `FFF4` | Timer enable flag | 0 or 1 | Yes | Set to 0 when mini-boss appears (freezes stopwatch) |
| `FFF5` | Stopwatch seconds | 0-99 BCD | Yes | Counts UP from 00:00 (not down!) |
| `FFF6` | Stopwatch minutes | 0-99 BCD | Yes | Updated in VBlank at 0x0727 every 60 frames |
| `FFFD` | Sub-counter | 0-99 | Yes | Compared to 100 at 0x0ADF, reset when reached |

#### DX Colorizer Addresses (added by DX mod)

| Address | Name | Notes |
|---------|------|-------|
| `DF04` | BG sweep row counter | Replaces FFA6 (game-used by bank 12) |
| `FFA5` | BG sweep phase counter | 0-47 (phase 1: 0-23, phase 2: 24-47) |

### WRAM Addresses (C000-DFFF)

#### Sprite / Tilemap Buffers

| Address | Name | Notes |
|---------|------|-------|
| `C000-C09F` | Shadow OAM buffer 1 | 40 sprites x 4 bytes (Y, X, tile, flags) |
| `C100-C19F` | Shadow OAM buffer 2 | Alternate OAM buffer |
| `C1A0-C4A0` | Tilemap copy buffer | 768 bytes, source for VRAM tilemap copy |
| `C200-C2FF` | Entity type data | Entity markers (FE FE FE XX pattern) |
| `C3E0` | Tile decompression buffer | Intermediate for scroll edge tiles |
| `C4E0` | Secondary tile data buffer | Alternate tile decompression target |

#### Game Variables

| Address | Name | Values | Verified | Notes |
|---------|------|--------|----------|-------|
| `D880` | Master scene state | 0x00-0x1C | Yes | 28-state machine, computed jump table at bank3:0x4A5A |
| `DC00-DC01` | X scroll position (16-bit) | 0-65535 | Yes | SCX = DC00 & 0x0F (fine pixel scroll) |
| `DC02-DC03` | Y scroll position (16-bit) | 0-65535 | Yes | SCY = DC02 & 0x0F |
| `DC04-DC08` | Section descriptor (5 bytes) | Various | Yes | Loaded from bank 13 level data; DC04 determines boss type |
| `DC0B` | Active tilemap toggle | 0 or 1 | Yes | 0=0x9800, 1=0x9C00 |
| `DC0C-DC0D` | Fine scroll offsets | Computed | Yes | From SRL x4 of scroll position |
| `DC0E-DC0F` | VRAM edge pointer offset | Computed | Yes | Within C3E0 buffer |
| `DC10-DC17` | Entity pointers (4x 16-bit) | WRAM ptrs | Yes | Used by zone gatekeeper |
| `DC81` | Section scroll counter | Init 0xC8, -4/tick | Yes | Probe-verified; DC82=0xC8 constant reference |
| `DC82` | Section scroll max | 0xC8 constant | Yes | Reference copy of DC81 initial value |
| `DC85,DC8D,DC95,DC9D,DCA5` | Entity slots (5 slots) | 0=dead | Yes | Entity alive state; all 0 triggers section advance |
| `DCB8` | Section cycle counter | 0-5+ (wraps) | Yes | Indexes spawn table; reset to 0 on death at bank1:0x40B7 |
| `DCBA` | Section advance arm | 0 or 1 | Yes | Only armed when FFD6 >= 0x1E |
| `DCBB` | Level/corridor death timer | 0xFF down | Yes | Two dec paths: 0x1024 (damage) and 0x4200 (time). 0 = game over |
| `DCDC` | Health sub-counter | 0-255 | Yes | SUB 16 each tick at 0x1F3C; underflow decrements DCDD |
| `DCDD` | Health / HP main | 0-23+ | Yes | 0 = death state |
| `DCDF-DCE0` | Timer cascade | Various | Partial | Linked to DCBB decrement |
| `DCFD` | Save data flag | 0 or nonzero | Yes | If nonzero at 0x3B37, JP 0x7393 for level select |
| `DCFF` | Damage timer 1 | Decremented at 0x0786 | Partial | |
| `DCF6-DCF9` | Damage timers 2-4 | Decremented at various | Partial | |
| `DD01-DD02` | Tilemap source pointer | 16-bit | Partial | Points to ROM tilemap data, may be transient |
| `DD03` | Status timer 1 | Decremented at 0x0B39 | Partial | |
| `DD04-DD05` | **UNUSED** | Always 0x00 | Yes | Probe-confirmed. Original RE was wrong. |
| `DD06` | Entity/scroll lock | 0 or nonzero | Partial | When nonzero, D880=0x0B (lock state) |
| `DD08` | Secret code check | 0xC8 | Yes | Checked during boss arena entry |
| `DD09` | Input blocking flag | 0 or 1 | Yes | If nonzero, all input zeroed |
| `DDAE` | Global timer | Decremented at 0x0710 | Partial | |

#### Sound Engine State (D887-D89x)

| Address | Name | Notes |
|---------|------|-------|
| `D880` | Master scene state | Also used by sound engine for music changes |
| `D885` | Music state flag | Checked in sound engine main loop |
| `D887` | Sound command mailbox | 1-deep mailbox: game writes, Timer ISR reads |
| `D888` | Previous sound command | Priority comparison for reject logic |
| `D889-D88A` | Sound state | D889 rarely changes; D88A = active state |
| `D894` | Sound processing state 1 | Cleared when new command processed |
| `D895-D896` | Sound data pointers | Set by command table lookup |
| `D897` | Sound processing state 2 | Cleared when new command processed |
| `D898-D899` | Sound data pointers 2 | Set by second table entry |

### D880 State Machine (28 states)

Dispatched at bank3:0x4029:

| Range | Purpose |
|-------|---------|
| 0x00 | Idle/reset |
| 0x01 | Title menu |
| 0x02-0x09 | Normal dungeon gameplay |
| 0x0A | Mini-boss fight mode (set when FFBF!=0) |
| 0x0B | Entity/scroll lock (when DD06!=0) |
| 0x0C-0x14 | Boss arenas (one per FFBA 0-8) |
| 0x15 | New game start |
| 0x16 | Post-boss dungeon reload |
| 0x17 | Cinematic/death transition |
| 0x18 | Boss cinematic splash screen |
| 0x19 | Post-Angela/final special |
| 0x1A | Post-stage-boss dungeon restoration |
| 0x1B | Name entry / high score |
| 0x1C | Credits / ending |

### SRAM Layout

| Address | Content |
|---------|---------|
| `0xBF00-0xBF27` | Checkpoint slot 1 (0x28 bytes) |
| `0xBF28-0xBF4F` | Checkpoint slot 2 |
| ... | ... |
| `0xBFA0-0xBFC7` | Checkpoint slot 7 |

### Cheat Codes (for testing)

```
Room warp:       FFBD = room (1-7), FFE5 = room (mirror)
Boss mode:       FFBF = index (1=Gargoyle, 2=Spider, 3-8=bosses)
Infinite health: DCDD = 0x17, DCDC = 0xFF (must refresh)
Sara form:       FFBE = 0 (Witch) or 1 (Dragon)
Powerup:         FFC0 = 0 (none) / 1 (spiral) / 2 (shield) / 3 (turbo)
```


---

## 3. VBlank Handler

### Original Handler at 0x06D1

The VBlank ISR entry point is at 0x0040, which jumps to 0x06D1.

```
0x0040: JP 0x06D1      ; VBlank ISR vector

0x06D1: PUSH AF/BC/DE/HL   ; save registers
        CALL 0x34FF         ; unknown (bank-related?)
        CALL 0x0824         ; ** joypad read (ONLY location) **
        CALL 0x086C         ; screen effects / DMA handler
        ; ... timer update at 0x0727 (FFF5/FFF6 every 60 frames)
        ; ... screen shake handler at 0x08F8 if FFE8 != 0
        POP HL/DE/BC/AF
0x081D: RETI                ; re-enables IME, Timer ISR fires here
```

### Call Chain from VBlank

```
0x06D1 VBlank handler
  |-- 0x34FF  (bank/state management)
  |-- 0x0824  (joypad read -> FF93)
  |-- 0x086C  (screen effects)
  |   |-- 0x08F8  (screen shake SCX/SCY if FFE8!=0)
  |   |-- 0x0929  (DMA / additional effects)
  |-- 0x0727  (timer: FFF5/FFF6 update, every 60 frames)
```

### Timing Budget

- Original VBlank: ~2000 T-cycles
- DX v2.84.3: ~5000 T (palette load every frame)
- DX v2.86+: hash-cached palette loading reduces average overhead
- DX v2.90: joypad + cond_pal + OBJ(10 sprites) + DMA = ~285 M-cycles total
- Maximum safe overhead beyond original: ~200 M-cycles per frame

The GB VBlank period is ~1140 M-cycles (LY=144-153). Timer ISR fires every ~11,200 M-cycles (~47,104 T-cycles, ~89 Hz). Any VBlank extension delays pending Timer IRQs, affecting sound engine timing.


---

## 4. Joypad Pipeline

### Complete Path: Hardware to Game Logic

```
FF00 (hardware register)
  |
  v
0x0824 (VBlank handler reads joypad hardware)
  |  - Reads FF00 twice (direction + button halves)
  |  - Combines into single byte
  |
  v
FF93 (raw joypad state, current frame)
  |
  v
0x00A8 (edge detection routine)
  |  - Computes: FF94 = (FF93 XOR FF95) AND FF93 AND FF96
  |  - FF95 = previous frame's FF93
  |  - FF96 = mask (always 0xFF)
  |
  v
FF94 (edge-detected: only NEW presses this frame)
  |
  v
Game logic reads FF94 for input decisions
```

### Key Facts

- 0x0824 is called from VBlank at 0x06DC -- it is the ONLY joypad read location in the entire ROM
- DD09 = input blocking flag: if nonzero, all input is zeroed after the edge detection
- Edge detection requires a "release" frame (FF94=0) between presses for the XOR to fire
- VBlank handler at 0x06D1 calls 0x0824 first, making joypad read the highest-priority VBlank task

### Key Bitmask (GB Standard)

| Key    | Index | Bitmask |
|--------|-------|---------|
| A      | 0     | 0x01    |
| B      | 1     | 0x02    |
| Select | 2     | 0x04    |
| Start  | 3     | 0x08    |
| Right  | 4     | 0x10    |
| Left   | 5     | 0x20    |
| Up     | 6     | 0x40    |
| Down   | 7     | 0x80    |


---

## 5. Sound Engine

### Architecture

The sound engine runs on the Timer interrupt, completely independent of VBlank:

- **Timer ISR at 0x06B3** (29 bytes)
- **Frequency**: TMA=0xD2 (210), prescaler=1024 -> period = (256-210) * 1024 = 47,104 T-cycles -> **89.04 Hz**
- **Fires ~1.49 times per frame** (70,224 T-cycles/frame)
- Sound engine code lives in **bank 3 at 0x4000**

### Timer ISR Disassembly (0x06B3-0x06D0)

```asm
06B3: PUSH AF/BC/DE/HL         ; save registers (8M)
06B7: LD A,0x03                ; bank 3
06B9: LD [0x2100],A            ; switch to bank 3 (4M)
06BC: CALL 0x4000              ; sound engine entry (6M + engine time)
06BF: LD A,0x01
06C1: LD [0x2100],A            ; switch to bank 1
06C4: CALL 0x0D79              ; bank 0 helper (FFD1 counter)
06C7: LDH A,[FF99]             ; ** RESTORE BANK from FF99 **
06C9: LD [0x2100],A
06CC: POP HL/DE/BC/AF          ; restore registers (8M)
06D0: RETI                     ; return, re-enable interrupts
```

**CRITICAL**: The Timer ISR saves NO bank context itself -- it just writes 0x03 to the bank register, then restores from FF99. If FF99 is wrong (e.g., set to 0x0D by a trampoline), the Timer ISR restores to the wrong bank -> garbage code execution.

### D887 Sound Command Mailbox

D887 is a 1-deep mailbox with no synchronization:

- **Game code writes** D887 via RST $38 or direct stores during the main loop
- **Timer ISR reads** D887 ~89 times/second at bank3:0x45B1
- The phase relationship between writes and reads determines which Timer tick processes which command

#### D887 Command Reader (bank3:0x45B1-0x4613, 99 bytes)

```asm
45B1: LD A,[D887]         ; read command
45B4: OR A
45B5: RET Z               ; no command -> return
45B6: LD C,A              ; save in C
45B7: LD A,[D888]          ; previous command
45BA: OR A
45BB: JR Z,+0A (->45C7)   ; prev=0 -> process new
45BD: CP C
45BE: JR Z,+07 (->45C7)   ; ** REDUNDANT ** (JR NC below catches this)
45C0: JR NC,+05 (->45C7)  ; prev>=new -> process
45C2: XOR A
45C3: LD [D887],A          ; reject: clear D887
45C6: RET
45C7: CALL 0x457B          ; process: load channel registers
45CA: CALL 0x4567          ; set NR volumes
45CD: XOR A
45CE: LD [D894],A          ; clear state
45D1: LD [D897],A
45D4: LD [D887],A          ; ** LATE CLEAR ** (race window!)
45D7: LDH [FF10],A         ; NR10 sweep = 0
45D9: LD A,C
45DA: LD [D888],A          ; save as previous
; ... table lookup and music data pointer setup (45DD-4613)
```

**Race window**: D887 is read at 0x45B1 but not cleared until 0x45D4 (200-500 T-states later). During this window, D887 still holds the original command value.

#### D887 Writers (all verified call sites)

| Location | Bank | Mechanism |
|----------|------|-----------|
| 0x0038 (RST $38) | 0 | `LD [D887],A; RETI` (patched to RET in v2.88) |
| 0x0E5F | 0 | `EA 87 D8` (game event table [HL]) |
| 0x0EF3 | 0 | `EA 87 D8` (game event table [HL]) |
| bank1:0x49A4 | 1 | `EA 87 D8` (game logic) |
| bank1:0x49D2 | 1 | `LD HL,D887; LD [HL],A` (game logic) |
| bank3:0x413F | 3 | `EA 87 D8` (music init/reset) |

#### Valid Command Range

All RST $38 call sites use immediate values in range 0x00-0x29. Command 0 = no-op. Commands 1-41 (0x01-0x29) are valid. The command table is at bank3:0x4748 (41 entries x 4 bytes = 164 bytes). Commands >= 0x2A would index past the table into music data = garbage pointers.

### Chaotic Sensitivity

The sound engine is chaotically sensitive to timing:

- Even 1 M-cycle of VBlank overhead change causes TOTAL audio waveform divergence
- Raw PCM cross-correlation is USELESS for comparison (always ~0 with any timing change)
- The only reliable perceptual metric is **silence ratio** (RMS energy envelope, 50ms blocks)
- Vanilla silence ratio: ~0.5%
- DX with OBJ colorizer: 3.8-8.8% silence (BROKEN)
- DX joypad+cond_pal only: 0.5% (matches original)

### Phantom Sound Root Cause (RST $38 RETI Issue)

The RST $38 handler at 0x0038 originally uses RETI, which re-enables IME mid-VBlank:

```asm
0038: LD [D887],A     ; write sound command
003B: RETI            ; re-enables IME! Timer fires immediately!
```

With DX's ~5000T VBlank, Timer is pending ~10.6% of frames (vs ~2.3% vanilla). Timer fires after RST $38's RETI -> D887 double-consumption -> phantom sounds on Channel 1.

**v2.88 fix**: Changed RETI to RET at ROM 0x003B (1-byte patch). IME stays disabled; Timer fires after VBlank's RETI at 0x081D instead.

### D887 Hardening Patch (v2.90 design)

Combined early-clear + range validation patch at bank3:0x45B1:

1. Clear D887 immediately after read (before priority check) -- reduces race window from 200-500T to ~28T
2. Range check: reject commands >= 0x2A (defense against garbage pointers)
3. Removes redundant JR Z (original code bug -- JR NC already catches equal case)
4. Fits in original 99 bytes (98 used + 1 NOP padding)

### Audio Budget Constraint

Maximum safe per-frame VBlank overhead: ~200 M-cycles beyond original joypad read.

**What fits (0 phantom onsets):**
- Joypad read: ~40M
- cond_pal (hash check): ~30M
- OBJ colorizer (10 sprites/page): ~175M
- DMA: ~40M
- Total: ~285M -- passes audio test at 3.4% silence

**What does NOT fit:**
- OBJ colorizer (40 sprites): ~700M -> audio dropouts
- bg_sweep (1 row, 32 STAT waits): ~1200M -> audio dropouts

**Safe mechanisms (don't affect per-frame audio):**
- Enhanced tilemap copy palette pass (room transitions only, runs with DI)
- cond_pal palette RAM loading (hash-gated, runs rarely)


---

## 6. Scroll Engine

### Architecture: Double-Buffered Full Tilemap Rewrites

**CRITICAL FINDING**: The game does NOT use incremental column/row writes during scrolling. It uses double-buffered full tilemap rewrites.

- Two VRAM tilemaps: 0x9800 (BG map 0) and 0x9C00 (BG map 1)
- DC0B = active tilemap toggle (0 = 0x9800, 1 = 0x9C00)
- Each scroll update writes the ENTIRE 24x24 tilemap to the OFFLINE buffer
- Then toggles LCDC bit 3 to swap the visible tilemap

### Scroll Position Registers

| Register | Purpose |
|----------|---------|
| DC00/DC01 | X scroll position (16-bit absolute) |
| DC02/DC03 | Y scroll position (16-bit absolute) |
| SCX (FF43) | DC00 & 0x0F (fine pixel X scroll, lower 4 bits) |
| SCY (FF42) | DC02 & 0x0F (fine pixel Y scroll, lower 4 bits) |

Upper bits of DC00/DC02 determine which tile column/row is at the edge.

### Full Tilemap Copy: 0x42A7 (bank 1)

Entry: H = tilemap base (0x98 or 0x9C), L = 0x00
Source: DE = 0xC1A0 (WRAM tilemap buffer)

- Copies 24 rows x 24 columns = 576 tiles to VRAM
- 6 STAT-wait groups per row x 4 tiles per group = 24 tiles/row
- After 24 tiles: ADD HL,8 (skip 8 unused VRAM columns per 32-byte row)
- DI/EI around each 4-tile burst for safe VRAM access
- C = 0x08 at entry as row stride constant
- 24 rows total (B = 0x18)

**This function is hooked by DX** for the enhanced tilemap copy.

### Toggle + Copy: 0x4295 (bank 1)

```asm
LD A,[DC0B]       ; current buffer
INC A; AND 0x01   ; toggle
LD [DC0B],A
JR Z -> H=0x98    ; select tilemap 0
else -> H=0x9C    ; select tilemap 1
JP 0x42A7         ; do full copy
```

### Main Scroll Update Flow (0x12A0, bank 0)

```
0x12A0: Check scroll direction (A != 0?)
0x12A5: CALL 0x423F    ; load DC00-DC03 into HL/DE
0x12A8: CALL 0x4250    ; apply scroll offset (direction C)
0x12B0: CALL 0x1322    ; prepare new tiles into C3E0
0x12B9: CALL 0x793C    ; check room transition
0x12C2: CALL 0x4466    ; check scroll boundary
0x12C8: CALL 0x5096    ; update edge flags (FFC2-FFC5)
0x12CB: CALL 0x5119    ; update entity scroll offsets
0x12CE: CALL 0x5143    ; update entity positions
0x12D1: CALL 0x4284    ; save new DC00-DC03

--- Tilemap update ---
0x12D4: CALL 0x439F    ; prepare tilemap + compute offsets
0x12D7: LD HL,0xC1A0   ; source buffer
0x12DA: CALL 0x1399    ; process tiles into C1A0
0x12DD: CALL 0x4295    ; toggle tilemap + FULL VRAM COPY
0x12E0: update LCDC    ; based on DC0B
0x12F4: SCX = DC00 & 0x0F
0x1300: SCY = DC02 & 0x0F
```

### Tile Decompression (0x1322, bank 0)

- Computes source address = (L x 64 + E + 0xC780)
- Reads from banked ROM tile data
- Writes 8x8 tile blocks into C3E0 buffer
- 8 rows (B=8) x 8 columns (C=8) per decompression pass

### Room Transition Mechanism

- Scroll handler reads FFCF (scroll position index)
- High nibble of FFCF indexes room transition table at 0x0BBF
- Table mapping: idx4->room1, idx5->room2, idx1->room3, idx9->room4, idx8->room5, idxA->room6, idx2->room7
- FFCE = next-room value from table; consumed at 0x0B78 -> written to FFBD
- DC81 counts down from 0xC8 (200) by 4 per scroll tick within each section
- 0x4228 computes tilemap pointer from new room + FFEB/FFBE state

### SCX/SCY Write Locations (All Banks)

Bank 0: 0x090A, 0x0916 (screen shake), 0x12F9, 0x1300 (main scroll), 0x3080/0x3087 (boss arena), plus several mode-specific writes.

Bank 1: 0x4061/0x4063 (init), 0x41AE/0x41B1 (tilemap copy loop), 0x7526-0x75D6 (room transitions).

Bank 2: 0x404D-0x4C6C (boss arenas), 0x793C/0x793E (alternate scroll).

### Key Scroll Functions Summary

| Address | Bank | Purpose |
|---------|------|---------|
| 0x12A0 | 0 | Main scroll handler entry |
| 0x1303 | 0 | No-scroll path (still does full tilemap update) |
| 0x1322 | 0 | Tile decompression to C3E0 |
| 0x1360 | 0 | Address computation (Lx64+E+0xC780) |
| 0x1399 | 0 | Process C3E0 -> C1A0 buffer |
| 0x423F | 1 | Load DC00-DC03 -> HL/DE |
| 0x4250 | 1 | Apply direction offset to scroll |
| 0x4284 | 1 | Save HL/DE -> DC00-DC03 |
| 0x4295 | 1 | Toggle DC0B, select tilemap, call 0x42A7 |
| 0x42A7 | 1 | **FULL TILEMAP COPY** C1A0 -> VRAM (hooked by DX) |
| 0x436E | 1 | Compute DC0C/DC0D from position |
| 0x439F | 1 | Tilemap prep -> JP 0x48C2 |
| 0x4466 | 1 | Scroll direction/boundary handler |
| 0x48C2 | 1 | Compute DC0E/DC0F edge offset |
| 0x4F96 | 1 | Tilemap mirror copy (0x98xx <-> 0x9Cxx) |
| 0x5096 | 1 | Edge visibility flags (FFC2-FFC5) |
| 0x5119 | 1 | Entity scroll offset update |
| 0x5143 | 1 | Entity position update |


---

## 7. Entity / Boss System

### Mini-Boss System (DCB8 / Spawn Tables)

#### Section Cycle Counter (DCB8)

DCB8 indexes into the level's spawn table (bank 13). It cycles through entries, some of which spawn mini-bosses.

Level 1 example (bank13:0x4024, 6 entries of 5 bytes each):

| DCB8 | DC04 | Type |
|------|------|------|
| 0 | 0x04 | Normal enemies |
| 1 | 0x22 | Normal enemies |
| 2 | 0x30 | **Gargoyle** (Haunt Dragon) |
| 3 | 0x04 | Normal enemies |
| 4 | 0x22 | Normal enemies |
| 5 | 0x35 | **Spider** (The Arachnid) |

#### Boss Detection Formula (0x0C07-0x0C18)

```asm
0x0C07: LD A,[DC04]    ; load section type
0x0C0A: ADD A,0x40
0x0C0C: SUB 0x70       ; effectively: A = DC04 - 0x30
0x0C0E: JR C,no_boss   ; if DC04 < 0x30 -> not a boss
0x0C10: LD B,0x00      ; B = boss counter
0x0C12: INC B           ; loop: divide by 5
0x0C13: SUB 0x05
0x0C15: JR NC,0x0C12
0x0C17: LD A,B          ; A = boss_number
0x0C18: LDH [FFBF],A   ; store boss flag

Result: boss_number = (DC04 - 0x30) / 5 + 1
```

#### Section Advance (0x2248)

Three conditions required:
1. FFBF == 0 (no mini-boss active)
2. DCBA != 0 (advance armed; only armed when FFD6 >= 0x1E)
3. All 5 entity slots dead (DC85, DC8D, DC95, DC9D, DCA5 = 0x00)

When met, DCB8 is incremented at 0x224F, new 5-byte section loaded from bank 13.

DCB8 resets to 0 on death/game-over (bank1:0x40B7). This is why auto-play bots see Gargoyle (DCB8=2) repeatedly -- dying before Spider (DCB8=5).

#### All 16 Mini-Bosses

| # | Name | DC04 | FFBF | Level |
|---|------|------|------|-------|
| 1 | Gargoyle | 0x30 | 1 | L1 |
| 2 | Spider | 0x35 | 2 | L1 |
| 3 | Crimson | 0x3A | 3 | L2 |
| 4 | Ice | 0x3F | 4 | L2 |
| 5 | Void | 0x44 | 5 | L3 |
| 6 | Poison | 0x49 | 6 | L3 |
| 7 | Knight | 0x4E | 7 | L4 |
| 8 | Angela | 0x53 | 8 | L4 |
| 9 | Boss9 | 0x58 | 9 | L5 |
| 10 | Boss10 | 0x5D | 10 | L5 |
| 11 | Boss11 | 0x62 | 11 | L6 |
| 12 | Boss12 | 0x67 | 12 | L6 |
| 13 | Boss13 | 0x6C | 13 | L7 |
| 14 | Boss14 | 0x71 | 14 | L7 |
| 15 | Boss15 | 0x76 | 15 | L8 |
| 16 | Boss16 (unkillable) | 0x7B | 16 | L8 |

Mini-boss 16 (DC04=0x7B) never dies via combat -- 5-minute timeout required for force-kill.

#### Spawn Table Pointer Table (Bank 13)

| Level | Ptr Table ROM | Spawn Table ROM | Entries | Bosses |
|-------|---------------|-----------------|---------|--------|
| 1 | 0x34000 | 0x34024 | 6 | Gargoyle(0x30) + Spider(0x35) |
| 2 | 0x343C8 | 0x343EC | 16 | Crimson(0x3A) + Ice(0x3F) x3 |
| 3 | 0x3463F | 0x34663 | 18 | Void(0x44) + Poison(0x49) x3 |
| 4 | 0x34C42 | 0x34C66 | 25 | ALL 8 bosses cycling |
| 5 | 0x34CF2 | 0x34D16 | 12 | Boss9(0x58) + Boss10(0x5D) |
| 6 | 0x34DFD | 0x34E21 | 16 | Boss11(0x62) + Boss12(0x67) |
| 7 | 0x35010 | 0x35034 | 24 | Boss13(0x6C) + Boss14(0x71) + all prev |
| 8 | 0x350EF | 0x35113 | 6 | Boss15(0x76) + Boss16(0x7B) |

Each pointer table has 18 entries (0-17); entry[13] points to next level. Tables are chained: Table[N].entry[13] -> Table[N+1].start_addr.

#### FFAC/FFAD Per Level

| Level | FFAC | FFAD | Bank 13 Addr |
|-------|------|------|-------------|
| 1 | 0x00 | 0x40 | 0x4000 |
| 2 | 0xC8 | 0x43 | 0x43C8 |
| 3 | 0x3F | 0x46 | 0x463F |
| 4 | 0x42 | 0x4C | 0x4C42 |
| 5 | 0xF2 | 0x4C | 0x4CF2 |
| 6 | 0xFD | 0x4D | 0x4DFD |
| 7 | 0x10 | 0x50 | 0x5010 |
| 8 | 0xEF | 0x50 | 0x50EF |

#### Key ROM Addresses for Mini-Boss Patching

- Level 1 entry 2 (DCB8=2) DC04 byte: **ROM 0x3402F** (Gargoyle=0x30)
- Level 1 entry 5 (DCB8=5) DC04 byte: **ROM 0x3403E** (Spider=0x35)
- Entity alive check: ROM 0x2240 (JR NZ = 0x20 0x26; NOP = 0x00 0x00)

#### Mini-Boss HP / DCBB Dual Role

During mini-boss fights, DCBB also serves as boss HP with phase resets:
- Phase 1: DCBB=0xFF
- Phase 2: at <0x80, adds 0x80 back
- Phase 3: at <0xC0, adds 0x40 back

### Stage Boss System (Event Sequence)

Stage bosses are a COMPLETELY SEPARATE system from mini-bosses. They run in ROM Bank 2 under their own rendering/game logic.

#### Event Sequence System

- Master handler at bank0:0x13E5
- FFBA-indexed subtable pointers at 0x1BCA
- Each level has its own event sequence; FFD3 indexes into it
- **Event 0x29** = boss arena transition (handler at 0x1A2B)

#### Boss Arena Entry Flow (0x1A2B)

```
1. Check FFBF=0 (no mini-boss active) -- RET NZ if busy
2. Clear FFC2-FFC5, FFB2-FFB6
3. Set FFDA=1, FFE4=1
4. CALL 0x16FD (save game state)
5. CALL 0x174E (save more state)
6. CALL 0x759B -> D880=0x18 (boss cinematic splash screen)
7. CALL 0x1EC0 (post-cinematic)
8. Secret code check: DD08=0xC8, input=0x4F
9. Switch to ROM bank 2
10. CALL 0x4000 (boss arena entry!)
11. RST 0x28 (return from bank 2)
12. Post-arena: FFBA++ (if <6), JP 0x54C0 (if =6, Angela path)
```

#### Boss Name Table (bank2:0x7A78)

9 entries x 16 bytes, tile encoding: tile+0x40=ASCII, 0x00=terminator.

| FFBA | Boss Name | D880 State | Arena Setup (bank2) |
|------|-----------|------------|---------------------|
| 0 | SHALAMAR | 0x0C | 0x486E |
| 1 | RIFF | 0x0D | 0x48F8 |
| 2 | CRYSTAL DRAGON | 0x0E | 0x4999 |
| 3 | CAMEO | 0x0F | 0x4A0D |
| 4 | TED | 0x10 | 0x4A76 |
| 5 | TROOP | 0x11 | 0x4AED |
| 6 | FAZE | 0x12 | 0x4B61 |
| 7 | ANGELA | 0x13 | 0x4BD5 |
| 8 | PENTA DRAGON | 0x14 | 0x4C46 |

#### Event 0x29 Availability Per Level

| FFBA | Event 0x29 at Index | Notes |
|------|---------------------|-------|
| 0 | Not present | Level 1 |
| 1 | Index 5 | Level 2 -- early boss arena |
| 2 | Not present | Level 3 |
| 3 | Index 1 and 26 | Level 4 -- immediate + repeat |
| 4 | Index 0 | Level 5 -- immediate |
| 5 | Not present | Level 6 |
| 6 | Index 24, 25, 26 | Level 7 -- triple boss at end |
| 7 | Index 0 and 27 | Bonus -- immediate + repeat |
| 8 | Index 0 | Final -- immediate |

#### Post-Boss Progression

- FFBA < 6: FFBA++ (next level)
- FFBA = 6: JP 0x54C0 -> D880=0x19 (Angela/final boss path, sets FFBA=8)
- FFBA > 6: FFBA = 5 (reset for bonus loop)

#### Three-Layer Gating for Boss Trigger

Writing FFD3 directly does NOT work -- it's computed each frame by the gatekeeper at 0x797B:

1. Room guard (0x4466) -- boundary check
2. Entity zone gatekeeper (0x797B) -- computes FFD3 = entity_coord - FF9F
3. Event dispatch (0x13E5) -- reads FFD3, dispatches to event handler

To trigger a specific boss in auto-play, ROM-patch subtable[0] to 0x29 so index 0 triggers the boss arena, then manipulate FF9F/FFA2 zone boundaries.

#### Mini-Boss vs Stage Boss Comparison

| Feature | Mini-Boss | Stage Boss |
|---------|-----------|------------|
| Trigger | DCB8/spawn table cycle | Event 0x29 in event sequence |
| D880 state | 0x0A | 0x0C-0x14 |
| Location | Same dungeon room | Separate arena (bank 2) |
| FFBF flag | Set to 1-16 | Not used |
| FFBA role | Not used | Indexes boss + arena |
| Sprite data | Shared mini-boss sheet | Individual per boss |
| After defeat | FFBF cleared, resume | FFBA++, reload dungeon |

#### Key Stage Boss ROM Locations

| ROM Address | Bank:CPU | Purpose |
|-------------|----------|---------|
| 0x013E5 | bank0:0x13E5 | Event sequence handler |
| 0x01A2B | bank0:0x1A2B | Boss arena entry (event 0x29) |
| 0x01B76 | bank0:0x1B76 | Event handler jump table |
| 0x01BCA | bank0:0x1BCA | FFBA-indexed event subtable pointers |
| 0x08000 | bank2:0x4000 | Boss arena entry point |
| 0x0AEA6 | bank2:0x6EA6 | Boss arena FFBA dispatch table |
| 0x0B978 | bank2:0x7978 | Boss name display code |
| 0x0BA78 | bank2:0x7A78 | Boss name table (9x16 bytes) |
| 0x0C029 | bank3:0x4029 | D880 state dispatch entry (reads D880, computes jump) |
| 0x0CA5A | bank3:0x4A5A | D880 state handler jump table (28 entries × 2 bytes) |

#### D880 State Handler Addresses (bank 3, computed from jump table at 0x4A5A)

| State | Handler | Description |
|-------|---------|-------------|
| 0x00 | 0x41F4 | Init/idle (direct JP, not in table) |
| 0x01 | 0x4A92 | Title screen |
| 0x02 | 0x4BAC | Dungeon gameplay |
| 0x03 | 0x4E3C | Room transition setup |
| 0x04 | 0x5076 | Room transition execute |
| 0x05 | 0x52EB | Scroll/movement processing |
| 0x06 | 0x5689 | Entity spawn/despawn |
| 0x07 | 0x617B | Unknown (between entity and mini-boss) |
| 0x08 | 0x6328 | Unknown |
| 0x09 | 0x592A | Unknown (back-reference in table) |
| 0x0A | 0x64B0 | Mini-boss fight |
| 0x0B | 0x671B | Entity/scroll lock |
| 0x0C | 0x5B7A | Boss arena phase 1 |
| 0x0D | 0x5BD0 | Boss arena phase 2 |
| 0x0E | 0x5DDE | Boss arena phase 3 |
| 0x0F | 0x6966 | Unknown |
| 0x10 | 0x5FF3 | Boss arena phase 4 |
| 0x11 | 0x6B92 | Unknown |
| 0x12 | 0x6DE1 | Boss arena phase 5 |
| 0x13 | 0x6F43 | Unknown |
| 0x14 | 0x71BC | Boss arena phase 6 |
| 0x15 | 0x73F2 | Unknown |
| 0x16 | 0x74EF | Unknown |
| 0x17 | 0x6041 | Death / game over cinematic |
| 0x18 | 0x7659 | Boss splash screen (name display) |
| 0x19 | 0x7751 | Angela / final boss path |
| 0x1A | 0x788C | Post-boss dungeon restoration |
| 0x1B | 0x7CC6 | Name entry / high score |
| 0x1C | 0x7E4B | Credits / ending |


---

## 8. Title Menu Flow

### Entry Point (0x39C3)

```
0x39C3: Entry (clears DD09 input blocking flag)
        Setup calls
        Falls through to 0x3AF6 (cursor loop)
```

### Cursor Loop

- 953 iterations at 0x3B1C
- Each iteration calls 0x3BF6 (input handler)
- Handler at 0x3BF6: CALL 0x3C3F -> 0x00A8 -> FF94, checks A/UP/DOWN

### GAME START Path

```
0x3B37: Stack reset
        Read DCFD (save data flag)
        JP NZ 0x7393     ; level select (if save data exists)
        ; else: start new game
```

### Level Select (0x7393)

- Has its own input loop at 0x73C3
- Reads FF94 directly (edge-detected joypad)
- Loads checkpoint data from SRAM (0xBF00-0xBFC8)

### Automated Game Start Sequence (verified working)

Input frame windows:
```
DOWN:  frames 180-185
A:     frames 193-198
A:     frames 241-246
A:     frames 291-296
START: frames 341-346
A:     frames 391-396
```

FFC1 (gameplay active) = 0x01 at ~frame 420 (DX ROM) or ~frame 320 (A-fix ROM).


---

## 9. Timer / Clock System

### Stopwatch Timer (FFF5/FFF6) -- COUNTS UP, NOT DOWN

- FFF5 = seconds (0-99 BCD)
- FFF6 = minutes (0-99 BCD)
- Counts UP from 00:00 (walkthroughs claiming it counts down are INCORRECT)
- Updated in VBlank handler at ROM 0x0727, incrementing every 60 frames
- FFF4 = timer enable flag (set to 0 when mini-boss appears, freezing display)
- Used for high-score comparison at ROM 0x52F4 (best time to complete stage)

### Level/Corridor Death Timer (DCBB)

- Counts DOWN from 0xFF
- When reaches 0 -> 0x4A44 cinematic -> GAME OVER
- Initialized to 0xFF at ROM 0x04101

Two decrement paths:
- 0x1024: SUB B (damage-based, subtracts based on hit damage)
- 0x4200: DEC (time-based, via DCDF/DCDE cascade timer)

When DCDF = 0, stops DCBB decrement. DCE0 linked to DCDF cascade.

### 0x4A44 Cinematic = Death/Timeout Sequence

Triggered when DCBB reaches 0 (combat or corridor timeout):

```
- Sets D880=0x17
- Sets FFE4=1
- Loads tiles from bank 0x0E into VRAM 0x9000
- Enables window layer (WX=7, WY=0) for name splash
- A-skip path (0x4AD4): clears FFE4, JP 0x016C (proper cleanup)
- Normal path: does NOT clear FFE4, JP 0x015F (causes stuck state)
```

This is the game over sequence, NOT a stage boss intro.

### FFBA Difficulty Check (0x03A6)

```asm
0x03A6: LDH A,[FFBA]
        CP 2
        JR NZ -> check_zero
        LD A,5             ; FFBA=2: multiplier=5
        LDH A,[FFBA]
        OR A
        JR NZ -> A=20      ; FFBA>0 (not 0 or 2): multiplier=20
        LD A,10             ; FFBA=0: multiplier=10
```

Damage multiplier: FFBA=0 -> 10x, FFBA=2 -> 5x, else -> 20x.


---

## 10. DX Colorization Architecture

### v2.90 Architecture (Latest Stable)

v2.90 achieves clean audio + OBJ sprite colorization on MiSTer. No trampoline, no bg_sweep in this version.

**Build**: Inline Python3 script (not create_vblank_colorizer_v289.py -- that has the broken trampoline).

**ROM**: `rom/working/penta_dragon_dx_v290.gb`

#### VBlank Handler Components

The DX VBlank handler extends the original with colorization:

```
Original VBlank (0x06D1):
  CALL 0x34FF
  CALL 0x0824 (joypad)
  CALL 0x086C (screen effects)

DX additions (after original handler returns):
  1. cond_pal      -- conditional palette RAM load (~30M)
  2. OBJ colorizer -- 10 sprites per page (~175M)
  3. DMA           -- OAM DMA transfer (~40M)
```

Total DX overhead: ~285M, within the ~200M audio budget (measured at 3.4% silence).

#### cond_pal (Conditional Palette Loading)

Hash-cached palette RAM loading:
- Computes a hash of current game state (FFBE, FFC0, FFBF, FFD0)
- Compares with stored hash at DF04 (originally FFA6, but FFA6 is game-used by bank 12)
- If hash matches, SKIP palette load (saves ~550M of BCPD/OCPD writes)
- If hash differs, load all 8 BG + 8 OBJ palettes via BCPS/BCPD and OCPS/OCPD

This was the v2.86 optimization: silence ratio dropped from 17.3% to 7.5%.

#### OBJ Colorizer (shadow_colorizer_main)

Processes shadow OAM buffer to set CGB palette attributes for sprites:
- Iterates through OAM entries in the shadow buffer
- Reads tile ID, looks up palette in tile-to-palette table (bank 13 at 0x7000)
- Writes palette index to VBK=1 OAM attribute
- Throttled to 10 sprites per page (not 40) to stay within audio budget
- 4 frames to color all sprites

#### DMA (OAM DMA Transfer)

Standard OAM DMA from shadow buffer to real OAM (FE00-FE9F):
- Uses FFCB (DMA buffer toggle) to select C000 or C100
- ~160 M-cycles (~40 microseconds)
- Adds negligible audio overhead (+0.1% silence)

### The Trampoline Problem (v2.89 -- BROKEN)

v2.89 used a trampoline at 0x42A7 that jumped to bank 13 for an enhanced tilemap copy. This set FF99=0x0D during the copy. When Timer ISR fired during the copy, it restored the bank from FF99 to bank 13 instead of bank 1 -> garbage code execution -> garbage D887 writes -> phantom sounds.

**v2.90 fix**: Removed the trampoline entirely. All colorization runs in the VBlank handler only. NEVER bank-switch during tilemap copy.

### BG Sweep (Not Yet in v2.90)

The BG sweep writes palette attributes to VRAM VBK=1 during VBlank:
- Reads tile IDs from VRAM VBK=0
- Looks up palette for each tile
- Writes palette to VRAM VBK=1 at same address
- Uses FFA5 as phase counter (0-47: phase 1 rows 0-23, phase 2 rows 24-47)
- Uses DF04 (not FFA6!) for sweep row counter

Previous attempts crashed due to uninitialized FFA6 (game-used) and bad address math.

Audio budget constraint: bg_sweep with 1 row + 32 STAT waits costs ~1200M per frame -- exceeds the 200M budget. Must be throttled or run only during specific safe windows (DI-protected room transitions).

### CGB Boot ROM Interaction

CGB boot ROM initializes BG palette RAM to all-white for games with CGB flag (0x143=0x80). This means:
- Without explicit palette loading, all BG tiles render as white
- v2.84.3 fix: moved CALL cond_pal BEFORE FFC1 check so palettes load during menus (FFC1=0)
- OBJ colorizer still guarded by FFC1 (only during gameplay)

### CGB Double Speed Mode -- INCOMPATIBLE

CGB double speed (KEY1+STOP at 8 MHz) is INCOMPATIBLE with Penta Dragon DX:
- Game logic is NOT purely VBlank-rate-limited
- Processes multiple game ticks per frame via CPU-cycle counting
- At 8 MHz: 2x ticks per frame -> 2x gameplay speed
- Causes missing sprites (Sara), half-colored items, scroll artifacts
- v2.89 double speed experiment was a dead end

All timing strategies must work within normal speed (~1140M VBlank, ~51M HBlank max).

### Tilemap Copy Hook Approaches

Since the game uses full tilemap rewrites (not incremental column updates), three approaches exist for palette attribute integration:

**Approach A (current v2.90)**: 2-phase -- tiles written immediately via existing copy, palettes applied separately by bg_sweep during VBlank. Palette lag up to 4 frames during scrolling.

**Approach B**: Inline palette writes during tilemap copy. Write tiles and palettes in alternating STAT-wait windows (VBK=0 for tiles, VBK=1 for palettes). Doubles STAT waits from 144 to 288 per frame.

**Approach C**: Dual-buffer palette in WRAM. Maintain parallel palette buffer alongside C1A0. Write both during VRAM copy.

### MiSTer Deployment Requirements

- MiSTer requires "Audio mode = No Pops" in Gameboy core OSD settings
- Deploy via `/mister-deploy` skill
- Game input via BLISS-BOX gamepad (physical only -- virtual keyboard reaches MiSTer for system keys only)
- Start game sequence: DOWN -> A -> A -> A -> START -> A on gamepad

### D887 Verification Method

Lua watchpoint script monitors D887 writes during 20s gameplay:
- Original ROM = 1 valid event (the expected startup command)
- v2.90 = 0 garbage events
- Any non-zero garbage value = detectable phantom sound source
- Always verify D887 before deploying to MiSTer


---

## 11. Key Findings and Gotchas

### RST $38 RETI Issue (CRITICAL -- SOLVED)

The RST $38 vector at 0x0038 is the sound command dispatch:
```asm
0038: LD [D887],A   ; write sound command to mailbox
003B: RETI          ; ** RE-ENABLES IME! **
```

With DX's extended VBlank (~5000T), Timer interrupt is pending ~10.6% of frames (vs ~2.3% vanilla). RETI at 0x003B re-enables IME mid-VBlank -> Timer fires immediately -> D887 double-consumption -> phantom sounds.

**Fix**: 1-byte patch at ROM 0x003B: change 0xD9 (RETI) to 0xC9 (RET). IME stays disabled; Timer fires after VBlank's proper RETI at 0x081D.

### CGB Boot ROM All-White Palette (CRITICAL -- SOLVED)

When ROM has CGB flag 0x80 at 0x0143, the CGB boot ROM initializes all BG palette RAM entries to white (0x7FFF). Without explicit palette loading before the first frame renders, the entire screen is white.

**Fix**: cond_pal runs before the FFC1 gameplay check, so palettes load during menus.

### FFA6 is Game-Used (CRITICAL -- SOLVED)

FFA6 is used by the game engine itself (bank 12 code). Using it as a DX scratch register caused collisions. DX uses DF04 instead for the BG sweep row counter.

### Timer ISR + FF99 Interaction (CRITICAL -- SOLVED)

The Timer ISR at 0x06B3 restores the ROM bank from FF99. If any DX code changes FF99 (e.g., a trampoline setting it to bank 13 during tilemap copy), the Timer ISR restores to the wrong bank after processing sound. This causes garbage code execution in the wrong bank.

**Rule**: NEVER bank-switch during tilemap copy. NEVER modify FF99 outside the original game's expected flow.

### Bank 10 JP 0x083C Was a False Positive

During reverse engineering, a JP instruction at bank 10 targeting 0x083C was initially identified as a code path. It turned out to be tile data, not code. The only real caller of the relevant routine is 0x06DC (in the VBlank handler).

### DD04/DD05 Were Misidentified

Original reverse engineering identified DD04 as a scroll position register and DD05 as a section scroll counter. Probe v3 confirmed both are ALWAYS 0x00 during all gameplay. The real addresses are FFCF (scroll position, HRAM) and DC81 (section scroll counter, WRAM).

### Audio Measurement Methodology

- Raw PCM cross-correlation is USELESS (always ~0 due to chaotic sensitivity)
- RMS energy envelope (50ms blocks) is the only reliable metric for dropout detection
- Silence ratio = percentage of 50ms blocks with RMS < 0.005
- Dropout = consecutive 100ms blocks with RMS < 0.003 lasting >= 50ms
- Record via PulseAudio null sink + mgba-qt at 48kHz/16-bit stereo
- Skip first 12s of boot/title for gameplay-only analysis

### emu:screenshot() Corrupts Lua IO Buffer

In mgba's Lua environment, calling emu:screenshot() can corrupt the IO buffer. All critical ROM/memory writes must happen BEFORE screenshots. This is a confirmed mgba bug.

### Headless Testing Pattern

```bash
QT_QPA_PLATFORM=offscreen SDL_AUDIODRIVER=dummy \
timeout 30 xvfb-run -a mgba-qt rom.gb -t state.ss0 --script script.lua -l 0
```

### ROM Patching via mgba Lua

```lua
-- WRONG: writes to MBC register, NOT ROM!
emu:write8(0x3B26, 0x18)

-- WRONG: 'memory' global is nil
memory.cart0:write8(0x3B26, 0x18)

-- CORRECT: use emu.memory.cart0
emu.memory.cart0:write8(0x3B26, 0x18)
```

Banked ROM addressing: Bank N at offsets N*0x4000 to (N+1)*0x4000-1.

### Boot Sequence Critical Addresses

| Address | Purpose | Safety |
|---------|---------|--------|
| 0x0150 | Boot entry | DO NOT HOOK |
| 0x0190 | Main init | CRASHES if hooked |
| 0x06D6 | VBlank handler | CRASHES during menu init |
| 0x0824 | Input handler | CRASHES if replaced |
| 0x0A0F | Init function | CRASHES |
| 0x3B69 | Level load (post-menu) | SAFE for hooks |
| 0x40A0 | VRAM clear | Called multiple times |
| 0x495D | Most-called utility | Called 9x during init |

---

## 12. Gap Investigation Results (April 2026)

Detailed investigation notes live in `reverse_engineering/notes/gap_*.md`. Summary of findings:

### 12.1 Banks 4-9 + 11 (gap_banks_4_to_11.md)
See updated bank map in Appendix A. Banks 4/5 = sprite animation lookup data; banks 6/7 = sprite/form rendering code; banks 8/9 = primary tile graphics; bank 11 = mixed code/data with a 16-bit lookup table. Bank selection is data-driven via bank-IDs stored in bank-13 sprite descriptors.

### 12.2 D880 States 0x02-0x09 (gap_d880_states_02_09.md)
States 0x02-0x09 are NOT alternate code paths but a **data-driven handler structure** stored at each jump-table target: marker byte, substate count, config value, and 16-bit handler pointers. State 0x08 is uniquely 3-substate (others are 2). States 0x03 (config 0x8C) and 0x09 (config 0xC8) carry distinct configs vs the 0xFF default.

| State | Phase | Config | Substates |
|-------|-------|--------|-----------|
| 0x02 | Main gameplay (entry) | 0xFA | 2 |
| 0x03 | Room transition setup | 0x8C | 2 |
| 0x04 | Room transition execute | 0xFF | 2 |
| 0x05 | Scroll/movement | 0xFF | 2 |
| 0x06 | Entity spawn/despawn | 0xFF | 2 |
| 0x07 | AI/collision/lock | 0xFF | 2 |
| 0x08 | Combat / mini-boss detect | 0xFF | **3** |
| 0x09 | Finalization/reset | 0xC8 | 2 |

### 12.3 Per-Boss Arena Setup (gap_boss_arena_setup.md)

Dispatch table at bank2:0x6EA6 → 9 handlers in 0x486E-0x4C46 range. Most are **data tables** (palette IDs, tile sheet IDs, init params) consumed by a common arena-init routine at 0x4853, not standalone functions. Handlers for TROOP (0x4AED), FAZE (0x4B61), and PENTA DRAGON (0x4C46) have embedded code (RET-terminated).

| FFBA | Boss | Handler | Size |
|------|------|---------|------|
| 0 | SHALAMAR | 0x486E | 138 |
| 1 | RIFF | 0x48F8 | 161 |
| 2 | CRYSTAL DRAGON | 0x4999 | 116 |
| 3 | CAMEO | 0x4A0D | 105 |
| 4 | TED | 0x4A76 | 119 |
| 5 | TROOP | 0x4AED | 116 |
| 6 | FAZE | 0x4B61 | 116 |
| 7 | ANGELA | 0x4BD5 | 113 |
| 8 | PENTA DRAGON | 0x4C46 | 150 |

### 12.4 Tile Decompression at 0x1322 (gap_tile_decompression.md)

**Format**: Fixed 4:1 LUT expansion. NOT RLE/LZ. Each compressed byte is an index into 256-entry × 4-byte LUT at 0xA400. Input 64 bytes → output 256 bytes at 0xC3E0. Nested 8×8 loop. Modding tile graphics requires editing the 1024-byte LUT at 0xA400.

Five callers: bank0:0x12B0, 0x130B; bank1:0x43A4, 0x4663, 0x5087.

### 12.5 FFAC / FFAD (gap_ffac_ffad.md)

**16-bit little-endian pointer pair** in HRAM. FFAC=lo, FFAD=hi. Constructor at bank0:0x1404 returns `HL = (FFAD:FFAC)`. Writers: bank 0A + 0C (FFAC), bank 0B (FFAD, 4 sites). Used by spawn-table code in bank 13. Likely points to active level's spawn/entity sub-table.

### 12.6 Sound Command Table (gap_sound_command_table.md)

41 entries × 4 bytes at bank3:0x4748. Each entry = **two 16-bit LE pointers** to bank-3 audio data streams. Reader at 0x45B1 applies priority filter (rejects if `prev_cmd > new_cmd`), indexes table by `(cmd-1)*4`, populates D894-D899. Pointer 0x47EC is reused by 33/41 commands — likely a "silence" stream.

### 12.7 Mini-boss #16 Unkillable (gap_miniboss_16_unkillable.md)

**Status: root cause not confirmed.** The previously-suspected handler at 0x4F63 is a D880 state-decision routine (sets D880=0x0A on FFBF≠0), not a damage path. Likely cause: DC04=0x7B is outside the intended spawn-id range (0x30-0x76 = bosses 1-15) so entity AI/HP table lookup falls through to a no-op handler, leaving DCBB unmodifiable via combat. Suggested fix: clamp `boss_index = min(15, ...)` at 0x0C17. **Was likely a developer placeholder, not a shipped boss.**

### 12.8 CGB Boot ROM Palette (gap_cgb_boot_palette.md)

Original ROM (CGB flag=0x00, title checksum 0x33, 4th letter 0x54) gets DMG-compat palette index 0x1C (all-white 0x7FFF) — `(0x33, 0x54)` is unmatched in CGB boot ROM table. DX ROM (CGB flag=0x80, checksum 0xB3) bypasses DMG-compat logic entirely; title still appears white because CGB native mode leaves palette RAM uninitialized and our `cond_pal` doesn't fire until first VBlank. **Recommended fix**: hook 0x0150 boot entry to write a baseline 4-color BG palette before any title-draw runs.

### 12.9 SRAM Checkpoint Layout (gap_sram_checkpoint_layout.md)

**7 slots × 0x28 bytes** confirmed at SRAM 0xBF00-0xC017 (slots 5-6 cross 0xC000 boundary). 7-iteration save loop at ROM 0x86FD-0x8724. Per-byte field map (best inference):

| Offset | Field | WRAM |
|--------|-------|------|
| 0x00 | Validity flag | — |
| 0x01-0x04 | Scroll X/Y (16-bit each) | DC00-DC03 |
| 0x05 | Level/boss index | FFBA |
| 0x06 | Room | FFBD |
| 0x07 | Sara form | FFBE |
| 0x08 | Powerup | FFC0 |
| 0x09 | Mini-boss flag | FFBF |
| 0x0A-0x0B | HP main / sub | DCDD / DCDC |
| 0x0C-0x0D | Timer sec / min (BCD) | FFF5 / FFF6 |
| 0x0E-0x12 | Section data | DC04-DC08 |
| 0x13-0x27 | Spawn/entity state | DCB8 + flags |

### 12.10 SRAM Validity Flag (gap_sram_validity_flag.md)

**Magic byte mechanism, NOT checksum.** Slot offset 0x00 holds the validity marker:

- `0x01` = valid slot
- `0xFF` = empty (uninitialized SRAM default)

Validation at ROM 0x8757:
```z80
8757: 7E       LD A,(HL)        ; first byte of slot
8758: FE 01    CP $01
875A: 20 38    JR NZ, +0x38     ; skip if not 0x01
```

SRAM enable: `LD A,$0A; LD ($1FFF),A` at 0x09CE. Disable: `LD A,$00; LD ($1FFF),A` at 0x09D6. (MBC5 standard.)

### 12.11 Mini-boss Damage Path (gap_miniboss_damage_path.md, gap_miniboss_16_unkillable.md)

DCBB writers (9 sites) inventoried:

| Site | Purpose |
|------|---------|
| 0x102F | Main combat damage (SUB B) |
| 0x1049 | Reset to 0xFF on death |
| 0x4101 | Game-start init = 0xFF |
| 0x4204 | Time-based DEC (corridor timer) |
| 0x4AD6 | Phase HP refill |
| 0x77C0 | Phase 1 init |
| 0x77D1 | Phase 2 trigger (< 0x80) |
| 0x77E2 | Phase 3 trigger (< 0xC0) |
| 0x7B01 | Defeat sequence |

**Boss-detect formula at 0x0C07** (verified disassembly):
```z80
0C07: FA 04 DC      LD A,(DC04)
0C0A: C6 40 D6 70   ADD A,$40; SUB $70   ; A = DC04 - 0x30 (carry if <0x30)
0C0E: 38 10         JR C, +0x10          ; reject → FFBF=0
0C10: 06 00         LD B,$00
0C12: 04 D6 05      INC B; SUB $05       ; divide-by-5 loop
0C15: 30 FB         JR NC, -5
0C17: 78 E0 BF      LD A,B; LDH ($FFBF),A
```

For DC04=0x7B → FFBF=16. **Boss 16 unkillable root cause**: per-boss spawn/AI table in bank 12 is sized for FFBF=1-15. FFBF=16 reads OOB → entity hitbox never populated in DC85+ → projectile collision never reaches DCBB damage path at 0x102F. Boss 16 is a developer placeholder, not shipped content. Suggested patch: clamp FFBF ≤ 15 at 0x0C18.

### 12.12 D880 State 0x08 (gap_d880_state_08_third.md)

Combat state with 3-phase substate structure. Sub-counter at WRAM 0xDDA8:

| Substate | Handlers | Phase |
|----------|----------|-------|
| 0 | 0x6398 / 0x63A0 | Arena setup + first render |
| 1 | 0x6451 / 0x6485 | Active combat (input/AI/damage loop) |
| 2 | 0x63AD / 0x645E | Cleanup + transition |

Common helpers: 0x068F (arena init), 0x0671 (entity dispatcher), 0x5804/0x5809 (WRAM r/w), 0x53A5 (animation), 0x63DF (render). 3 substates instead of 2 cleanly separates setup/combat/cleanup phases without internal branching.

### 12.13 Bank 11 Lookup Table (gap_bank11_table.md)

Bank 11 is **always loaded** as a permanent shared library (zero `LD A,$0B; LD ($2000),A` instances). Contains:

- **16-bit lookup table** at bank11:0x4000 — 8-byte entries holding stage/arena metadata (palette ref, tileset ID, collision layer, canvas dims). ~10-16 entries.
- **6 RET-terminated routines**: 0x0451, 0x1F7A, 0x24F0, 0x3686, 0x370D, 0x3AF6
- **1064+ CALL targets** into bank 11 across other banks. Hottest: 0x1804 (107 calls), 0x1809 (73 calls), 0x172E (28 calls), 0x0068 (19 calls)

Bank 11 is the dynamic game-mechanics library: sprite animation driver + collision detection + character state machine + arena init.

### 12.14 Banks 6 / 7 Function Catalog (gap_banks_6_7_functions.md)

29 functions documented across both banks (15 in bank 6, 14 in bank 7).

- **Bank 6** (~6.4 KB used / 16 KB): form-specific sprite animation frames for 9 character forms. External calls into 0xDDDC (sprite render dispatch in fixed bank). HRAM: FFF1 (anim counter), FF81 (positioning).
- **Bank 7** (~13.3 KB used / 16 KB): main sprite rendering engine. Largest functions: master renderer at 0x4FD6 (4943 bytes), sprite composition at 0x67C9 (2160 bytes), transformation at 0x6325 (1188 bytes). HRAM: FF73 (form flag), FF00 (PPU), FFF8 (interrupt). WRAM shadow buffers in 0x7AFC-0xE4EB range.

**Pattern**: Form ID written to FF73 → bank 6/7 switched in → bank 7 renderer reads bank 6 form data → composes to OAM shadow → calls fixed-bank 0xDDDC to finalize → switches back.

### 12.15 Sound Pointer Stream Format (gap_sound_pointer_targets.md)

Sound command pointers reference **null-delimited variable-length command streams**:

- Format: `[CMD_BYTE] [arg bytes...] [0x00]` repeated
- 0x47EC ("silence") starts with `0x00` → handler skips immediately. Used as default fallback by 33/41 commands.
- Other streams contain mixed 1-12 byte command entries. Boss music (0x48B1) uses 11-12 byte entries (multi-channel NR-register writes).
- No explicit end marker observed — streams appear open-ended, with the handler's own state machine determining termination.
- Format is similar to Trekkie/GB sound tracker patterns: variable-length commands carrying NR-register arguments.

### 12.16 Combat Damage Write at 0x102F (gap_combat_damage_disasm.md)

Verified disassembly of 0x1024 damage path:

```z80
1024: FA BB DC      LD A,(DCBB)        ; current HP
1027: 90            SUB B              ; B = damage value
1028: C1            POP BC
1029: DA 44 4A      JP C, $4A44        ; underflow → death cinematic
102C: CA 44 4A      JP Z, $4A44        ; HP=0 → death cinematic
102F: EA BB DC      LD (DCBB),A        ; ★ damage write
1032: FE 20         CP $20
1034: 30 0C         JR NC,+12          ; if >= 0x20, skip threshold logic
...
```

**No FFBF range check anywhere in the damage path.** Damage value comes in B (1-15 typical, never validated). Caller chain: collision detector → 0x1004 → 0x1024. This confirms boss 16 unkillability is upstream — collision never fires because boss 16's hitbox isn't populated in OAM/entity slots.

### 12.17 FFBF Spawn/AI Table at 0x2C8F (gap_ffbf_spawn_table.md)

**16 entries × 16 bytes** — INCLUDES entry 16. Lookup at 0x2A99:

```z80
2A99: F0 BF 3D 87 87 87   LDH A,(FFBF); DEC A; ADD A,A x3   ; A *= 8
2A9F: 47 6F 26 00 29       LD B,A; LD L,A; LD H,0; ADD HL,HL ; *= 16 total
```

**Boss-16 OOB hypothesis REJECTED.** Entry 16 exists at 0x2D7F: `04 00 03 03 00 05 01 00 0A 02 00 08 04 00 03 03`. Suspect now: the embedded `00` bytes in entry 16's 4-tuples encode entity-type=0 (no-op), so the entity AI never spawns a hitbox. All entries 1-15 have non-zero entity-type fields. Boss 16 is finished-but-broken placeholder content.

### 12.18 Scroll Engine State (gap_scroll_state.md)

Verified scroll-state byte semantics:

| Address | Purpose | Notes |
|---------|---------|-------|
| DC0B | Tilemap buffer toggle | 0=$9800, 1=$9C00; toggled at 0x4295 (`INC; AND $01`) |
| DC0C | Fine X (low 4 bits of scroll) | Written 0x437D |
| DC0D | Fine Y | Written 0x4376 |
| DC0E/DC0F | VRAM edge pointer (LE) | Computed at 0x48C2 from DC0C/DC0D |
| FFC2 | Top edge visible | 0/1 flag |
| FFC3 | Bottom edge visible | 0/1 flag |
| FFC4 | Left edge visible | 0/1 flag |
| FFC5 | Right edge visible | 0/1 flag |

Edge flags written by 0x5096 routine; boundary check at 0x50DF. The double-buffer + full-tilemap-rewrite design is what makes scroll modifications expensive (~80K T-cycles per copy).

### 12.19 Powerup State Machine FFC0 (gap_powerup_state_machine.md)

State machine at 0x7AC0-0x7B30 (bank 0). Only 4 live FFC0 writes in code:

| Address | Action | Value |
|---------|--------|-------|
| 0x25EC | Game init | FFC0=3 (Turbo default) |
| 0x7AC9 | Expiration | XOR A → FFC0=0 |
| 0x7AE6 | Spiral pickup | FFC0=1 |
| 0x7B16 | Shield pickup | FFC0=2 |

(Other `E0 C0` byte sequences in banks 6-13 are graphics data, not code.)

- Expiration timer at HRAM 0xFC (countdown). Shield: 15 frames (0x0F).
- **Projectiles use palette indices ONLY** — same sprite tile, different palette. Confirms `palettes/penta_palettes_v097.yaml` powerup_palettes mapping.
- Per-powerup handlers: 0x174E (generic projectile state), 0x799E (timer/anim), 0x1B3A (shield invincibility flag at HRAM 0xE4)
- 24 FFC0 reads, all in rendering code (banks 7-14).

### 12.20 Bank 14 Death Cinematic (gap_bank14_death_cinematic.md)

- 16 KB of pure 2bpp tile graphics (~978 non-zero of 1024 tiles)
- Loaded to VRAM 0x9000 via 0x109E (size 0x0800 = 128 tiles)
- Triggered when DCBB=0 → 0x4A44 sets D880=0x17, FFE4=1
- State 0x17 handler at bank3:0x6041; 9-frame animation (~146 frames @ 60 FPS)
- Frame timing table at 0x60A1: `00 0A 0C 10 16 14 12 0E 08` (accel/decel pattern)
- A-skip path at 0x4AD4 clears FFE4 + JP 0x016C (clean exit)
- Normal path leaves FFE4 set + JP 0x015F (known stuck-state bug)

---

## Appendix A: ROM Bank Map

| Bank | File Offset | Key Content |
|------|-------------|-------------|
| 0 | 0x00000-0x03FFF | VBlank/Timer ISR, joypad, scroll handler, event system, boss detection |
| 1 | 0x04000-0x07FFF | Tilemap copy (0x42A7), room dispatch (0x4481), section advance, scroll engine |
| 2 | 0x08000-0x0BFFF | Stage boss arenas, boss name table, arena dispatch |
| 3 | 0x0C000-0x0FFFF | Sound engine (0x4000), D880 state machine, D887 command reader |
| 4 | 0x10000-0x13FFF | Sprite/tile animation lookup tables (data, dominant byte 0x0E) |
| 5 | 0x14000-0x17FFF | Secondary sprite animation data (paired with bank 4) |
| 6 | 0x18000-0x1BFFF | Code: ~20 functions, sprite animation state machine |
| 7 | 0x1C000-0x1FFFF | Code: ~10 functions, variant sprite rendering / form overlays |
| 8 | 0x20000-0x23FFF | Primary sprite/tile graphics sheet (GB bitplane format) |
| 9 | 0x24000-0x27FFF | Secondary sprite/tile graphics, animated tiles |
| 10 (0x0A) | 0x28000-0x2BFFF | Tile data (NOT code despite JP 0x083C false positive); also writes FFAC |
| 11 (0x0B) | 0x2C000-0x2FFFF | Mixed: 16-bit lookup table + sparse code; writes FFAD (4 sites) |
| 12 (0x0C) | 0x30000-0x33FFF | Game logic; uses FFA6; also writes FFAC |
| 13 (0x0D) | 0x34000-0x37FFF | Spawn tables, level data, DX palette/tile lookup tables (0x7000); reads FFAD |
| 14 (0x0E) | 0x38000-0x3BFFF | Death cinematic tile data (loaded to VRAM 0x9000) |

Banks 4-9 + 11 selection is data-driven (no explicit `LD ($2000),A` in the running code paths) — bank IDs are stored as bytes inside bank 13 sprite descriptors, then loaded by the dispatch code based on FFC0 (powerup), FFBF (mini-boss), and D880 (state).

## Appendix B: Complete Function Address Summary

### Bank 0

| Address | Purpose |
|---------|---------|
| 0x0038 | RST $38: LD [D887],A; RET (patched from RETI) |
| 0x0040 | VBlank ISR -> JP 0x06D1 |
| 0x0050 | Timer ISR vector (v2.89 rate compensation for CGB double speed) |
| 0x0067 | Early boot helper |
| 0x00A8 | Edge detection: FF94 = (FF93 XOR FF95) AND FF93 AND FF96 |
| 0x00C8 | Init helper |
| 0x0150 | Boot entry point |
| 0x06B3 | Timer ISR (29 bytes, calls bank3:0x4000 sound engine) |
| 0x06D1 | VBlank handler (save regs, joypad, screen effects) |
| 0x0727 | Timer update (FFF5/FFF6 stopwatch, every 60 frames) |
| 0x0824 | Joypad read (reads FF00 hardware -> FF93) |
| 0x086C | Screen effects / DMA handler |
| 0x08F8 | Screen shake SCX/SCY handler |
| 0x0B78 | FFCE consumption (next-room -> FFBD) |
| 0x0BBF | Room transition table |
| 0x0C07 | Boss detection formula (DC04 -> FFBF) |
| 0x0D79 | FFD1 counter helper (called from Timer ISR) |
| 0x0E5F | D887 write (game event table) |
| 0x0EF3 | D887 write (game event table) |
| 0x12A0 | Main scroll handler entry |
| 0x1322 | Tile decompression to C3E0 |
| 0x1399 | Process C3E0 -> C1A0 buffer |
| 0x13E5 | Event sequence master handler |
| 0x1A2B | Boss arena entry (event 0x29 handler) |
| 0x1BCA | FFBA-indexed event subtable pointers |
| 0x1F3C | Damage system (DCDC SUB 16 -> DCDD DEC) |
| 0x2248 | Section advance trigger |
| 0x39C3 | Title menu entry |
| 0x3AF6 | Title cursor loop |
| 0x3B37 | GAME START (stack reset, check DCFD) |
| 0x3BF6 | Title input handler |
| 0x4A44 | Death/timeout cinematic |
| 0x7393 | Level select |

### Bank 1

| Address | Purpose |
|---------|---------|
| 0x40B7 | DCB8 reset to 0 (death/game-over) |
| 0x4200 | DCBB time-based decrement |
| 0x423F | Load DC00-DC03 -> HL/DE |
| 0x4250 | Apply direction offset to scroll |
| 0x4284 | Save HL/DE -> DC00-DC03 |
| 0x4295 | Toggle DC0B + call 0x42A7 |
| 0x42A7 | FULL TILEMAP COPY (hooked by DX) |
| 0x436E | Compute DC0C/DC0D |
| 0x439F | Tilemap prep |
| 0x4466 | Scroll boundary handler / room guard |
| 0x4481 | Room dispatch (DEC A / JP Z chain, 7 rooms) |
| 0x48C2 | Compute DC0E/DC0F edge offset |
| 0x4F96 | Tilemap mirror copy |
| 0x5096 | Edge visibility flags (FFC2-FFC5) |

### Bank 2

| Address | Purpose |
|---------|---------|
| 0x4000 | Boss arena entry point |
| 0x4853 | Arena rendering setup |
| 0x486E-0x4C46 | Individual boss arena setup functions |
| 0x6EA6 | Boss arena FFBA dispatch table |
| 0x7978 | Boss name display code |
| 0x797B | Entity zone gatekeeper (computes FFD3) |
| 0x7A78 | Boss name table (9x16 bytes) |

### Bank 3

| Address | Purpose |
|---------|---------|
| 0x4000 | Sound engine entry (JP 0x416D) |
| 0x4029 | D880 state dispatch (28 states) |
| 0x413F | D887 write (music init) |
| 0x416D | Sound engine main loop |
| 0x4505 | Playback state machine |
| 0x4567 | Set NR volumes |
| 0x457B | Load channel registers |
| 0x45B1 | D887 command reader (99 bytes, key function) |
| 0x4748 | Sound command table (41x4 bytes) |
| 0x4A5A | D880 scene data pointer table |
