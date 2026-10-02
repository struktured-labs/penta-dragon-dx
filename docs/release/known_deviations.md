# Known deviations from the original game (release notes source)

Measured differences between Penta Dragon DX and the original DMG game, with
their current acceptance state. Anything not listed here that differs from the
original is a defect, not a deviation.

## 1. Dungeon pace: Stage 5 is 2.15% slower (ACCEPTED)

The restart-successor receipt (`docs/release/verification/latest.json`, 2026-09-16)
measures Stage 1 at 1.0000, Stage 2 at 1.0066, Stage 3 at 1.0000, Stage 4 at
1.0039, **Stage 5 at 0.9785 (2.15% slower)**, and Stage 6 at 1.0040. The
separate Stage-7 world-position route measures 0.9972 after bounded vertical
settling and reaches equal endpoints. Stage 5 is now the only stage outside
the symmetric 2% target, and misses it by 0.15 percentage points.

**Correction (2026-08-31):** this section previously quoted Stage 1/5/7 at
0.970/0.968/0.974 with a 0.96 floor. Those figures came from the superseded r9c
receipt. Stage 5 regressed from 0.968 to 0.9506 during the death/ending work,
and the release runner's accepted-slow floors were lowered to **0.95** for
stages 1/2/3/5/7 in the same commit window — so the doc, the gate, and the
receipt disagreed until now. The floors in
`scripts/diagnostics/verify_release_candidate.py` are the authority; this text
now matches them.

**Operator decision (2026-08-31):** the measured ~5% Stage 5 slowdown is
accepted for 1.0, consistent with the standing "6% slow is acceptable but I
wish we could do better" ruling. Revisit as post-release optimisation, not as a
ship blocker.

The speed gate remains **one-sided** per the 2026-08-18 ruling: slower is the
binding concern, mild speed-ups are acceptable. The release runner retains the
symmetric 2% target, reports every target miss, and accepts only bounded
slowdowns at or above the explicit **0.95** floor. The r536 result is much
closer to parity than the earlier 0.9506 measurement, but remains listed until
it reaches the strict target. Any future floor change must be accompanied by
an operator ruling recorded here.

## 2. Boss arenas: matched-work throughput differences (ACCEPTED)

The release matrix now samples the boss-phase vector on every arena-loop
iteration, aligns OG/DX transition streams, and compares only matched spans.
Both sides replay twice, and an intentionally phase-shifted same-ROM control
must measure exactly 0.00%. Negative figures below mean DX completes the same
arena-loop work faster:

- Shalamar -5.08%, Riff -4.39%, Crystal Dragon +2.47%
- Cameo -16.36%, Ted +0.56%, Troop +0.86%
- Faze -12.52%, Angela -15.86%, Penta Dragon -13.05%

The matched-span loop result and a second frames-per-matched-transition result
agree in direction for every boss. This means the larger speed-ups are real boss-state
transition cadence, not merely a loop counter or fixture-phase artifact.
All-nine deterministic semantic-cadence, geometry, material, and silhouette
gates pass. Every >2% speed-up is promoted into the top-level exception ledger
rather than hidden behind a green policy result. Current evidence is bound by
the `release_ledger` in `docs/release/verification/latest.json`; the retained
nested artifact is
`tmp/restart-publication-suite-20260916-03/matrix/artifacts/boss-trajectory-pairing.json`.

**Operator ruling (2026-08-18), verbatim:** *"its ok to be faster than stock
slightly I think, honestly my real concern is slower."* The speed requirement
is therefore ONE-SIDED: slowdowns bind, bounded speed-ups do not. Two
consequences the release policy inherits:

- Do NOT risk terrain, publication, or animation correctness merely to pull a
  faster build back toward parity. A candidate measuring faster than the
  original remains compliant under the operator's one-sided ruling, but the
  12–16% cases are explicitly recorded for later tuning rather than called
  "slight" or dismissed as instrument noise.
  The ±2% symmetric target remains as *telemetry* — every miss stays visible
  in the receipt — but only the slowdown side is a release bound.
