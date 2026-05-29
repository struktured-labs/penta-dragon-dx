# Boss Teleport — WORKING MECHANISM (2026-05-17, validated in PyBoy)

## TL;DR — the teleport sequence that WORKS

Validated in PyBoy headless for boss 0 (Shalamar, D880→0x0C) and boss 3
(Cameo, D880→0x0F). Both rendered real arenas (6 colors, 0% white).

From normal dungeon gameplay (D880=0x02, FFC1=1), execute:

```
1. FFBA = N          ; boss index 0..8 (selects arena + boss)
2. FFBF = 0          ; must be 0 (0x1A2B does RET NZ if mini-boss active)
3. map ROM bank 3    ; write 3 to MBC1 (0x2000-0x3FFF); also FF99 = 3
4. IE (0xFFFF) = 0   ; SAVE it first. Masks ALL interrupts.
5. CALL 0x1A2B       ; the event-0x29 boss-entry handler (bank 0)
6. (arena init runs ~270K-680K cycles; D880 becomes 0x0C+N)
7. restore IE (0xFFFF)
```

### Why this works (and why prior attempts froze)
- **0x1A2B is the NATURAL boss-entry handler** (event 0x29 handler). It does
  the full setup — clears flags, sets FFDA/FFE4, CALL 0x16FD/0x174E
  (save state), CALL 0x759B (splash, **bank 3** code), CALL 0x1EC0, then
  switches to bank 2 and CALL 0x4000 (FFBA-indexed arena init). The arena
  routine writes D880=0x0C+N and FFB7=0x0C+N.
- The prior reverted attempt jumped straight to **bank2:0x4000**, skipping
  0x1A2B's setup, AND ran inside the VBlank IRQ where the `0x0099` STAT
  busy-wait can't complete + EI caused recursion → freeze.
- **The IE=0 trick is the key.** The arena init's palette loop (bank2:0x78E5)
  busy-waits on `0x0099` (waits LCD mode 3 then mode 0). That completes fine
  because the LCD advances independently of the CPU. The problem was the
  VBlank handler (our colorize, which bank-switches via FF99/0x2100) firing
  mid-init and leaving the WRONG ROM bank mapped → arena code executed
  garbage → bailed back to dungeon (D880 stayed 0x02). Setting **IE=0**
  masks all interrupts (even if arena code does EI), so no VBlank corrupts
  the bank. With IE=0 the transition completes cleanly.
- **bank 3 must be mapped** before CALL 0x1A2B, because 0x1A2B's
  `CALL 0x759B` is bank-3 code. (My first injection that mapped bank 3 but
  did NOT set IE=0 reached the arena code but bailed; adding IE=0 fixed it.)

### Empirical proof
- `/tmp/tp_bank3map.py` (copied to `scripts/teleport_mechanism_pyboy.py`):
  boots to dungeon, sets FFBA/FFBF, maps bank 3, IE=0, simulates
  CALL 0x1A2B (pushes a valid return addr so stack stays clean), ticks.
  Result: `FINAL D880=0x0C ... PASS` for boss 0; `0x0F` for boss 3.

## The stage-boss event system (fully mapped)

Stage bosses are driven by a **level-progression event engine**, NOT a flag:

- **Event sequence handler: bank0:0x13E5.** Reads `event = subtable[FFBA][FFD3]`,
  then dispatches via the handler jump table at **0x1B76** (`JP (HL)`).
- **Subtable pointers: bank0:0x1BCA**, indexed by FFBA*2. Each level's event
  list is a sequence of opcodes.
- **FFD3 = event index.** NOT directly writable — recomputed every frame by
  the gatekeeper at **bank3:0x797B** from FF9F/FFA2 (zone boundaries) and
  entity coords (DC10-DC17): roughly `FFD3 = f(entity_coord, FF9F, FFA2)`.
  FFD3 advances as the player crosses zone boundaries → events fire
  sequentially as you progress through a level.
- **Event 0x29 = boss arena transition**, handler = **0x1A2B**
  (verified: jump table entry at 0x1B76+0x29*2=0x1BC8 contains `2B 1A`).
- The engine is **progression-gated, not a per-frame poll** — setting
  FFBA=4 + FFD3=0 in the dungeon did NOT fire the boss (FFD3 stayed 0,
  engine never dispatched). That's why direct `CALL 0x1A2B` + IE=0 is the
  reliable approach rather than trying to drive the natural progression.

