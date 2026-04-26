# Runtime Probe Final — Closure Document (April 2026)

Synthesis of all 8 probe rounds. What we now KNOW vs what remains UNKNOWABLE without input injection.

## Definitively Confirmed

### 1. CGB Palette RAM is Literally All-White

Probe 7 read CGB palette RAM (BCPS auto-increment) at 8 checkpoints from frame 1 to frame 400. **Every byte was 0xFF** in BG palette 0-7 AND OBJ palette 0-7. BGP=0xE4 (default DMG mapping).

This is the empirical confirmation of why the original Penta Dragon title screen is invisible on CGB hardware — every color = 0xFFFF (BGR555 maximum = white). The DMG-compat boot ROM picks the all-white palette index 0x1C for unrecognized title checksums.

The DX hack's `cond_pal` routine fixes this by writing custom palettes, but in the unmodified A-fix ROM tested here, palette RAM never changes from boot 0xFF.

### 2. Boss 16 IS Killable via Direct DCBB Write

| Test | Result |
|------|--------|
| Spawn boss 16 (DC04=0x7B via ROM patch) | f=15: FFBF=0x10 set |
| State machine response | f=23: D880 → 0x0A (mini-boss) |
| Direct DCBB writes (-= 0x10 every 5 frames) | DCBB drops 0xFF → 0 |
| Death pipeline | f=535: D880 → 0x17 (death cinematic) |

**Conclusion**: damage path 0x102F (`SUB B; LD (DCBB),A; JP C/Z $4A44`) is GENERIC. Any path that drives DCBB to 0 triggers death cinematic via 0x4A44. Boss 16 is not "specially protected."

### 3. Boss 16 Renders as a Moving Entity

Slot 1 (DC85+) byte 0 transitions 0x00 → 0x10 (active) ~145 frames after spawn. Bytes 2-3 advance frame-by-frame indicating movement (Y/X position). Byte 7 = sprite-base index 0x0E (stable).

### 4. Entity Slot Byte Map (8 bytes per slot)

| Offset | Confirmed semantic |
|--------|--------------------|
| 0 | Active flag (0x00=empty, 0x10/0x2A=active) |
| 1 | Animation frame counter (cycles 0-9) |
| 2 | Y position (or screen Y) |
| 3 | X position |
| 4 | Constant flag 0x7F |
| 5 | Direction/speed indicator (0x01/0x02) |
| 6 | Sub-counter |
| 7 | Sprite-base index (per-entity stable) |

### 5. D880 State Machine — Live Behavior

**Only observed values**: 0x00 (uninit), 0x02 (gameplay), 0x0A (mini-boss), 0x17 (death cinematic).

- D880 writes persist (game does NOT continuously reset)
- States 0x02-0x09 from jump table at bank3:0x4A5A appear unreached during normal play
- State 0x18 (boss splash), 0x0E (Crystal Dragon arena) etc need OTHER preconditions to enter (FFD3 event sequence + room conditions); raw D880 write reverts on next frame

**DDA8 is NOT a substate counter** — stayed 0 across all probes, including state 0x0A combat.

### 6. FFBF → State Transition Confirmed

- FFBF=0 → D880 = (FFB7 normal scene)
- FFBF != 0 → D880 = 0x0A (boss state)
- Transition takes 2 frames

Boss-detect at 0x4F63 verified: `LDH A,(FFBF); AND A; JR NZ +0x0E (→ D880=0x0A); else D880=(FFB7)`.

### 7. Sound Stream D894 = Note Duration Counter

After D887=5 write:
- D894 loaded with 0x0B
- Decrements 1 per frame to 0
- D896 advances stream pointer (0x4A → 0x48)
- D898/D899 stable (envelope/channel state)

### 8. Boss-Detect Formula at 0x0C07 — Verified Disassembly

