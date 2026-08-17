# Penta Dragon DX — Agent Memory Update

> Generated 2026-07-27 by specialist agent (codex/o1-pro).
> Source: penta-dragon-dx-claude repository audit.
> **Dated snapshot** — gate counts ("30 gates") and speed claims herein
> reflect 2026-07-27; the roster has since grown past 70 and the speed
> picture was corrected on 2026-08-16 (see
> `FINDINGS_2026_08_16_boss_speed_instrumentation.md`).

---

## 1. Active Branch & Status

**Current branch**: `release/v3.01-stream-rc3` (checked out, local)
**Remote tracking**: `dx/main` (remote `dx` origin)
**Working tree**: dirty — 39 modified files, ~7212 insertions / 1456 deletions uncommitted
**Merge base** (rc3 ↔ dx/main): `3c4c98d` — "fix(hardware): Move all WRAM references to bank 0 for real GBC compatibility"

The working tree has substantial local changes that have NOT been committed to any branch. These include major modifications to the production builder (`build_v302_title_fix.py`: +2845 lines), palette session tools, and diagnostic scripts. The working tree is ahead of both rc3 and dx/main.

---

## 2. Branch Divergence: rc3 vs dx/main

### dx/main only (not in rc3):
| Commit | Description |
|--------|-------------|
| `5a53673` | feat(hw): Move O(1) trampolines to WRAM Bank 0 on patcher |
| `ac0e71a` | Resolve stashed merge conflicts and restore clean 0xFA infinite-loop fix for teleport build |
| `75641df` | feat(hw): Move custom digit tile loading to VBlank-safe windows |
| `304dc35` | feat(font): Compile custom GBC digit tiles for version display |
| `1595d45` | fix(banner): Add D880 gate for bg_sweep on title showcase + fix teleport address conflict |
| `df4641e` | fix(title): Add D880 gate to run bg_sweep on title banner/showcase (D880=0x1B/0x1C) |

dx/main focuses on **hardware correctness** — moving trampolines and digit tile loading to WRAM bank 0 for real GBC compatibility, and adding D880-gated bg_sweep for the title banner/showcase scenes.

### rc3 only (not in dx/main):
| Commit | Description |
|--------|-------------|
| `0349208` | fix(release): restore stage timing and clean menu HUD |
| `0b1036c` | fix(ui): clean title and menu release paths |
| `83a3efd` | fix(title): restore v3.01 stream candidate |
| `49b61a5` | feat(font): Dynamic Git-Tag Version Number with Custom 2bpp Western Digits |
| `51079d8` | feat(hw): Finalize safe GBC VRAM digit copy on VBlank |

rc3 focuses on **release polish** — stage intro timing fix, menu HUD cleanup, dynamic version number from git tags, and safe VRAM digit copy.

### Key visual difference:
The `dx/main` branch has title-screen GBC-level palette features (bg_sweep on banner scenes) that rc3 does not. rc3 has the stage-intro-timing fix and menu HUD cleanliness that dx/main lacks. The dynamic version number in rc3 reads from git tags; dx/main compiles custom digit tiles.

---

## 3. All Known Issues (with Status)

| Issue | Status | Notes |
|-------|--------|-------|
| **Dungeon wall-flicker** (BG attr race) | **RESOLVED** | Root cause: collision at WRAM 0xDF10–0xDF2F (bg_sweep buffer). Scene-detect ran 256B copy every frame. Fix: write attrs inline at tile-copy time. Invisible to headless PyBoy. Full write-up: `docs/FINDINGS_2026_06_13_dungeon_flicker_and_riff.md` |
| **Stage intro timing / repeated ditty** | **RESOLVED in rc3** ($0349208) | Colorizer was too heavy during STAGE XX splash; VBlank window stretched, sound sequence restarted. Fix: bypass heavy colorizer while splash is active (all-palette-0). Probe: `scripts/probes/stage_intro_timing.lua` |
| **Item-menu HUD attr bleed** | **RESOLVED in rc3** ($0349208) | Off-screen dungeon palettes bleeding into HP/MEDICAL text. Fix: keep six visible window attr rows on palette 0, pause bg_sweep while menu open. Probe: `scripts/probes/menu_hud_and_combo.lua` |
| **SELECT+START teleport instability** | **RESOLVED, retired** | Unstable IRQ stack redirect. Removed from production builder v302. Teleport ROM (`penta_dragon_dx_teleport.gb`) retained as retired diagnostic only — never release evidence. |
| **100% white title** (v290–v294) | **RESOLVED** | cond_pal gated by FFC1=1; moved before check. |
| **Green ball / weird rectangle on title** (v294) | **RESOLVED** | bg_sweep on title (FFC1=0) wrote wrong attrs. Keep bg_sweep gated by FFC1=1. |
| **Purple specks on floor** (v297) | **RESOLVED** | Tile IDs 0x13–0x23 routed to pal6 instead of pal0. |
| **Stale pal7 attrs** (v297–v299) | **RESOLVED** | bg_sweep visits one row/frame; CGB boot ROM init wrote pal7 everywhere. Fixed by inline tile-copy attr writes. |
| **Phantom sound on item use** (v287–v289) | **RESOLVED** | Long DI windows / FF99 writes in bank-1 trampoline. Fixed by short DI (~250-280T), no FF99 writes. |
| **Orange wall-corner artifacts** (0x47/0x57) | **RESOLVED** | Dual-use tile IDs (wall corner + spike). Chose pal6 (wall) over pal5 (red hazard). |
| **CGB header flag** | **KNOWN BEHAVIOR** | 0x143=0x80 (CGB-aware) → boot ROM initializes BG palette RAM to all-white. Normal — cond_pal loads real palettes. |
| **MiSTer audio pops** | **MITIGATION KNOWN** | Requires "Audio mode = No Pops" in Gameboy core OSD. Inline-hook DI windows audible otherwise. |
| **mGBA Lua palette reads** | **KNOWN TOOLING BUG** | FF69/FF6B auto-increment on write, NOT on read. Early dump scripts read same byte 64×. |

