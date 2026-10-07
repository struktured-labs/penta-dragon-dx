# Current-candidate secret-return visibility (#45)

The October candidate (`6c4a9654b5c6dad70c8ea21bfd39b6e53766a3cd1a642153c6085774392ec228`)
was replayed from its own retained frame-6960 checkpoint, with pulsed A for
240 frames and a screenshot/state at every frame. The short restored replay
does not write game memory; the cold ancestor's position/health assistance
remains a limitation. This is not the exact OBS input history.

In `tmp/current-secret-return-boundary-01`, scene 02 begins at relative frame
111. Frames 111–115 contain unfinished map cells but render uniformly white.
Frame 116 has the complete map. In the 70-frame boundary window there are
five hidden unfinished frames, 15 hidden complete frames, and 50 visible
complete frames. Frames 115, 140 and 180 were visually inspected: blanking,
coherent intermediate fade, and coherent resumed dungeon respectively.

`check_secret_return_visibility.py` records every checkpoint hash and compares
the selected physical map's 24×24 area with native C1A0 source data throughout
that window. It rejects exposed mismatches, missing frames, a truncated or
wrong transition, permanent blanking, and failure to resume gameplay. Five
unit tests include deliberate exposed-cell and wrong-page negative controls.
The existing boss-handoff integration verifier now performs this short replay
from its own cold-generated candidate checkpoint and requires the check.

This extends regression coverage; it does not change the ROM or promote the
unqualified late-fade experiment. Encoded checkpoints are not continuous native
AV capture. Full native audio/timing equivalence and hardware acceptance remain
separate; the exact recorded Stage 2 lake patch is not reproduced here. Keep
#45 open while its broader qualification remains incomplete.

Full source qualification completed in `tmp/return-visibility-full-suite-01`
on 2026-10-07, 04:26:38–05:08:45 UTC (42 minutes 6 seconds): all 97 serial
gates passed and two fresh builds produced the unchanged ROM hash above.
The source fingerprint is
`3f2c77f0ce62055310048674f764157473a94e2f45fcd6cd8c8577a7daaf9ffe`.
The source-bound receipt is `docs/release/verification/latest.json`.
The five focused unit tests also passed without skips. This is offline
qualification, not a claim that the recorded lake/trail symptom is resolved.