```z80
0C07: FA 04 DC      LD A,(DC04)
0C0A: C6 40 D6 70   ADD A,$40; SUB $70   ; A = DC04 - 0x30
0C0E: 38 10         JR C, +0x10          ; reject if DC04 < 0x30
0C10: 06 00         LD B,$00
0C12: 04 D6 05      INC B; SUB $05       ; divide-by-5 loop
0C15: 30 FB         JR NC, -5
0C17: 78 E0 BF      LD A,B; LDH (FFBF),A
```

For DC04=0x7B → FFBF=16. Confirmed by probe.

## Strong Hypothesis (Not Conclusively Verified)

### Boss 16 Unkillability Root Cause = Collision Detection Failure

Entity AI table at 0x2C8F, 16 entries × 16 bytes. Boss 16 entry at 0x2D7F:

```
04 00 03 | 03 00 05 | 01 00 0A | 02 00 08 | 04 00 03 | 03
```

Pattern: 5 sub-records of 3 bytes (likely `[type, hitbox/HP, behavior]`) + terminator. Boss 16's middle byte is **0 in every sub-record** — unlike all 15 other valid bosses.

If middle byte = hitbox-validity flag, this would explain why:
1. Boss 16 spawns and renders normally (other byte fields populate slot)
2. State machine accepts it (FFBF=16 transitions to D880=0x0A)
3. Direct DCBB writes work (damage pipeline is generic)
4. **Projectile collision NEVER fires** (no valid hitbox → no detection → no 0x102F call)

Probe 8 attempted to patch boss 16's middle bytes from 0x00 to 0x04 (mid value). Slot population looked identical — but without input injection to fire real projectiles, we couldn't verify if the fix actually enables collision.

### Comparison Table

| | Bytes |
|---|-------|
| Gargoyle (entry 1) | `03 01 0A 04 02 08 08 03 0A 08 02 0A 03 01 0A 04` |
| Boss 15 (entry 14) | `14 02 03 14 03 01 14 04 02 14 04 01 14 04 02 14` |
| Boss 16 (entry 15) | `04 00 03 03 00 05 01 00 0A 02 00 08 04 00 03 03` |

Zero-byte count: gargoyle 0, boss 15 0, **boss 16: 5 zeros**.

## Cleanly Disproven

| Claim | Status |
|-------|--------|
| D880 cycles through 0x02-0x09 substates | DISPROVEN — only 0x02, 0x0A, 0x17 observed |
| State 0x08 has 3 substate handlers | DISPROVEN — D880=0x08 never reached in normal play |
| FFAC/FFAD = per-level pointer | DISPROVEN — constant $4000 |
| Powerup expiration timer at HRAM 0xFC | DISPROVEN — FFFC unchanged after FFC0 write |
| DDA8 = substate counter | DISPROVEN — stays 0 always |
| Game continuously resets D880 | DISPROVEN — direct writes 0xA1-0xAE persisted 30+ frames |

## Still Unknowable Without Input Injection

- Whether patching boss 16's AI table zero bytes actually enables collision (needs real projectile fire)
- The exact interpretation of AI sub-records (`[type, ?, behavior]` vs other formats)
- Whether stage boss arenas (D880=0x0C..0x14) have visible behavior when entered via game-driven path
- FFAC/FFAD values during real level transitions

## Tooling Inventory

All probes in `scripts/probes/`:
- `runtime_probe.lua` — Round 1: initial state, FFBA cycle, entity slots, shield write, sound, DDA8 watch
- `runtime_probe2.lua` — Round 2: HRAM diff, FFBF=1 force, boss-16 spawn attempt, FFBF=16 direct, full HRAM watch
- `runtime_probe3.lua` — Round 3: D880 micro-trace, boss 16 spawn (wrong addresses), stage boss arena tests, slot decoder
- `runtime_probe4.lua` — Round 4: boss 16 corrected addresses, DDA8 combat watch, D880 reset detector
- `runtime_probe5.lua` — Round 5: gargoyle damage protocol (control)
- `runtime_probe6.lua` — Round 6: boss 16 isolated damage test
- `runtime_probe7.lua` — Round 7: CGB palette RAM trace + AI table comparison
- `runtime_probe8.lua` — Round 8: patched boss 16 AI entry test
