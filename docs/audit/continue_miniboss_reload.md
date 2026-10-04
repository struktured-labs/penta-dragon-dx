# Continue during a miniboss leaves death-fade BG palettes (#28)

Status: production stage `continue-miniboss-reload`, built by
`scripts/diagnostics/build_continue_miniboss_reload_trial.py` on parent
`792319cb`. The release-lock candidate is now
`db09de8d1b4293401f587fcce77689d8c13799eb009f13001487786c3accdcb8`.
Earlier attempts (`93d21c4e`, `5d7a29c3`, the 1f7b8ad6 prototype) are
superseded: each traded attract-demo, Stage-7 or boss-speed timing for the fix.
This stage changes no per-frame cycle count, so every original gate holds
unrelaxed.

## Repro
In the Stage 1 Gargoyle fight (FFBF=01, scene D880=0A), die with one credit and
accept Continue. The game resumes in D880=0A with the miniboss still present.
All 8 BG palettes keep the death/white-fade set (`7FFF7FFF7FFF7F29 ...`) until
the miniboss dies, so the room and HUD render flat pink.

## Root cause
1. The bank13 VBlank commit gate at $7703 consumes the deferred reload request
   DF5D only while D880==02. Continue resumes into 0A, so nothing reloads.
2. Palette-sequencer CRAM bursts take bank13 $7FE0 → bank20 $7A2A → $7320 →
   $7D80 → router $732A. The router waits for a fresh HBlank, then reaches the
   4-write burst at bank13 $71E3 through `PUSH HL / PUSH 71E3 / JP 0061`
   ($0061/$09BE mapper switch). The 4th write ends 54 M-cycles (216 dots)
   after the edge, past the 167-dot minimum mode-0 + mode-2 window, so on
   long mode-3 lines it is dropped (stale BG byte 59 / OBJ byte $CF; the
   `4A29` byte of #28).
3. The death service (bank13 and bank16 $7182-$7188) repeats an unchecked
   direct write of BG byte 39 that can land in mode 3 during the death fade.

## Why timing has to be exact
The attract demo, `boss_speed_parity` and the Stage-7 patrol are frame-timed.
Any change of a few M-cycles per frame moves the demo onto another route
(e.g. widening the $7703 gate saved 9 M/frame and the Gargoyle spawned 125
frames before the demo exit; the router hardening alone lost the loop-2
Gargoyle in `title_visual_receipts`; Angela's speed ratio went to 1.201).
So this stage keeps every path cycle-identical to 792319cb and spends nothing
outside the post-death Continue menu frame.

## Stage
- **Cycle-funded dispatch (bank 20).** The forward chain at $7A2A kept the
  source bank in B and re-saved it through `PUSH BC / LD B,A ... LD A,B /
  POP BC`, then hopped `JP 7320 → JP 7D80 → ... → $7323 (LD D,A, IE save)`.
  Keeping the bank in D (`$7A2B PUSH DE / LD D,A`, `$7A54 LD A,D / POP DE`)
  and jumping straight to a new dispatcher (`$7A59 JP $6320`) saves 13
  M-cycles per burst. The dispatcher spends exactly those 13 M choosing a
  router; each leaf is padded (NOP, `INC BC / DEC BC`) to the parent's cycle
  count with the same carry flag:
  - source page $68xx (bank 13 or 16; the pages are identical): RC68, which
    reads a bank-20 copy of the page at the same address;
  - source page $7Cxx: RC7C, H translated to the bank-20 copy ($6E00 for
    bank 13, $7000 for bank 16) and restored to $7C afterwards;
  - the Stage-7 local path ($7DB1), the original router ($732A) and every
    other source keep the original code (an inline byte copy of the router
    for non-bank-13 sources).
  RC68/RC7C keep the router's VBlank / LCD-off fast paths and HBlank wait
  byte for byte, issue the four writes right after the edge (4th write 16 M
  after the edge, at most 22 M with poll latency = 88 dots), pad, load A=D
  and enter the shared tail at bank20 $71E9 (`CALL 0061` → bank13 $71EC).
  Edge → $71EC is 54 M as in the parent, with the same registers, flags,
  $DC09/$FF99, IE, SP and bank.
- **Death service (banks 13 and 16, $7182).** `LD A,A7 / LDH [68],A /
  DEC HL / LD A,[HL] / LDH [C],A` → `LD A,A8 / LDH [68],A / DEC HL /
  LD A,[HL] / LD A,[HL]`. Same size and cycles, the index still ends at A8,
  and the unchecked byte-39 write is gone (the following mode-safe bursts
  write that byte anyway).
- **Reload request (death-only).** Continue acceptance (OG bank 1 $4AD4,
  `LD A,FF / LD [DCBB],A`, reached only when the player picks Continue)
  becomes `LD A,27 / CALL 0847`. The bank-$27 helper does the original store
  and, when the resume scene has a live miniboss (FFBF≠0), queues the palette
  sequencer's reload job DF4C=$11 (what the $7703 gate's reload path hands
  it; its BG writer folds 0A onto 02). The sequencer does not step during
  scene 17, so the job runs from the first 0A frame after resume, through the
  mode-safe routers. The $7703 gate and the scene hooks are untouched.
- **Lineage:** `release_lock_lineage.py` assigns the new runs to
  `CONTINUE_OWNER`. None of them meets the spans of `menu_commit_protocol`,
  `crystal_transition_contract` or `stage_card_palette_handoff`, which keep
  their original code.

## Verification
- Lockstep against 792319cb, attract demo frames 0-26000 (mGBA r454 latches,
  `emu:currentCycle` every frame): cycle counter, scene, RNG, CRAM (every
  10 frames) and WRAM $C000-$DEFF / HRAM (every 50 frames) identical on every
  frame. The only difference is a dead stack slot at $DFC1-$DFC4 below SP
  (the parent leaves the pushed $71E3, the stage the CALL's $71EC).
- SM83 model of the chain for bank 0D/10/0E sources, both CRAM ports, all
  source pages, FFBA/D880/D889/BGP cases: identical cycles, registers, flags
  and stack at every router entry and after every burst.
- Gate `stage1_miniboss_continue_palette`
  (`verify_stage1_miniboss_continue_palette.py`): two cold-boot cases,
  miniboss death → Continue and a no-boss control. BG CRAM at resume
  +30/+60/+300 must equal the pre-death CRAM and no FF69/FF6B write may land
  in STAT mode 3 from the death through resume+300. Passes on db09de8d,
  fails on 792319cb.
- All original gates (`title_idle_reel`, `title_visual_receipts`,
  `gameplay_movement_stress`, `boss_speed_parity`, Stage-7 patrol) run with
  their original verifiers.
