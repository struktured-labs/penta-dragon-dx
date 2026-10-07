# Low-health later-dungeon attribute dispatch (#59)

Experimental branch: `fix/later-lowhealth-dispatch`. Not merged, deployed, or
release-qualified. Qualified parent SHA-256:
`6c4a9654b5c6dad70c8ea21bfd39b6e53766a3cd1a642153c6085774392ec228`.
Trial SHA-256:
`0fd7f1e50f688927e21541bca99cd8d353391a85a626530df9f39ac9435fbf08`.

## Corrected causal evidence

The initial bank-filtered observer missed Stage2 entry. Do not infer skipped
initialization from that observer. Unsegmented PC breakpoints plus FF99 in
`tmp/current-lowhp-mapper-observation-01/mapper.tsv` show bank13:555D through
0061 to bank21:4200/4219 at frame3421. Initialization resets readiness; later
attribute publication is absent. All141 PNG checkpoints match observer-off;
native PCM/state neutrality has not been established.

The installed DBDF resolver returns0B for low-health later dungeons, whereas
the DABB dispatcher accepts dungeon IDs03..08 or arena IDs0C..14. Thus Stage2
low-health tilemap updates proceed without the corresponding attributes.
At frame4200 the parent has eight missing pickup attributes on one physical
map and those eight plus76 stale boss attributes on the other. The material
LUT is correct, so the older material-only checkpoint oracle passes. BG0 and
BG4 have identical bytes, hiding the stale boss shape in this current replay.
This is not a claim to have reproduced the exact visible OBS cyan patch.

## Trial and narrow regression

`build_later_lowhealth_dispatch.py` changes four immediate constants in the
existing fragmented DBDF resolver. Its accepted canonical range becomes
03..14. Normal scenes and arena aliases retain their existing result; Stage1
canonical02 retains0B. Canonical09/0A still fall into dispatcher rejection.
No new code space, WRAM, mapper call, or native sound-state write is added.
The accepted new alias branch costs four fewer T-cycles per resolver call;
the newly enabled attribute work still needs gameplay/audio timing checks.

Trial checkpoint comes from its own fresh cold7200-frame secret route in
`tmp/later-lowhealth-dispatch-cold-01`, not retargeted parent state. The cold
ancestor explicitly assists position/health. Both4200-frame boss routes use
an assisted native boss call and boss HP zero at1800. The low-health variant
additionally sets Sara HP109 once. No rendering memory is forced.

`tmp/trial-lowhp-late-boss-stage2-01` now has1016 neutral plus8 palette2 cells
on each physical map. `check_lowhealth_stage2_attributes.py` compares all1152
tile/attribute pairs across both24x24 maps at11 settled checkpoints3900..4200.
Trial passes; the exact qualified parent fails with92 stale/missing cells.
Seven unit tests pass, including all65536 raw/canonical scene combinations,
wrong-parent rejection, stale boss and missing pickup mutations, and scene/
policy rejection.

`tmp/trial-normal-late-boss-stage2-01` matches all141 parent normal-route PNGs,
the full gameplay trace and full transition trace byte-for-byte. Low-health
health outcomes differ (parent48, trial33 at4200); no timing-equivalence claim
is made. No native PCM was captured. Full-suite integration, later-dungeon
and boss timing/audio qualification, source-build integration, and hardware
retest remain outstanding. The earlier97-gate receipt is for the parent, not
this experimental trial or these new source inputs.

## Follow-up cadence and audio checks

The explicit `--health 109` speed mode preserves raw scene11 and additionally
requires canonical FFB7=stage+1 and FFBA=stage-1. Normal-health expectations
are unchanged. Stage2's fresh 900-frame, two-runs-per-ROM comparison in
`tmp/trial-lowhp-native-speed-03/manifest.json` passes: original242 loops,
trial241 (0.99587), scroll30/30, strict horizontal coverage116/116. No speed
tolerance or route requirement was relaxed. The preceding `speed-02` attempt
failed Lua compilation (local-variable limit); it remains a failed receipt.
The new configuration uses the existing assistance table to avoid that limit.
The sixteen stage-speed unit tests complete with five optional-fixture skips.

Native full-route audio guard **FAILS**, and this trial is not release-qualified.
`tmp/lowhp-native-pair-01/receipt.json` compares two complete900-frame captures
from each ROM's own frame3420 state, with the startup barrier and the same
native core/tap. PCM has not been trimmed, normalized, or resampled. RMS ratio
is1.12966, silent blocks and digital-silence intervals differ; clipping and
maximum sample jumps do not increase. All sample differences are retained.
The first PCM difference is sample27535, before the first differing damage
event at capture frame297, so differing damage alone cannot explain the onset.
The per-frame state diagnostic is additional evidence, not audio acceptance.
No claim of listening or perceptual equivalence is made.

The later-stage low-health matrix (`tmp/trial-lowhp-later-speed-01`) passes
Stages3–6: loop ratios0.978,0.996,1.000,0.976 with strict route coverage.
Stage7 remains **FAIL**: loop count253/253, but horizontal coverage242 versus
original240. Its qualified-parent control (`tmp/parent-lowhp-stage7-speed-01`)
also fails, for a different reason:270/253 loops (6.7% too fast), with strict
coverage240/240. Thus the trial restores cadence but does not yet meet the
complete Stage7 route contract. Neither failure is waived or called fixed.

The follow-up sound observers (`tmp/{parent,trial}-lowhp-sound-observer-01`)
are neutral against their respective observer-off runs: full native PCM,
all900 delivered frames, serialized states, and input/frame/PCM timelines
are byte-identical within each exact ROM/core. Both routes service1342 timer
interrupts with median gap94208 cycles. Maximum gap rises from121280 to148984
cycles; the first differing sound-port write occurs at frame3 during newly
enabled attribute work. The first shot request moves from frame44 to54;
total requests change27 to44 and accepted commands24 to34. This verifies
timing/encounter divergence rather than observer contamination. It does not
prove acceptable audio fidelity. Full logs and all timer gaps remain in
`tmp/lowhp-native-pair-01/sound-observer-diagnostic.json`.

## Deferred-DMA follow-up: not accepted

Experimental `build_lowhealth_deferred_dma.py` produces
`1f7ee0d22f86f62708b769c86f9678e856275d6dd769b03bc8a9f3f5fc154ca6`.
It expands bank23:6D20's classifier by six bytes into authenticated FF space:
raw0B reads FFB7, then the unchanged03..08/LCD-on domain test runs. Bosses
remain synchronous. Three bounded classifier/preimage unit tests pass.
This is not a release fix: the subsequent capture still has late interrupts.