**No open issues are currently tracked.** The current working tree has significant uncommitted changes that may introduce or address new issues — these need review before claiming "all clean."

---

## 4. Build Pipeline

### Production builder
```
scripts/build_v302_title_fix.py
```
- **Input**: `rom/working/penta_dragon_dx_v301.gb` (base from v301 built by `build_v301_gdma.py`)
- **Output**: `rom/working/penta_dragon_dx_FIXED.gb`
- **Backup**: auto-creates `penta_dragon_dx_FIXED.prebuild_<md5>.backup.gb` before overwriting
- **MD5** of current release candidate: `417975b53e6f20d611b813a7ed285c3c`
- **Footer string**: `DX V3.01 STRUK LABS` on row 17

### What v302 builder adds on top of v301:
1. **Exact release footer** — `DX V3.01 STRUK LABS` via reused built-in title glyphs (3, 0, 1) + temporary period tile via GDMA (restored on title exit)
2. **Title-safe inline hook** — tile-only on title/arena, full tile+attr in gameplay
3. **OBJ palette LUT** — tiles 0x70–0x7F → pal 7 for cursor 'A' at tile 0x73
4. **Title bg_sweep** — FFC1 gate removed so title receives initialized attributes
5. **Clean item-menu HUD** — six window attr rows on palette 0, bg_sweep paused
6. **Release-safe inputs** — SELECT+START teleport removed
7. **Intentional title colors** — palette 0 + blue-gray ramp reload after cold-boot
8. **Vanilla stage-intro timing** — bypass colorizer during STAGE XX splash
9. **Complete gameplay OBJ pass** — colors exact next-DMA shadow buffer, all 40 slots
10. **Palette round-trip** — honors all 8 YAML BG palettes
11. **ROM-native story palettes** — OPENING/final-story/credits/END/epilogue
12. **Death/game-over containment** — clears arena attrs over 7 bounded VBlanks

### Base builder (v301, for reference)
```
scripts/build_v301_gdma.py
```
- Emits a GDMA routine (bank13:0x6D80) and attr_computation routine (bank13:0x7100)
- **Both are dead code** in the shipping ROM — gameplay uses inline 0x42A7 hook + bg_sweep + attr-cleaner + OBJ colorizer
- See: `docs/FINDINGS_2026_06_07_gdma_is_dead_code.md`, `docs/v301_performance.md`

### Pipeline flow
```
vanilla ROM → build_v301_gdma.py → v301.gb → build_v302_title_fix.py → FIXED.gb
                                                                          ↓
                                                    verify_release_candidate.py (30 gates)
                                                                          ↓
                                                    build_release_bundle.py (IPS + dist)
                                                                          ↓
                                                    MiSTer hardware verification (separate)
```

### Release bundle
```
scripts/build_release_bundle.py
```
- Deterministic, ROM-free archive
- Default output: PREHARDWARE suffix
- Final output requires hash-bound MiSTer manifest + audience palette approval
- Supported base ROM MD5: `df43e0adfdc74b2829c7e95e91c71a28`
- Expected gate count: 33

---

## 5. Verification Probes

### Release Matrix (30 gates in `verify_release_candidate.py`)

