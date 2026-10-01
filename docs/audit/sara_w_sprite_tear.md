# Sara Witch partial-pose tear — issue #6

Tracking: https://github.com/struktured-labs/penta-dragon-dx/issues/6

Current status: the same 60-byte atomic emitter is now what
`scripts/build_v302_title_fix.py` installs, and the working ROM
`rom/working/penta_dragon_dx_FIXED.gb` carries it.
SHA-256 `4079c238c84888a448f9bb60a0a4e8c7547142084b725b59ab75795d17efbf1b`,
MD5 `c3d865ed2a20f358ff63278634ae437a`. Against the previous working ROM
(`8676468e66e417a6…`) the only changes are the bank-13 and bank-16 emitter
images plus the global checksum. Slots 0–2 leave interrupts disabled; slot 3
enables them after the quartet. `$1188` is not modified.

On this ROM, both ordinary-input pose gates pass: 2,400 walking frames
(2,388 witch-walking observations, 12 startup-absent, 438,483 opaque pixels)
and 2,400 rapid-turn-plus-fire frames (2,391 walking, 9 absent, 438,198
opaque pixels), zero mixed poses. `gameplay_speed_parity` and `phantom_sound`
also pass. The full 92-gate matrix does **not** pass. Rechecked
`gameover_restart` and `gameover_spike_restart` fail the same way on the
unpatched ROM, and the other failures are this branch's existing palette and
layout contracts, not the emitter delta. Not deployed and not hardware-tested.
#6 stays open. Ceiling #14 is separate and unresolved.

The historical trial below remains the fully matrix-clean ROM. It is a
different parent (`4f5a67b8…` on `c693eafb…`), not this working candidate.

The original-source rebuild is `tmp/sara-atomic-pose-source-16/candidate.gb`,
SHA-256 `4f5a67b8a9afb178ac0760daa2357de74fd7eb7f3de4de010385c50ea4cb08f5`.
Its source fingerprint is
`35de183f104f0aed85965611481d399ef1ed8c42daa50d2393e15a9f2bf3e02e`.
The complete campaign preserved ROM, source and runtime identities. Both
2,400-frame Sara routes, all three Game Over/restart routes, all-six-stage
strict speed targets, no-color-bleed traversal, nine-boss checks, title/demo,
story/ending, native sound-command checks and build roundtrips pass.

