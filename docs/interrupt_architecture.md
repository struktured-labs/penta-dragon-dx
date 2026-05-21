# Penta Dragon Interrupt Architecture

Documents how the ROM's interrupt service routines (ISRs) interact with our
v3.01 colorization handler, and the bank-switching protocol that ties them
all together via the FF99 shadow register. Companion to
`v301_gdma_freeze_diagnosis.md` — that doc explains a specific freeze;
this doc explains the system.

## ROM bank map (MBC1, 256KB, 16 banks)

| Bank | Range            | Purpose                                         |
|------|------------------|-------------------------------------------------|
| 0    | 0x00000-0x03FFF  | Bootstrap, ISR vectors at 0x0040-0x0060, main code, palette stub |
| 1    | 0x04000-0x07FFF  | Main game logic — default switched bank vanilla |
| 2    | 0x08000-0x0BFFF  | Level data + room transition logic              |
| 3    | 0x0C000-0x0FFFF  | **Sound engine** — Timer ISR target (bank 3:0x4000) |
| 4-12 | 0x10000-0x33FFF  | Tile graphics, sprite data, level tile maps     |
| 13   | 0x34000-0x37FFF  | **v3.01 patched bank** — colorization handler at 0x6E00, palettes at 0x6800, bg_table at 0x7000 |
| 14-15| 0x38000-0x3FFFF  | More tile data + death cinematic                |

The vanilla game keeps **bank 1 selected most of the time** during gameplay,
switching to bank 2 for room transitions, bank 3 inside the Timer ISR,
and various banks for graphics loading.

## Interrupt vectors (bank 0)

| Vector | Addr   | Bytes at vector       | Target  | Owner   |
|--------|--------|-----------------------|---------|---------|
| VBlank | 0x0040 | `C3 D1 06`            | 0x06D1  | game    |
| STAT   | 0x0048 | `C3 53 08`            | 0x0853  | game    |
| Timer  | 0x0050 | `C3 B3 06`            | 0x06B3  | game    |
| Serial | 0x0058 | `D9 7D FB ...`        | RETI    | unused  |
| Joypad | 0x0060 | `D9 EA 09 ...`        | RETI    | unused  |

The game uses three interrupts: **VBlank**, **STAT**, and **Timer**.

## The FF99 protocol (critical invariant)

**FF99 is the ROM bank shadow register.** Game code that switches banks does:

```asm
LD A, <target_bank>
LDH [FF99], A        ; update shadow FIRST
LD [0x2100], A       ; then update MBC register
```

Why both: the MBC register at 0x2100 is **write-only**. Game code that
needs to know "what bank is currently mapped" reads FF99 instead.

Each ISR (STAT, Timer) uses FF99 to restore the bank on exit:

```asm
STAT_handler:                        Timer_handler (bank 3:0x4000 target):
  PUSH AF BC DE HL                     similar pattern
  LD A, 1                              LD A, 3
  LD [0x2100], A     ; bank 1          LD [0x2100], A    ; bank 3
  CALL <work in bank 1>                CALL <sound engine work>
  CALL <work in bank 1>                ...
  LDH A, [FF99]                        LDH A, [FF99]
  LD [0x2100], A     ; restore         LD [0x2100], A    ; restore
  POP HL DE BC AF
  RETI                                 RETI
```

If FF99 is stale at the moment an ISR exits, the wrong bank is restored
and the interrupted code resumes with wrong bank mapped — **this is the
exact failure mode that produced the v3.01 freeze.**

### Timer ISR full disassembly (0x06B3)

