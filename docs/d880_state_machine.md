# D880 Master Scene State Machine

Consolidates the per-state notes from `reverse_engineering/notes/gap_d880_*`
into a single unified state diagram.

## Dispatch

The D880 state machine is dispatched by code at **bank3:0x4029**, using
a jump table at **bank3:0x4A5A**:

```asm
bank3:0x4029:
    LD A, (D880)
    DEC A
    ADD A             ; ×2 for word table
    ; ... index into bank3:0x4A5A ...
    JP (HL)           ; jump to handler
```

States 1-9 use **data-driven dispatch**: each handler points to a struct
with substate counts + handler pointers. States 0x0A+ use direct code.

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