Campaign 06's 89-pass/two-failure/one-blocked result remains immutable history
below. Its checker issues [#15](https://github.com/struktured-labs/penta-dragon-dx/issues/15)
and [#16](https://github.com/struktured-labs/penta-dragon-dx/issues/16) now pass
focused negative controls and the fresh full campaign. The ROM did not change
while correcting those two checkers. Native PCM has a separate, explicitly
limited dropout/clipping/level guard; no perceptual-equivalence claim is made.

## Reproduction and cause

On 2026-09-19, cold boot followed by ordinary right/up/left/down inputs,
changing direction every 45 display frames, reproduces the reported tiny
missing sprite pieces. No HP, position, animation, OAM or VRAM writes are
used to reach this failure.

Parent: `c693eafb50e7872fa884d0d26ce3fbfd4f2fac0dba246ff738931643e7f0ba5d`.
Sample 139 / emulator frame 661 publishes tiles `2D,2C,2F,2A` instead of
`2D,2C,2F,2E`. The stale bottom-right quadrant has 11 transparent pixels
where the completed pose is opaque. All captured opaque pixels match the
hardware OAM/ROM-art model: the renderer is displaying the incomplete pose
it was given, not randomly losing CHR pixels.

The CPU trace catches VBlank at `$DA52`, after the third central-emitter
return has enabled interrupts. C100 contains the mixed pose; C000 already
contains the complete new pose. `$FF80` then selects C100 and copies it into
hardware OAM. Two initial 720-frame replays match byte-for-byte, including
all PNGs. A stock-ROM control also exhibits mixed pose generations; this
is not established as a DX-only defect.

## Experimental fix

Current trial 04: `4f5a67b8a9afb178ac0760daa2357de74fd7eb7f3de4de010385c50ea4cb08f5`.
`scripts/diagnostics/build_sara_atomic_pose.py` changes only the two 60-byte
central-emitter installer images (banks 13 and 16) and the global checksum.

The existing `$10D1` DI wrapper remains. Slots 0–2 defer EI; slot 3 restores
it after the complete quartet. Other slots retain per-entry EI. The native
`$10B1` emitter always emits all four entries; `$0BB4/$0BBC` use it for Sara
in C000 and C100. No new RAM, graphics, input logic or ceiling-priority
behavior is introduced. The original priority-helper CALL is retained.
Equivalent palette calculation and register scheduling reclaim the required
space without enlarging the installed WRAM helper. SRAM is disabled before
the EI decision; the native ADD then restores the original return flags and
A=C contract. The two Sara call sites run with bank 1 mapped (measured).

## Current evidence and limitations

- New `verify_sara_pose.py` rejects the exact parent at sample 139.
- Trial 04 passes 2,400 consecutive direction-change captures and another
  2,400 with rapid turns plus firing: 4,790 walking observations, ten explicitly
  reported startup-absent frames, zero mixed poses or opaque pixel mismatches.
  The raw frame-139 image was inspected at native resolution.
- Trial 04 completes the full cold-title/demo-miniboss/returned-title test:
  244 miniboss samples, no palette mismatches, all four title captures present.
- Trial 04 parent-relative strict ±1% timing checks pass in Stages 1, 5, 7:
  283/282 (+0.35%), 332/329 (+0.91%), 362/362 (unchanged), with matching
  measured route distance. The fresh 2,800-frame original-ROM comparison also
  passes all six stages' strict ±2% targets with matching route distances:
  664/667, 739/754, 698/699, 759/764, 785/790, 757/756. None needs the
  harness's accepted-slowdown exception. Fresh campaign 16 repeats these strict
  passes; hardware release qualification remains pending.
- Fifteen targeted unit tests pass, including landed tail-byte execution,
  missing-pixel and mixed-pose negative controls, exact reversible parent
  authentication, and inherited map/menu/handoff contract checks.
- The complete 1,210-test unit suite passes (`tmp/sara-atomic-unit-06.log`,
  369.787 seconds). Both ordinary-input Sara gates are included in the release
  matrix and the standard pre-stream profile. A prior unit run found that
  profile omission; it was fixed before the fresh campaign.
- Original-source rebuild `tmp/sara-atomic-pose-source-06/candidate.gb` matches
  trial 04 exactly. Its source fingerprint is
  `e2023acea120b2017d07d58013ef6329b1d692bf6b3b84846276c4168517fcf9`.
- `tmp/sara-atomic-release-matrix-04` was intentionally interrupted after
  twenty completed passes (and a passing speed child) to fix the pre-stream
  profile omission. It is not a completed matrix and is not resumed after
  that source change. Campaign 05 found a missing exact-successor recognition
  branch in `semantic_expansion_is_exact`; the fully authenticated parent
  passed the unchanged static contract and both live raster/write checks were
  clean. After the checker correction and a corrupted-hazard negative control,
  `tmp/sara-hazard-contract-focused-06` passed the hazard replay and all four
  mutation controls. Campaign 05 was stopped at child completion, not promoted.
- The earlier complete campaign `tmp/sara-atomic-release-matrix-06`
  passes both Sara routes, all three Game Over/restart routes, low-health and
  scrolling tests, six-stage speed, nine-boss geometry, boss speed/trajectories,
  and Ted checks. Source fingerprints remain identical before/after. Its
  failures are retained below; it is not a full pass.
- The local `tmp/sara-pose-evidence-05/index.html` side-by-side page was
  rendered and visually checked. It uses untouched parent/candidate native
  frames, labels focused scope and pending hardware/full qualification, and
  explicitly does not claim whole-frame equality.

### Campaign 06 qualification failures (resolved in campaign 16)

1. Penta silhouette gallery (#15): every sampled phase has a detached
   component, so the old requirement for one wholly connected frame fails.
   At frame 120, both reported 56-pixel components match hardware OAM tile
   `$4F` exactly at slots 4 and 8: origins `(76,1)` and `(104,11)`. Captured
   projectile CHR equals the fresh stock and qualified-parent CHR. This
   verifies a native-projectile classification error at that frame, but the
   earlier three phases need their own OAM/CHR evidence before qualification.
   Do not relax fragment limits. The dependent side-by-side gate is blocked.
   **Focused follow-up:** `tmp/sara-projectile-phases-08/receipt.json` now
   supplies per-phase OAM, CHR, LCDC and OBJ palettes. All seven suspect
   components across candidate phases 30/60/90/120 match native `$4F`
   projectiles exactly, including RGB pixels. The corrected checker labels
   those components separately while retaining raw counts and original images;
   the fragment limits are unchanged. Stock, parent and candidate two-boss
   corpora pass. All 24 sampled full PNGs match the earlier same-ROM/core
   captures byte-for-byte; this is sampled raster equality, not complete
   observer neutrality or acoustic equivalence. DMG receives no projectile
   exemptions and still passes its original bounds. Thirteen new unit tests
   and actual-capture corrupted-pixel/missing-evidence negative controls pass.
   A first direct-palette-access attempt timed out because that domain was
   unavailable; run 07 remains failed. Its child was cleaned up and the process
   check was clear before retrying with the existing selector-read fallback.
   Full qualification and the dependent comparison remain pending; run 06
   retains its original failed result. These are source-tool changes, not a
   new ROM revision.
2. Phantom-sound mailbox counter (#16): candidate has 38 sampled transitions
   versus stock/parent 18. Fresh same-core 600-frame traces confirm this, but
   actual native `$26` requests are stock 34, parent 37, candidate 36, all at
   bank 1 `$57B2`; each also has one `$0C` request at `$79A2`. Thus the higher
   sampled pulse count does not establish more native requests. Sound-engine
   consumption and audible/native-PCM equivalence remain unproven. No audio
   acceptance threshold was changed and no acoustic pass is claimed.
   **Consumption follow-up:** `tmp/sara-engine-consumption-09/receipt.json`
   records optional, bank-qualified breakpoints at the unchanged bank-3
   mailbox read (`$45B6`) and acceptance/rejection branches (`$45C7/$45C2`).
   Fresh 600-frame stock/parent/candidate runs consume 34/37/36 `$26` requests,
   accept 33/36/35, and reject one each; each accepts its one `$0C` request.
   The full earlier frame-sample/RST reports remain byte-identical with this
   instrumentation. Each replay took about 23.7 seconds. This establishes
   that the sampled transition increase is not increased engine request
   consumption. It does not establish PCM or acoustic equivalence. The
   existing sound acceptance rule remains unchanged and #16 stays open.
   The source fingerprint has changed since run 06; a new full campaign is
   required after the remaining sound verification work, not reuse of run 06.

### Native sound follow-up (#16)

`/mnt/data/tmp/penta-sara-native-audio-14/` retains full native stereo PCM16
at 131,072 Hz, playable WAV files, every video frame, serialized frame states,
and input/sample timelines. Optional sound-engine breakpoints on versus off
produce byte-identical video, states, input timelines, and all 2,063,680 native
sample frames for the same candidate/core (938 display frames). This validates
the extra breakpoints with the common recorder; it is not an absolute claim
that the recorder is unobservable. The earlier raw command traces also match.

The parent/candidate full-length PCM comparison passes the narrow guard in
`verify_native_audio_pair.py`: RMS ratio 1.0002344841, zero clipped samples,
the same 62 quiet 50-ms blocks and 20 digital-silence intervals, and no larger
maximum sample discontinuity. All differences are retained; 810,405 sample
frames differ. No trimming, retiming, resampling or normalization was used.
This is **not waveform or perceptual equivalence**, nor a claim to have listened.
The stock recording has a different native duration and is retained as context,
not trimmed to force an equal-length comparison.

The corrected command oracle measures native requests and engine decisions,
retains frame-sampled diagnostics, and keeps the existing 1.5 count tolerance.
It rejects missing consumption, novel commands, incorrect priority decisions,
excess activity and silence. Fresh gate `tmp/sara-sound-command-gate-15`
passes (35 stock requests / 37 candidate requests; accepted shots 33 / 35).
Fresh gate 16 repeats that pass after the final sampled-count consistency
checks. Sixteen command-oracle tests and eight PCM negative-control tests pass.
`tmp/sara-native-audio-negative-16.json` additionally records rejection of
silence, a 100-ms gap, clipping and half-volume mutations of the actual candidate
PCM, and the full observer-on/off artifact equality hashes.

Native capture initially exposed a Qt destruction race when Lua called exit
from the emulation thread. Failed attempts 10–13 are retained, including the
GDB backtrace. The diagnostic recorder flushes synchronously before process
exit; ordinary command checks now finish through a closed completion marker
and termination of their exact owned child. Neither path bypasses single-flight
or changes ROM execution. No abandoned emulator processes remained afterward.

### Earlier trials (not release candidates)

Trial 02: `998a660f0c81796d4fa75a3b8fe59a41fe561abc8788846a94d52ae017fd1be0`.

- Candidate passes 2,400 consecutive direction-change captures and another
  2,400 captures with 17-frame direction changes plus firing. Each has five
  initial absent-Sara frames, reported rather than silently discarded.
- Offline raster reconstruction finds zero missing opaque Sara pixels in
  the 2,400-frame walking capture, using the unchanged authenticated art.
- Two hazard-area Game Over/title/restart cycles pass, including saved-game
  stage selection. That lifecycle test accelerates each loss with HP=0;
  it is not a movement-only death claim.
- Parent-relative 1,200-frame timing checks: Stage 1 285/282 (+1.06%),
  Stage 5 328/329 (-0.30%), Stage 7 360/362 (-0.55%). Stage 1's stricter
  diagnostic ±1% bound fails. Its longer 3,600-frame check is 872/861
  (+1.28%) and also fails that bound. These are not full-release passes.
- The first implementation was retained as trial 01; it removed tearing
  but had extra SRAM-helper overhead. Trial 02 removes that overhead.
- Trial 02 failed the complete title/demo inventory: no miniboss samples.
  The same fresh test passes the unchanged parent. Its 92-gate campaign was
  interrupted after 20 completed gates; it is not a full qualification result.
  Other initial rejections concerned exact-ROM ABI recognition, not observed
  stage-card raster failures. The failed artifacts remain unchanged.
- Trial 03 attempted an IE-masked wrapper in bank 14, but failed to display
  Sara. A read-only caller trace identified bank 1 as the actual caller bank.
  This variant is retained only as a failed experiment; it is not deployed.
- Full release qualification and MiSTer/user confirmation remain pending.
  Do not close #6 or label this candidate hardware-tested.

Local, ignored evidence:

```
/mnt/data/tmp/penta-sara-direction-changes-20260919-01/
/mnt/data/tmp/penta-sara-publication-20260919-01/
/mnt/data/tmp/penta-sara-negative-control-20260919-01/
/mnt/data/tmp/penta-sara-atomic-v2-long-20260919-01/
/mnt/data/tmp/penta-sara-atomic-v2-fire-20260919-01/
tmp/sara-atomic-speed-parent-02/manifest.json
tmp/sara-atomic-speed-stage1-long-01/manifest.json
tmp/sara-atomic-v2-hazard-restart-01/receipt.json
tmp/sara-atomic-release-matrix-01/manifest.json
tmp/sara-parent-title-control-01/receipt.json
tmp/sara-title-04/receipt.json
tmp/sara-speed-parent-04/manifest.json
/mnt/data/tmp/penta-sara-emitter-04-long/receipt.json
/mnt/data/tmp/penta-sara-emitter-04-fire/receipt.json
/mnt/data/tmp/penta-sara-callers-04/gameplay.callers.tsv
/mnt/data/tmp/penta-sara-final-negative-04/receipt.json
tmp/sara-atomic-pose-source-05/build-receipt.json
tmp/sara-atomic-release-matrix-05/manifest.json
tmp/sara-atomic-unit-05.log
tmp/sara-pose-evidence-05/rendered.png
tmp/sara-atomic-pose-source-06/build-receipt.json
tmp/sara-atomic-release-matrix-06/manifest.json
tmp/sara-hazard-contract-focused-06/manifest.json
tmp/sara-atomic-unit-06.log
tmp/sara-phantom-diagnostic-06/receipt.json
tmp/sara-atomic-pose-source-16/build-receipt.json
tmp/sara-atomic-release-matrix-16/manifest.json
tmp/sara-atomic-unit-16.log
tmp/sara-sound-command-gate-16/receipt.json
tmp/sara-native-audio-negative-16.json
tmp/sara-pose-evidence-05/rendered-qualified-16.png
/mnt/data/tmp/penta-sara-native-audio-14/parent-comparison/receipt.json
```

## Ceiling overhangs are separate

Tracking: https://github.com/struktured-labs/penta-dragon-dx/issues/14

The current priority helper at `$1188` is `RES 7,A; RET`: Sara's native
OBJ-behind-background flag is always cleared. This was introduced to prevent
colored floor pixels bleeding through her body. It can explain drawing over an overhang,
but the exact reported ceiling location and collision behavior have not
been reproduced. Restoring priority globally would risk the earlier floor
bleed. The reviewed ceiling-mask route remains pending; no ceiling fix is
claimed by this sprite-publication change.

The current ROM also replaces bank-1 `$50C5/$50CA` with NOP pairs. These
were native writes to the `$FFC4` Sara priority flag; r381 retired them
after a traced collision with the completed scrolling-map target. Stock
`$1188` indexes `$FFC2-$FFC5`, so simply restoring that helper would read
inputs whose ownership and writers no longer match stock. See
`build_stage1_sara_priority_clear_r365.py`,
`build_native_priority_collision_r381.py`, and the confirmed collision in
`docs/hram_allocation_map.md`. This is code/history evidence, not a verified
reproduction of the reported room.
