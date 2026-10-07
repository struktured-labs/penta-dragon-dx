# October 6 regression retest — emulator-qualified October 7

Candidate SHA-256:
`6c4a9654b5c6dad70c8ea21bfd39b6e53766a3cd1a642153c6085774392ec228`

This is not a release-ready declaration or a hardware pass. See
[the evidence log](playtest_20261006.md) for implemented changes and limitations.
The full source-bound run passed97/97 checks with two byte-identical builds;
[the receipt](../release/verification/latest.json) records the exact bindings.
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
6. Exercise Continue after a death, then Game Over and a fresh new game. Check
   title colors, both stage-card variants where encountered, and Stage 1 terrain
   after restart. The native Continue confirmation is A; report input trouble
   separately from the intentional countdown expiring.

If something fails, note the recording timestamp and last action, and capture
the first bad screen before resetting. Distinguish a transient flash from
persistent corruption. A clean replay of one route does not close unrelated
open issues or prove all stages, audio, and hardware configurations.
