# Continue during a miniboss leaves death-fade BG palettes (#28)

Status: production stage `continue-miniboss-reload`, built by
`scripts/diagnostics/build_continue_miniboss_reload_trial.py` on parent
`792319cb`. The release-lock candidate is now
`93d21c4e00d2565c9bb9423de77d90f1e7b5b986b5633c53000d6e13c80e62fe`.
The prototype from 1f7b8ad6 (`build_continue_miniboss_reload.py`) is superseded
and has been removed.

## Repro
In the Stage 1 Gargoyle fight (FFBF=01, scene D880=0A), die with one credit and
accept Continue. The game resumes in D880=0A with the miniboss still present.
All 8 BG palettes keep the death/white-fade set (`7FFF7FFF7FFF7F29 ...`) until
the miniboss dies, so the room and HUD render flat pink.

## Root cause
1. The bank13 VBlank commit gate at $7703 requires D880==02 and DF5D==1. Only
   the scene-02 hook at $7D18 raises DF5D. Continue resumes into 0A, so nothing
   ever requests the palette reload.
2. The CRAM writer has a mode-3 race. Its path is bank13 $7FE0 → bank20
   $7A2A/$7320/$7D80 → router $732A. The router waits for HBlank and then
   reaches the 4-byte burst at bank13 $71E3 through `PUSH HL / PUSH 71E3 /
   JP 0061`. That costs about 38 M-cycles before the first `LD [C],A`. On
   sprite-heavy lines, the last write lands in mode 3 and is dropped. This
   produced the stale `pal4 0x29` / `4A29` byte from #28.

## Stage
- **Reload request:** the gate at $7703 accepts `D880 & F7 == 02`. The hooks
  at $7D18 and $7D35 call a bank-0x27 helper at $6C80 through a
  bank-13 cave at $7719. The helper raises DF5D for scene 02, as before, and
  also for scene 0A when the previous scene (DF0D) is 17 (death/continue).
  Everything else is unchanged, so the no-boss Continue and normal stage entry
  take the old path.
- **Palette-write hardening (STAT-mode-checked writes):** $732A becomes
  `JP $71B2`. The new bank20 router at $71B2-$71E2 does the DC09/FF99
  bookkeeping and `PUSH HL` *before* the wait (IE is already 0). It keeps the
  LCD-off and VBlank fast paths. It then waits for mode 3 and then mode 0,
  and switches the bank with a direct `LD [2100],A` as its last
  instruction, so execution falls straight into the unchanged writer at $71E3.
  In the worst case, the fourth CRAM write lands 32 M-cycles (128 dots) after
  the mode-0 edge. That is inside the minimum mode 0 + mode 2 window
  (87 + 80 dots). The palette data, order and frame cadence are the same.
  Only the in-line placement moves earlier.
- **Lineage:** `release_lock_lineage.py` assigns the six changed runs to
  `CONTINUE_OWNER`. `menu_commit_protocol`, `crystal_transition_contract` and
  `stage_card_palette_handoff` still check their original byte contracts. They
  first authenticate this stage with `verify_installed()` and exclude only
  its owned runs, so any other byte change still fails.

## Gate
`stage1_miniboss_continue_palette`
(`verify_stage1_miniboss_continue_palette.py`) runs two cold-boot cases:
miniboss death → Continue, and a no-boss control death → Continue. For both, it
requires BG CRAM at resume +30/+60/+300 frames to equal the pre-death CRAM.
It also requires zero FF69/FF6B writes in STAT mode 3 from the death through
resume+300. It passes on 93d21c4e and fails on 792319cb.