```asm
0x06B3: F5             PUSH AF
0x06B4: C5             PUSH BC
0x06B5: D5             PUSH DE
0x06B6: E5             PUSH HL
0x06B7: 3E 03          LD A, 0x03
0x06B9: EA 00 21       LD (0x2100), A      ; bank → 3 (sound engine)
0x06BC: CD 00 40       CALL 0x4000         ; bank 3 sound engine main
0x06BF: 3E 01          LD A, 0x01
0x06C1: EA 00 21       LD (0x2100), A      ; bank → 1
0x06C4: CD 79 0D       CALL 0x0D79         ; bank-0 code (0x0D79 is always mapped)
0x06C7: F0 99          LDH A, (FF99)       ; read shadow
0x06C9: EA 00 21       LD (0x2100), A      ; restore bank from FF99
0x06CC: E1             POP HL
0x06CD: D1             POP DE
0x06CE: C1             POP BC
0x06CF: F1             POP AF
0x06D0: D9             RETI
```

Note that Timer does **two** bank switches during its work: first to bank 3
for the sound engine, then to bank 1 for a follow-up call to 0x0D79. The
final restore reads FF99 — so the bank Timer restores is whatever FF99
says, NOT necessarily the bank that was mapped when Timer fired.

### STAT ISR full disassembly (0x0853)

```asm
0x0853: F5             PUSH AF
0x0854: C5             PUSH BC
0x0855: D5             PUSH DE
0x0856: E5             PUSH HL
0x0857: 3E 01          LD A, 0x01
0x0859: EA 00 21       LD (0x2100), A      ; bank → 1
0x085C: CD F8 08       CALL 0x08F8         ; bank-0 code
0x085F: CD 29 09       CALL 0x0929         ; bank-1 code
0x0862: F0 99          LDH A, (FF99)
0x0864: EA 00 21       LD (0x2100), A      ; restore bank from FF99
0x0867: E1             POP HL
0x0868: D1             POP DE
0x0869: C1             POP BC
0x086A: F1             POP AF
0x086B: D9             RETI
```

STAT only switches to bank 1 (no bank 3 detour), but the same restore-from-
FF99 pattern at exit.

### 0x086C — VBlank's post-hook dispatcher

```asm
0x086C: F0 B2; B7; C8       LDH A,(FFB2); OR A; RET Z   ; FFB2==0 → skip
0x0870: 3D; CA 08 3D        DEC A; JP Z, 0x3D08         ; FFB2==1 branch
0x0875: CA 94 08            JP Z, 0x0894                ; FFB2==2 branch
0x0878: F0 B8; 3C; E6 03; E0 B8  ; FFB8 = (FFB8+1) & 3   ; 4-frame cycle
0x087F: C0                  RET NZ                      ; only every 4th frame
0x0880: CD E0 08            CALL 0x08E0
0x0883: B5; C8              OR L; RET Z
0x0885: 06 08               LD B, 8                     ; 8 iterations
0x0887: loop:
        CD 99 00            CALL 0x0099                 ; bank-0 sub
        CB 0E; 23           RRC (HL); INC HL            ; rotate-right (HL)
        CB 0E; 23           RRC (HL); INC HL
        05; 20 F4           DEC B; JR NZ loop
0x0893: C9                  RET
```

Purpose: FFB2-gated dispatcher with a 4-frame cycle counter (FFB8).
Every 4th VBlank, if FFB2 is in a non-trivial mode, this runs an 8-step
RRC-and-advance loop. Likely animates 16 bytes of state (perhaps tile
animation, effect cycling, or palette rotation). Not yet fully traced.

### Bank-3 sound engine main loop (0x416D)

```asm
bank3:0x416D: CD 05 45      CALL 0x4505               ; init/sample stage A
              CD B1 45      CALL 0x45B1               ; init/sample stage B
              FA 85 D8      LD A, (D885); OR A
              JR NZ 0x4154                            ; if D885 != 0, jump
              FA 80 D8      LD A, (D880); LD C, A     ; load D880 (master scene)
              FA 81 D8      LD A, (D881)
              CP C; JP NZ, 0x4003                     ; if D881 != D880, branch
              OR A; RET Z                             ; if both zero, return
              ; D882 += D883 (delta accumulator)
              FA 82 D8; 47; FA 83 D8; 80; EA 82 D8
              RET NC                                   ; return if no carry
              ; If D88A != 0, call 0x422D
              FA 8A D8; B7; CALL NZ 0x422D
              XOR A; LD (D884), A
              ; Process 3 channels at D800, D820, D840 (32 bytes each)
              LD DE, 0xD800; CALL 0x4326
              LD DE, 0xD820; CALL 0x4326
              LD DE, 0xD840; CALL 0x4326
              ...
```

