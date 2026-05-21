# D880 Master Scene State Machine

Consolidates the per-state notes from `reverse_engineering/notes/gap_d880_*`
into a single unified state diagram.

## Dispatch (revised — verified by full disasm)

The D880 dispatcher at **bank3:0x4029** reads D880, indexes table at
**bank3:0x4A5A**, loads a pointer, and uses the pointed-to **data** to
initialize the **3 sound channels** at D802-D85F + engine state at
D882-D886. Full disasm:

```asm
bank3:0x4029:
    LD A, (D880)
    LD (D881), A          ; D881 = D880 (transition snapshot)
    OR A; JP Z, 0x41F4    ; if state 0, skip
    DEC A; ADD A          ; A = (D880-1) × 2  (16-bit index)
    ADD 0x5A              ; + jump table offset (0x4A5A low byte)
    LD L, A
    LD A, 0x4A; ADC 0     ; high byte 0x4A + carry
    LD H, A               ; HL = 0x4A5A + 2×(D880-1)
    LD A, (HL+); LD H,(HL); LD L,A   ; load 16-bit pointer to scene data

    ; Now HL points to scene data table for this D880 value.
    ; Initialize 3 sound channels at D802/D822/D842
    LD DE, 0xD802; LD B, 3
loop:
    LD A, (HL+); AND 0x07; SWAP A; LD C, A
    RRCA; ADD C; ADD 0x14
    LD (DE), A            ; channel +2 init
    LD A, 0x46; ADC 0
    INC E; LD (DE), A     ; channel +3 init
    LD A, E; ADD 0x1F; LD E, A   ; advance to next channel block (32 bytes)
    DEC B; JR NZ, loop

    LD A, (HL+); LD (D883), A   ; tempo
    XOR A; LD (D882), A         ; clear accumulator
    LD (D885), A; LD (D886), A  ; clear engine status
    ; ... continues with more channel-state init from HL data ...
```

So the **"handlers" in the bank3:0x4A5A jump table are data pointers**,
not code. The dispatcher consumes the data to set up sound channel
state — `marker`, `substate count`, `config`, and the "handler pointers"
in the data table are actually **sound-pattern offsets and tempo
configuration for the scene**.

This **revises the interpretation in `gap_d880_state_08_third.md`** — what
that doc described as "Handler A / Handler B" for combat substates are
actually **pointers to per-channel sound-pattern data**, not code. The
labeling "arena setup / active combat / post-combat" may still be a
useful chronological grouping (substate 0/1/2 representing different
music sections), but the per-handler descriptions are music-driver data,
not direct game logic.

### What the game state machine looks like THEN

The D880 dispatcher's primary job is **scene-specific music init**.
Each scene change (via RST 20 or direct write) triggers a new sound
configuration. The game-state logic (rendering, input, AI) lives
elsewhere — possibly in the bank-3 sound engine's "music has progressed
to new section" callbacks, or in the main loop's other subsystems
(0x0DE9, 0x0E7C, etc.) keyed off D880.

The 4-byte "signature" `05 07 09 89` likely represents the **channel
offset positions** — bytes that determine where in the channel state
block to write specific fields. The constant pattern across states
0x02-0x09 makes sense: all gameplay scenes use the same sound channel
layout; only state 0x01 (title?) differs slightly (`08 07 09 89`).

## All known D880 values