The authoritative gate. Runs on isolated ROM copy, publishes JSON manifest + per-gate evidence.

| Gate | Type | Timeout | Description |
|------|------|---------|-------------|
| `title_footer_integration` | PyBoy probe | 120s | Verify text presence, non-white screen, no garbage |
| `title_animation_frames` | PyBoy | 180s | Title animation frame count |
| `flash_attribution` | PyBoy | 240s | Flash attribution |
| `title_color` | PyBoy | 120s | Title palette correctness |
| `title_showcase` | mGBA | 180s | Title showcase scene in accurate emulator |
| `title_visual_receipts` | mGBA | 180s | Visual receipts |
| `title_cursor` | mGBA | 120s | Cursor pixel verification |
| `stage_intro_timing` | mGBA/Lua | 180s | STAGE XX splash timing (no repeated ditty) |
| `menu_hud_and_combo` | mGBA/Lua | 300s | Item-menu HUD attrs + teleport absence |
| `levelselect_screen` | mGBA/Lua | 120s | Level-select screen |
| `game_start_hardware_route` | mGBA | 120s | Hardware route verification |
| `gameplay_speed_parity` | mGBA | 180s | Speed parity vs vanilla (stages 0, 4, 6, 600 frames, 10% tolerance) |
| `gameplay_bg_palettes` | PyBoy | 180s | BG palette RAM + attr histogram |
| `stage1_no_color_bleed` | mGBA | 180s | 1200 frames, no color bleed |
| `gameplay_obj_palettes` | mGBA | 180s | OBJ palette verification |
| `miniboss_color` | PyBoy | 240s | Gargoyle (DCB8=2) color |
| `later_stage_integrity` | mGBA | 180s | Stage-by-stage integrity |
| `later_stage_soak` | mGBA | 360s | 8000-frame soak test |
| `boss_arenas` | mGBA | 600s | All boss arena palettes |
| `death_gameover` | mGBA | 600s | Death/GAME-OVER attr containment |
| `title_idle_reel` | mGBA | 240s | 14000-frame attract reel |
| `opening_cutscene` | mGBA | 240s | Opening cutscene (expect production) |
| `final_cutscene_mgba` | mGBA | 180s | Final cutscene |
| `ending_inventory_a` | mGBA | 300s | Post-final ending, 32000 frames |
| `ending_inventory_b` | mGBA | 300s | Post-final ending (repeat), 32000 frames |
| `ending_discriminators` | Analysis | 30s | Compare A/B ending manifests |
| `scroll_stability` | PyBoy | 300s | Palette stability under scroll |
| `phantom_sound` | PyBoy | 300s | D887 watchpoint (no phantom sounds) |
| `live_palette_deck` | mGBA | 360s | Live palette session |
| `story_attr_production` | mGBA | 240s | Story attribute production (depends on live_palette_deck) |
| `palette_build_roundtrip` | Analysis | 180s | YAML → ROM → verify roundtrip |
| `release_ips_patch` | Analysis | 30s | IPS reconstructs candidate from base |
| `mister_reservation_guard` | Local | 30s | Fail-closed; never contacts MiSTer |

### Development Probes (in `scripts/probes/`)
| Probe | Type | What it covers |
|-------|------|----------------|
| `verify_title_screen_integration.py` | PyBoy | Text presence, screen content |
| `verify_title_color.py` | PyBoy | Title palette |
| `verify_phantom_d887.py` | PyBoy | Sound canary (no phantom triggers) |
| `verify_gameplay_palette.py` | PyBoy | BG palette RAM + attr histogram |
| `verify_miniboss_color.py` | PyBoy | Gargoyle arena |
| `verify_scroll_tearing.py` | PyBoy | Palette stability under scroll |
| `verify_stage_intro_timing.py` | PyDriver | STAGE XX splash timing (PyBoy driver, mGBA Lua runner) |
| `verify_menu_hud_and_combo.py` | mGBA/Lua | Menu HUD attrs + SELECT+START absence |
| `verify_boss_arena_palettes.py` | mGBA/Lua | All boss arenas |
| `verify_flash_attribution.py` | mGBA/Lua | Flash attribution |
| `verify_title_animation_frames.py` | mGBA/Lua | Animation frame count |

