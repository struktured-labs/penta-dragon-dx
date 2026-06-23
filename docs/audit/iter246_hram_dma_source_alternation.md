# iter 246 — HRAM DMA source alternates 0xC0/0xC1 — block A is racing

## HRAM DMA routine decoded

Dumped 0xFF80-0xFF90 via mGBA Lua probe at runtime:
```
F0 CB        LDH A, [FFCB]
3C           INC A
E6 01        AND 0x01
E0 CB        LDH [FFCB], A
C6 C0        ADD A, 0xC0       ; A = 0xC0 + (FFCB+1)%2 = 0xC0 or 0xC1
E0 46        LDH [FF46], A     ; trigger OAM DMA
3E 28        LD A, 0x28        ; 40 cycle wait
3D           DEC A
20 FD        JR NZ, -3
C9           RET
```

So the HRAM routine alternates DMA source between 0xC000 (block A) and
0xC100 (block B) each call. It uses FFCB as a 1-bit toggle.

## Combined handler structure (decoded)

`scripts/diagnostics/probe_hram_dma_routine.lua` + ROM byte dump at
bank13:0x6E00:
```
LDH A, [FF4F]; PUSH AF; LD A, 0; LDH [FF4F], A  ; save VBK, set VBK=0
LD A, [DF02]; CP 0x5A; JR Z, +0x1A             ; cold-boot sentinel check
[26 bytes cold-boot init copy WRAM 0xDA00 from ROM 0x7000]
CALL 0x6C90                                     ; cond_pal-like routine
LD A, [DF08]; CP 0x5A; JR NZ, +0x33            ; another sentinel
[BG colorizer trampoline path]
LD A, 0x5A; LD [DF08], A
LD A, 0x20; LD [DF07], A
LDH A, [FFC1]; OR A; JR Z, +9                  ; FFC1 gate
CALL 0x6CD0                                    ; bg_colorizer
CALL 0x69D0                                    ; shadow_main
CALL 0xFF80                                    ; DMA (alternates 0xC0/0xC1)
POP AF; LDH [FF4F], A; RET
```

`scripts/diagnostics/probe_ffc1_per_frame.lua` confirms FFC1=0x01
throughout the lag window — gate passes, DMA fires.

## Per-frame FFCB + HW OAM correlation

`scripts/diagnostics/probe_ffcb_per_frame.lua` samples FFCB + HW slot
0/2 at every frame from f=1 onward:
| frame | FFCB | DMA source | HW slot 0 | HW slot 2 |
|---|---|---|---|---|
| f1 | 01 | block B | 04 (savestate) | 00 (savestate) |
| f2-f5 | 00/01 | A/B | 00 | 00 |
| f6-f10 | mixed | A/B | 04 | 24 |
| f11 | 01 | block B | **02** | 22 |
| f12 | 00 | block A | 04 | 24 |
| f13 | 01 | block B | **02** | 22 |
| f14+ | ... | ... | 04 (mostly) | 24/22 alternating |

**Pattern discovered**: HW OAM at f11/f13 has pal 2 — those are frames
where FFCB=01 (DMA from block B). At f12 (FFCB=00, DMA from block A),
HW OAM = pal 4. **Block A and block B have DIFFERENT effective values
at DMA-read time, even though iter 245's probe showed both have pal 2
at frame-callback time.**

## Conclusion: block A is being RACED

shadow_main writes pal 2 to BOTH blocks each frame (verified via the
`CALL 0x6A10` twice in 0x69D0's bytes). But between shadow_main's
write to block A and the DMA reading from block A, SOMETHING writes
pal 4 to block A. Block B is NOT raced.

Candidates for the writer:
- Game's main-loop OAM rebuild (memory says "the game's main-loop OAM
  rebuild leaves DISPLAYED HW OAM uncolored" — this matches)
- STAT IRQ during HBlank (but stub at 0xDB50 only touches slot 1)
- Some other interrupt-driven OAM write

Since the combined handler is sequential WITHIN a VBlank (no IRQ
during it under IME=0), the race must be in PRIOR-FRAME write order.
The sequence per frame:
1. VBlank N IRQ fires (IME=0)
2. shadow_main writes pal 2 to A and B
3. DMA from A or B → HW OAM
4. VBlank handler RETs (IME restored to 1)
5. Main loop runs until next VBlank
6. Main loop writes pal 4 to block A (suspect: game's OAM rebuild)
7. VBlank N+1 fires
8. shadow_main writes pal 2 to A and B (overwriting main loop's pal 4)
9. DMA from A or B...

So at step 8, shadow_main DOES overwrite to pal 2. So why does the
DMA at step 9 read pal 4 from A?

UNLESS step 8's writes are partially overwritten by something between
shadow_main and DMA. Or shadow_main isn't reaching block A's slot 0
in some frames (e.g., loop terminates early on a condition).

## Quick-test fix candidate: force DMA to always use block B

The HRAM routine at 0xFF87 has `C6 C0` (ADD A, 0xC0). If we patch to
`C6 C1` (ADD A, 0xC1), DMA always reads from block B. Since block B
seems unraced, this might eliminate the lag.

Risk: block A might be used for sprite-specific updates that block B
doesn't have. Won't know without testing.

Recommended next iter: build `tmp/teleport_block_b_only.gb` with this
2-byte patch and run the probe. If HW OAM stays pal 2 from frame 11
onward, the fix path is confirmed.

NO ROM change this iter — pure RE.
