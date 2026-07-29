# Emulator release receipt — `67cf1235`

- Candidate ROM MD5: `67cf123591765e8113e4cdb09dc80448`
- Supported base ROM MD5: `df43e0adfdc74b2829c7e95e91c71a28`
- IPS: 6,571 bytes, MD5 `f63e57b4470ff0010315281f504b3b58`
- Emulator matrix: 32/32 passed; source and isolated ROM hashes remained exact
- Hardware: pending the reservation-backed MiSTer sweep

## Speed

All routes count the stock main-loop entry at CPU `$016C` for 600 rendered
frames after 120 consecutive stable frames in the exact requested scene.

| Route | Stage 5 | Stage 7 |
|---|---:|---:|
| Right | 156/164 (95.1%) | 153/167 (91.6%) |
| Stationary | 166/171 (97.1%) | 170/170 (100%) |
| Patrol | 133/166 (80.1%) | 149/163 (91.4%) |

Stage 1 rightward gameplay is 139/141 (98.6%). The Stage 5 patrol is the
remaining worst case and contains 40 real lava-layout changes.

## Integrity and visual comparison

The six `stage*-soak8000.report` files cover 48,000 total gameplay frames,
rooms 1/3/5/7 in every stage, and report zero unsafe attributes, unexpected
attributes, or Stage 5/7 lava mismatches.

`stable-vs-candidate.png` contains 24 labeled pairs (48 native 160×144
captures). The candidate is the exact promoted ROM. The stable side is MD5
`7cfe7b6c0c4424476c026240fcd78127`.

`emulator-matrix.json` is the complete hash-bound 32-gate manifest. The four
package screenshots under `artifacts/` make this receipt directory directly
usable by `scripts/build_release_bundle.py`; two independent builds produced
the identical PREHARDWARE ZIP SHA-256
`4eba57d62de700fb07724ad75d511f5c1176d9b1a078f282b70f18adafb1e5e9`.