State at D800-D85F: three 32-byte channel blocks (D800-D81F, D820-D83F,
D840-D85F). Each channel processed by 0x4326 (bank 3). Engine state at
D880-D88A:
- D880: master scene/song
- D881: previous master scene (compared to detect transitions)
- D882: delta accumulator
- D883: delta increment
- D884: per-frame channel-processing flag
- D885: status (jump target if non-zero)
- D88A: special flag (triggers 0x422D)

The Timer ISR fires this main loop at ~89 Hz, giving the engine a
~5500T budget per tick (well under Timer-ISR ceiling).

### VBlank handler full structure (0x06D1)

```asm
0x06D1: F5 C5 D5 E5       PUSH AF, BC, DE, HL
0x06D5: CD 80 FF          CALL 0xFF80          ; OAM DMA (HRAM routine)
                                                ; NOTE: we NOP this for v3.01 — DMA is done in colorize handler
0x06D8: 21 D4 FF; 34      INC (FFD4)           ; frame counter tick
0x06DC: CD 24 08          CALL 0x0824          ; joypad-read slot (OUR HOOK lives here)
0x06DF: CD 6C 08          CALL 0x086C          ; another VBlank sub (TBD)
0x06E2: ...               BGP palette animation via FFE3/FFE2/FF47 timing
0x0702: ...               OBP palette animation via DDAE/DDAD timing
0x0727: ...               FFD5 timer logic (cycle 0..0x3C)
...
        D9                RETI
```

Our hook at 0x0824 runs in the middle of the VBlank handler with IME=0
(set on VBlank IRQ entry). We can EI inside our handler — and we do,
inside attr_computation — so STAT/Timer can fire AFTER OUR EI. That's
when FF99 must already say 0x0D, or bank corruption occurs.

### STAT helper 0x08F8 (mid-frame scroll registers)

```asm
0x08F8: F0 E8; B7; C8       LDH A,(FFE8); OR A; RET Z   ; FFE8=scroll-active flag
0x08FC: 21 E9 FF; 34        INC (FFE9)                  ; sub-cycle 0..255
0x0900: 7E; E6 03; 4F       A = FFE9 & 3; LD C, A
0x0904: FA 00 DC; E6 0F     A = [DC00] & 0x0F           ; camera-Y sub-pixel
0x0909: 81; E0 43           ADD C; LDH (FF43), A        ; SCX = (cam_Y & 0xF) + C
0x090C: F0 D4; A0; 4F       A = [FFD4] & B (some mask); LD C, A
0x0910: FA 02 DC; E6 0F     A = [DC02] & 0x0F           ; camera-X sub-pixel
0x0915: 81; E0 42; C9       ADD C; LDH (FF42), A; RET   ; SCY = (cam_X & 0xF) + C
```

Purpose: smooth scrolling by updating SCX/SCY mid-frame. STAT IRQ fires
on a configured trigger (mode 0 / LYC=LY), and this updates scroll
registers at specific scanlines to break the screen into scroll regions
(e.g., for HUD vs playfield). The FFE8 flag gates this — when FFE8=0
(menus etc.), STAT does nothing meaningful.

### Timer helper 0x0D79 (centisecond counter)

```asm
0x0D79: F0 D1               LDH A, (FFD1)
0x0D7B: 3C; FE 64           INC A; CP 0x64               ; wrap at 100
0x0D7E: 38 02               JR C, +2
0x0D80: 3E 00               LD A, 0                      ; reset
0x0D82: E0 D1; C9           LDH (FFD1), A; RET
```

