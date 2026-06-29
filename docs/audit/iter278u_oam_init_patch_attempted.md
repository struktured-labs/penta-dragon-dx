# iter 278u — Sara spawn-OAM init patch (attempted, reverted)

## Summary

Multi-agent workflow (ultracode, 2026-06-28) proposed a single-byte ROM
patch at offset 0x29A0 (`0x40 → 0x42`) to set Sara spawn-time OAM attr
to pal-2 directly, theoretically eliminating the iter 244 240-frame
startup orange-Sara transient.

## Investigation result

The workflow's byte structure analysis was incorrect. Disassembly at
bank0:0x2990 shows:
```
2990: LD HL, 0xDC85          ; sprite descriptor table base
2993: LD A, [HL]; AND A; RET NZ  ; gate (skip if already initialized)
2996: LDH A, [FFBF]           ; load Y (player Y pos)
2998: LD [HL+], A             ; descriptor[0] = Y
2999: LD A, 0x01; LD [HL+], A ; descriptor[1] = X (=1)
299C: LD A, 0x40; LD [HL+], A ; descriptor[2] = tile (=0x40)
299F: LD A, 0x08; LD [HL+], A ; descriptor[3] = attr (=0x08, VRAM-bank-1+pal-0)
```

Tested patch 0x29A0 (the `0x08` value) → `0x0A` to add pal-2 bit:

**Result**: visible color UNCHANGED. Slot 0/2 attrs differ slightly
(0x12/0x32 vs baseline 0x02/0x22) but colorizer's `AND F8; OR pal` 
sequence yields identical pal-2 output. Patch is INERT for the user-
perceptible orange-Sara fix.

## Why this doesn't solve the bug

The orange-Sara transient is caused by hwoam_recolor's HW OAM tile read
returning 0xFF during LCD mode 2/3 (mode lock). The dispatch then
routes to pal-4 (hornet orange). My patch changes the SPAWN value of
the OAM attr in shadow OAM (via DC85+ descriptor table), but:

1. Shadow OAM is overwritten by game's main loop each frame
2. The race is in hwoam_recolor's STAMPING of HW OAM, not in shadow OAM
3. Patching descriptor attr has no effect on the timing-sensitive race

## NOFLICKER.gb still exists as user play-build

`rom/working/penta_dragon_dx_NOFLICKER.gb` is iter 278s (hoist
hwoam_recolor to first in wrapper). Visually eliminates orange-Sara
(Sara PINK at f=60) but breaks 16 regression tests due to stale tile
reads in enemy slot 4-39 palette dispatch. Not ship-clean but suitable
for human play testing.

## Build state

Reverted to iter 278p baseline (commit `2d94d67`):
- iter 278p: stage intro letter brightening (component 4 SHIPPED)
- iter 278l: cursor visible as 'A' character (component 3 SHIPPED)
- iter 278e: 75% Sara race reduction (components 1+2 partial)

## /goal status — 12 distinct attempts

iter 277/278d/g/h/n/o/q/r/s/s2/t/u all reverted with documented blockers.

The 99% reduction the user requested is architecturally bounded by:
- iter 8's 30T parallax break threshold (STAT IRQ + wrapper paths)
- iter 244's main-loop OAM race (shadow OAM overwritten per frame)
- mGBA setBreakpoint instability for multi-hook (iter 278q crash)
- colorizer FROZEN byte budget (28-byte cascade is GB-ISA-optimal per
  Investigation 3 of 2026-06-28 workflow)

User decision required for next steps. See `project_iter278_sara_99pct_quest.md`
memory for full trade-off list and ranked alternatives.
