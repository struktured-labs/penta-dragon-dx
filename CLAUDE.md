# CLAUDE.md

Guidance for Claude Code when working in this repository.

## Project

Penta Dragon DX is a Game Boy Color colorization of the DMG game
**Penta Dragon (J)** by Japan Art Media (1992). The patched ROM adds
8 BG + 8 OBJ palettes plus per-scene boss palettes, while preserving
the original gameplay, sound, and timing.

**Current production**: `rom/working/penta_dragon_dx_FIXED.gb` is
v3.02 (`scripts/build_v302_title_fix.py`; `FIXED.gb` == `v302.gb`,
md5 `f4ac6367f75d50765cf018661f7c5e8c`). Overwrote v3.01 on
2026-07-18 (old v3.01 teleport-era build had title screen regressions:
cursor 'A' at tile 0x73 was missing due to D880-gated inline hook and
OBJ palette LUT assigning pal 6 instead of pal 7). FIXED.gb.v300c.backup.gb
is the pre-teleport base; FIXED.gb.v302.gb is the new v3.02 build.

> **Naming caveat (verified 2026-06-07):** the "GDMA" in
> `build_v301_gdma.py` is a misnomer. It *writes* a GDMA routine
> (bank13:0x6D80) and a 1024-byte `attr_computation` routine
> (bank13:0x7100) into ROM, but **neither is ever CALLed** — scanning
> the built ROM for `CD 80 6D` / `CD 00 71` finds nothing. They are
> dead code. What actually ships is the v3.00-style inline tile+attr
> copy at bank1:0x42A7 + `cond_pal` + attr-cleaner + ungated
> `bg_sweep` + OBJ colorizer.
>
> The inline 0x42A7 hook is the ONLY live BG-attr writer, and it already
> does the fused `[BC]` lookup (`LD A,[DE]; INC DE; LD C,A; LD A,[BC];
> LD [HL+],A`) single-pass — so don't try to "add" a fused lookup
> anywhere (PR #1's fused `bg_sweep` was closed for this reason). If
> GB-speed parity is ever the goal, the real lever is the hook's
> **second (attr-phase) STAT mode-0 wait per group** (vanilla waits
> once/group, we wait twice, ×144 groups) — NOT `attr_computation`,
> which is dead. The 53K T / 76%-frame figure in old perf notes was for
> that dead path. Full write-up:
> `docs/FINDINGS_2026_06_07_gdma_is_dead_code.md`;
> corrected cost picture: `docs/v301_performance.md`.

## CRITICAL: Verification Standards (Hard Gate)

- **LAUNCH GATE REQUIRED:** Before launching mGBA-qt with any ROM, you MUST first run `python3 scripts/launch_gate.py <rom>` to verify the ROM boots correctly. If launch_gate exits non-zero, do NOT open mGBA — fix the ROM first. This is a hard gate — there is no override.

- **PyBoy memory-register dumps are NEVER sufficient for timing bugs.** PyBoy does not enforce VBlank/STAT mode-3 write blocking. Writes that miss their VBlank window land cleanly in PyBoy's virtual memory. This means any test that only reads OAM/attribute registers and asserts "no orange" is fundamentally broken for flicker verification.

- **All flicker/timing/rendering verification MUST go through mGBA's accurate pixel pipeline.** Use the mgba-mcp MCP tools to:
  1. `mgba_run` to advance frames
  2. `mgba_read_memory` on hardware OAM (0xFE00) to check actual displayed sprite attributes
  3. `mgba_run_lua` to run the existing Lua probes in probes/diagnostics/
  
- **The 5 probes in scripts/probes/ are a MINIMUM, not a guarantee.** Passing them does not mean the build is good. The user's eyes are the final judge.

- **Any fix that claims "0% orange flicker" must be verified using `scripts/diagnostics/verify_sprite_flicker.py` inside PyBoy AND pass all 5 probes.** Accepting one without the other is a gate failure.

- **The hwoam_recolor floor-through for tiles 0x10-0x1F is a KNOWN, DOCUMENTED, UNSOLVED timing issue.** See build_v301_teleport.py lines 548-580. DO NOT claim it's fixed without also confirming the fix does NOT cause fresh-boot CRAM regressions (run a cold-boot probe). The B=20 attempt (iter 277) was reverted for this exact reason.

- **The golden check: build the ROM, launch it in mGBA-qt with the NVIDIA GL driver override (`QT_QPA_PLATFORM=xcb __GLX_VENDOR_LIBRARY_NAME=nvidia`), navigate to Stage 1 gameplay, and visually confirm zero orange flicker on Sara and monsters across 5 seconds of gameplay.** No automated test replaces this.
- **Colorize VBlank timing: keep custom WRAM scratch OUT of
  `0xDF10–0xDF2F`** (bg_sweep's per-frame swept-row buffer — anything
  there is clobbered every frame). A cache byte at `0xDF23` collided
  with it and caused the dungeon wall-flicker (scene-detect ran a 256B
  copy every frame → colorize spilled out of VBlank into active
  display). Timing bugs like this are **invisible to headless PyBoy**
  (it doesn't enforce VRAM windows) — diagnose with an LY-timing probe
  (`hook_register` on bg_sweep, read `FF44`/LY; writes must land at
  LY 144–153). Full write-up + reusable methods (deterministic A/B
  frame diff, banked VRAM reads, palette-RAM reads, Riff arena
  colorization): `docs/FINDINGS_2026_06_13_dungeon_flicker_and_riff.md`.
- **Promote to FIXED.gb only via the backup pattern**
  `cp FIXED.gb FIXED.vNN.backup.gb && cp candidate.gb FIXED.gb`.
  Keeps rollback one command away.
- **Use `/launch-mgba` skill, never raw `mgba-qt`.** It handles the
  KDE-Wayland-NVIDIA quirks correctly.
- **MiSTer deploy via `/mister-deploy` skill.** Audio mode = "No Pops"
  is required on the Gameboy core.

## Where things live

### Build pipeline
- `scripts/build_v302_title_fix.py` — **current production builder** (v3.02).
  Builds on the teleport infrastructure (scene_detect, position sweep, arena
  bg_tables, teleport combo) with two critical fixes:
  - **Ungated inline hook**: writes tile+attr on the title screen (was tile-only
    due to D880 gate in teleport build, causing cursor to go missing).
  - **OBJ palette LUT**: tiles 0x70-0x7F → pal 7 (was pal 6), matching the
    original CP-cascade that cursor 'A' (tile 0x73) depends on.
  Preserves DMG NOP removal (bg_sweep runs on title), O(1) OAM intercept,
  and all teleport features.
- `scripts/build_v301_gdma.py` — v3.01 base builder (see the
  naming caveat above: the GDMA/attr_comp routines it emits are dead code;
  the shipping path is the inline 0x42A7 hook + bg_sweep + attr-cleaner)
- `scripts/build_v300_inline_hook.py` — historical v3.00 inline-hook builder
- `scripts/build_v29*_*.py` — milestone builders (v294 title-fix,
  v295 minimal-title, v296 phantom-safe sweep, v297 calibrated table
  + viewport sweep, v298 refined table, v299 minimal table)
- `scripts/create_vblank_colorizer_v*.py` — historical builders.
  v288 introduced RST $38 RETI→RET patch at 0x003B. v289 added
  enhanced_tilemap_copy via trampoline (BG fix but phantom regress).
  v290 was the no-trampoline base we built on.
- `scripts/bg_experiment.py` — shared palette loader, OBJ colorizer,
  tile-to-palette subroutine, original `create_bg_tile_table()`.
  The calibrated/minimal tables live inline in the v296/v299 builders.

### Verification (the trust-me-not-the-user loop)
- `scripts/probes/verify_title_screen_integration.py` — boots in PyBoy,
  captures title screen, verifies text presence (PENTA DRAGON DX, JAPAN ART
  MEDIA, STRUKTURED LABS), non-white screen, and no garbage artifacts.
  0=PASS 1=FAIL 2=harness error
- `scripts/probes/verify_title_color.py` — 0=PASS 1=FAIL
- `scripts/probes/verify_phantom_d887.py` — vanilla-baselined
- `scripts/probes/verify_gameplay_palette.py` — auto-presses start,
  dumps BG palette RAM + attr histogram
- `scripts/probes/verify_miniboss_color.py` — force DCB8=2 (Gargoyle)
- `scripts/probes/verify_scroll_tearing.py` — palette stability under scroll
- `scripts/probes/*.lua` — mgba-Lua probes (screenshot, palette dump,
  D887 watchpoint, tile-table dump)

### Reverse-engineering reference
- `docs/inline_hook_analysis_v300.md` — bank-1 tile-copy disassembly
- `palettes/bg_tile_categories.yaml` — manual tile-ID → category map
- `palettes/penta_palettes_v097.yaml` — 8 BG + 8 OBJ + boss palettes
- `reverse_engineering/notes/game_memory_map.md` — HRAM + WRAM addresses
- User's project memory at
  `~/.claude/projects/-home-struktured-projects-penta-dragon-dx-remote/memory/`
  has every non-obvious fact: phantom-sound root cause, FF99 race,
  RST $38 quirk, sweep timing, bg_table calibration, mini-boss
  spawn mechanism, stage-boss arenas, RL kill signals, more.
  **Read those memory files before re-deriving anything.**

### Tooling skills
- `/launch-mgba` → `scripts/launch_mgba.sh` (KDE-Wayland-NVIDIA aware)
- `/mister-deploy` → `scripts/deploy_mister.sh`
- `/mister-status` → status via MiSTerClaw MCP (port 9900)
- `/mister-screenshot`
- `/mister-shell`

## Key memory addresses (Penta Dragon)

| Address | Meaning |
|---------|---------|
| **FFBA** | Level / boss counter (0=Shalamar, 1=Riff, …, 8=Penta Dragon) |
| **FFBD** | Room within level (1-7) |
| **FFBF** | Mini-boss flag (1=Gargoyle, 2=Spider/Arachnid, 3+=spawn table) |
| **FFC0** | Powerup state |
| **FFC1** | Game state (0=menu/title, 1=gameplay) |
| **D880** | Master scene (0x02 dungeon, 0x0A mini-boss arena, 0x0C-0x14 stage-boss arenas, 0x17 death, 0x18 boss splash) |
| **DCB8** | Section cycle counter (mini-boss spawn at DCB8=2 and DCB8=5 in L1) |
| **DCBB** | Corridor death timer / boss HP (dual purpose) |
| **DCDC/DCDD** | Player HP sub-counter / main |
| **D887** | Sound queue byte — write coalesced by sound engine. PHANTOM-SOUND CANARY |
| **FF99** | Bank restore byte used by Timer ISR. **DO NOT WRITE FROM HOOKS** |
| **FF68/FF69** | CGB BG palette index/data |
| **FF6A/FF6B** | CGB OBJ palette index/data |
| **FF4F** | VRAM bank (0=tiles+IDs, 1=BG attrs) |
| **WRAM 0xDA00-0xDAFF** | bg_table copy (v3.00 only) — verified unused otherwise |

## Game architecture

- **7 stages**, each with 7 interconnected rooms (FFBD=1-7).
- **8 named stage bosses** (Shalamar, Riff, Crystal Dragon, Cameo, Ted,
  Troop, Faze, Penta Dragon) + **Angela** in a hidden SHMUP stage = 9.
- **2-3 hidden SHMUP stages** where Sara becomes a top-down spaceship.
  FFBA=7 inside the SHMUP.
- **Mini-boss spawn mechanism**: at section index `DCB8`, the table
  in bank 13:0x4024 specifies which entity slot loads. In L1, DCB8=2
  spawns Gargoyle (FFBF=1) and DCB8=5 spawns Spider (FFBF=2).
- **Stage boss arenas**: D880 transitions to 0x0C+FFBA. Boss kill = D880
  goes to 0x16 (post-boss reload).
- **A-fix ROM** (`rom/Penta Dragon (J) [A-fix].gb`) patches the vanilla
  bug where the A button fires every frame. Used for RL fairness.

## RL experimentation (parallel track in `rl/`)

The `rl/` subsystem stress-tests colorization by playing many varied
scenes and is also a longer-term project for shipping an autonomous
playtester. Model checkpoints (`*.pt`) are user-local — not committed,
not present in fresh clones. Train (or copy from the user's machine)
before any RL eval. Highlights:

- `rl/ppo_v19_resume18_ep200.pt` — 100% mini-boss kill from arena state
- `rl/bc_kill_oversampled.pt` — BC trained on synth v19 demos with
  kill-frame oversampling, 20/30 mini-boss kills
- `rl/train_demo_curriculum.py` — curriculum trainer mixing user-demo
  save states (FFBA=1 L2 entries) + arena synth states + gameplay_start
- `rl/saves/user_demo/converted/` — 20 mgba → PyBoy converted demo
  states via the WRAM/HRAM/OAM injection pipeline
- `rl/saves/curriculum/arena_*.state` — synthesized stage-boss arenas
  for direct curriculum starts

## Common pitfalls (from prior agent sessions)

1. **CGB header flag 0x143=0x80 vs 0x00.** Vanilla is 0 (DMG-only).
   We set 0x80 (CGB-aware) which makes the boot ROM initialize BG
   palette RAM to all-white instead of running the grayscale
   compatibility mapping. Title screens look pure white until our
   cond_pal loads palettes.

2. **The "100% white title" bug** (v290-v294 family): the cond_pal
   call was gated by FFC1=1, so palette load never fired on title.
   Fix: move cond_pal **before** the FFC1 check.

3. **The "green ball / weird rectangle on title" bug** (v294 attempt):
   running `bg_sweep` on title (FFC1=0) writes BG attrs for title
   tiles whose IDs happen to fall in colored-palette ranges, producing
   visible artifacts. Fix: keep bg_sweep gated by FFC1=1, accept
   DMG-style 2-color title.

4. **The "purple specks on floor" bug** (v297 calibrated-table attempt):
   tile IDs 0x13-0x23 are FLOOR-EDGE TRANSITION tiles, not walls.
   Routing them to pal6 (slate) created visible seams on the floor.
   Fix: route 0x13-0x23 to pal0; OR (v299 minimal) only colorize
   items + hazards, everything else stays pal0.

5. **The "stale pal7 attrs" bug** (v297-v299 sweep race):
   the CGB boot ROM init writes pal7 to all BG attrs. Our bg_sweep
   visits one row per frame, so when the game writes new tiles
   between sweep visits, those attrs stay at pal7. Visible as
   flickering specks at scroll edges. v3.00 fix: write attrs inline
   at the game's tile-copy time, eliminating the race.

6. **The "phantom sound on item use" bug** (v287-v289 trampoline):
   the bank-1 trampoline at 0x42A7 wrote FF99=0x0D and held DI for
   ~10,000 T-cycles during enhanced_tilemap_copy. Timer ISRs piled
   up, and the sound engine's `consume-D887` loop in bank 3 saw
   inconsistent state on `EI`, producing extra D887 transitions.
   Fix: v3.00 inline hook avoids both FF99 writes and long DI
   windows; per-mini-group DI stays ~250-280T.

7. **MiSTer requires "Audio mode = No Pops"** in the Gameboy core OSD
   menu. Without it, the inline-hook's DI windows are audible as pops
   even though they don't corrupt D887.

8. **mgba Lua palette reads need explicit BCPS index.** Writes to
   FF69/FF6B auto-increment, reads do NOT. The early dump scripts
   read the same byte 64 times because of this.

## Workflow rules

1. **Branch on `main`**, commit often, tag every visible milestone.
2. **All changes verified through the five probes** before promotion.
3. **Backups in `rom/working/penta_dragon_dx_FIXED.vNN.backup.gb`** before
   overwriting FIXED.gb.
4. **Hardware test via `/launch-mgba` then `/mister-deploy`.**
5. **Don't push `setenv.sh`** (per user's global rule).
6. **Use `uv` or `pixi`, never `pip`** (per user's global rule).

## When stuck

- Check `~/.claude/projects/-home-struktured-projects-penta-dragon-dx-remote/memory/MEMORY.md`
  — it lists the topic-specific memory files (boss mechanics, sound
  engine analysis, palette pipeline, RL findings, etc.).
- Run all 5 probes to localize which dimension regressed.
- Compare against the nearest passing backup ROM via `md5sum` + the
  per-version build scripts to bisect.
- Per the user: "I really want you to work on this autonomously. I've
  tried hard to give you tooling to do so." — use the agent system
  for parallel investigations; use the probes to self-verify; ship
  candidates with backups; iterate.

## Active Hardware Alert (July 13, 2026)
* **The MiSTer FPGA is ONLINE:** The physical MiSTer console (port 9900) is online right now. You are encouraged to run `/mister-deploy` to test your builds on cycle-accurate GBC silicon after completing headless verification!
* **Maximize Headless Testing:** Verify all builds headlessly against the 5 probes before physical deployment.