### Per-level event 0x29 availability (event list dumps)
- Level 1 (FFBA=0): list `09 11 12 ... 28 28 28 28` — **no 0x29**
- Level 5 (FFBA=4): list `29 09 11 12 ...` — **0x29 at index 0** (immediate)
- Others per `reverse_engineering/penta_dragon_architecture.md` lines 669-799.
- (Direct CALL 0x1A2B doesn't care about list availability — it reads FFBA
  to pick the arena regardless.)

### FFBA → boss → D880 (from architecture doc)
| FFBA | Boss | D880 | bank2 arena setup |
|------|------|------|-------------------|
| 0 | SHALAMAR | 0x0C | 0x486E |
| 1 | RIFF | 0x0D | 0x48F8 |
| 2 | CRYSTAL DRAGON | 0x0E | 0x4999 |
| 3 | CAMEO | 0x0F | 0x4A0D |
| 4 | TED | 0x10 | 0x4A76 |
| 5 | TROOP | 0x11 | 0x4AED |
| 6 | FAZE | 0x12 | 0x4B61 |
| 7 | ANGELA | 0x13 | 0x4BD5 |
| 8 | PENTA DRAGON | 0x14 | 0x4C46 |

## In-ROM implementation plan (NOT yet built)

The teleport can run **from the VBlank hook (bank 13)** — no main-loop hook
needed (bank 0/1/HRAM are all packed; bank 13 has free space). On combo:

1. **Combo detect.** The VBlank hook at 0x0824 already reads the joypad into
   **FF93** (active-high after CPL): bit0=A, bit1=B, bit2=Select, bit3=Start,
   bits4-7=directions. In the colorize handler (bank 13), check FF93 for a
   combo (suggest SELECT+START = 0x0C, or SELECT+A+B = 0x07) with a debounce
   flag so it fires once per press.
2. **Teleport stub** in bank-13 free space (e.g. **0x53C2**, many 36-byte
   gaps available). Pseudocode:
   ```
   LD A,[FFFF] ; save IE
   PUSH AF
   XOR A
   LD [FFFF],A          ; IE = 0
   LD A,<boss>          ; or read/cycle a counter in DF0B
   LDH [FFBA],A
   XOR A
   LDH [FFBF],A
   LD A,3
   LD [2100],A          ; map bank 3
   LDH [FF99],A         ; FF99 shadow = 3
   CALL 0x1A2B          ; arena init (completes with IE=0)
   POP AF
   LD [FFFF],A          ; restore IE
   RET
   ```
3. **Boss cycling UX:** keep a counter byte (DF0B, currently unused) 0..8;
   each combo press increments it (wrap 8→0), sets FFBA, teleports. Lets the
   user cycle through all boss rooms to check colors.

### Caveats / open risks
- The IE=0 window spans the whole arena init (~270K-680K cycles ≈ 4-10
  frames). Interrupts (incl. the sound Timer ISR) are masked that whole
  time → brief freeze + possible audio blip on teleport. Acceptable for a
  debug feature, but violates the usual "DI < 7000T" rule — do NOT leave
  this enabled in a normal play build without gating.
- Only validated in PyBoy via simulated CALL. **Needs verification from the
  actual VBlank-hook context** (build it, press combo in mgba/PyBoy) and on
  **MiSTer hardware**.
- Teleporting mid-dungeon may leave some dungeon state set; after the boss
  is defeated the game does FFBA++ and reloads — behavior of repeated
  teleports / post-boss flow is untested.
- Bank/stack: in the real VBlank-hook version, after CALL 0x1A2B returns the
  arena is set up (D880=0x0C+N); just restore IE and let the VBlank hook's
  normal FF99 restore + RET run. The next frame runs the arena state.

## Key addresses
| Addr | Purpose |
|------|---------|
| bank0:0x13E5 | event sequence handler (reads subtable[FFBA][FFD3]) |
| bank0:0x1B76 | event handler jump table |
| bank0:0x1BCA | FFBA-indexed event subtable pointers |
| bank0:0x1A2B | **event 0x29 = boss-entry handler (CALL THIS)** |
| bank3:0x797B | FFD3 gatekeeper (computes index from FF9F/FFA2/coords) |
| bank3:0x759B | splash routine (called by 0x1A2B — why bank 3 needed) |
| bank2:0x4000 | arena init (FFBA dispatch via table at 0x6EA6) |
| bank0:0x0099 | STAT busy-wait (mode3 then mode0) — needs LCD on, not IRQ |
| 0x0824 | our VBlank hook (reads joypad → FF93; calls colorize 0x6E00) |
| bank13 0x53C2+ | free space for teleport stub |

PyBoy proof scripts: `scripts/teleport_mechanism_pyboy.py` (the working one).
