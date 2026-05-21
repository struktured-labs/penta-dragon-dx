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
  (RST 10 = HUD print, RST 28 = death cinematic, RST 38 = phantom-sound
  trampoline, etc.) + boot init routine at bank 1:0x4000.
- [`hram_allocation_map.md`](hram_allocation_map.md) — HRAM byte-by-byte
  purpose. Cross-bank access census + identified roles for ~80% of bytes.
- [`wram_allocation_map.md`](wram_allocation_map.md) — WRAM page heatmap
  (DCxx and DDxx are 953 accesses combined — primary game state).
  Hot addresses identified.

## v3.01 colorization (current production)

- [`v301_gdma_freeze_diagnosis.md`](v301_gdma_freeze_diagnosis.md) —
  Full diagnosis of the v3.01 freeze: root cause was **stale FF99**;
  ISRs restored bank from FF99 → wrong bank → garbage exec.
  **Status: RESOLVED.**
- [`v301_performance.md`](v301_performance.md) — Per-VBlank cycle
  estimate (~53K T = ~76% of frame budget). Comparison to vanilla and
  v3.00. Empirical efficiency evidence from probes (scroll tearing
  0/s vs vanilla 1.50/s, phantom D887 ≤ threshold).
- [`inline_hook_analysis_v300.md`](inline_hook_analysis_v300.md) — v3.00's
  inline-hook tile+attr copy design (the predecessor; v3.01 only does
  tile inline, attrs go through VBlank attr_computation + GDMA).
- [`bg_tile_architecture.md`](bg_tile_architecture.md) Versioning
  section — quick version table.

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