| D880 | Name                        | Source                                    |
|------|-----------------------------|-------------------------------------------|
| 0x00 | Pre-init / power-on default | Set by boot WRAM clear (bank1:0x4000)     |
| 0x01 | Post-RST 20 / unspec        | Set at 0x39D0 (`LD A,1; LD (D880),A`)     |
| 0x02 | Dungeon (gameplay)          | Active gameplay outside boss arenas       |
| 0x03 | Pre-arena transition        | Per `gap_d880_states_02_09.md`            |
| 0x04 | Map/menu                    | Per existing notes                        |
| 0x05 | TBD                         | Per existing notes                        |
| 0x06 | TBD                         | Per existing notes                        |
| 0x07 | TBD                         | Per existing notes                        |
| 0x08 | **3-substate combat**       | Per `gap_d880_state_08_third.md` (DDA8 = substate counter; uses 0x6398/0x63A0, 0x6451/0x6485, 0x63AD/0x645E) |
| 0x09 | TBD                         | Per existing notes                        |
| 0x0A | **Mini-boss arena**         | FFBF flag active (Gargoyle / Spider / etc.) |
| 0x0B | Stuck transitional          | Memory: "scene 0xb stuck state"           |
| 0x0C | **Stage 1 boss arena**      | Shalamar fight (per existing memory)      |
| 0x0D | Stage 2 boss arena          | Riff arena (per arena curriculum saves)   |
| 0x0E | Stage 2 (alt position)      | `arena_FFBA2_D880_0xe_*` curriculum saves |
| 0x0F | Stage 3 boss arena          | Per arena curriculum                      |
| 0x10 | Stage 4 boss arena          | Per arena curriculum                      |
| 0x11 | Stage 5 boss arena          | Per arena curriculum                      |
| 0x12 | Stage 6 boss arena          | Per arena curriculum                      |
| 0x13 | Stage 7 boss arena          | Per arena curriculum                      |
| 0x14 | Stage 8 boss arena (Penta)  | Per arena curriculum                      |
| 0x15 | **Game-start scene**        | Set at 0x3B4D (`LD A,0x15; LD (D880),A`)  |
| 0x16 | Post-boss reload            | Memory: "D880 transitions to 0x16 on stage boss kill" |
| 0x17 | Death cinematic             | 0x4A44 cinematic; godmode reverts to 0x02 |
| 0x18 | Boss splash                 | Memory: "cinematic splash"                |
| 0x19 | TBD                         |                                            |
| 0x1A | TBD                         |                                            |
| 0x1B | TBD (game-end?)             | Set at 0x3A9E                             |
| 0x1C | TBD (continuation?)         | Set at 0x3BA5                             |

## Static D880 write sites (bank 0)

| Site    | Value             | Context                                          |
|---------|-------------------|--------------------------------------------------|
| 0x0020  | A (any)           | RST 20 inline (`EA 80 D8 D9`) — atomic write     |
| 0x0084  | 0                 | Boot init                                        |
| 0x15BF  | A (conditional)   | TBD code path                                    |
| 0x39D0  | 0x01              | TBD entry                                        |
| 0x3A9E  | 0x1B              | Possibly game-end / "the end" scene              |
| 0x3B4D  | 0x15              | **Game start entry** (after DCFD continue check) |
| 0x3BA5  | 0x1C              | TBD — continuation? cutscene?                    |
| 0x3DD1  | A                 | TBD                                              |

Plus dynamic writes via **RST 20** (`E7` opcode) from anywhere in the
ROM. Any code with `LD A, <state>; RST 20` will perform an atomic
state change + return from interrupt.

## State-flow overview

```
                    boot
                     │
                     ▼
                 D880 = 0x00 (cleared by boot)
                     │
                     ▼
            ┌── title screen handling ──┐
            │   (D880 transitions through small  │
            │    states during title menu, then  │
            │    gets to game-start)             │
            └─────────────────────────────────────┘
                     │  press START + level 1
                     ▼
                 D880 = 0x15 (game-start entry, 0x3B4D)
                     │
                     │  scene-load → enter gameplay
                     ▼
                 D880 = 0x02 (dungeon / gameplay)
                     │
                     │  mini-boss spawn (DCB8 cycle, FFBF set)
                     ▼
                 D880 = 0x0A (mini-boss arena)
                     │
                     │  mini-boss killed (FFBF→0)
                     ▼
                 D880 = 0x02 (back to dungeon)
                     │
                     │  all stage rooms cleared, reach arena
                     ▼
                 D880 = 0x0C..0x14 (stage boss arena, by stage)
                     │
                     │  boss killed
                     ▼
                 D880 = 0x16 (post-boss reload)
                     │
                     │  load next stage
                     ▼
                 D880 = 0x18 (boss splash cinematic)
                     │
                     ▼
                 D880 = 0x02 (next stage dungeon)
                     │
                     ⋮
                     │  death event (any time)
                     ▼
                 D880 = 0x17 (death cinematic)
                     │
                     │  cinematic completes
                     ▼
                 D880 = 0x02 (resume from checkpoint, or game over)
```

## State handler data table format (verified from rom dump)

Every state 0x01-0x09 handler is a **data table** with this layout:

```
offset  size  field          notes
------  ----  -------------  --------------------------------------
 +0x00   1    marker         0x02 (states 2-9) or 0x03 (state 0x01)
 +0x01   1    substate cnt   2 for most; 3 for state 0x08
 +0x02   2    config         lo byte = 0x01 always; hi byte = duration/timer
 +0x04   4    signature      `05 07 09 89` for states 2-9; `08 07 09 89` for state 0x01
 +0x08   *    handler ptrs   2 handlers per substate (A=render, B=update);
                              16-bit bank3 addresses, repeating
```

### Per-state config + handler dump

