# Ted failure: incorrect dynamically loaded emulator library

The September 15 Game Over candidate's Ted failures reproduced on the unchanged
r536 ROM. The September 14 passing run used the same mGBA executable, but **not
the same runtime library**. Comparing executable hashes alone was insufficient.

| Runtime | libmgba SHA-256 | Current Ted entry result |
| --- | --- | --- |
| Installed, uncorrected | `df25d1ecfdd1bb3acab3be96e0c2c00848c475c51ecfb4354828fda334e355e4` | White arena; rejected |
| Documented CGB-latch correction | `20fa5ddaf77abed9cf55972616242a232181a04fb1d52bf3e38e58e7b809b4cf` | Pass, frame 301, settled frame 287 |

The corrected-runtime result holds for both r536
`b93ebc46ed4ac23ec7d2c44d80fae1ae1538b38c038bab0ba8173b93fe252350`
and the Game Over row-guard candidate
`e709869c85edfd647dd01dbca0c222a493b335ee6759adaa573416143a66e45b`.
No ROM bytes, entry budgets, or visual assertions changed to obtain these passes.
Fresh artifacts are under `tmp/ted-research-qualified-library-01` and
`tmp/ted-research-row-guard-qualified-01`.

The [existing register-level audit](mgba_cgb_latches_r454.md) explains the
failure: the installed library mishandles FF72–FF74, including Ted's GDMA
destination latch. This also invalidates conclusions drawn from the exploratory
old-state replays under that library. Those captures remain useful as bad-runtime
controls, not as evidence of a newly established production Ted defect.

The release matrix now rejects this exact known-broken library for CGB ROMs
before launching an emulator, checking both Qt and headless dependencies.
Unknown future builds are not automatically qualified; normal full gates and
runtime fingerprinting still apply. A negative preflight run is retained under
`tmp/ted-runtime-preflight-negative-01`.

The matrix's Game Over restart gate now enables the extended traversal oracle:
matching terrain after each of two Game Over/title/restart cycles, including
three camera checkpoints. It does not compare only the initial spawn screen.

## Completed qualification

`tmp/gameover-row-guard-full-integration-qualified-01/manifest.json` now reports
**88/88 passed**, full scope, zero failures, with ROM, source, and runtime
identities intact. The read-only full-manifest verifier independently accepted
the complete current gate roster afterward.

The initial corrected-runtime attempt passed 86 gates, but the sandbox denied
the local socket required by the browser palette editor; its dependent story
check was blocked. The original failure manifest and log are preserved in the
run's `sandbox-denial/` directory. The checked resume path reran only those two
gates with loopback permission, after verifying unchanged ROM/source/runtime
identities. Both passed. A first resume attempt rejected the logical versus
physical checkout spelling in LD_LIBRARY_PATH; the successful resume used the
original exact path spelling, with no library change.

This is not a combination with the older uncorrected-runtime 69-pass run.
Ted entry, all-nine boss geometry, Ted determinism/cadence, all-seven stage
comparisons, endings, death/Game Over, extended restart traversal, and palette
editing all passed under the corrected runtime.

The baseline control `tmp/gameover-baseline-qualified-negative-01` still fails
the identical extended restart verifier under that same corrected runtime:
`rendering changed: title-before.png -> title-after-1.png`. The candidate passes
both restart cycles and all three terrain checkpoints per cycle. Thus the
Game Over correction is independently necessary; it is not explained away by
the emulator-library correction.

Hardware and human visual acceptance remain separate. No MiSTer deployment or
human approval is implied by these emulator results.
