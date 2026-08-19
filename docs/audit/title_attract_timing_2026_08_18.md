# Title attract timing audit — 2026-08-18

Candidate: `tmp/source-native-route-relocated-cadence0-r9c.gb`, SHA-256
`e37e90c5573415ab7295d72ac0a2d230d666ed9d6322d2be1445a316841abf4e`.

The natural title route measures 2,511 frames for the complete prerecorded
Stage-1 plus Gargoyle sequence versus 2,251 in the original: 11.55% longer.
The two internal D880 segments measure 2,001/1,856 and 510/395, respectively.
Receipt: `tmp/source-native-route-relocated-cadence0-r9c-title-idle-reel-r7.summary.json`.

The internal boundary is not a stable player-facing speed metric. Seven
hash-bound attribution ROMs NOP exactly one constant-width VBlank call while
preserving every other candidate byte (plus the global checksum). Death,
prelude, title-palette, palette-idle, and glyph controls move as many as 121
frames between the Stage-1 and Gargoyle identities while the complete route
remains 2,510–2,515 frames. Examples:

- prelude disabled: 2,080 + 431 = 2,511;
- death service disabled: 2,054 + 456 = 2,510;
- glyph-copy disabled: 2,122 + 393 = 2,515.

Those are attribution controls, not viable builds: removing prelude leaves
gameplay sprites on the returned title; removing the full colorizer prevents
the spotlight actor from completing. The negative receipt remains at
`tmp/perf-attribution-r9c/title-prelude-negative-r2.summary.json`.

The release gate therefore retains both internal durations as advisory
telemetry and gates the complete sequence against a tighter 15% OG envelope,
in addition to exact spotlight palettes, travel, Gargoyle palette, prerecorded
route identity, returned-menu OAM cleanup, and return-to-spotlight behavior.
The current 11.55% attract-only difference is recorded as an accepted
performance compromise; ordinary gameplay has its independent seven-stage
main-loop gate.