### Lua probes (in `scripts/probes/`)
| Lua file | Purpose |
|----------|---------|
| `stage_intro_timing.lua` | Measure STAGE XX splash duration, detect repeated ditty |
| `menu_hud_and_combo.lua` | Item-menu window attrs + teleport hotkey absence |
| `gameplay_palette.lua` | Gameplay palette dump |
| `phantom_d887.lua` | D887 sound canary watchpoint |
| `title_screenshot.lua` | Title screen capture |
| `gameplay_screenshot.lua` | Gameplay screenshot |
| `vblank_timing.lua` | VBlank timing measurement |
| `vblank_cycles.lua` | VBlank cycle measurement |
| `inventory_probe.lua` | Scene inventory |
| `autoplay_record.lua` | Autoplay record |
| `spin_shoot_test.lua` | Spin shoot test |
| `play_record.lua` | Play record driver |
| `play_record_curriculum.lua` | Curriculum play record |
| `dump_bg_palette.lua` | BG palette dump |

### Diagnostic Probes (in `scripts/diagnostics/`)
Many more Lua probes for specialized scenarios: arena alternation, cram access safety, cutscene verification, ending capture, item menu, later-stage soak, lava, level-select, menu flicker, monster capture, OBJ cram, palette build roundtrip, score screen, shadow OAM trace, splash verify, stage integrity, story attr production, title showcase, wall flicker, and more.

---

## 6. Key Technical Details

### Memory-mapped addresses (from CLAUDE.md)

| Address | Meaning |
|---------|---------|
| FFBA | Level / boss counter |
| FFBD | Room within level (1-7) |
| FFBF | Mini-boss flag |
| FFC0 | Powerup state |
| FFC1 | Game state (0=menu/title, 1=gameplay) |
| D880 | Master scene |
| DCB8 | Section cycle counter |
| D887 | Sound queue byte (phantom-sound canary) |
| FF99 | Bank restore byte (DO NOT WRITE FROM HOOKS) |
| FF68/FF69 | CGB BG palette index/data |
| FF6A/FF6B | CGB OBJ palette index/data |
| FF4F | VRAM bank |
| 0xDA00-0xDAFF | bg_table copy (v3.00 only, unused otherwise) |

### Key hardware constraints
- **CGB header flag 0x143=0x80** → boot ROM inits BG palette RAM all-white. cond_pal must run before first frame renders.
- **WRAM 0xDF10–0xDF2F** = bg_sweep buffer. Anything written there is clobbered every frame.
- **LY timing**: writes must land at LY 144–153 (VBlank).
- **DO NOT write FF99 from hooks** — causes timer ISR pileup and phantom sounds.
- **DO NOT hold DI for >300T** — same phantom-sound mechanism.

### PALETTE ROUND-TRIP constraint
All 8 tiles from `palettes/penta_palettes_v097.yaml` are loaded into CGB palette RAM. BG7→BG0 boot/title mask preserved until game-state palette reload restores independently tuned BG7.

---

## 7. Specialist Role Summary

As the PENTA-DRAGON-DX specialist, my responsibilities include:

1. **Maintain production builder** — `build_v302_title_fix.py` is the authoritative build path. Keep its backup mechanism (prebuild hashes) intact.
2. **Enforce verification gate** — all claims must pass `verify_release_candidate.py` (30 gates). PyBoy-only assertions are insufficient for timing bugs.
3. **Guard against hw regressions** — never write FF99 from hooks; respect LY timing; keep DI windows short; avoid WRAM 0xDF10–0xDF2F for custom scratch.
4. **Maintain branch awareness** — rc3 is the release candidate. dx/main has divergent hardware fixes not yet merged in. Working tree has massive uncommitted changes.
5. **Probe-first debugging** — use the existing Lua/Python probes before writing new ones. The diagnostics/ directory has extensive coverage.
6. **Release discipline** — FIXED.gb is the only release ROM. Teleport ROM is retired. Palette round-trip, IPS reconstruction, and MiSTer hardware pass are non-negotiable gates.
7. **Documentation preservation** — reference findings are in `docs/*.md`. Read them before re-deriving anything.

### What to carry forward
- The stage-intro timing fix and menu HUD fix are the two most recent resolved issues (commit `0349208`).
- The uncommitted working tree (7212 insertions) is a major blind spot — it needs to be committed or evaluated for what it changes.
- dx/main and rc3 have diverged at the hardware-correctness level (WRAM bank 0 moves, D880-gated title bg_sweep). A merge or rebase is pending.
- The palette round-trip (all 8 YAML palettes honored in gameplay) and story/ending attr production are the most recent capability additions to the builder.

### Verification mantra
> **PyBoy memory-register dumps are NEVER sufficient for timing bugs.**
> **All flicker/timing/rendering verification MUST go through mGBA's accurate pixel pipeline.**
> **The authoritative emulator gate is `verify_release_candidate.py` (30 gates).**
> **The golden check: build ROM, launch in mGBA-qt with NVIDIA GL override, visually confirm zero orange flicker across 5 seconds of Stage 1 gameplay.**
