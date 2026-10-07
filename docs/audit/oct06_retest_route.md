# October playtest regression retest

Candidate SHA-256:
`126861281b75edaf8daace834ccbe41e53ed0c9eebb71e50fe3bd6823e8b6941`

This is not a release-ready declaration or a hardware pass. See
[the latest evidence log](later_lowhealth_dispatch_20261007.md) for implemented
changes and limitations. The direct matrix passed 97/97 checks and the new
240-frame low-health scrolling gate passed. After repairing the publication
gate-roster bug (#68), the fresh source-bound campaign passed all 97 checks,
produced two identical builds, and emitted the current
[receipt](../release/verification/latest.json) for this exact revision.
Do not load a savestate made with another ROM. Begin with a fresh boot of the
qualified candidate; keep the recorded older run intact.

## One continuous playthrough

1. Start Stage 1. Check ceiling-overhang priority and projectile colors while
   using the large front/back weapon near enemy shots. Mild Sara tearing is the
   existing accepted deferral, not permission for new missing graphics.
2. Enter the first secret area. Move both forward and backward, collect the
   star, and open/close the item menu. Watch for even a brief garbage-tile flash.
3. Return to Stage 1 and keep moving. Check for yellow trails, inconsistent
   scenery colors, and a map that only repairs after scrolling or pausing.
4. Continue into Shalamar without resetting. Observe boss arrival, combat,
   low-health behavior if encountered, defeat, and the score/Stage 2 cards.
   Look for corrupted side tiles, stale bullets, a broken boss, or a freeze.
5. In Stage 2, move and reverse direction past scenery. A cyan/yellow shape
   must not remain attached to the screen while terrain scrolls underneath it.
   Repeat at low health if practical: the prior fault involved that mode, so a
   normal-health-only replay is insufficient to confirm it is gone.
6. Exercise Continue after a death, then Game Over and a fresh new game. Check
   title colors, both stage-card variants where encountered, and Stage 1 terrain
   after restart. The native Continue confirmation is A; report input trouble
   separately from the intentional countdown expiring.

If something fails, note the recording timestamp and last action, and capture
the first bad screen before resetting. Distinguish a transient flash from
persistent corruption. A clean replay of one route does not close unrelated
open issues or prove all stages, audio, and hardware configurations.

## Explicitly not claimed fixed

- Mild Sara tearing (#6), accepted by the player as non-blocking for first release.
- The short Select-press issue (#34): the release-lock build does not include
  the experimental input buffer. This is separate from Continue confirmation.
- Stage 7 speed work (#52), tracked as post-release; passing the current
  speed bounds is not a claim of identical stock cadence in every situation.
- Hardware palette-bridge behavior and art-direction approval still require
  direct confirmation; emulator captures cannot supply those approvals.
