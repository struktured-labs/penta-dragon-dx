# Final verification runbook — Ted promotion → stream-ready

The exact sequence from "Ted candidate accepted" to "candidate ready for the
palette stream", with owners. Complements `docs/stream_runbook.md` (which
owns the stream itself and post-stream release steps). Written 2026-08-17
while Ted v8 (`dbf33612…`, exact Aug-12 base + expanded Ted banks) was
finishing its gate battery.

## 0. Preconditions (state as of writing)

- Ted v8 passes: 2800×2 determinism (47-pose contract, zero mismatches),
  stage-1 north-route (0/576 packed-room diffs vs Aug-12), rendered 920
  contract, strict geometry. Open items: entry-ceiling re-derivation
  (144+17+margin), 13/14 defer cadence-correlation gate.
- `rom/working/penta_dragon_dx_FIXED.gb` currently holds a stale Aug-14
  experimental build that is **cold-boot broken in the dungeon** — it must
  be REPLACED at promotion, never used as a base.
- Stage sweep, cutscene/menu review, speed close-out: done
  (`docs/audit/stage_sweep_2026_08_17.md`, `docs/release/known_deviations.md`).

## 1. Promotion (Codex lane)

1. Rebuild the candidate from a clean builder state (commit or stash the
   in-flight diagnostics first so the build is reproducible).
2. `python3 scripts/launch_gate.py rom/working/penta_dragon_dx_FIXED.gb`
   — must exit 0.
3. Stage-1 cold-boot entry check (any of: north-route receipt, or one
   `capture_stage_side_by_side.py --stage 0` panel showing colored play) —
   guards the exact regression class found on the Aug-14 build.
4. Announce promotion on the `penta-dragon-dx` intercom with the new MD5.

## 2. Independent visual passes (Claude lane, fires on the promotion ping)

1. Full stage sweep vs OG:
   `python3 scripts/diagnostics/capture_stage_side_by_side.py rom/working/penta_dragon_dx_FIXED.gb --output tmp/stage-sweep-promoted`
   — expect 7/7 CLEAN as with the Aug-12 baseline.
2. 8-boss OG/DX side-by-sides (Ted covered by its own battery):
   `capture_boss_side_by_side.py --target {0,1,2,3,5,6,7,8}` with the
   freshest state pairs — review contact sheets for bleed/fragments/seams.
3. File verdicts in `docs/audit/`; any regression blocks step 3.

## 3. Matrix re-green (both lanes)

1. `python3 scripts/diagnostics/verify_release_candidate.py` full roster.
   Expected reds to clear with promotion: the ~20 ted_* gates, boss gates
   blocked behind them, and the Aug-14-build artifacts.
2. Receipt bookkeeping must remain explicit:
   - `boss_trajectory_pairing` must pair all nine bosses and its phase-shifted
     same-ROM null must remain exactly 0.00%.
   - The top-level release ledger must retain every accepted target miss.
   - Ted entry ceiling must retain its provenance comment.
3. Deterministic suite double-build (`run_deterministic_suite.py`) for the
   hash-bound receipt.

## 4. Pre-stream

1. `verify_live_regression.py` live profile against the promoted candidate.
2. `docs/stream_runbook.md` takes over: palette session, audience vote,
   `record_palette_approval.py`, reservation-backed MiSTer pass
   (Audio = "No Pops"), then `build_release_bundle.py` for the final
   packaging with both approval manifests.

## Known accepted deviations at ship time

See `docs/release/known_deviations.md` — remaining dungeon ~3% pace,
matched-work boss throughput, Crystal's accepted slowdown and 1-cell wrap
seam, title-attract duration, Ted's pending effect choice, and the DX footer.
