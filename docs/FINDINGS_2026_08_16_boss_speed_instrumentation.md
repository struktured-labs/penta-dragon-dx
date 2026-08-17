# FINDINGS 2026-08-16: Boss-arena speed — instrumentation, measurements, and the state-pairing confound

**TL;DR: There is no valid evidence that boss fights run ~5% slower than
vanilla. The measurable deviation runs the other way — on the Aug-12
checkpoint (`832dd43b`, commit `fef1739`), five of nine arenas iterate
7–17% FASTER than OG, crystal_dragon is ~+2.9% slower, riff/penta are near
parity. The per-boss magnitudes carry an unresolvable trajectory confound
(direction is robust, sizes are not). The only speed gate free of that
confound remains `gameplay_speed_parity`, whose Stage 7 failure (0.850) is
the one hard speed regression in the project.**

Receipts: `tmp/boss-speed-parity/` (gitignored). New tools (committed):
`scripts/diagnostics/probe_boss_speed_parity.lua`,
`scripts/diagnostics/verify_boss_speed_parity.py`.

## 1. The arena main loop is not $016C

The dungeon speed gate counts main-loop executions at `$016C`. Measured in
shalamar's arena (599 in-scene frames): **zero hits**. Arenas park inside
`1A6F: CALL 4000` (bank 2 mapped) for their whole life — `$1A72` stays on
the stack — and iterate a loop headed at **bank2:$406F**; `$4083`
increments the `FFCD` phase counter exactly once per iteration
(`PUSH AF; LDH A,[CD]; INC A; AND 03; LDH [CD],A; POP AF`).

Validation: breakpoints at $406F and $4083 fire identically (45/45 OG,
46/46 DX per 240 frames), `FF99` bank shadow reads `$02` at 100% of hits
on both ROMs, and bank2:$4000–$40A0 is byte-identical OG↔DX. The verifier
enforces `raw_anchor_hits == filtered hits` so foreign-bank pollution can
never silently corrupt the count. Iteration rate ~0.19/frame (~5.3
frames/iteration) matches the publication cadence mean gap (~5), confirming
publications ride the loop.

## 2. Measured results (Aug-12 checkpoint ROM vs vanilla)

Fresh same-session state pairs, 7200-frame windows, warmup 120, keep-alive
writes identical on both sides:

| boss | DX vs OG loop rate | note |
|---|---|---|
| shalamar | **−10.6%** (DX faster) | +4.8% at 1800 frames — window-sensitive |
| riff | ≈−3% | |
| crystal_dragon | **+2.9% (DX slower)** | only slower boss; from older pairs |
| cameo | −17.0% | |
| ted | −17.1% | matches cadence receipt's −14.5% |
| troop | −7.3% | |
| faze | −9.6% | |
| angela | −20.6% (older pairs) | DX-side fresh generation failed (see §5) |
| penta_dragon | ≈parity (−0.4%, older pairs) | stock-side generation unsupported (§5) |

Direction is stable across two instruments (loop rate here, publication
cadence gaps historically), two independent state generations (Aug-11
og-states + Aug-12 matrix states; fresh same-session pairs), and 1800 vs
7200-frame windows.

**The `4.58%/4.59%` slowdown figures in `fef1739`'s commit message came
from a 600-frame cadence run on phase-mismatched pairs — instrument noise
on the two bosses nearest parity.** The consistent story is DX-faster, and
this is a fidelity bug in its own right: bosses animate and attack faster
than the original game.

## 3. Mechanism facts (shalamar, measured)

- **VBlank ISR duration** (entry `$06D1` → RETI `$081D`): OG median **3**
  scanlines, DX median **6**, p90 7. The colorize handler costs ~3
  scanlines ≈ **2% of frame budget** — real, small, bounded. It cannot
  explain DX-faster (it pushes the other way), and it also cannot explain
  a 5% slowdown.
- **Publication duration** (`$4295` entry → `$028D` return): OG median 650
  scanlines, DX 626 (~4.2 frames each, HBlank-throttled). Comparable.
- DMG palette-animation region `$06E2–$0730`: **byte-identical** OG↔DX.
- Publication dispatch `028A: CALL $4295`: identical in OG, Aug-12, and
  current ROMs. None of the cadence gate's `BANKED_WRITER` sniff patterns
  match any of the three.
- The only VBlank-handler head difference: OG `CALL FF80` (OAM DMA) vs DX
  `NOP NOP NOP` (DMA relocated into the colorize path).

