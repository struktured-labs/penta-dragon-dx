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
