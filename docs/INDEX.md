# Penta Dragon DX — Documentation Index

Master index for all ROM understanding and modification documentation.
Organized by topic. New readers: start with **System architecture**,
then dive into the specific subsystem you care about.

## System architecture (start here)

- [`bg_tile_architecture.md`](bg_tile_architecture.md) — How background
  tiles flow from level data → tile buffer (0xC1A0) → VRAM tilemap.
  Has the v2.90/v3.00/v3.01 version table.
- [`interrupt_architecture.md`](interrupt_architecture.md) — ROM bank
  map, all 3 ISRs (VBlank/STAT/Timer), the **FF99 protocol** (every
  ISR restores ROM bank from this shadow register), VBlank handler
  chain, sound engine entry, modifications vs vanilla.
- [`rst_and_boot.md`](rst_and_boot.md) — All 8 RST vectors decoded
  (RST 10 = HL += A pointer math, RST 28 = state-dispatcher wrapper, 
  RST 38 = phantom-sound trampoline, etc.) + boot init at bank 1:0x4000.
- [`main_loop_and_entry.md`](main_loop_and_entry.md) — Power-on → 0x0150
  setup → main loop at **0x016C-0x018A** (6 subsystem CALLs + JP back).
  Game-start entry at 0x3B37 confirmed.
- [`d880_state_machine.md`](d880_state_machine.md) — **D880 is sound-
  engine state, NOT the gameplay state machine.** Documents the
  bank3:0x4029 dispatcher (which sets up sound channels per scene),
  all known D880 values, and per-state handler data tables.
- [`gameplay_state_via_ffc1.md`](gameplay_state_via_ffc1.md) — The
  ACTUAL gameplay-active flag: FFC1. 13 read sites across the ROM
  with the classic "skip if 0" gate idiom. Same flag our v3.01
  colorize handler uses to gate game-only work.
- [`hram_allocation_map.md`](hram_allocation_map.md) — HRAM byte-by-byte
  purpose. Cross-bank access census + identified roles for ~80% of bytes.
- [`wram_allocation_map.md`](wram_allocation_map.md) — WRAM page heatmap
  (DCxx and DDxx are 953 accesses combined — primary game state).
  Hot addresses identified.

## v3.01 colorization (current production)

- [`v301_resolved_issues.md`](v301_resolved_issues.md) — **CURRENT PRODUCTION 2026-05-23.**
  Four user-reported issues resolved with mGBA-probe verification BEFORE
  deployment: (1) Sara color change near miniboss [palette_loader OCPS
  slot×8 fix]; (2-4) Title splotches root causes [cold-boot zero
  overrunning VBlank, FF99 protocol overhead, missing bg_table pal 5
  entries]. SELECT menu identical to v3.00. Scroll flicker is
  pre-existing (matches v3.00).
- [`scroll_flicker_analysis.md`](scroll_flicker_analysis.md) — Root cause
  of scroll flicker: game double-buffers tilemaps (0x9800 ↔ 0x9C00) every
  ~5 frames but bg_sweep only sweeps the DISPLAYED one. Non-displayed
  accumulates uninit attrs that flash when LCDC bit 3 toggles. Both v3.00
  and v3.01 have this characteristic. Three potential fixes described
  but deferred (regression risk).
- [`FINDINGS_2026_06_13_dungeon_flicker_and_riff.md`](FINDINGS_2026_06_13_dungeon_flicker_and_riff.md)
  — **TELEPORT-build dungeon wall-flicker root cause + fix** (distinct from
  the double-buffer scroll flicker above): scene-detect's cache byte at
  `0xDF23` collided with bg_sweep's `0xDF10–0xDF2F` scratch buffer → 256B
  table copy every frame → colorize spilled out of VBlank → flicker while
  roaming. Fix: move byte to `0xDF0D` (tag `v8.6-gold-flicker-fixed`). Also:
  Riff single-purple-body colorization (tag `v8.7-gold-riff-purple`), and
  reusable diagnostic methods (LY-timing probe, deterministic A/B frame diff,
  banked VRAM / palette-RAM reads in PyBoy). Key rule: keep custom WRAM scratch
  out of `0xDF10–0xDF2F`.
- [`inline_tile_attr_copy.md`](inline_tile_attr_copy.md) — Full
  documentation of the 0x42A7 inline tile+attr copy: entry points,
  5 static callers, tile/attr phase structure with STAT-mode waits,
  bg_table dependency, VBK toggling. v3.01 body is byte-for-byte
  identical to v3.00's.
- [`v301_breakthrough.md`](v301_breakthrough.md) — **HISTORICAL** (2026-05-21).
  Earlier attr_comp + GDMA approach. Proved unreliable on hardware,
  currently disabled in production (warm path is v3.00-equivalent).
- [`v301_gdma_freeze_diagnosis.md`](v301_gdma_freeze_diagnosis.md) —
  Earlier root cause of v3.01 freeze: stale FF99 caused ISR bank
  corruption. **Status: HISTORICAL** (attr_comp+GDMA disabled).