Fresh cold7200-frame state: `tmp/lowhealth-deferred-dma-cold-01`.
`tmp/deferred-lowhp-late-boss-stage2-01` stays in a native item menu and is
marked incomplete. Initial commentary incorrectly attributed this to a
rejected boss-entry call; the detailed trace proves boss entry and the HP-zero
stimulus did occur. A later suspicion of engine freeze is also unsupported:
restoring its exact frame4200 state and sending six Select frames at30 closes
the menu and reaches Stage2 (`tmp/deferred-lowhp-menu-resume-01`). This matches
the previously documented stock automatic low-resource menu behavior (#29).
Do not patch that native behavior or recategorize the incomplete run as PASS.

The transition harness now offers an explicit `--close-menu-frame`: six
ordinary Select frames, recorded in the edge trace, with no menu-memory
writes. With frame1000, `tmp/deferred-lowhp-late-boss-stage2-02` completes the
boss/card/Stage2 route, but arrives with HP3 and enters death at3949/3951.
Therefore the settled low-health attribute checker correctly fails this
recipe; it does not prove a tile failure or a passing live-health window.

Native capture `tmp/deferred-lowhp-sound-observer-01` from its own frame3420
state includes all900 frames and1980224 stereo sample frames, including death
and title. It is not directly equivalent to the prior1975072-sample captures.
No samples were trimmed. The full maximum timer gap is238448 cycles; even the
additional low-health-phase diagnostic has late gaps150424 and152272 cycles
ending at bank1:12E0. Thus moving DMA alone did not eliminate the delay.
The next observation targets the interrupt-closed attribute compiler, not a
relaxed audio guard or a longer campaign. Nothing from this trial is merged
or deployed.

Direct compiler observation on the first dispatch-only trial establishes a
65,688-cycle interrupt-closed interval from bank1:4302 at1492524716 to4324
at1492590404, frames3423–3424. It executes24 row calls2688 cycles apart with
SVBK3 selected, IE04 (Timer only), SP=DFF9. This explains why deferring the
subsequent DMA alone cannot eliminate the long delay. Observer02 verifies
live bank1 instruction bytes, not just FF99 (the sound ISR maps bank3 without
changing FF99). The first FF99-only observer included sound-bank false hits
and must not be used to count compiler calls. Both observers match all141
PNG checkpoints; PCM neutrality for these compiler observers is unmeasured.
Evidence: `tmp/trial-lowhp-compile-observer-02/compile-critical.tsv`.
Next fix must safely service Timer between compiler rows with native SVBK1
and preserve the mirrored stack and unfinished attribute buffer. There is
no20-byte all-FF/all-zero bank0/1 cave in this exact ROM; do not overwrite
live code to insert a helper. Bank30 already owns a compiler service and a
mirrored-stack return path that needs inspection before reusing its space.

## Timer-yield compiler trials (not release-qualified)

The first timer-yield ROM `7774f603d91253d429e829daf991bd3746fe8585dfbf0dd12366c5621cc641ca`
times out at the Stage2 transition. The guarded launcher cleans up; read-only
process checks find no stranded emulator. Its receipt remains incomplete at
`tmp/timer-yield-lowhp-late-boss-stage2-01`.
Runtime byte capture (`tmp/timer-yield-sites-03/row-code.hex`) identifies the
mistake: Stage2 installs a mapper-owning dispatcher at D400, not a plain row
subroutine. Its bank21 full-row path returns to bank1, so calling it from
bank30 is invalid. The failure happens before the new Timer window; do not
attribute it to Timer stack corruption. These short site observers timed out
and are diagnostic-only, not qualified replays.

The revised helper emits the original 24-cell LUT row directly in bank30,
retains row padding, and allows Timer only between rows with SVBK1. It admits
only raw low-health scene0B plus canonical03..08 and IE04. Stage2 map-ready
bits are invalidated because a full-buffer replacement must not leave old
sparse-cache validity. The native mirrored return is rewritten exactly like
the existing Stage1 bulk helper. Four executable-byte unit tests cover all
cells/padding, saved returns, 24 Timer windows, all excluded IE masks and
scene values. These tests model the helper, not the Timer sound engine.

Trial02 SHA `90a6133730c60404b53f8b1adc5e00548a7e89fdc5957b7211a81efc5b2762dd`:

- Fresh cold7200 prefix and assisted boss/score/Stage2 replay complete4200.
  `tmp/timer-yield-lowhp-late-boss-stage2-02` passes all11 settled checkpoints,
  each checking1152 cells across both physical maps.
- Native900-frame capture has1975072 stereo sample frames. Observer on/off
  has byte-identical complete PCM, video, state and timeline artifacts.
- Timer service occurs23 times inside the new helper, all with native SVBK1.
  Full-trace maximum gap121288 cycles versus148984 on dispatch-only trial and
 121280 on qualified parent. The narrow latency gate requires at most141312
  (1.5 native Timer periods), complete coverage and observer neutrality.
  It rejects the real dispatch-only failure as well as synthetic negative
  controls. `tmp/later-compile-timer-yield-02/timer-check.json` records bindings.
- Low-health speed: Stages2–6 pass strict routes and original-game cadence
  tolerance. Stage7 still FAILS:253/253 loops but H240/242 route coverage;
  it is not waived. See `tmp/timer-yield-lowhp-stage2-speed-02` and
  `tmp/timer-yield-lowhp-later-speed-02`.
- Full native-PCM guard still FAILS: RMS ratio1.0521907088539906, different
  silence blocks/intervals, no added clipping or larger discontinuity.
  Preserve `tmp/timer-yield-native-pair-02`; the latency PASS is not an audio
  fidelity PASS. Sound-event counts differ (for example damage command20
  requests9 versus4 on parent), and the independent source states are not
  machine-state equivalent. Do not trim or align the audio to hide this.

Trial03 narrows the hook to the non-Stage1 FFBA branch only. Stage1's scene0B
fallback now retains its original instruction path/timing as well as its bulk
compiler. Builder additionally authenticates the exact Timer ISR and mapper
bank-shadow ABI before patching. ROM SHA
`ee359af0c1ad11d9b66539c587b59f0134a69810d8c32aa8603869e37e25c99c`;
qualification is in progress, not inherited from trial02. No merge/deployment
or hardware-ready claim has been made.

Trial03 fresh results:

- Assisted4200-frame boss-to-Stage2 route completes; all11 map checkpoints
  pass. Inspected final rendered frame: cyan terrain and white lower boundary,
  with no assertion that this recreates the exact recorded OBS route.
-900-frame Timer trace passes:1342 hits,20 inside compiler, maximum121280
  cycles (same maximum as qualified parent). Full observer on/off PCM/video/
  states/timeline match byte-for-byte. Receipt:
  `tmp/later-compile-timer-yield-03/timer-check.json`.
- Audio level now passes the unchanged two-percent limit: RMS ratio
  1.0034593041736257. No additional clipping/larger discontinuity. Overall
  audio guard STILL FAILS for silence interval/block equality; native damage,
  shot and pickup command timelines differ. Preserve all samples in
  `tmp/timer-yield-native-pair-03`; this is not acoustic fidelity acceptance.
- Fresh low-health Stage2 speed passes237/242 loops (0.979), strictH116/116.
  Stage7 still fails strictH240/242 despite253/253 loops and identical first/
  final viewport and ordered room transitions. The verifier contains an
  existing named Stage7 release95 two-pixel policy, but it was not enabled
  or assumed applicable to this new low-health recipe.
- Cold7200 prefix matches all72 retained screenshot checkpoints against
  dispatch-only parent. Full trace is NOT identical: frame4715 in secret
  scene0A retains sound-command value212 for one additional sample. Secret
  stage FFBA07 still takes the new helper's rejected guard. The narrowed
  Stage1 FFBA00 path does not imply all secret-area timing is unchanged.

Remaining before promotion: investigate full-route audio equivalence and
Stage7 coverage, qualify normal-health and other transition paths on the
exact final candidate, integrate the source build chain and run the full
release suite. Issue59 remains open. No MiSTer action in these trials.

### Stage7 native stride investigation (2026-10-07)

Fresh diagnostic repeats `tmp/timer-yield-lowhp-stage7-status-04` and `-05`
retain the exact trial03 ROM and the strict failure:253/253 loops,
horizontal coverage240/242, vertical28/28. No route exception was enabled.
The optional movement-write observer now includes FFC1 and correctly admits
stock DMG writes (FF70 is not a usable WRAM-bank filter on DMG). It is
diagnostic instrumentation, not an audio-neutrality qualification.

In repeat05, the first candidate FFC1 clear occurs at play frame80, loop19,
PC25CA, ROM bank1, HLDC8A. Stock first clears it at frame572, loop158,
PC25CA, HL DCA2. Further candidate clears occur at frames538 and747;
stock also clears it at647. These are actual native writes at25C8, not
inferences from a frame-sampled flag. Both builds execute the original
25C2 routine: sound command14, FFC1=0, DD00=1, DCFF=10.

Stock4250 conditionally calls the two-pixel step at4258 an extra time
when FFC1 is nonzero. This explains the candidate's change from four-pixel
to two-pixel steps after loop19. The older qualified parent also changes
stride on this route, so the mere existence of a stride change is not
evidence that the new compiler created a movement bug. The encounter's
identity and cause of its different timing are still unverified. In
particular, the existing HRAM table's label "gameplay active flag" is
insufficient to describe FFC1; do not force this byte to1 in a speed test.

This establishes nonidentical gameplay-event histories, not a pass, and
does not resolve the independent full-PCM differences. Preserve the strict
failure while investigating the first encounter divergence. Four executable
compiler-model unit tests passed again. No production bytes changed during
this investigation; no merge, deployment, or hardware-ready claim.

### Initial encounter mismatch, issue66

`tmp/timer-yield-lowhp-stage7-spawn-06` records native spawning during the
loading hold. The first stock spawn is type43 at DC95 with RNG index69;
candidate first spawn is type43 at DC9D with RNG index79. At the first
measured full-entry event, stock's five types are41/41/43/43/40, candidate's
40/17/41/43/41. The initial enemy populations therefore already differ;
the measured stride divergence is not a matched-encounter comparison.
Filed https://github.com/struktured-labs/penta-dragon-dx/issues/66 before
modifying the harness.

The probe now captures physical DC80..DCAF, FFD1 and FFC1 at the first
measured016C boundary, without memory writes. The runner reports missing,
different, or equal sampled state separately; even equal samples do not
qualify complete matched work. This does not weaken any existing gate.
Four unit tests cover each changed field, malformed/missing samples, the
limited meaning of equality, and Lua5.3+ compilation without an emulator.

Initial attempt07 produced no receipt because adding one top-level local
exceeded Lua's200-local limit. Read-only process inspection found no
remaining emulator. The value was moved into the existing telemetry table;
compile-only validation passed before replay08. Fresh repeat08 completes
and preserves253/253 loops, H240/242, V28/28 and the strict FAIL, now with
an explicit initial-encounter DIFFERENT diagnostic. No production ROM
change. Next: a separately labeled matched-start isolation, not a native
stride override, and a valid matched-event audio comparison before promotion.

### No-input native audio isolation (2026-10-07)

Fresh180-frame no-input captures use the exact existing parent/trial03
states, unchanged, with no assistance writes. Outputs:
`tmp/parent-lowhp-noinput-01`, `tmp/timer-yield-lowhp-noinput-01`, and
their corresponding `-noinput-off-01` observer-disabled repetitions.
Each contains395008 native stereo PCM16 frames at131072Hz. Startup epoch
checks pass. Recomputed artifact hashes agree with receipts; for each ROM,
observer on/off full PCM, video, states and timeline match byte-for-byte.

Both runs request/accept zero new sound commands. The complete ordered
sequence of536 APU-register address/value writes is identical. Both have
268 Timer hits, with maximum gap121280 cycles. The candidate has five
Timer hits inside the bank30 compiler, parent zero. Register-write cycle
differences range from-24660 to10968; this is timing difference, not
waveform equality or a claim of inaudibility.

Unchanged full-PCM guard in `tmp/timer-yield-lowhp-noinput-pair-01` still
FAILS exact digital-silence-interval equality. All other checks pass:
RMS ratio1.0095264267863147, same silent blocks, no added clipping and no
larger sample discontinuity. There are four >=20ms digital-silence
intervals on each side; corresponding boundaries differ by at most29
samples (~0.221ms). All395008 samples and their unselected differences
are retained. No trimming, alignment or retiming was applied.

Parent WAV SHA98ed6519b6a31f16a704807a6b323a3684b3514c4c0df43862fc511f56019f53;
candidate SHA7029c1866f1bde2ef34ea82f2d0826be31533aa754070e0280a44a9251d530f2.
This isolates a command-matched short music interval from the different
shot/damage histories in the900-frame firing route. It does not qualify
all audio, change the existing guard, or clear the remaining release work.

### Source-build integration, still experimental

The existing native-PCM guard's unit tests were rerun:10 pass, one optional
historical fixture skipped. Its inserted20ms silence, pop, clipping, gain
loss, silent-reference and truncation controls still reject the defects;
the guard itself has not been changed or waived.

Added `--later-lowhealth-timer` to `scripts/build_stream_regression_candidate.py`.
It requires the full boss-rearm chain and appends the exact dispatch resolver
and Timer-yield builders, each retaining its exact-parent/preimage checks.
Default builds and the normal release-source profile remain unchanged.
The build receipt binds both added builders and retains
`release_qualified=false`, with an explicit warning about unresolved audio
and default Stage7 comparisons.

Fresh `tmp/later-lowhealth-source-01` construction from the original ROM
and palette sources reproduces the emulator-tested trial03 SHA
ee359af0c1ad11d9b66539c587b59f0134a69810d8c32aa8603869e37e25c99c.
No retained candidate is consumed. A second build02 follows the receipt-copy
clarification; neither construction is a substitute for runtime qualification.
Added source-chain tests cover missing prerequisites, exact candidate bytes,
stage-parent continuity, builder bindings, and non-release receipt labels.

### Equal-start Stage7 patrol, issue66

Reused the existing state-keyed patrol wrapper rather than adding another
controller. Its exact textual sync anchor had become incompatible with the
new initial snapshot. The wrapper now replaces the entire delimited sync
block; a unit test executes its transformations and compiles the generated
Lua without running an emulator. Six initial-state tests and five existing
patrol policy tests pass.

The wrapper additionally accepts its own complete516-byte stock dump,
retaining the captured RNG cursor unless an explicit seed override is given.
Length is validated before any injection. WRAM image reads/writes now use
physical bank1, not a possibly selected CPU WRAM bank. These are explicit
diagnostic world-image writes, not ordinary gameplay or audio qualification.

Fresh900-frame HP109 loop-patrol runs:

- `tmp/lowhealth-state-patrol-native-01`: original249/candidate229 loops,
  H526/504, V4/4, FAIL.
- `tmp/lowhealth-state-patrol-equal-01`: same captured stock world image and
  its RNG seed, original249/candidate229, H526/520, V4/6, FAIL.
- `tmp/lowhealth-state-patrol-parent-equal-01`: previous qualified6c4a build
  under the same diagnostic recipe, original249/parent256, H526/572,
  V4/8, route FAIL but throughput within the existing tolerance.

All four equal-trial post-injection world dumps match the source SHA
8017e7e3cef2cfc874ec6d7937e5daa006634817cf825f64aae1dd39991b4d36.
The legacy image covers D800..D8FF, DC00..DCFF, FFCB, FFD4..FFD5 and FFD1,
not all machine/gameplay state. Do not call this complete state equivalence.
Nevertheless the candidate's throughput deficit persists after matching
those fields; the early rightward diagnostic pass is insufficient to clear
performance. Next investigate newly enabled full attribute-compilation cost
and whether canonical-stage dispatch can reuse the native optimized path.
No release-floor waiver, no merge and no deployment.

### Earlier-start diagnostic09

Added opt-in `STAGE_SPEED_START_POLICY=first-lowhealth-loop` under issue66.
It starts at016C as soon as the native raw low-health scene is present in
the selected stage; it does not rewrite enemies, RNG, FFC1, interrupts, or
coordinates. Default remains `stable-120-frames`. Receipts label the policy
and its diagnostic status. Invalid policies and normal-health use are
rejected before launching an emulator. Five focused unit tests now pass.

Fresh trial03 replay `tmp/timer-yield-lowhp-stage7-first-loop-09` passes
the unchanged strict route and throughput criteria: original251 loops,
candidate257 (1.0239), H240/240, V28/28. Two repetitions per ROM agree.
Nevertheless its initial encounter samples STILL DIFFER: stock RNG74 with
type43 in DC95 versus candidate RNG83 with type43 in DC9D. This policy
therefore supplies an additional successful route, not matched-work proof
and not a replacement for the default replay's retained failure. It does
not qualify PCM fidelity. No production ROM change, merge or deployment.

## Stage7 low-health fast-path isolation (issues #59/#66)

The Timer-yield trial03 still bypasses three raw-scene08 checks while the
native low-health sound scene is0B. Experimental builder
`build_stage7_lowhealth_fastpath.py` admits canonical08 only for that alias;
all other fast-path eligibility checks remain unchanged.

- Trial01 `ce16a6bd60bba28d1851992134dfe942f9372ed41c4a3290b0007e81376aa5c1`
  called WRAM DBDF from bank13's early selector. Startup stalled, no candidate
  receipt, verifier failed. Suspected pre-install runtime ownership; not
  asserted as a verified PC-level cause. Process check after timeout found
  no remaining emulator. Original builder preserved alongside trial01.
- Trial02 `9780e072e16f27cb9e3c1abd54398537a457f68a12d4d7fd151f767ad246b4c2`
  leaves that selector unchanged and patches only bank22 checks to its own
  ROM-local resolver. Same assisted world-image patrol: stock249 loops,
  candidate238; H526/544, V4/8. FAIL, retained in
  `tmp/lowhealth-state-patrol-fastpath-02`.
- Trial03 `9bba2276a97e3178f9e860b1bc7008f2185086c46ae0a7979b9c35b160c85399`
  gives bank13 its own ROM-local resolver in the remaining documented
  code cave6EE8..6EF3, fenced by JP5422 (not a palette-table zero run).
  Stock249/candidate239 loops; H526/514, V4/6. FAIL, retained in
  `tmp/lowhealth-state-patrol-fastpath-03`.

These improve on Timer-yield's229 loops but not the qualified parent's256
on this diagnostic. The world-image assistance does not establish complete
machine-state parity. No rendered-map, sound, or release qualification is
inferred. Three static unit tests check bounded alias selection and rejection
of an unknown parent. Default source/release profile unchanged. Next useful
observation is executed fast-path/fallback cost, not another broad campaign.

### Executed-code trace, and cache hypothesis rejected

Fresh `tmp/lowhealth-state-patrol-fastpath-code-06` adds instruction-byte
signatures to generic optional trace counts (issue #66). Six harness tests
including Lua compilation pass. Full primary timeline/PCM neutrality has
not been qualified; the traced replay retains the same239 loops and route
as the prior replay, which is only a narrower observational check.

The exact Stage7 copier entry executes84 times:33 optimized entries and51
fallbacks. The bank30 Timer-yield helper does not execute. Address4302's
62 observed hits are bytes `2AFE8020093E10EA`, belonging to the sound bank3,
not bank1's DI/compiler entry. FF99 alone had misleading bank1 samples
because the sound ISR maps bank3 without updating that shadow. Therefore
do not attribute this Stage7 deficit to the Timer-yield helper itself.
Fresh parent trace `tmp/lowhealth-state-patrol-parent-code-07` reproduces
256 loops and no optimized-bank22 entries.

Trial04 `98daa0a99fa421b784cd2cdb27092db96d40079d90881eb3f2b97518a6bbf23c`
also resolves only canonical08/raw0B at bank28's DF0D cache comparison.
`tmp/lowhealth-state-patrol-fastpath-cache-08` still returns239 loops,
H526/512 and V4/6 (FAIL). It now enters the bank30 compiler51 times and
does not improve throughput. This cache hypothesis did NOT produce a
performance fix; do not promote it. Exact builder and base-probe copies
are retained with the trial/evidence. Four static alias tests pass.

Remaining actionable boundary: bank22's51 fallbacks include samples with
A=02 at the existing camera-alignment check; its optimized publisher only
admits offsets0/4, not2/6. Any extension needs proof of its destination and
LUT semantics plus actual map captures, not a relaxed acceptance threshold.

### Low-nibble camera trial and visible-map check

Historical r274 already proves the viewport union for all SCX/SCY0..15:
rows0..19 and columns0..21. Current helper still compiles20 rows of24
cells; the F3 mask accepts0/4/8/12 (not merely0/4). A new exact-parent
builder `build_stage7_lowhealth_camera.py` rechecks the current compiler
preimage and changes all four entry/post-service masks toF0, leaving every
other guard unchanged. It uses fastpath trial03, NOT the failed cache trial04.

Candidate `3d581fc835e15e0d6df691b566b7e2053e1b8d17783496c2e2fcade54a33d626`
changes just four mask bytes and the global checksum. Fresh900-frame patrol
`tmp/lowhealth-state-patrol-camera-10`:249/249 loops,86 optimized copier
entries, zero exact bank22 fallback entries (previous33/51). Route remains
different H526/530,V4/6, so overall FAIL is preserved.

Optional sparse screenshots and exact-ROM savestates were added to the
speed probe. `check_stage7_visible_attributes.py` verifies the displayed BG
map's visible cells against the installed LUT and ROM22:7600 policy;
rejects window-enabled/out-of-domain states. Four checkpoints at1/300/600/900
all pass (360/399/378/380 cells). Inspected final before/after images show
no obvious new corruption, but are not full-route visual qualification.
Five checker tests include stale-color, missing-color, and partial-edge
mutations. Four geometry tests pass including an out-of-domain crop exposure.
New report: `tmp/stage7-lowhealth-camera-01/visible-map-check.json`.

Fresh unassisted default-start right-input replay
`tmp/lowhealth-camera-default-11` has STRICT route equality H240/240,V28/28
but271/253 loops (1.0711), exceeding the upper timing tolerance. Overall
FAIL retained. This is progress on the fallback cost, not final speed
qualification; initial encounter/contact divergence still needs separating
from intrinsic cadence without forcing native flags or weakening the gate.
No source-profile promotion, merge, deployment, or readiness claim.

### Longer native-start versus state-keyed replay

Same camera candidate,4000-frame native-start right-input replay
`tmp/lowhealth-camera-default-long-12` remains FAIL:1298/1140 loops
(1.1386), with exact H240/240,V28/28. Both reach and remain at world
X344,Y1648; initial entity/RNG samples and subsequent damage histories
differ. This wall replay does not establish matched computational work.
No limit was relaxed and the entire failure remains preserved.

Fresh4000-frame copied-world state-keyed patrol
`tmp/lowhealth-camera-patrol-long-13` records1130/1138 loops (0.9930).
The nested fixed-frame route comparison still fails H3404/3500,V18/18.
Applying the pre-existing strict settled-motion metric, without changing its
thresholds, yields:

- all four traces settle at half-cycle22;
-32 common post-settle legs, **zero contact-affected legs excluded**;
-stock1890 frames, candidate1915 frames in both repetitions;
-cadence ratio0.986945, within the existing0.98..1.02 bounds;
-exact endpoint room/X sequence and post-settle Y;
-the full settled-route ratio is identical to the uncontested ratio.

`check_lowhealth_patrol_cadence.py` saves these results and original nested
failures together, verifies copied-field equality and deterministic A/B
traces, hashes the inputs, and explicitly leaves release qualification false.
Report: `tmp/stage7-lowhealth-camera-01/settled-cadence.json`.
The copied world image is not complete machine state; corrected the wrapper's
old comment that overstated that guarantee. Five existing patrol mutation
tests and six base/wrapper tests pass. This supports the local movement
cadence fix, not startup, unmatched terminal work, audio or whole-release
qualification. Next: reproduce the camera candidate through the opt-in
source build, then qualify the affected low-health map/audio/transition routes.

### Reproducible camera source and fresh Stage2 transition

The opt-in source chain (`--later-lowhealth-timer --later-lowhealth-camera`,
with its required preceding presentation/boss fixes) now reproduces
`3d581fc835e15e0d6df691b566b7e2053e1b8d17783496c2e2fcade54a33d626`
at `tmp/later-lowhealth-camera-source-01/candidate.gb`. No retained candidate
ROM was used as a build input. The rejected cache-alias experiment remains
explicitly opt-in; the source chain uses fastpath trial03. The normal release
profile is unchanged and this experimental build is not release-qualified.

Fifteen source-chain/fastpath/camera/visible-attribute unit tests pass, plus
23 dispatch/compiler/Timer/low-health and initial-encounter tests. The local
Python has no pytest module; these are unittest tests and were run with the
standard-library unittest runner, not skipped.

A fresh7200-frame cold prefix generated an exact-ROM state, followed by the
same assisted4200-frame low-health boss-defeat transition used previously:
`tmp/camera-lowhp-late-boss-stage2-01`. Both physical maps pass all1152
tile/attribute comparisons at each of11 settled checkpoints3900..4200
(12672 comparisons total). Report:
`tmp/later-lowhealth-camera-source-01/stage2-attributes.json`.
The final screenshot was inspected; this is still a settled-map diagnostic,
not proof of every transition frame or a recreation of the recorded stream.
The replay uses synthetic boss entry/defeat and a one-time HP109 stimulus;
no palette/cache writes are used to make the checkpoint pass.

Fresh900-frame Stage2 captures `tmp/camera-lowhp-native-01` and
`tmp/camera-lowhp-sound-observer-01` have identical complete PCM/video/state/
timeline hashes. The Timer gate passes1342 interrupts,15 inside the compiler,
maximum121920 cycles (unchanged gate limit141312). Receipt:
`tmp/later-lowhealth-camera-source-01/timer-check.json`.

The cross-ROM full PCM guard against the qualified parent still **fails**:
`tmp/camera-parent-native-audio-01` has RMS ratio1.049697 and failures in
silence placement and maximum sample step. A separate180-frame no-input
diagnostic `tmp/camera-parent-noinput-audio-01` has RMS ratio1.009736,
no added clipping/step, but still fails silent-block/interval equality.
Neither comparison was trimmed, aligned, normalized or waived.

Inspection identifies a confound, not an audio fix: the old frame3420
checkpoint enters gameplay on relative frame1, whereas this candidate
enters on relative frame4. Both start in scene18, but their initial music
register FF18 is5F versus61; the no-input ordered register streams have536
versus537 writes and differ from the first write. Therefore these are not
matching music-phase controls, despite matching requested frame numbers.
The same-ROM observer-neutrality result remains valid; cross-ROM acoustic
fidelity and the three-frame transition shift remain unresolved. Next work
must distinguish the changed native transition timing from an audio defect,
without retargeting states or hiding the retained failed comparisons.

### Separating transition phase from later gameplay cadence

The retained per-frame transition traces show the same ordered scene sequence.
Both Timer-only and camera candidates leave score polling at3221, select
Stage2 at3237, and enter scene18 at3261. They enter low-health gameplay at3421
and3424 respectively: the final card interval is160 versus163 frames. Earlier
synthetic boss calls occur at122 versus123; defeat is observed at1802 versus1804.
This is a real timing difference, not a missing scene. It also explains why
frame3420 is not an equivalent audio start across these builds. It does not
by itself prove the cause of the timing difference or acoustic fidelity.

Fresh900-frame native-start Stage2 right-input/HP109 replay:
`tmp/camera-lowhp-stage2-speed-01/manifest.json` passes the existing matrix
target0.95..1.05 (no accepted-slowdown override),234/242 loops=0.966942,
strict equal H116/V0 route, and zero sampled scene mismatches. Initial entity
slots/RNG differ, explicitly recorded by the manifest, so this is route and
native-start throughput evidence, not matched-work speed equivalence.

The same900-frame native-start recipe also passes Stages3..6:
`tmp/camera-lowhp-middle-stages-speed-01/manifest.json`. Loop counts
candidate/original are224/230,245/249,246/248,239/247 respectively; all use
the unchanged0.95..1.05 target, with strict route equality and zero sampled
scene mismatches. Each retains its DIFFERENT initial-encounter annotation;
these short runs do not establish full-stage or matched-work qualification.

A fresh default source build at `tmp/lowhealth-default-source-control-01`
passes its construction verifier and remains exactly
`6c4a9654b5c6dad70c8ea21bfd39b6e53766a3cd1a642153c6085774392ec228`.
Added unit checks for opt-in defaults and unchanged default candidate/stage
chain; all four source-chain tests pass. The construction receipt was verified
at build completion; subsequent test/audit edits change the suite fingerprint
and this receipt is not a current full-suite qualification. Remote main remains
e87c24568cf2fa6afd7a7f3e4d092ea008adee74, with no open PR at this check.

### Candidate-aware full-suite coverage and event-based return fixture

Added `lowhealth_candidate_lineage.py`: exact3d581 candidate and exact6c4a
ancestor, explicit reverse delta, changed-component rejection, and source
replay of the four low-health builders. Existing unchanged-component oracles
can identify this descendant, but cannot treat its changed bytes as inherited.
The expansion-tail owner reconstructs banks21..31 through those builders;
all eleven pass. The boss dispatcher oracle explicitly applies only the four
new scene-resolver immediates; all other fragment bytes remain checked.
The static boss atomic-attribute contract passes. The live roster now retains
all97 required gates, including header and secret/boss handoff checks that
otherwise were omitted for an unrecognized candidate. Twenty-one focused
lineage/observer tests pass, including mutation and oracle-preimage controls.

Selected suite `tmp/camera-successor-gates-01` passes all-nine-header/native
timing verification (59.5 seconds), with deliberately damaged records7/8
rejected. Its handoff gate failed when mGBA exited-11 after the control's
frame7200 capture. The process check found no orphan. An exact control replay
at `tmp/camera-rearm-control-repeat-01` completed normally; the original
failure is retained, not accepted as a negative-control success.

Complete retry `tmp/camera-boss-handoff-02` passes the boss/Stage2 comparisons:
candidate checkpoints900/3000 pass, the rearm-only broken control fails both
with stale graphics scene. It then fails the return visibility check because
the old hardcoded frame6960 is already gameplay on this candidate. The actual
cold trace has return card6691 and dungeon6860, with a card checkpoint6840.

`verify_playtest_boss_handoff.py` now selects a captured card checkpoint before
the observed secret-return edge from a complete cold trace, checks its exact
ROM identity, records state/trace/receipt hashes, and requires enough replay
for the full70-frame initialization tail. It rejects boot-only, missing,
ambiguous, post-return and too-short fixtures. Six new selector tests and the
five existing visibility mutation tests pass; the visibility oracle is unchanged.

The resulting240-frame ordinary-input replay `tmp/camera-event-return-03`
passes: boundary at relative20, five unfinished map frames hidden, then visible
complete gameplay. No memory writes or savestate retargeting. Full fresh
handoff and all97 gates still need completion; neither the retained failures
nor unresolved cross-ROM audio comparisons are waived.

Fresh end-to-end handoff `tmp/camera-boss-handoff-event-04/result.json` now
passes both corruption controls and event-selected return visibility. Both ROMs
cold-booted independently; candidate checkpoint6840 precedes return6860.
The combined focused unit run passes76 tests with no skips. These results
justify expanding to the complete regression inventory; the full suite is
still required and does not replace unresolved native-PCM comparison work.

### Full-suite first failures: shared-runtime component authentication

`tmp/lowhealth-camera-full-suite-01` is running against exact candidate
`3d581fc835e15e0d6df691b566b7e2053e1b8d17783496c2e2fcade54a33d626`.
At the first review, 21 checks had passed, two failed, and movement stress
was running. Source remains frozen during this run.

Both `stage1_captured_menu_stationary` and `stage_card_stability` fail with
`component intersects low-health delta`, not a rendered-image assertion.
The menu contract authenticates the installer fragments at $356CA and
$356FA as unchanged; the card inspector authenticates the encompassing
$3569A..$356FF component. Both overlap the four deliberately changed
scene-resolver immediates ($356EA, $356EC, $356FC, $356FE). The rejection
is correct: these components are no longer wholly inherited unchanged.

The next revision must explicitly verify the changed dispatcher fragments
against their reviewed parent plus the four owned immediates, retaining
all other component comparisons and live visual assertions. It must not
globally permit changed ranges through `authenticated_parent`. The menu
fixture also needs a review of `release_lock_boundary`: its successor
overlap scan currently enumerates only the older successor delta, not the
new low-health delta. This is an additional fixture-safety concern, not an
observed gameplay failure. Preserve these original failures and rerun both
checks after the current campaign completes. Cross-ROM audio qualification
remains separately unresolved.

### Full-suite hazard coverage exposes an uncorrected #37 consumer

The same campaign subsequently fails `stage1_current_hazard_menu` and the
clean control of `stage1_exact_destination_mutation`; its dependent hazard
mutation gate is blocked. Both stationary replays are deterministic and
all sampled raster, palette, attribute, map-flip, and endpoint assertions
pass. The failing inner assertion is the nonempty native item dispatch:
both report `f266:g00:i00`. This is a coverage failure, not proof that a
normal player's item use or graphics failed.

Read-only source inspection finds that `probe_stage1_spike_palettes.lua`
still writes DCDD/DCDC as a pseudo-health word before item use and in its
warning phase, while unconditionally writing actual health DCBB=FF.
Those addresses are inventory/cursor state, not health. The reported
`low_health_forced_frames=195` therefore cannot qualify warning coverage;
`low_health_scene_frames=0` is retained. DCBD/DCDB setup also still uses
CPU-window writes instead of the existing physical-bank1 helper (#41).
Its dynamically selected bank at setup has not yet been proved.

Reopened issue #37, comment6033535641, before implementation. Correct the
declared item fixture and health-only stimulus after this campaign finishes;
require an actual selected nonzero item and observed native warning state,
retain negative controls, and rerun the live sequence. Do not waive the
failure or relabel the existing healthy execution as low-health validation.

An isolated scratch contract design, `tmp/lowhealth-contract-review.py`,
passes four offline tests: current component rejection, explicit ownership
of the four dispatcher immediates, rejection of all other mechanisms, and
unknown-image/range rejection. No running suite source was changed.

Scratch copy `tmp/lowhealth-harness-draft-01` now contains tested proposed
changes to `lowhealth_candidate_lineage.py`, `verify_stage1_captured_menu.py`,
`stage_card_palette_handoff.py`, `verify_low_health_flicker.py`, and
`verify_ted_expanded_integration.py`, plus
`tests/test_lowhealth_component_contracts.py`. These are NOT yet integrated
into the running campaign's sources. Forty-one offline unit tests pass
with `PYTHONPATH=src` in the draft directory, including copied-WRAM refresh,
ROM/WRAM execution-boundary rejection, damaged component controls, the
complete source-replayed compiler profile, and the new prelude-tail resolver.

Additional campaign failures: both low-health gates reject the changed
bulk-compiler branch before emulator execution (`bulk compiler completion
ABI mismatch`); the static Ted gate rejects the newly occupied prelude-tail
cave (`menu_window_prelude_exact`). The draft changes authenticate these
explicit new owners; they do not weaken the runtime assertions. The overhang
gate also fails: Sara reaches world1240/1352, camera0808 rather than the
fixture's required1240/1356, camera0C08. Occlusion at the required position
is unqualified, not proved broken. Keep this failure pending a controlled
position/input fixture review; do not relax the pixel/priority oracle.

Further #37 source review: native fixed1E08 selects
`DCBD + 10*DCDB + DCDD`;1F22 is cursor movement, not healing. Native bank1
5050 uses DCBB: 20..7F sets DD06=1, below20 can request the auto-menu,80+
clears the warning. A corrected hazard fixture should seed inventory and
cursor once in physical bank1 and use DCBB alone for its health stimulus.
The existing hazard oracle recognizes02/0A, whereas real warning uses0B;
record raw and canonical scene authority and require the actual warning
transition rather than merely counting writes. Implementation/live replay
of this correction is still pending.

### Full-suite completion and footer correction (October 7)

The immutable `tmp/lowhealth-camera-full-suite-01/manifest.json` finished:
80 passed, 11 failed, 6 dependency-blocked (97 total). This is a failed
qualification, not a release receipt. The three restart failures are a real
footer defect: returned title shows `V3901` in place of `V3.01`. Main title
ROI matches. The differing footer pixels are confined to x40..46/y137..143.
Normal restart cycle1 differs at ages60..290; spike cycles1/2 at60..89 and
60..191; saved-game cycle2 at60..282. Preserve those full original sequences.

Reopened #8, comments6033834580 and6033903066. Experimental builder
`build_title_glyph_read_window.py` waits before the VRAM read predicates,
retaining the GDMA write wait. The old helper guarded the write but could
skip the copy when a mode3 predicate read returned FF. Child SHA256
`a1ff1f90018122d84a378d0150a9fcbd0b5da6ffb228462b4f16c8bcd74e6d6d`
changes only bank13:6DA7..6DFF and checksum over exact3d581 parent.
All three unchanged restart sequence verifiers pass (482 title pairs and
102 Game Over frames each): `tmp/title-glyph-read-restart-01` (traversal),
`tmp/title-glyph-read-spike-01`, `tmp/title-glyph-read-saved-spike-01`.
Returned title age60 visually inspected; period is present. Two ownership
and precondition unit tests pass. Source-profile integration, wider timing
guards, and hardware acceptance remain pending; do not promote this trial.

After the suite exited normally, integrated the bounded component-owner
and physical inventory/health draft corrections into the worktree with
apply_patch. Focused cohort:47 tests passed, no skips. New hazard replay
`tmp/native-health-hazard-menu-01` runs the original3d581 candidate and its
authenticated own-ROM hazard state; footer trial is not substituted into
that state. The legacy low-health-flicker default still needs correction
because it writes cursor bytes as fake health. Do not claim that default
profile covers true low health yet.

Follow-up: both650-frame current hazard replays pass with190 actual warning
frames, item dispatch `g00:i01:c00`, and health C0→FF on use. The bounded
scene0B replay/recovery passes twice byte-exact in `tmp/native-health-scene0b-02`.
The first attempt (`native-health-scene0b-01`) correctly rejected an identical
ROM at a different path than its state provenance. The retry used the exact
recorded ROM path; no provenance assertion was weakened. The legacy/default
profile now uses DCBB FF→40 and verifies DD06/scene0B rather than cursor
values. Its paired replay also passes (`tmp/native-health-default-01`).
Issue37 comment6033951986 records the bounded results.

The overhang fixture now holds Down only until native Y reaches1356, bounded
by frame1230, and records every input. Position assist and sample frames are
unchanged. Exact world/camera/OAM/priority/768-black-footprint oracle passes
on a1ff against stock, with visible open-floor control (`tmp/title-glyph-overhang-01`).
Issue14 comment6033940851 explains the old fixture's failure to reach its
reviewed position. This is not a new claim that user-confirmed occlusion broke.

The three previously incompatible component gates all pass on3d581 after
explicit owner validation: captured menu, stage cards, Ted integration
(`tmp/lowhealth-component-replay-01`,3/3). No full-suite pass is claimed.

Fresh original-cartridge source construction reproduces a1ff exactly:
`tmp/later-lowhealth-title-source-01`. Added opt-in `--title-glyph-read-window`
after the low-health camera chain, with transitive source hashes and exact
parent checks. All new flags remain false by default; release_qualified is
false. Lineage replays/authenticates both exact3d581 and a1ff, and refuses to
treat the changed footer as an unchanged component. Focused35 tests pass
without skips, including source construction and footer ownership controls.
The broader31-test cohort passed with2 historical parent-ROM fixture skips;
those skips are not new verification. A nine-gate fresh-source title/restart/
stage-card/speed regression run is in progress at `tmp/title-read-source-focused-01`.
Still unresolved: native-start audio epoch/comparison, wider qualification,
fresh complete suite, merge and hardware/user acceptance. No deployment.

**Do not promote a1ff:** the fresh-source focused run fails
`title_visual_receipts` (zero demo miniboss samples; no returned footer/banner
by26000frames). Reopened #62, comment6034060197. The three restart passes
are genuine but insufficient. The title observer also reads native D880
through selected SVBK, producing repeated0/gameplay alternation; whether
that explains lost coverage is unproved. Preserve the unchanged failed gate.
Scratch-only blocked-read retry trial126861281b75edaf8daace834ccbe41e53ed0c9eebb71e50fe3bd6823e8b6941
is built by `tmp/title_glyph_retry_experiment.py` from3d581. It changes just
the failed footer-predicate branch operand and8bytes in the old helper's
zero tail (plus ROM checksum), leaving successful-path opcodes/cycles
unchanged. This trial is not emulator-tested yet and is not a production
source-chain stage. The current nine-gate run must finish before another
emulator-backed command starts.

That focused run finished8/9, with only title_visual_receipts failing.
Footer integration, cursor, intro timing, stage cards, ordinary gameplay
speed matrix and all three restart sequences passed. Trial126861 now enters
the unchanged title-visual gate (`tmp/title-glyph-retry-visual-01`). No source
promotion or assertion weakening is justified by the8/9 result.

Trial126861 passes the unchanged title-visual inventory:70 demo-miniboss
samples,280 sprites,0 palette mismatches, returned footer18586/banner20651.
It also passes all three unchanged restart sequences (482 title pairs plus
102 Game Over frames each) in `tmp/title-glyph-retry-{restart,spike,saved-spike}-01`.
Promoted the **builder only** from scratch into
`scripts/diagnostics/build_title_glyph_retry_window.py`; source profile still
points to the rejected a1ff opt-in experiment, so do not deploy that profile.
Next integrate126861 as a separately authenticated source stage and qualify
its transitive identity. Two new retry ownership/branch-target tests pass;
focused37-test cohort has no skips. All emulator commands have finished;
read-only process check reports none running. Audio and full qualification
remain pending; no commit/merge/deployment or readiness claim.
# Follow-up: source retry candidate and exact replay gate (#8, #62, #67)

## Explicit audio follow-up

### Default integration and fresh full suite

`prepare_native_replay.py` now builds the existing native adapter against the
libmgba resolved by `ldd` for the guarded frontend. It records compiler,
library, frontend, CMake flags, source, and transitive header hashes; external
preload/capture/startup-marker injection is rejected. Native captures use
`/mnt/data/tmp/` when available. The low-health runner uses it by default,
validates the restore epoch, and keeps playable native audio. The pair gate
now also requires whole native PCM/video/state/input-timeline hash equality.
The suite fingerprint includes diagnostic C sources.

`tmp/lowhealth-default-native-01/receipt.json` passes all three acceptance
checks using the normal runner: both child oracles, complete unshifted
sampled corpus, and complete native outputs. No manually supplied adapter
or capture variables were used. Related tests: 41 run, 38 passed, three
historical-fixture tests skipped; no failures. No emulator was left running
after these focused runs.

The fresh 97-gate suite `tmp/title-retry-full-suite-01` was then started on
the source-built `12686128...` candidate, using the checked Ted v4 baseline
receipts and pin. Sources remain frozen during this run. Initial failures
identified read-only (not corrected mid-run):

- `stage1_visual_contract_controls`: synthetic compound/menu fixtures still
  supply only `low_health_forced_frames`, not actual observed warning count.
  The strengthened checker correctly rejects them. Update the clean synthetic
  fixture and retain a missing-observation negative control (#37/#67).
- `playtest_secret_boss_handoff`: rearm-only control expects the camera
  parent's reversal SHA even for title descendants. Verified pure reversal
  hashes are `15264f4c19e649bf9c0c85e863e13d9b8f1586f4d5af574524046c1efff488fc`
  for retry candidate and `acc3d07674300458053942b2afc0c8ac9e6000b2c4c77b8a758619b68739ab60`
  for rejected unconditional-read candidate. Only rearm bytes and checksum
  were changed in this read-only calculation. Authenticate each exact child
  and control instead of reusing the old pin (#59).
- Human visual-audit readers still recognize the v1 low-health schema and
  old check names. They need v2 support requiring both exact sampled and
  native checks; do not merely accept a new schema string (#67).

The suite remains incomplete at this note. These findings do not establish
new rendered regressions and do not justify readiness or a merge.

### Prepared corrections while the full suite remains source-frozen

Scratch copies in `tmp/suite-followup-draft-01/` contain unapplied corrections
to the three files above. They are not part of the running suite:

- The clean compound fixture includes 180 actual warning observations; an
  additional missing-observation mutant is rejected. Its standalone visual
  controls pass before switching the audit schema check to v2.
- The boss-handoff draft authenticates each exact child through source replay
  and pins each corresponding reversal hash. Read-only checks on all three
  low-health candidates confirm exactly 11 changed bytes, all inside the
  rearm hook or global checksum. No control emulator was launched alongside
  the suite.
- The visual-audit draft admits only complete v2 pairs, requiring candidate
  bindings, successful child statuses, exact full sample counts, empty mismatch
  lists, successful native restore epochs, and equal complete native hashes.
  Its eight tests pass against the real default-native receipt and deliberately
  damaged receipts. Gallery illustrations now use observed low-health plus
  native DD06 warning samples, rather than adding a settle-frame offset to
  sample-indexed filenames and accidentally captioning recovery as warning.
  This is illustration selection only; complete-corpus acceptance is unchanged.

Before applying, diff these drafts against current source, promote tests out
of scratch, update the issue notes, and rerun targeted controls. The full
suite was still live at 20 passes / two failures with gameplay-speed parity
running at this checkpoint (session 90466). Do not launch another emulator
until that exact suite is terminal.

The next checkpoint has 21 passes: gameplay-speed parity passed in 201.432 s;
movement stress is running, with a live guarded Stage7 patrol child confirmed.
Remote `main` still points to `e87c24568cf2fa6afd7a7f3e4d092ea008adee74`.
An additional scratch-only follow-up sets compiler `TMPDIR` to its repository
`native-runtime` directory. A real compiler-only build in
`tmp/native-adapter-local-scratch-01` produces the identical adapter SHA
`9c85658b9fe1da74e11ae41ff86f08653b72a3acf623537b5dbc05d716d92b22`.
This avoids implicit system temporary-file placement without changing the
adapter. No extra emulator was launched; apply the draft
`prepare_native_replay.py` change after the suite completes.

The low-health child now passes explicit mGBA configuration `mute=0`,
`volume=256`, `fastForwardMute=-1`, `fastForwardVolume=256`, matching the
existing native-capture runner. Its receipt records those settings. With no
ROM/state/input change, `tmp/lowhealth-explicit-audio-01` and
`tmp/lowhealth-explicit-audio-delay-01` both pass the child oracle and match
all 241 sampled rows/images exactly. Their entire native PCM, video,
serialized states, and input/sample timeline are also byte-identical.
Each captures 361 frames and 792,192 stereo samples at 131,072 Hz. The
finalizer creates playable `native.wav` without modifying PCM and validates
both restore epochs. This is reproducibility evidence, not a listening
assessment or parent-versus-candidate fidelity claim.

Negative control `tmp/lowhealth-explicit-audio-ungated-01` retains the same
explicit audio setup but removes the startup barrier and delays host startup
10 ms. Its visual child gate passes, but the epoch checker correctly fails:
512 audio samples were captured before restoration. The control is retained,
not trimmed. Together these trials distinguish the two independent harness
problems: inherited audio configuration and pre-restore startup execution.

`tests/test_low_health_startup_evidence.py` locks in the complete-byte positive
comparison, inherited-audio failure, and ungated-epoch rejection. The related
cohort passes 31 tests with no skips. The barrier still needs reproducible
default runner integration before a fresh release-suite claim. No full suite
was started while that prerequisite remained outstanding.

The opt-in `--title-glyph-retry-window` source build now reproduces SHA-256
`126861281b75edaf8daace834ccbe41e53ed0c9eebb71e50fe3bd6823e8b6941`
at `tmp/later-lowhealth-title-retry-source-01/candidate.gb`. It does not
promote the experimental profile to the default release build.

The completed `tmp/title-retry-source-hazard-focused-01/manifest.json`
reports eight passes and one failure. Title visual inventory, current hazard
state, menu, hazard mutations, exact-destination mutation, and all three
Game Over/restart routes pass. Low-health determinism fails: the second
replay reports one invalid expected-plane promotion and 48 publications
versus 50 in the first replay. Historical captures remain unchanged.

Issue https://github.com/struktured-labs/penta-dragon-dx/issues/67 records
that failure and the independently verified weakness in the old comparison:
it accepted a shifted, shortened overlap while masking four state fields.
Acceptance now requires the complete unshifted sampled state/image corpus,
including the publication-completion tail. Alignment is diagnostic only.
Eight new behavioral tests reject shifted/missing/extra frames and changed
health fields. The exact-corpus, native-item-health, and scene-0B unit cohort
passes 28 tests; `git diff --check` passes.

Two diagnostic runs use the existing native startup barrier, with the same
exact ROM/state and installed low-health observers. The second deliberately
delays host startup by 10 ms:

- `tmp/lowhealth-startup-barrier-01`
- `tmp/lowhealth-startup-barrier-delay-01`

Both low-health child gates pass. All 241 sampled rows and images match
without alignment or masking. Full native video and input/sample timeline
also match. Both lifecycle traces restore before any native output.
However, native PCM and full serialized states **do not match**: equal-length
PCM differs in 3,167,378 bytes; serialized states differ in 49,042 bytes,
including audio-state offsets. These are diagnostic runs with inherited
audio configuration, not acoustic-fidelity qualification. Do not discard,
normalize, or trim those differences. The barrier is not yet adopted as the
default low-health runner; its Lua readiness signal is diagnostic opt-in.

The focused results support the title/restart fix and a startup-ordering
hypothesis, not a complete release claim. Full qualification, audio work,
merge, and deployment remain outstanding. No MiSTer state was changed.

### Current source-frozen campaign and palette follow-up

The current `tmp/title-retry-full-suite-01/manifest.json` campaign uses
candidate `126861281b75edaf8daace834ccbe41e53ed0c9eebb71e50fe3bd6823e8b6941`.
At this checkpoint 26 gates passed, including normal speed parity and the
fixed nine-seed movement stress test. Two harness compatibility failures
remain (`stage1_visual_contract_controls`, `playtest_secret_boss_handoff`).
The suite is still running; this is not a final result or release approval.
Production scripts remain frozen during the run.

For existing issue #19, a scratch-only bridge update recognizes this exact
candidate and its normalized palette layout
`f2a14a38e0fec9f8c1c7372d4a5ef65ad7465a06bbd544bc2ed4f5b371a9a9b5`.
All 15 primary rows and the Stage 2 ownership selector match the prior
supported candidate. Six actual-ROM offline tests pass: exact identity,
palette/checksum write boundaries, Stage 1/2 aliases and ambiguous-context
rejection, unrelated-ROM mutation rejection, projectile labels, and mocked
Apply/Undo. Drafts are under `tmp/suite-followup-draft-01/`. They have not
been promoted into production; no hardware access or Apply/Resume occurred.

### Exact-destination control reader follow-up (#67)

The campaign subsequently reached 34 passed gates and a third failed gate,
`stage1_exact_destination_mutation`. Its retained receipt shows both clean
replays pass and both wrong-map mutants reject 248/248 rendered hazard
frames. The mutant pair also passes the complete unshifted sampled corpus
and native PCM/video/state/timeline comparisons. The outer reader still
queries the removed `alignment.passed` acceptance field, causing its failure.

The scratch draft now requires v2, child exit codes `[1, 1]` (expected visual
rejection), exact sampled comparison, and exact native comparison. Four pure
tests cover the expected rejection, old shifted evidence, native/sample
differences, and child crashes or unexpected success. Applying this draft
predicate to the retained mutant receipt returns true; this read-only check
does not rewrite the original failed receipt. Production promotion and a
fresh targeted gate remain pending the running source-frozen campaign.
Issue comment: https://github.com/struktured-labs/penta-dragon-dx/issues/67#issuecomment-6034816934.

The next checkpoint reached 46 passes, with the same three failed outer
checks. Fresh `low_health_flicker` and `low_health_scene0b_publication`
both pass the strict v2 comparisons (full unshifted sampled corpus and
native PCM/video/state/timeline). Frame flicker, miniboss color, miniboss
continue palettes, Sara overhang priority, and later-stage integrity also
passed. Later-stage soak is running; the suite is not yet complete.

Two more scratch tests in `test_title_control_variants.py` exercise all
three actual source-authenticated candidate/control pairs. Each reversal
changes exactly 11 bytes inside the rearm hook/global checksum and preserves
the title retry/footer area. One-byte unrelated mutations are rejected.
Both tests pass. This validates construction only, not the still-pending
emulator boss-handoff rerun.

### Full campaign terminal; corrections promoted

`tmp/title-retry-full-suite-01/manifest.json` finished with 94 passes and
three failures: visual contract controls, boss handoff control construction,
and the exact-destination mutation's obsolete alignment reader. Both source
and ROM integrity checks are true. Death/Game Over, all three restart paths,
title idle reel, normal speed and boss-speed checks passed. This remains a
failed full-suite receipt, not a release approval.

After terminal exit and a read-only check reporting no mGBA processes,
the reviewed drafts were promoted into production: the three corrections,
strict v2 visual-audit admission/accurate low-health illustration selection,
repository-local compiler scratch, and exact title-retry palette support.
The new tests were promoted to `tests/`. The audit-reader's eight core cases
now use self-contained synthetic evidence, with a separate optional retained
native capture test. The palette test can rebuild the exact candidate from
source or consume an explicitly hash-checked fixture. Historical three-ROM
control checks are explicitly optional when their local source builds are
absent. All 21 new tests pass locally without skips, the standalone visual
contract controls pass, and `git diff --check` is clean.

Fresh targeted campaign `tmp/title-retry-harness-followup-01` is running
the three previously failed gates plus both strict low-health gates and
their dependencies. Production source is frozen again while it runs.
No full-suite pass, merge, hardware retest, or deployment is claimed.

### Boss negative control: stimulus incorrectly required repaired cache

The targeted follow-up finished with five passes and one failure. Visual
controls, exact-destination mutation, both strict low-health pairs, and the
hazard-state dependency pass. Boss control construction now succeeds, but
the broken control's transition failed its completion check.

At frame900 the retained state is raw scene0B, native scene0C, graphics cache
0A, armed0. The HP stimulus incorrectly required cache0C before running:
that is exactly the defect the deliberately broken control must retain.
Its Lua assertion skipped the stimulus, leaving a missing trace row and an
incomplete route. This is not evidence of a repaired gameplay path.

`probe_shalamar_transition.lua` now selects the stimulus through native scene
identity only (raw0C, or raw0B plus native0C), retaining wrong-scene rejection
and all graphics assertions in the independent checker. A test executes the
actual Lua predicate for all 65,536 raw/native scene combinations.
`tmp/title-retry-boss-handoff-fixed-01/result.json` now passes: both independent
cold boots and transitions complete, the control fails with stale graphics
at Shalamar900 and Stage2 frame3000, and the candidate passes both. The short
every-frame secret-return visibility check also passes. No old receipt was
rewritten. This is assisted checkpoint evidence, not organic combat/audio
or whole-route hardware qualification.

A fresh `tmp/title-retry-lowhp-stage2-01` run now uses this exact candidate's
own cold state, HP109 once, native boss call, defeat stimulus1800, and4200
frames, to refresh the dedicated later-stage low-health evidence.

That fresh low-health route completed and passed all 11 settled checkpoints
3900..4200: 1152 physical tile/attribute cells each, 12672 comparisons total.
The final native screenshot was inspected. This is not a full-transition
or acoustic-fidelity verdict. The same candidate-owned low-health recipe
and checker are now part of `verify_playtest_boss_handoff.py`, following its
normal comparison, so normal-health soaks cannot substitute for this case.
The expanded gate is running end-to-end at
`tmp/title-retry-boss-lowhealth-gate-01` (session16027). No other emulator is
running; earlier suite and follow-up sessions are terminal. Remaining work
includes expanded-gate result, current-source full qualification, native
audio/transition fidelity investigation, evidence rendering, and merge.

The expanded gate finished successfully (session16027 exit0): normal boss
control comparison, low-health Stage2 maps, and every-frame secret-return
visibility all pass in `tmp/title-retry-boss-lowhealth-gate-01/result.json`.
All emulator sessions from this checkpoint are terminal. `git diff --check`
is clean. A fresh full suite against the final current source is still
required; the earlier 94/97 manifest remains failed and source-historical.

### Current retry audio diagnostic: observer neutral, starting states unequal

Fresh 180-frame no-input captures are retained in
`tmp/title-retry-{parent,candidate}-noinput-01` and their native corpora in
`/mnt/data/tmp/penta-title-retry-{parent,candidate}-noinput-01-av`.
Both restore epochs pass. The unchanged full PCM guard in
`tmp/title-retry-parent-noinput-audio-01/receipt.json` fails silence placement
and maximum sample-step checks. RMS ratio is 1.003738784351926; clipping is
unchanged. The first 24421 sample frames match, then 361044 sample frames
differ. No samples were trimmed, retimed, normalized, or excluded.

The corresponding `*-sound-01` captures add read-only sound observers.
Within each exact ROM/state pair, full PCM, video, state and timeline hashes
all match the observer-off capture. Thus observer neutrality is established
for these runs. Neither command trace records a command event. FF26 is
written at relative frame11 in the parent and frame13 in the retry build.
The complete trace shows parent gameplay from frame1 with HP60, versus retry
gameplay from frame3 with HP75. Matching initial sound registers alone did
not establish equivalent transition/gameplay states. The failed cross-ROM
comparison remains diagnostic evidence, not proof of an added audible defect
or acoustic fidelity. No listening claim, waiver, or release approval.

Added self-contained #59 checker mutation tests: every one of the 1152
checked cells must reject trailing lake attributes, both maps must reject
missing water color, and wrong scene/identity/material policies must fail.
These complement, rather than replace, the fresh expanded emulator gate.

All 93 selected regression unit tests pass (51.740 seconds), including the
palette candidate's source-build fallback without a prebuilt fixture.
The current retry ROM also passes the fresh 900-frame Timer guard in
`tmp/title-retry-stage2-timer-observed-01/timer-check.json`: 1342 interrupts,
14 serviced inside the compiler, maximum gap117792 cycles below the
unchanged141312 limit. The matching `*-plain-01` capture is byte-identical
in full PCM, video, state and timeline. This establishes bounded Timer
service and observer neutrality for the current ROM, not cross-ROM
perceptual equivalence. The final Stage2 screenshot was inspected.

The short visual/stimulus gates now pass, so the next full current-source
campaign is `tmp/title-retry-full-suite-02`. Production source is frozen
for that run. The unresolved unequal-start cross-ROM audio diagnostic is
not waived or relabeled as a pass by launching broader visual tests.

### Full current-source matrix:97/97 pass

`tmp/title-retry-full-suite-02/manifest.json` finished successfully at
2026-10-07T10:35:33Z (session4261 exit0). All97 gates passed; both
`source_inputs_intact` and `rom_hashes_intact` are true. The run began at
09:54:39Z, about40 minutes54 seconds earlier. All three former outer-gate
failures now pass, as do all three restart routes and both strict native
low-health determinism pairs. The Stage5 speed ratio0.9646 uses the existing
0.95 accepted floor; the nine-seed movement ratio0.9732818974 meets its
existing0.97 floor. No new slowdown allowance was introduced.

This direct matrix is not the two-source-build deterministic publication
receipt required for committing production changes. The source-profile v3
draft under `tmp/title-retry-profile-draft-01` is not promoted yet.

A coverage review found that the normal-health Stage2 soak visits4 rooms
over8000 frames but reports material_expected0. The separate low-health
settled-map check has actual water exposure, but its firing-only follow-up
has one world position and one scroll position. Neither proves low-health
scrolling consistency. A draft visible-palette checker under
`tmp/check_stage2_scrolling_draft.py` rejects8 of360 visible cells in the
retained parent frame4200 and passes the retry frame4200 (8 water cells).
It also requires actual player and scroll movement, so page alternation or
stationary correct colors cannot qualify this missing case. Fresh240-frame
right-input captures from each exact ROM's own authenticated frame4200 are
running at `tmp/title-retry-scroll-{parent,candidate}-01`. The native startup
barrier is enabled; all reused adapter dependencies and both checkpoint/ROM
receipt bindings were revalidated first. No second emulator ran concurrently.

### Scrolling regression completed and added to the permanent gate

Both captures completed with status 0 and valid native restoration epochs.
`check_stage2_scrolling.py` revalidates all six native capture hashes and the
source state, preserves all unsupported frames as failures, and checks every
visible palette cell. The parent fails all 240 frames (168 unsupported LCD/
window frames and 3,228 mismatched cells across the other frames). The retry
candidate passes all 240, with actual camera/player movement, low-health
exposure and visible water. This is palette consistency, not a tile-geometry
or audio-fidelity claim. Both final screenshots were visually inspected.
The captured overlap was also counted explicitly: all 240 candidate frames
are low-health frames with visible water, spanning four distinct scroll
positions. Water and low-health coverage are not disjoint in this replay.

The expanded permanent boss handoff gate passed at
`tmp/title-retry-scroll-gate-01/result.json`, including its own fresh cold
prefix, assisted late boss defeat, settled maps, unassisted right-only
scrolling, and secret-return visibility. Ten viewport/settled-map unit tests
pass, including both pages, wraparound, missing water and stale water colors.
Issue #59 remains open for hardware retest. The source profile is now v3 and
builds the same exact 12686128 ROM; final two-source-build publication
qualification must still pass before the previous release receipt is replaced.

The final source-publication campaign is running at
`tmp/title-retry-source-suite-01` (launcher session 11916). Both independent
fresh builds produced the exact 12686128 candidate and `run.json` records
`deterministic_build: true`; the complete serial matrix is now running.
Production inputs are frozen for this run. The separate selected unit sweep
passed 98 tests in 41.185 seconds without skips; the promoted source-profile
and palette-candidate tests also passed (16 tests including viewport tests).
Do not treat a running matrix or the old publication receipt as final approval.

### Publication inventory regression (#68), repaired before retry

Session 11916 terminated with exit 1 after its matrix passed all 97 gates.
The matrix ran from 10:45:54Z to 11:23:27Z, preserving source, runtime and ROM
integrity. The final wrapper rejected it with `expected 95 emulator gate
results, found 97`, so it emitted no publication receipt. Its `run.json`
remained labeled matrix-running despite the terminal process; that file is
preserved as failed-run evidence, not used to infer a live process.

Issue #68 records the cause: candidate-specific gate insertion depended on a
real ROM path, while the publication validator uses the authenticated SHA and
a missing placeholder path. Four exact supported hashes reproduced the
95-versus-97 mismatch in a new test. Gate selection now uses the already
authenticated identity in both cases; unknown identities and conflicting
actual-ROM/SHA inputs remain rejected by their respective contracts.

The deterministic runner now preflights actual/hash-only gate inventories
before launching its long matrix. It also records terminal matrix/receipt
evidence errors instead of leaving dead runs marked running. Twelve
inventory/source-profile tests pass, including deliberate roster drift,
conflicting identity, terminal rejection, and no receipt emission on a mere
successful preflight. The real candidate inventory and a read-only collection
of the retained nested ledger pass. No prior manifest or receipt was relabeled,
no gate was removed, and ROM bytes did not change.

Fresh qualification is `tmp/title-retry-source-suite-02`. It must complete
with current source bindings before publication/merge. The previous complete
runtime results remain evidence about the exact ROM, not a substitute for
that missing publication receipt.

## Source-suite-02 completed; publication inventory repair verified

The fresh campaign completed at 2026-10-07T12:17:42.423355Z, starting at
11:29:56.722125Z (47m45.7s including builds and receipt work). Session22790
terminated with exit0: 97/97 serial gates and two byte-identical source builds
of SHA256 `126861281b75edaf8daace834ccbe41e53ed0c9eebb71e50fe3bd6823e8b6941`.
The runner emitted `docs/release/verification/latest.json`; the standalone
receipt verifier passes with the same pinned r454 library environment.
Running that verifier without LD_LIBRARY_PATH first failed runtime identity
admission, as intended; no evidence was changed to work around that check.

The generated web audit is `tmp/title-retry-source-suite-02-web/index.html`:
236/260 machine-covered items, 559 unique images, 24 explicit missing items
in two categories (optional miniboss/projectile galleries). The rendered page
was inspected and labels the exact candidate, emulator-only scope and gaps.
It is not a complete human visual review. File-URL rendering cannot persist
server checkpoints; use the checked-in local review server for that feature.

Issue #68's runtime/hash-only inventory mismatch is resolved by this actual
successful publication, not only unit tests. Hardware reports remain open.
The separate #34 Select experiments under `tmp/select-current-canonical-trial-01`
are BUILT_NOT_TESTED and do not change this qualified ROM. The full objective
is still incomplete: input qualification, hardware retest and explicitly
documented visual/performance limitations remain; no all-bugs-fixed claim.