FFD1 is the centisecond counter for the stopwatch (FFF5/FFF6 minutes/
seconds are incremented elsewhere when FFD1 wraps). Timer fires at
~89 Hz so FFD1 hits 100 about once a second.

### Bank 3:0x4000 (sound engine entry)

```asm
0xC000: C3 6D 41       JP 0x416D           ; -> sound main loop entry
0xC003: ... subroutine that operates on D881-D88A state vars
```

The sound state lives at D881-D88A (WRAM bank 0, always mapped). The Timer
ISR fires at ~89 Hz, giving the engine a fixed processing budget per tick.

### Sound engine end-to-end (event-driven music driver)

**Command pipeline:**
1. Game code issues a sound effect / music change via `LD A, <id>; RST 38`.
   `RST 38` is patched in v2.88+ to `LD (D887), A; RET` (no IME re-enable
   to avoid phantom-sound race).
2. Next Timer ISR tick (~89 Hz), the engine main at `bank3:0x416D` runs
   and calls `0x45B1` (command dispatcher).
3. `0x45B1` reads D887, checks against D888 (previous command) to skip
   duplicates, sets up channel state, and clears D887.

**Per-tick channel processing:**
1. `0x4505` (sequence reader): if D894 (note delay) is non-zero, decrement
   and continue. If zero, read next byte from `(D895:D896)`, advance the
   pointer, store new delay in D894, dispatch the event via `0x4586`.
2. For each of 3 channels (D800/D820/D840), `0x4326` processes that
   channel: read event-type byte at DE+1, decrement sub-counter at DE,
   when sub-counter hits zero call `0x43D4` to advance to the next
   channel event.

**Sound state map (D880-D89F):**
| Addr   | Purpose                                                        |
|--------|----------------------------------------------------------------|
| D880   | Master scene state (game-visible) — drives sound mode          |
| D881   | Previous master scene (transition detector)                    |
| D882   | Delta accumulator (incremented each tick by D883)              |
| D883   | Delta increment (effectively the tempo)                        |
| D884   | Per-frame channel-processed flag (counts 0-3)                  |
| D885   | Engine status (non-zero = jump to song-init handler)           |
| D886   | TBD                                                            |
| D887   | **Sound command byte** — written via RST 38 from game code     |
| D888   | Previous sound command (for de-dup in 0x45B1)                  |
| D889   | Engine ready flag (set to 1 in boot init at bank1:0x402A)      |
| D88A   | Special flag — triggers 0x422D when non-zero                   |
| D894   | Current note delay countdown                                   |
| D895   | Song-data pointer low                                          |
| D896   | Song-data pointer high                                         |
| D897   | TBD (read in 0x4505 alongside D894 for skip-init test)         |

**Channel block layout (D800-D85F, 32 bytes each):**
- `DE+0`: per-channel event sub-counter (decremented each tick by 0x4326)
- `DE+1`: event flag/type (BIT 1 tested in 0x4326)
- `DE+2..31`: channel-specific state (frequency, envelope, pattern data;
  exact layout TBD — would need deeper trace of 0x43D4 to fully map)

**Timer ISR's bank-switching sequence (now complete end-to-end):**

```
Timer fires → 0x06B3 → switch to bank 3 → CALL 0x4000 → JP 0x416D
  → CALL 0x4505 (sequence reader; may emit new note + advance pointer)
  → CALL 0x45B1 (command dispatcher; consumes D887 if non-zero)
  → check D885 / D880 vs D881 for state transition
  → D882 += D883 (tempo accumulator)
  → if carry (timing slot reached): process 3 channels via 0x4326
  → return → back in 0x06B3 → switch to bank 1 → CALL 0x0D79
                              (FFD1 centisecond counter tick)
  → restore bank from FF99 → RETI
```