- [`v301_regression_stage_load_stuck.md`](v301_regression_stage_load_stuck.md) —
  **HISTORICAL.** Earlier "every combination breaks" matrix.
- [`v301_performance.md`](v301_performance.md) — Per-VBlank cycle
  estimate (~53K T = ~76% of frame budget). Comparison to vanilla and
  v3.00. Empirical efficiency evidence from probes (scroll tearing
  0/s vs vanilla 1.50/s, phantom D887 ≤ threshold).
- [`inline_hook_analysis_v300.md`](inline_hook_analysis_v300.md) — v3.00's
  inline-hook tile+attr copy design (the predecessor; v3.01 only does
  tile inline, attrs go through VBlank attr_computation + GDMA).
- [`bg_tile_architecture.md`](bg_tile_architecture.md) Versioning
  section — quick version table.

## Game engine architecture (2026-05-23 additions)

- [`game_state_machine.md`](game_state_machine.md) — Unified reference for
  the 5 state bytes (D880, FFC1, FFBA, FFBF, FFBD) and their interactions.
  Includes full D880 value table (boot, dungeon, mini-boss, 9 boss arenas,
  death), authority chain, common transitions, autoplay timeline trace.
- [`boss_arena_routines.md`](boss_arena_routines.md) — All 9 boss arena
  setup routines (Shalamar through Penta Dragon + 1 hidden). Per-arena
  init position, first data pointer, common setup chain. Includes
  arena 1 disassembly for reference.
- [`bank_switched_call_pattern.md`](bank_switched_call_pattern.md) —
  CALL → thunk → RST 28h → bank-switched function → cleanup pattern
  used throughout for cross-bank function invocation.
- [`sound_engine.md`](sound_engine.md) — Timer ISR chain (0x0050 →
  0x06B3 → bank 3:0x4000), sound engine state bytes D880-D88A,
  bank-switching, why v3.01's removed FF99 protocol is safe.

## Reverse engineering — specific subsystems

In `reverse_engineering/notes/`:
- `game_memory_map.md` — Master memory map; reconcile against the newer HRAM/WRAM maps here.
- `gap_boss_arena_setup.md` — How stage boss arenas initialize.
- `gap_ffbf_spawn_table.md` — Mini-boss spawn mechanism.
- `gap_combat_damage_disasm.md`, `gap_miniboss_damage_path.md` — Combat damage path.
- `gap_sound_command_table.md`, `gap_sound_pointer_targets.md` — Sound engine commands.
- `gap_d880_state_08_third.md`, `gap_d880_states_02_09.md` — D880 master-scene state machine.
- `gap_powerup_state_machine.md` — Powerup + form transform mechanics.
- `gap_scroll_state.md` — Scroll variables and DC81 mechanics.
- `gap_tile_decompression.md` — Compressed tile data unpacking.
- `gap_cgb_boot_palette.md` — Why pal7 needs override.
- `gap_sram_checkpoint_layout.md` — SRAM 7 checkpoint slots at 0xBF00.
- `gap_bank14_death_cinematic.md` — Death cinematic + FFE4=1 + RST 28 chain.
- `gap_banks_4_to_11.md`, `gap_banks_6_7_functions.md` — Banked ROM surveys.
- `runtime_probe_findings.md`, `runtime_probe_round2_findings.md` — Probe discoveries.

## Modification approaches (historical)

- `ADVANCED_COLORIZATION_APPROACHES.md`
- `CGB_COLORIZATION_FINDINGS.md`
- `GBC_NATIVE_APPROACH.md`
- `RELIABLE_APPROACH.md`
- `SCALABLE_PALETTE_APPROACH.md`
- `VBLANK_HOOK_LIMITATIONS.md` — Constraints inside a VBlank handler.
- `projectile_colorization_plan.md`, `_compact.md`, `_tile_mapping.md` — Projectile sprite coloring.
- `stage_detection.md` — Identifying stage transitions.

## Reference

- `COLOR_NAMES.md` — Palette YAML color names.
- `ENTITY_DATA_STRUCTURE.md` — Enemy slot byte layout (DC85+).
- `QT_WINDOW_POSITIONING.md` — mgba-qt screenshot tooling.
- `stub_gbc_palette.asm` — Standalone CGB palette init.

## Session reports (chronological)

- `SESSION_SUMMARY_2025-12-27.md`
- `v228_stage_detection_results.md`
- `v229_testing_guide.md`
- `v230_fix_summary.md`
- `research.md` — Loose research notes.

## Live production state

- ROM: `rom/working/penta_dragon_dx_v301.gb`
- Build: `python3 scripts/build_v301_gdma.py`
- Probes:
  - `scripts/probes/verify_title_color.py`
  - `scripts/probes/verify_gameplay_palette.py`
  - `scripts/probes/verify_scroll_tearing.py`
  - `scripts/probes/verify_phantom_d887.py`
  - `scripts/probes/verify_miniboss_color.py`
- v3.00 fallback: `rom/working/penta_dragon_dx_FIXED.gb` (MiSTer-deployed until v3.01 hardware-verified)