The residual DX-faster mechanism is **not identified**. Candidates
eliminated: ISR cost (wrong sign), publication duration (equal), palette
animation (identical), dispatch rewiring (identical). The growth of the
gap with window length (+4.8%→+10.6% for shalamar) points at
**trajectory divergence** — the two sides' arenas drift into different
boss-phase/entity configurations and the average work per iteration
differs — rather than a fixed CPU delta.

## 4. The state-pairing confound is structural

Every cross-ROM boss-speed number ever produced by this repo (cadence gate
and this new gate alike) compares an OG save state against a DX save state.
Measured problems:

1. **Landing phase is condition-based, not fixed.** Historic pairs: OG all
   saved at arena frame 77, DX all at frame 120 (43-frame offset baked into
   every pair). Fresh same-session pairs: OG landed at frames
   89/91/102/292/90/77/99, DX at 92/133/106/144/137/122/60. The generator
   saves when its stability receipt settles, which differs per ROM.
2. **Cross-loading is impossible.** OG state on DX ROM and DX state on OG
   ROM both refuse to restore (DMG vs CGB machine model — mGBA restarts to
   title, `D880=01`). The clean 2×2 ROM-vs-state experiment cannot be run.
3. Therefore ROM cost and trajectory cannot be separated within this
   paradigm. **Treat all per-boss magnitudes as direction-only.**

`gameplay_speed_parity` has no such confound — it boots both ROMs from
power-on through identical scripted input. Its Stage 1 0.943 / Stage 5
0.939 / **Stage 7 0.850** remain the trustworthy speed numbers, and the
Stage 7 failure is the one hard speed regression. (Mechanism for those:
see the cells-per-HBlank analysis in `CLAUDE.md` and
`docs/v301_performance.md` — the atomic tile+attr path fits 3 cells per
HBlank window where vanilla fits 4.)

## 5. Generator gaps observed (not fixed here — file under active Ted work)

`generate_stream_boss_states.py`:
- **Crystal (target 2) on vanilla**: capture marker never appears (20s and
  60s timeouts). The Aug-11 all-nine og-states run predates this; the stock
  crystal path regressed since.
- **Angela (target 7) on the Aug-12 ROM**: `arena-left-before-save`,
  `D880=FF` at frame 60 — the one-shot arena-exit latch fires before the
  save; the keep-alive writes don't cover it there.
- **Penta (target 8) on vanilla**: unsupported by design (fixture retarget
  requires candidate arena tables).
- Fixed this session: `stock_rom` detection is content-hash based
  (`SUPPORTED_BASE_MD5`), not path-equality — the Aug-12 matrix ran gates
  on isolated ROM copies under `tmp/`, so path comparison misclassified a
  byte-identical vanilla copy as a candidate and applied DX-only
  assertions to it (`FF91/DF0D/unsafe_attr`). That was the failure that
  left `boss_publication_cadence` permanently `blocked` behind
  `boss_og_states`.

## 6. What a sound boss-speed gate needs

1. **Pairing validity as a checkable precondition**: the generator should
   record boss-phase WRAM (`DD85–DD88`, `DCB8`, `DD08`, `FFCD`) in each
   state's `.report`, and the comparison gate should refuse pairs whose
   phase vectors mismatch.
2. Failing that, an **input-identical route** into one arena (the
   stage-speed paradigm extended past the stage boss door) gives a
   confound-free spot check at the cost of a long scripted route.
3. Until one of those exists, gate boss speed as **direction + bound**
   (e.g., "no boss more than X% off parity in either direction, averaged
   over ≥2 windows"), not as a precise percentage.

## 7. Probe-authoring traps hit during this work (reusable)

- **A DMG-mode ROM reads `FF70` (SVBK) as `$FF`.** An unconditional
  banked-WRAM guard skips every frame and hangs the probe. Gate it on the
  ROM actually having a banked writer (`BANKED_WRITER` sniff), and never
  let run termination depend on WRAM-bank state.
- **mGBA breakpoints are bank-blind.** Filter on the `FF99` bank shadow
  and keep the raw count beside the filtered one so a filter mismatch is
  loud. (At `$4295`, 96% of entries carry `FF99≠02` — a naive filter
  silently discards almost all real events.)
- `emu:stop()` in mgba-qt does not exit the process; poll a marker file
  and terminate the emulator explicitly (the existing verifiers all do
  this — copy them).
- System `luac` is Lua 5.1; mGBA's is 5.4. Structural syntax checking
  works by neutralizing `& | ~ << >>` first, validated against known-good
  production probes as controls.