## VBlank handler chain

```
 ┌─ CPU receives VBlank interrupt
 ├─ JP 0x06D1                                  [vector at 0x0040]
 │
 │  game's VBlank handler at 0x06D1
 │    ├─ saves regs
 │    ├─ palette / tilemap copy logic
 │    ├─ CALL 0x0824                            [joypad-read slot]
 │    │   │
 │    │   │  patched hook (us) at 0x0824:
 │    │   │    F0 99 F5             save FF99 to stack
 │    │   │    ... joypad reads (~28 bytes) ...
 │    │   │    3E 0D EA 00 20       LD A,13; LD [2100],A   ← bank switch
 │    │   │    CD <colorize_addr>   CALL into bank 13
 │    │   │
 │    │   │      colorize handler at bank 13:0x6E00:
 │    │   │        F0 99 F5         save FF99 to stack
 │    │   │        3E 0D E0 99      FF99 = 0x0D   ← critical fix
 │    │   │        ... cond_pal, bg_sweep, GDMA, attr_comp ...
 │    │   │        F1 E0 99         restore FF99
 │    │   │        C9               RET
 │    │   │
 │    │   │    F1 EA 00 20          POP AF; LD [2100],A   ← restore bank
 │    │   │    C9                   RET
 │    │
 │    ├─ ... rest of VBlank handler ...
 │    └─ RETI
 │
 └─ resume game code in main loop
```

**Hook constraints:** the joypad-read slot at 0x0824 is 47 bytes maximum.
We can't fit a full FF99 save/update/restore there alongside the bank
switch and joypad logic, so the FF99 fix lives inside the colorize
handler (no byte budget there).

## Bank-switching protocol for safe ISRs during a custom handler

If your custom handler runs with IME=1 at any point (e.g. you EI inside
attr_computation, OAM DMA, etc.), **you MUST update FF99 to match the
bank you've mapped**. Otherwise:

1. ISR fires while your handler is running
2. ISR saves regs, switches to its expected bank (1 or 3)
3. ISR does its work
4. ISR loads bank from FF99 → gets your handler's caller's bank, NOT yours
5. ISR returns; your handler resumes with the wrong bank mapped
6. Next instruction fetch reads garbage from the wrong bank

This applies even if you DI for parts of your handler — as soon as you EI,
any pending interrupt fires immediately. The Timer interrupt fires at
~89 Hz, so it's pending fairly often.

Symptoms of FF99-protocol violations:
- Game freezes at FFC1=0→1 transition (first gameplay frame)
- White screen on boot
- Crash partway through a long handler
- Cycle-precise sensitivity to handler runtime

Cure: at any point in a custom-bank handler where IME could be 1, ensure
FF99 reflects your current bank.

## What we modified vs vanilla

| Address                | Vanilla                | v3.01                                   |
|------------------------|------------------------|-----------------------------------------|
| 0x0040 (VBlank)        | JP 0x06D1              | unchanged                               |
| 0x0048 (STAT)          | JP 0x0853              | unchanged                               |
| 0x0050 (Timer)         | JP 0x06B3              | unchanged                               |
| 0x06D5-0x06D7          | game DMA               | NOP×3 (we do DMA in colorize handler)   |
| 0x0824-0x0852 (47B)    | joypad-read code       | our hook + bank switch + CALL colorize  |
| 0x003B                 | `D9` (RETI)            | `C9` (RET) — phantom-sound v288 fix     |
| 0x42A7-0x436D          | inline tile copy       | tile-only inline copy (vanilla speed)   |
| bank 13 0x6800-0x77FF  | unused                 | v3.01 colorization code + data          |
| 0x143 (CGB flag)       | 0x00                   | 0x80                                    |

The original game runs on DMG (Game Boy) without color. v3.01 sets the
CGB flag and installs a CGB-native palette+attribute pipeline.