| State | Marker | Substates | Config hi | Config interp | Handlers (sub 0)       | Handlers (sub 1)       |
|-------|--------|-----------|-----------|----------------|------------------------|------------------------|
| 0x01  | 0x03   | 2         | 0xA5      | 165 frames (title timer?) | 0x4AC6, 0x4AD8     | 0x4B34, 0x4B63         |
| 0x02  | 0x02   | 2         | 0xFA      | 250 frames (scroll cycle)  | 0x4C1C, 0x4C2A     | 0x4CC8, 0x4D42         |
| 0x03  | 0x02   | 2         | 0x8C      | 140 frames     | 0x4E7C, 0x4EE8         | 0x4E92, 0x4FB1         |
| 0x04  | 0x02   | 2         | 0xFF      | 255 (max)      | 0x50E6, 0x50EE         | 0x518D, 0x5222         |
| 0x05  | 0x02   | 2         | 0xFF      | 255 (max)      | 0x53BB, 0x5401         | 0x54C7, 0x557F         |
| 0x06  | 0x02   | 2         | 0xFF      | 255 (max)      | 0x5705, 0x570D         | 0x579E, 0x581F         |
| 0x07  | 0x02   | 2         | 0xFF      | 255 (max)      | 0x61BB, 0x6208         | 0x61C3, 0x6256         |
| 0x08  | 0x02   | **3**     | 0xFF      | 255 (max)      | 0x6398, 0x63A0         | 0x6451, 0x6485 + 0x63AD, 0x645E (substate 2) |
| 0x09  | 0x02   | 2         | 0xC8      | 200 frames (matches DC81 init) | 0x596A, 0x5972 | 0x5A1B, 0x5A85         |

### Config-byte interpretation

The hi byte of config maps to **scene duration / timer initialization**:

- Short cutscenes/transitions: 0x8C (140) — state 0x03
- Title/menu: 0xA5 (165) — state 0x01
- Scrolling section: 0xC8 (200) — matches `DC81 section scroll counter init`
- Normal gameplay scroll cycle: 0xFA (250) — state 0x02 (dungeon)
- Indefinite gameplay: 0xFF (max) — states 0x04-0x08 (interactive combat / boss arenas)

The 0xFF for states 0x04-0x08 means "no built-in timeout" — these are
states the game stays in until an external event (player action, kill,
death, etc.) transitions out via RST 20 or direct D880 write.

### Common signature `05 07 09 89`

The 4-byte signature is identical for all gameplay states (0x02-0x09).
For state 0x01, it differs: `08 07 09 89` (first byte changed). These
bytes are likely **scratch offsets** into a shared substate-handling
substructure (perhaps offsets into the entity-slot block at DC85+,
since DC85 + 0x00 = DC85, +0x07 = DC8C, +0x09 = DC8E, +0x89 — though
this last doesn't map cleanly).

Another interpretation: these are 4 separate offsets into the 16-byte
HRAM block FFE0-FFEF used as state-runtime scratch. Worth tracing a
handler to confirm.

## State 0x08 deep-dive (3-substate combat)

Most-detailed existing state. Uses DDA8 as a substate counter that
cycles 0 → 1 → 2:

| Substate | Handler A | Handler B | Phase                              |
|----------|-----------|-----------|-------------------------------------|
| 0        | 0x6398    | 0x63A0    | Arena setup / first-frame render    |
| 1        | 0x6451    | 0x6485    | Active combat (input/AI/damage)     |
| 2        | 0x63AD    | 0x645E    | Post-combat finalize / cleanup      |

Both handlers per substate are called in sequence each tick — A is
typically the "render" pass and B is the "update" pass.

## Connection to v3.01

Our colorize handler's behavior depends on D880 because of the FFC1
gate and the bg_sweep coverage. Specifically:

- **D880 = 0x0C-0x14** (stage arenas): the colorize handler is in
  full effect — attr_computation builds the buffer, GDMA copies to
  VRAM. This is exactly when scroll-tearing artifacts would be
  most visible (boss fights), so the fix matters most here.
- **D880 = 0x02** (dungeon): same handler path applies during
  normal gameplay.
- **D880 = 0x17** (death cinematic): godmode_env handler reverts
  this back to 0x02 for RL training (FFB7 check determines whether
  to allow the cinematic).

## What we still don't know

- Exact handler layout for states 0x03-0x07 and 0x09 (existing notes
  have the data table format but not per-state behavior)
- The role of 0x01, 0x1B, 0x1C states (only their setter addresses
  are known)
- Whether state 0x0B is a real reachable scene or pure transitional

These are tractable via further trace — the dispatch handlers in
bank 3 at addresses listed in the jump table can be disassembled.
