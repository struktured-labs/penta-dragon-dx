# Penta Dragon — Main Loop and Entry Chain

How the game gets from power-on to the main loop, and what the main loop
actually does.

## Power-on → main loop chain

```
0x0100  (canonical Game Boy entry)
   │
   │  NOP; JP 0x0150
   ▼
0x0150  (post-entry)
   │
   │  DI                       ; disable interrupts during setup
   │  RST 28                   ; -> 0x099A (calls 0x0061 with A=1)
   │  CALL 0x0067
   │  LD SP, 0xDFFF            ; **stack top at 0xDFFF** (high WRAM)
   │  CALL bank1:0x4000        ; main boot init (clears VRAM/WRAM/HRAM/SRAM)
   │  CALL 0x00C8              ; bank-0 follow-up init
   │  EI                       ; re-enable interrupts
   │  CALL 0x3B77              ; game-related setup
   │  CALL bank1:0x40F1        ; bank 1 init #2
   │  CALL 0x0F7A              ; bank 0
   │  XOR A; LD (DD09), A      ; DD09 = 0 (input enabled)
   │
   ▼
0x016C  ════════════════════════ MAIN LOOP TOP ════════════════════════
   │
   │  CALL 0x495D × 4          ; 4× sync calls (wait pattern; possibly HALTs?)
   │  CALL 0x0DE9              ; main loop body part A — likely contains VBlank wait
   │  CALL 0x0E7C              ; part B — AI / movement
   │  CALL 0x01E8              ; part C
   │  CALL 0x55BB              ; part D
   │  CALL 0x2222              ; part E
   │  CALL 0x4F5D              ; part F
   │  JP 0x016C                ; ════ LOOP BACK ════
   │
   ▼
(never reaches here under normal play)
0x018D onwards: secondary boot / reset path (sets DD05=0xC8, DD01=0,
DCFD initialization, more state setup)
```

## Main loop dispatch (0x016C-0x018A)

The main loop body is **6 CALLs** plus 4 sync calls at the top:

| CALL          | Bank | Hypothesized purpose                          |
|---------------|------|------------------------------------------------|
| 0x495D × 4    | bank-1 | Frame sync / wait (likely HALTs internally) |
| 0x0DE9        | bank-0 | Joypad processing / input dispatch          |
| 0x0E7C        | bank-0 | AI / movement / entity updates              |
| 0x01E8        | bank-0 | Collision / scroll                          |
| 0x55BB        | bank-1 | Subsystem (TBD)                             |
| 0x2222        | bank-0 | Subsystem (TBD)                             |
| 0x4F5D        | bank-1 | Subsystem (TBD)                             |

Each CALL is a "subsystem" — collectively they comprise one game tick.
The `JP 0x016C` at the bottom loops back forever, with interrupts
(VBlank/STAT/Timer) firing throughout to handle display, sound, scroll.

## Game-start entry (0x3B37)

Per the project memory: "GAME START: 0x3B37 (stack reset, reads DCFD,
JP NZ 0x7393 for level select)". The disassembly confirms:

```asm
0x3B37: CALL 0x007E              ; pre-start hook
        CALL bank1:0x408E
        DI; LD SP, 0xDFFF; EI    ; reset stack
        LD DE, 0xDCFD; LD A,(DE) ; check DCFD continue/save flag
        AND A; JP NZ, 0x7393     ; if non-zero, jump to level-select (0x7393)
        PUSH AF
        LD A, 0x15; LD (D880), A ; **D880 = 0x15** (title→game transition scene)
        POP AF
        XOR A; LD (DCE7), A      ; clear DCE7
        LD A, 1; CALL 0x3CAB     ; scene setup with arg 1
        CALL 0x0A16              ; another setup
        LD A, 2; CALL 0x34CA     ; scene-load with arg 2
        CALL bank1:0x5016
        CALL bank1:0x492B
        CALL bank1:0x40A0
        ...
```

So pressing START on the title transitions D880 to 0x15 (game intro
state), and from there the scene state machine takes over.

## RST 10 is HL += A (NOT HUD print — earlier docs corrected)

Disassembly of 0x09DE (RST 10 target):

