# CLAUDE.md

Guidance for Claude Code when working in this repository.

## Project

Penta Dragon DX is a Game Boy Color colorization of the DMG game
**Penta Dragon (J)** by Japan Art Media (1992). The patched ROM adds
8 BG + 8 OBJ palettes plus per-scene boss palettes, while preserving
the original gameplay, sound, and timing.

**Current production**: `rom/working/penta_dragon_dx_FIXED.gb` is
v3.00 (tag `colorize-v3.00-inline-hook`).

## Critical instructions

- **NEVER bank-switch by writing FF99 outside of the original game's
  own writes.** FF99 is the sound engine's bank-restore byte. Custom
  writes to it caused the v2.85-v2.89 phantom-sound regression.
  See `docs/inline_hook_analysis_v300.md` for the diagnosis chain.
- **NEVER hold DI for more than ~1 Timer period (~7000 T-cycles).**
  Long DI windows let Timer interrupts pile up, and on `EI` the
  backlog collapses through the sound engine's D887 consume loop
  in inconsistent state → phantom sounds.
- **Always verify against the five probes in `scripts/probes/`
  before declaring a build good.** The user's eyes are the final
  judge, but no-probe regressions waste their time.
- **Promote to FIXED.gb only via the backup pattern**
  `cp FIXED.gb FIXED.vNN.backup.gb && cp candidate.gb FIXED.gb`.
  Keeps rollback one command away.
- **Use `/launch-mgba` skill, never raw `mgba-qt`.** It handles the
  KDE-Wayland-NVIDIA quirks correctly.
- **MiSTer deploy via `/mister-deploy` skill.** Audio mode = "No Pops"
  is required on the Gameboy core.

## Where things live

### Build pipeline
- `scripts/build_v300_inline_hook.py` — current production builder
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
playtester. Highlights:

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