- The speed-up ceiling (1.20) is a **divergence detector**, not a fidelity
  gate. It exists because large apparent speed-ups have twice indicated
  instrument or pairing defects (the parked-frame denominator artifact and
  the DF5A cache-key collision), so a trip means investigate the measurement
  — never slow the ROM to satisfy it.

**Crystal Dragon slowdown — operator ratified (2026-08-18):** the current
2.47% measured slowdown is a *known accepted issue*: not a
stream-stopper and not a 0.9/beta-release stopper, but the operator would
like it fixed eventually. Tracked as post-release work, not a gate.

**Ted slowdown — recovered in r536:** the current matched-work result is only
0.56% slower and is inside the strict 2% target. The old `ted=0.975` accepted
floor remains historical policy, not an exception consumed by the current ROM.
Troop is likewise inside target at 0.86% slower. Crystal Dragon is the only
current boss slowdown outside the strict target.

## 3. Title attract demo: complete route 9.51% longer (ACCEPTED)

The complete prerecorded Stage-1 plus Gargoyle sequence is 2,465 frames
versus 2,251 in the original. Its internal scene boundary is phase-sensitive:
constant-width service controls redistribute over 100 frames between the two
segments without changing the combined duration. The gate therefore treats
the segment figures as advisory and enforces a tighter 15% envelope on the
complete player-facing sequence while retaining every visual, palette, route,
and returned-title cleanup assertion. Full evidence:
`docs/audit/title_attract_timing_2026_08_18.md`.

## 4. Crystal Dragon: one wrap phase-seam cell

The portal's cached dual-tilemap colorization allows exactly one
entry-layout cell (row 4, col 15) to sit on either side of a native camera
wrap, depending on serialization order. The strict verifier permits one such
cell and rejects two or more (`boss_geometry_contract.py`). Invisible in
practice.

## 5. Native visual states the original hides in grayscale

Colorization makes some original-game intermediate states visible that DMG
grayscale masked (e.g., Ted's camera-wrap half-frame, fixed by atomic
dual-GDMA publication in the Ted rework; pose cells that are detached in the
native art, such as Ted pose 4's floating orbs, are preserved as-is).
Anything of this class that remains should be indistinguishable from the
original's own animation when compared side-by-side in grayscale.

## 6. Ted: stabilized whip/orb sparse plane during native staging phases
**(PENDING OPERATOR RATIFICATION — clip review or MiSTer `boss_arena`
checkpoint)**

The original game's Ted alternates its sparse whip/orb cells between fully
drawn and absent every 5–6 frames (~10 Hz) during one native staging phase
(classifier key 14, measured frames 1045–1231 of the reference window) — a
DMG pseudo-transparency idiom. The DX candidate holds the last complete
pose instead, keeping the whip solid; motion is otherwise preserved
(containment gate: 486 tentacle-expansion frames, 0 violations over 3600).
Rationale: a colorized ~10 Hz strobe of red cells reads far harsher than
the DMG ghost. Counter-precedent: Crystal Dragon's translucency flicker was
deliberately PRESERVED — so this is a taste call, not a technical one, and
ships only if the operator ratifies the side-by-side clip
(`tmp/ted-native-delta-v8-side-by-side-60s/og-vs-dx.mp4`, 60.000 seconds,
1280x620 at 60 fps, SHA-256
`f201a00a71e8759822e7c32f6f079e4713d195cad60911f41264fc73110687c4`).
If ratified, this entry stays; if not, the publisher reproduces the native
alternation.

## 7. Title screen footer

`DX V3.01 STRUK LABS` replaces the original copyright row — intentional
branding, custom 2bpp digits.

## Gate bookkeeping note

`boss_publication_cadence` remains an event-rate telemetry gate, not the
player-speed authority. It preserves the ±1% target, requires raw A/B
deterministic replays, rejects dead publishers, and bounds phase-shifted ratios.
Ted's current publication ratio is 0.99384, a 0.62% slowdown inside target.
`boss_trajectory_pairing` is the magnitude-valid arena-loop authority: Ted
measures 0.56% slower over matched work and remains inside the ±2% target. The
legacy bounded parity gate is retained as an independent liveness/policy check,
not as the quoted magnitude.