```asm
0x09DE: ADD A, L         ; A = A + L
        JR NC, +1        ; if no carry, skip next
        INC H            ; H += carry
        LD L, A          ; L = A
        RET              ; HL = HL + A (16-bit pointer arithmetic)
```

This is a classic **16-bit pointer-offset primitive**, not text printing.
Common usage:

```asm
LD HL, table_base
LD A, index
RST 10              ; HL = table_base + index
LD A, (HL)          ; A = table[index]
```

This corrects my earlier hypothesis in `hram_allocation_map.md` and
`rst_and_boot.md` that FFC4-FFE3 was a HUD text buffer addressed via
RST 10. The "FFC4 writes" I counted were actually **operand bytes**
from `LD DE, $C4E0` instructions (`11 E0 C4` — the simple census
treated `E0 C4` as `LDH (FFC4), A` but it's the low+high bytes of a
16-bit LD DE immediate).

## Caveat for the HRAM census

The static census in `hram_allocation_map.md` over-counts any HRAM
byte that happens to appear as the low byte of a 16-bit `LD DE/HL/BC,
nn` immediate. Common cases:
- `11 E0 nn` is `LD DE, nnE0` — false-positive write to FFE0
- `21 E0 nn` is `LD HL, nnE0` — same
- `01 E0 nn` is `LD BC, nnE0` — same
- Similarly any `F0 nn` instance where the previous byte was a `LD A, nn`
  (3E) treats E0 as a flag value, not a read of FFnn.

A proper instruction-boundary-aware disassembler would correct these.
For the high-confidence game-state HRAM bytes (FFBA, FFBF, FFC1, FFCE,
FFD1, FFD4, FFD5, FF94, etc.), the patterns are unambiguous — those
identifications stand. For the lower-count "TBD" entries (FFC4, FFE0,
etc.), treat them as possibly-false-positive until confirmed.

The v3.01 production use of **FFE0 as scratch** has been confirmed
safe by Lua probe at runtime (no game state breaks). So even if the
static census mis-categorized it, runtime verifies it's unused by
vanilla code.

## Other RST targets revisited

- **RST 00, 08, 18**: still appear to be unused (target bytes look
  like garbage / soft-reset patterns).
- **RST 20**: still `LD (D880), A; RETI` inline — atomic scene-change
  shortcut. Confirmed.
- **RST 28**: target 0x099A is `PUSH AF; LD A, 1; CALL 0x0061; POP AF;
  RET`. So `RST 28` calls 0x0061 with A=1 then returns. Doesn't seem
  to be a death cinematic directly — more like a generic "do something
  with A=1" dispatcher. The death-cinematic chain (per existing
  `gap_bank14_death_cinematic.md`) goes via FFE4=1 + further calls.
- **RST 30**: target 0x42A5 is the tile-copy variant selector (sets
  H=0x98 then falls through to our v3.01 patched site at 0x42A7).
  Confirmed earlier; this is correct.
- **RST 38**: target 0x0038 inline `LD (D887), A; RETI`. Vanilla;
  v2.88 patches 0x003B `RETI → RET`. Confirmed.

## What this means for the main loop budget

The main loop is purely CPU-bound — there's no explicit VBlank `HALT`
in the visible main-loop assembly. Frame timing is enforced by:

1. **Interrupts that fire during main-loop execution** (VBlank, STAT,
   Timer) — these are the ONLY mechanism that synchronizes the loop
   with display timing.
2. **HALT inside `CALL 0x495D`** (the 4× sync calls at loop top) —
   likely each `0x495D` includes a HALT to wait for VBlank.

If the 4× HALT pattern at the top of the loop waits for VBlank each
time, the main loop runs at effectively **15 FPS** (4 VBlanks per
loop iteration). That matches the visual pace of the game (top-down
shmup with deliberate movement).

This also means our **VBlank handler's 53K T-cycle budget is real**:
the main loop is blocked on VBlank waits anyway, so handler time
directly reduces game logic time per loop. If handler exceeds the
VBlank period, subsequent CALLs in the main loop get less time
per "frame" before the next VBlank arrives.
