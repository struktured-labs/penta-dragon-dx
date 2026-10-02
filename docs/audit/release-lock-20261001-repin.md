# Release-lock chain re-pin evidence (2026-10-01)

The release-lock stream chain (`build_stream_regression_candidate.py --release-lock`,
suite `--stream-source`) defers two issues from the 126dd0b7 stream chain:

- **#34 select buffer** (stage `select-buffer`, 7c5afca5) is dropped. Its 235 changed bytes break
  game start after attract, the title showcase, pre-final, ending, final cutscene and opening
  timing on 126dd. No later stage touches those bytes.
- **#14 doorway priority helper** (the `ceiling` part of `presentation-composition`) is omitted
  via `compose_stream_presentation_trial.build(..., defer_ceiling=True)`. Its 251 changed
  bytes are the only difference between the original e8002aea stage and the new 51c832a1 stage.
  The combined helper's CPU cost desynced the attract demo, and the scratch-B variant moved the
  cold doorway route by 4 px in Y (1240,1352 instead of the reviewed 1240,1356), so #14 is deferred.

Method: each downstream builder was run natively on its new parent (an explicit
`REPINNED_PARENT` is now accepted beside the original `PARENT`). For each stage the change set
`{offset: (preimage, value)}` (header checksum excluded) on the new parent was compared with the
change set the same builder produced on its original parent. Every stage matches exactly:
same offsets, same preimages, same written values. A transplant cross-check (126dd0b7 with the
#34 and #14 bytes reverted to their preimages, checksum recomputed) gives the same bytes
as the native build: **6ec44fe6b77dd59088c06a07e0631187737e8471365a68806c0d5aa407563b97**.

| stage | original parent → child | re-pinned parent → child | changed bytes | identical change set |
|---|---|---|---|---|
| menu-quartet | 00f26298 → 04764550 | 88648550 → 60cc449c | 363 | yes |
| presentation-composition | eebf3f19 → e8002aea | eebf3f19 → 51c832a1 | n/a | differs from e8002aea only at the 251 #14 offsets, which revert to source07 |
| palette-window | e8002aea → b09ec41a | 51c832a1 → a4fc3949 | 35 | yes |
| select-buffer | removed (issue34 deferred) | | | |
| handheld-palette | 7c5afca5 → 106c2e01 | a4fc3949 → 40381cbf | 129 | yes |
| title-local-guard | 106c2e01 → 8ff1c98d | 40381cbf → 5f481bb0 | 104 | yes |
| ted-menu-reinstall | 8ff1c98d → 4731248a | 5f481bb0 → 50d64560 | 27 | yes |
| five-point-star | 4731248a → d744124d | 50d64560 → 9ca97f86 | 18 | yes |
| arena-sound-alias | d744124d → 4eff32d4 | 9ca97f86 → 35b71de0 | 45 | yes |
| arena-graphics-owner | 4eff32d4 → 35a8d40b | 35b71de0 → 64732610 | 12 | yes |
| arena-alias-fastpath | 35a8d40b → 585f5830 | 64732610 → 1b3bbf84 | 141 | yes |
| arena-completion-safe | 585f5830 → d901357a | 1b3bbf84 → d90f5fc7 | 87 | yes |
| secret-sound-alias-fast | d901357a → 665a33b6 | d90f5fc7 → e4809147 | 17 | yes |
| secret-alias-chunks | 665a33b6 → 2b797a6a | e4809147 → f23d6d09 | 8157 | yes |
| return-initial-map | 2b797a6a → 916ebb18 | f23d6d09 → 4d8f3fad | 23 | yes |
| return-cgb-fade | 916ebb18 → f938ae85 | 4d8f3fad → 2992a8a2 | 1713 | yes |
| return-card-deadline | f938ae85 → 8ac7fbe3 | 2992a8a2 → 3540f75e | 108 | yes |
| return-card-compact | 8ac7fbe3 → 126dd0b7 | 3540f75e → 6ec44fe6 | 932 | yes |

The menu-quartet sub-stage of the composition (#21) also needs a re-pin, because its
parent changes from ceiling+secret 00f26298 to secret-only 88648550; the secret (#23)
change set itself is identical on both parents (7657 bytes).

Construction evidence only; not hardware or audience approval. Full hashes are in each builder's
`REPINNED_PARENT` and in `PINS[True]` in `scripts/build_stream_regression_candidate.py`.

## Title footer (`DX V3901`) and the `title-glyph-window` stage

After a Game Over restart the title footer read `DX V3901`: tile $72 (the period) kept the
`9` glyph. The v3.01 title-glyph GDMA helper (bank13 $6DA7) runs late in the VBlank wrapper.
On the returned title it fires at LY0/mode 3 every frame, so the GDMA is dropped. Cold boot only
worked because its timing happened to be different. #34's extra work shifted that timing, which
hid the bug; it was never a fix. The new final stage `build_title_glyph_window_trial.py`
(`title-glyph-window`, bank13 $6DAD/$6DBD) waits for STAT mode 0/1, and only on frames that
copy. Candidate **792319cbe9db7d56ae6497018b727c8a0a8737c3c8c7a4a122713054677022db**. The
footer reads `DX V3.01`, pixel-identical to c693, after cold boot and after all three
`gameover_restart` variants (fresh, spike, saved-game).

## Lineage evidence for re-qualified checks

The last passing suite receipt (2026-09-16) covers only c693 (512 KiB,
`restart-original-source-v1`). None of the 1 MiB chain after 4f5a67b8 (including 126dd0b7) ever
passed the suite. Many checks pin whole-ROM identities from the 4f5a lineage. Instead of adding
the new hash blindly, `scripts/diagnostics/release_lock_lineage.py` records the exact delta
between the candidate and its 4f5a67b8 ancestor in the first 512 KiB: 61 runs covering all
6314 differing bytes. Each run has its owning stage (`RUN_OWNERS`), and the module carries the
compressed 4f5a preimage. Helpers:

- `sara_ancestor(rom, *ranges)` rebuilds 4f5a. It fails closed on the ancestor hash and on any
  requested range that meets the delta.
- `ancestor_bytes(rom, start, end, owners)` and `overlay(...)` allow only runs written by the
  named owners inside a range.

Verifiers use these helpers to apply their historical contract to bytes the candidate provably
shares with 4f5a. Each owner's change is then qualified separately, by a live gate or by an
explicit relocated contract.

Re-qualified checks and rationale:

- **Stage-card handoff** (`stage_card_palette_handoff.py`): #27 `arena-completion-safe`
  relocates the WRAM runtime. The post-copy guard moves $DBF1→$DBF3 (bank13 $5830 gains a
  RET/NOP prefix, and JR Z/JP becomes the equivalent JP Z $10E2). The dirty bridge moves
  $DBDF→$DBDC (still `JP $3497`). All other handoff bytes are outside the delta, and the
  4f5a ancestor is the reviewed identity. The live stage-card gate passes.
- **Low-health gates**: the candidate joins the r456c observer profile; every profile function
  still re-checks its exact ABI bytes. `verify_release_candidate` now gives the candidate the
  same candidate-owned hazard-state scene-$0B profile that c693 used on 2026-09-16. The legacy
  `save_states_for_claude` normalization falls back to the title on c693 as well, so that path
  is not candidate evidence.
- **Captured-menu operator fixture**: the r534 capture freezes the CPU in the bank-20 menu row
  routine (PC $406B). The menu-quartet stage (`build_menu_quartet_trial`) replaces that
  routine's $404A prologue and re-enters native code at $406F. Resuming the old frame on any
  build from `presentation-composition` onward unbalances SP (it reaches $E1C3), and the
  corrupt stack writes FFB7=$0C, which jumps to the Shalamar arena. Stages 00–06 pass and
  07–23 fail. For the candidate only, the verifier first runs the same no-input frames on the
  authenticated 4f5a ancestor until PC and every stacked return lie outside the delta and
  outside bank-20 [$4040,$406F) (one frame). It then refreshes the six relocated WRAM installer
  images, after proving that the capture holds the ancestor bytes there. The close/stationary
  contract, including the pixel oracle, runs entirely on the candidate and passes.
- **Hazard and tilemap checks**: `menu_commit_protocol`, `verify_stage1_spike_palettes`,
  `verify_stage1_tilemap_copy`, `verify_boss_atomic_attr_contract`, `arena_bank20_r455` and
  `expansion_bank_ownership_r456` apply ancestor contracts through the lineage helpers.
  `boss_dispatch_execution` loads the relocated DBA4 runtime.
- **Pins**: the #22 five-point-star LUT (66b0876c, tiles 82/83/92/93 → palette 5) is accepted
  wherever the reviewed canonical/tooth LUTs were. The 1 MiB size and header $05 are accepted
  for the candidate only. `verify_suite_receipt` expects 1 MiB for
  `stream-release-lock-original-source-v1`.

## Known limitation: #22 semantic LUT copies

#22 updates the gameplay and menu LUT but not the bank-20 semantic LUT copies at $50482/$50682.
A star tile inside a hazard semantic span can therefore stay neutral. This is a gap in #22, not
a regression against c693.

## Attract demo route (frame-flicker / attract reel)

The attract replay is cycle-sensitive. Spending any CPU in #23's secret copier changes the
demo's input alignment: the copier alone (s07k), and an equal-cost no-op (s07j), each lose the
Gargoyle segment. The OG reel is 2251 frames. The checks now accept a Stage-1-only demo route
with these requirements:

- combined duration within 15% of 2251 frames;
- Sara's OAM palettes LUT-exact against `build_obj_pal_table` (≥200 samples);
- a direct return to the title menu;
- the Gargoyle checks (≥20 samples) still apply whenever scene $0A is reached.

The broken 08/09 stages still fail this check.

## Stage-7 movement gate: equal-start, combined seeds, 0.97 floor (owner decision)

`gameplay_movement_stress` (`verify_stage7_state_patrol.py`, receipt schema v3) used to compare
one native boot of each ROM. Each build's boot/title timing leaves a different Stage-7 world at
the start of play: RNG cursor FFD1, frame counters FFD4/FFD5 and the DC5x–DCBx entity tables.
So the old gate mostly measured layout luck. 792319cb failed it at 0.9736. Its gameplay code is
byte- and cycle-identical to 6ec44, which passed at 0.994. The only difference is that the
fixed title glyph copy now succeeds instead of retrying, which shifts title timing.

**Method.**
- The gate first boots both ROMs natively. It keeps the native metric as a diagnostic and
  captures the stock ROM's start-of-play world image: D800–D8FF, DC00–DCFF, FFCB and FFD4–FFD5.
- It then replays both ROMs nine times from that identical image. At the first play-phase input
  join it injects the image and sets the RNG cursor FFD1 to each seed in
  {0, 10, 20, 30, 50, 60, 70, 80, 90}. Seed 40 is excluded because stock alone does not settle
  in time on it.
- Every trace dumps its post-injection image. The verifier requires the image to be
  byte-identical across all four traces, and requires A/B replay determinism, for every seed.
- A seed is usable when its traces keep the exact endpoint route and settle by half-cycle 24.
- **Pass condition:** the stock/DX ratio of frames summed over every common uncontested leg of
  every usable seed is in [0.97, 1.02], with at least 7 usable seeds and 120 measured legs.
- The 0.97 floor is an explicit owner-approved Stage-7 floor; the other stages keep their
  floors. Synthetic policy controls cover parity, the floor edge, below-floor, clean slowdown and
  too-few-seeds.

**Noise.** Equal starts do not make per-seed ratios repeatable. Some state is advanced per
frame (FFD4, VBlank-driven logic) while the game advances per loop, and the injection point
lands at different sub-frame phases (LY 15 vs 94 in one pair). Once DX spends more of each frame
in VBlank, enemy motion and contacts diverge. Byte-identical gameplay code (6ec44 vs 792319cb)
measured 0.940 vs 0.991 on seed 10, and about 1% apart combined. Single seeds swing by a few
percent; the combined ratio is the meaningful number.

Measurements (combined ratio; per-seed ratios in seed order, * = fewer than 20 legs):

| Build | Combined | Per seed |
|---|---|---|
| 792319cb (candidate) | 0.9817, 9/9 usable, 220 legs | 1.000, 0.991, 0.957*, 0.949*, 0.993, 0.985, 0.990, 0.977, 0.921* |
| 6ec44 (identical gameplay code) | 0.9722, 231 legs | 0.955*, 0.940, 0.915*, 0.972, 0.991, 0.986, 0.973, 0.978, 0.974 |
| c693 (main) | 0.9677, 8/9 usable (seed 10: settle 28 > 24), 197 legs | 0.992, n/a, 0.924, 0.994, 0.993, 0.952*, 0.991, 0.937, 0.944 |

c693 would sit just below the new floor. The old single-native-layout passes of c693 and 6ec44
were layout luck.

**Per-frame cost** (seed 80, measured legs, `emu:currentCycle`):
- The VBlank handler ($06D1 to RETI $081D) costs stock 2684 cycle units per frame (about 3
  scanlines). DX costs 5967 on average (about 7 scanlines; median 5664, p90 7608), out of 140448
  units per frame. The extra is DX's bank-13 VBlank work reached through the $0824 trampoline.
- With equal loop counts (561), the main loop gets 95.75% of each frame on DX versus 98.09% on
  stock. That predicts a 0.976 throughput ratio; measured was 0.9766.
- More loops take 4 frames instead of 3 (stock 320/241, DX 278/279; c693 193/366, because it
  also has extra main-loop cost).
- Follow-up: the per-frame VBlank cost issue (see PR).

**Validation.**
- **Candidate:** 792319cb PASSES at combined 0.9817 (9/9 seeds usable, 220 legs).
- **Slowed variants** fail on the combined floor. Each is 792319cb with a busy loop that runs
  right after the bank-13 VBlank work (CALL $73FC, then a DEC B / JR NZ loop, placed in the
  free 11-byte tail of the title-glyph helper slot at bank13 $6DF5):
  - slow45 (about 190 extra M-cycles per frame, f75ca730…): FAIL, 0.9558 (9 seeds, 256 legs).
  - slow90 (about 370 extra M-cycles per frame, 459e649c…): FAIL, 0.9553 (8 seeds, 213 legs).
- **Delay placed before the VBlank work instead:** the game stalls (route coverage 0) and the
  gate fails on its nested matrix checks. DX's VBlank work has a timing deadline.

**Probe fixes.**
- The native $0ABB frame-parity wait can re-enter the input join within one main-loop
  iteration. The duplicate is now compared against the first hit's stacked input rather than the
  next loop's planned input; the verifier already merges same-loop duplicates.
- The equal-start mode is enabled only through `STAGE7_WORLD_IMAGE` and `STAGE7_WORLD_SEED`.

## stage1_current_hazard_menu replay race (harness fix)

The two replays sometimes differed by one frame (menu acknowledged at 187 vs 186). mgba-qt
applies the `-t` savestate preload before the probe's first frame callback, but 0–4 frames can
run in between (observed: replay-2 frame 5 == replay-1 frame 1). The probe counted frames from
that callback, so the timeline started at a variable game frame.

`probe_stage1_spike_palettes.lua` now reloads the exact state on its first callback and seeds
the fixture map owner there, so frame 1 is a fixed point. On 792319cb the gate passed twice with
field-identical replays (menu open 186/186). This probe serves every `live_receipt` check.
