# Known deviations from the original game (release notes source)

Operator-reviewed list of measured, accepted differences between Penta
Dragon DX and the original DMG game. Anything NOT listed here that differs
from the original is a defect, not a deviation.

## 1. Dungeon pace: ~3% slower in the remaining slow stages (ACCEPTED)

The current qualified r9c input-identical receipt measures Stage 1 at 0.970,
Stage 5 at 0.968, and Stage 7 at 0.974. Stages 2/3/4/6 pass at
1.019/0.986/1.016/0.992. Stage 7's direction is reliable but its exact
magnitude remains route-confounded (70 versus 120 scroll changes). Earlier
~6% figures describe the superseded Aug-16 build, not r9c. Operator decision:
the remaining ~3% dungeon compromise is acceptable for 1.0; revisit only if
players report it. Current receipt:
`tmp/menu-icons-candidate-r5/deterministic-suite-r7/matrix/artifacts/gameplay-speed/manifest.json`.
The release runner retains the symmetric 2% target, reports every target
miss, and accepts only bounded slowdowns at or above the explicit 0.96 floor;
it does not excuse speed-ups outside the 2% envelope.

## 2. Boss arenas: matched-work throughput differences (ACCEPTED)

The release matrix now samples the boss-phase vector on every arena-loop
iteration, aligns OG/DX transition streams, and compares only matched spans.
Both sides replay twice, and an intentionally phase-shifted same-ROM control
must measure exactly 0.00%. Negative figures below mean DX completes the same
arena-loop work faster:

- Shalamar -1.25%, Riff -11.51%, Crystal Dragon +3.86%
- Cameo -15.81%, Ted +1.94%, Troop -13.04%
- Faze -11.72%, Angela -14.88%, Penta Dragon -11.60%

The matched-span loop result and a second frames-per-matched-transition result
agree for every boss. This means the larger speed-ups are real boss-state
transition cadence, not merely a loop counter or fixture-phase artifact.
All-nine deterministic semantic-cadence, geometry, material, and silhouette
gates pass. Every >2% speed-up is promoted into the top-level exception ledger
rather than hidden behind a green policy result. Current evidence:
`tmp/menu-icons-candidate-r5/deterministic-suite-r7/matrix/artifacts/boss-trajectory-pairing.json`.

**Operator ruling (2026-08-18), verbatim:** *"its ok to be faster than stock
slightly I think, honestly my real concern is slower."* The speed requirement
is therefore ONE-SIDED: slowdowns bind, bounded speed-ups do not. Two
consequences the release policy inherits:

- Do NOT risk terrain, publication, or animation correctness merely to pull a
  faster build back toward parity. A candidate measuring faster than the
  original remains compliant under the operator's one-sided ruling, but the
  11–16% cases are explicitly recorded for later tuning rather than called
  "slight" or dismissed as instrument noise.
  The ±2% symmetric target remains as *telemetry* — every miss stays visible
  in the receipt — but only the slowdown side is a release bound.
- The speed-up ceiling (1.20) is a **divergence detector**, not a fidelity
  gate. It exists because large apparent speed-ups have twice indicated
  instrument or pairing defects (the parked-frame denominator artifact and
  the DF5A cache-key collision), so a trip means investigate the measurement
  — never slow the ROM to satisfy it.

**Crystal Dragon slowdown — operator ratified (2026-08-18):** the ~3.9%
measured slowdown (0.95 floor) is a *known accepted issue*: not a
stream-stopper and not a 0.9/beta-release stopper, but the operator would
like it fixed eventually. Tracked as post-release work, not a gate. It is the
only approved slowdown in the matrix; no other boss may carry one without a
fresh operator ruling recorded here.

## 3. Title attract demo: complete route 11.55% longer (ACCEPTED)

The complete prerecorded Stage-1 plus Gargoyle sequence is 2,511 frames
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
**(PENDING OPERATOR RATIFICATION — stream-day clip review)**

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
(`tmp/ted-native-delta-v8-side-by-side-60s/og-vs-dx.mp4`). If ratified,
this entry stays; if not, the publisher reproduces the native alternation.

## 7. Title screen footer

`DX V3.01 STRUK LABS` replaces the original copyright row — intentional
branding, custom 2bpp digits.

## Gate bookkeeping note

`boss_publication_cadence` remains an event-rate telemetry gate, not the
player-speed authority. It preserves the ±1% target, requires raw A/B
deterministic replays, rejects dead publishers, and bounds phase-shifted ratios
to 0.95–1.20. Ted's 0.9860 publication ratio is an explicit 1.4021% accepted
target miss in the top-level ledger. `boss_trajectory_pairing` is the
magnitude-valid arena-loop authority: Ted measures 1.9391% slower over matched
work and remains inside the ±2% release target. The legacy bounded parity gate
is retained as an independent liveness/policy check, not as the quoted
magnitude.
