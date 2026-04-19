# Gap #7: Mini-boss #16 (DC04=0x7B) Unkillable — UPDATED

## Verified Facts (re-confirmed)

### Boss-detect formula at 0x0C07 (full disassembly)

```z80
0C07: FA 04 DC      LD A,(DC04)
0C0A: C6 40         ADD A,$40
0C0C: D6 70         SUB $70           ; A = DC04 - 0x30, carry if DC04 < 0x30
0C0E: 38 10         JR C, +0x10       → 0x0C20 (rejection)
0C10: 06 00         LD B,$00
0C12: 04            INC B             ; loop: count divisions
0C13: D6 05         SUB $05
0C15: 30 FB         JR NC, -5         → 0x0C12
0C17: 78            LD A,B
0C18: E0 BF         LDH ($FFBF),A     ; FFBF = boss_index
0C1A: AF            XOR A
0C1B: EA 1E DC      LD ($DC1E),A      ; DC1E = 0
0C1E: 18 03         JR +3             → 0x0C23
0C20: AF            XOR A
0C21: E0 BF         LDH ($FFBF),A     ; rejection: FFBF = 0
0C23: EF            RST $28
```

For DC04=0x7B: A=0x4B (75); divide-by-5 loop yields B=16; **FFBF=16=0x10** confirmed.

### DCBB Write Sites (9 sites — courtesy of damage-path agent, retained as inventory)

| # | File offset | Purpose |
|---|-------------|---------|
| 1 | 0x00102F | Main damage SUB B (combat hit) |
| 2 | 0x001049 | Reset to 0xFF when boss dead |
| 3 | 0x004101 | Boss HP init (DCBB=0xFF at game start) |
| 4 | 0x004204 | Time-based DEC (corridor death timer) |
| 5 | 0x004AD6 | Phase HP refill at transitions |
| 6 | 0x0077C0 | Phase 1 init |
| 7 | 0x0077D1 | Phase 2 trigger (< 0x80) |
| 8 | 0x0077E2 | Phase 3 trigger (< 0xC0) |
| 9 | 0x007B01 | Boss defeat sequence |

### 0x4F63 is NOT the damage path

Disassembly proven earlier:
```z80
4F63: F0 BF       LDH A,($FFBF)
4F65: A7          AND A
4F66: 20 0E       JR NZ, +0x0E      → 0x4F76
4F68: F0 B7       LDH A,($FFB7)
4F6A: EA 80 D8    LD ($D880),A      ; FFBF==0: D880 = FFB7
4F6D: C9          RET
4F76: F5 3E 0A EA 80 D8 F1 C9   ; FFBF≠0: D880 = $0A (mini-boss state)
```

This is a state-decision, not a damage handler.

## Most Likely Root Cause

**Boss 16 (FFBF=16) is out-of-range for downstream lookup tables.** The damage path at 0x102F (SUB B → DCBB) does not validate FFBF, but the **collision detection** that calls into it requires:
- Entity sprite slots DC85+ to be populated with hitbox data
- Boss-specific entity AI to spawn the projectile-blocking sprites
- Boss-specific tile graphics in OAM range

The boss-spawn code likely uses a per-boss table indexed by FFBF (1-15). For FFBF=16:
- Entity slots are not populated
- No sprite hitbox exists in OAM
- Player projectiles never collide with anything → 0x102F never invoked → DCBB unchanged

The FFBF=0 force-kill path bypasses combat entirely (probably triggers state 0x0B/lock cleanup → next section).

## What's Still Unproven

- Exact location of the per-boss spawn table indexed by FFBF
- Whether the table size is 15 entries or 16 entries with a sentinel
- The disassembly of 0x102F (the actual SUB B damage write) — agent located it but didn't show source caller chain

## Suggested Patch

Two options:

1. **Clamp FFBF after computation**: insert a `CP $10 / JR C, +1 / DEC A` after 0x0C18 to force FFBF=15 for the OOB case. This is the simplest one-byte test.

2. **Skip boss 16 entirely**: at 0x0C0E, change `JR C, +0x10` to a wider rejection that also rejects FFBF > 15 — needs `CP $10` insertion which requires more bytes.

## Open Question

Does spawn-id 0x7B correspond to a real intended entity (e.g., a debug/test sprite) or pure garbage? Patching DC04=0x7B in the spawn table at runtime is what we did to discover this — the original game NEVER spawns DC04=0x7B in shipped content. **This is likely a developer placeholder, not a missing feature.**

## Cross-References

- Full damage-path inventory: `gap_miniboss_damage_path.md` (9 DCBB writers, but agent's "boss 16 maps to FFBF=15" claim is INCORRECT — verified actual mapping is FFBF=16)
- Boss-detect formula: this file, section above
