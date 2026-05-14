# Penta Dragon DX

**Game Boy Color colorization of Penta Dragon (ペンタドラゴン)**

Converts the original DMG ROM into a CGB build with semantically-aware
palettes for floors, walls, items, hazards, and sprites — without the
phantom-sound and white-title regressions that plagued earlier attempts.

---

## Status: ✅ v3.00 — phantom-safe inline tile-write hook

All five visible-regression categories verified passing on
`rom/working/penta_dragon_dx_FIXED.gb`:

| Bug                       | Probe                                        | v3.00 result        |
|---------------------------|----------------------------------------------|---------------------|
| Title screen white        | `scripts/probes/verify_title_color.py`       | PASS (3 colors)     |
| Phantom sound on items    | `scripts/probes/verify_phantom_d887.py`      | 2 D887 transitions vs vanilla 12 |
| BG colorization missing   | `scripts/probes/verify_gameplay_palette.py`  | PASS                |
| Mini-boss colors wrong    | `scripts/probes/verify_miniboss_color.py`    | PASS                |
| Scroll tearing            | `scripts/probes/verify_scroll_tearing.py`    | PASS                |

Tagged `colorize-v3.00-inline-hook`.

---

## Quick start

### Build

The current production build script is `scripts/build_v300_inline_hook.py`:

```bash
python3 scripts/build_v300_inline_hook.py
# → rom/working/penta_dragon_dx_v300.gb
```

The current `rom/working/penta_dragon_dx_FIXED.gb` is the v3.00 output.
Eight prior milestones are kept as `rom/working/penta_dragon_dx_FIXED.v2*.backup.gb`
for one-command rollback if a hardware target regresses.

### Test in mgba (the self-verifier loop)

```bash
# Visual + audio human test on desktop
/launch-mgba                                # invokes scripts/launch_mgba.sh

# Self-verifying smoke test (all five probes)
python3 scripts/probes/verify_title_color.py    rom/working/penta_dragon_dx_FIXED.gb
python3 scripts/probes/verify_phantom_d887.py   rom/working/penta_dragon_dx_FIXED.gb
python3 scripts/probes/verify_gameplay_palette.py rom/working/penta_dragon_dx_FIXED.gb
python3 scripts/probes/verify_miniboss_color.py rom/working/penta_dragon_dx_FIXED.gb
python3 scripts/probes/verify_scroll_tearing.py rom/working/penta_dragon_dx_FIXED.gb
```

Exit code 0 = bug fixed. Exit code 1 = bug present.

### Deploy to MiSTer FPGA

```bash
/mister-deploy   # invokes scripts/deploy_mister.sh
/mister-status
```

On MiSTer, set Gameboy core's **Audio mode = "No Pops"** in the OSD.

---

## Architecture (v3.00)

The decisive structural fix in v3.00: **write BG palette attributes
inline with the game's own tile-copy routine** (bank 1, address 0x42A7),
instead of via a separate VBlank sweep that races the game.

```
Game's bank-1 tile copy (0x42A7-0x436D)
  ├─ DI window (vanilla unchanged): STAT-wait + 4 tile writes to VRAM
  ├─ EI gap (sound engine catches up)
  └─ NEW: short DI window — VBK=1 + 4 attr writes via [BC]=WRAM_BG_TABLE
```

- **bg_table[256]** copied from bank13:0x7000 → WRAM[0xDA00-0xDAFF] at
  cold boot via the DF02 magic-byte init path. WRAM 0xDA00-0xDAFF
  verified unused by 5000-frame multi-direction + forced-miniboss probe.
- **No FF99 writes outside the original game's own.** This is the
  phantom-sound source we fought in v2.85-v2.89 — the bank-restore
  byte that Timer ISR uses.
- **No bank-switching** in the hook. The 117-byte hook patches in place
  inside the original 199-byte routine; bg_table is bank-1-readable
  via WRAM, no banked CALL needed.
- **DI windows stay ~250-280T**, well below the threshold where Timer
  ISR backlog corrupts the bank-3 sound engine's `D887` consume loop.
- **bg_sweep retained as backup safety net** — removing it broke
  mini-boss state-machine timing (kept as a leash).

Disassembly + design writeup: `docs/inline_hook_analysis_v300.md`

---

## Project structure

```
.
├── rom/
│   ├── Penta Dragon (J).gb              # Vanilla (gitignored)
│   └── working/
│       ├── penta_dragon_dx_FIXED.gb     # Current production (= v300)
│       ├── penta_dragon_dx_v300.gb      # Latest milestone
│       └── penta_dragon_dx_FIXED.v*.backup.gb  # Per-milestone rollbacks
├── scripts/
│   ├── build_v300_inline_hook.py        # Current production builder
│   ├── build_v29*.py                    # Milestone builders (v294-v299)
│   ├── create_vblank_colorizer_v*.py    # Historical builders (v280-v289)
│   ├── probes/                          # 5 self-verifying harnesses
│   │   ├── verify_title_color.py
│   │   ├── verify_phantom_d887.py
│   │   ├── verify_gameplay_palette.py
│   │   ├── verify_miniboss_color.py
│   │   ├── verify_scroll_tearing.py
│   │   ├── gameplay_palette.lua         # Lua: BG palette + attr dump
│   │   ├── phantom_d887.lua             # Lua: D887 watchpoint
│   │   ├── phantom_d887_v2.lua          # Lua: aggressive gameplay test
│   │   ├── title_screenshot.lua
│   │   ├── dump_bg_palette.lua
│   │   └── README.md                    # Harness usage notes
│   ├── launch_mgba.sh                   # /launch-mgba implementation
│   └── deploy_mister.sh                 # /mister-deploy implementation
├── palettes/
│   ├── penta_palettes_v097.yaml         # 8 BG + 8 OBJ + boss palettes
│   └── bg_tile_categories.yaml          # Manual tile-ID → category map
├── docs/
│   └── inline_hook_analysis_v300.md     # v3.00 disassembly + design
├── reverse_engineering/                 # Notes on game internals
├── rl/                                  # RL experimentation (see below)
├── tmp/                                 # Scratch (gitignored)
└── save_states_for_claude/              # Captured test states
```

---

## RL experimentation (parallel track)

A reinforcement-learning subsystem in `rl/` plays Penta Dragon to
generate data and stress-test the colorization in varied scenes.

- `rl/ppo_v19_resume18_ep200.pt` — golden mini-boss kill policy
- `rl/bc_kill_oversampled.pt` — behavior-cloned with kill-frame
  oversampling, 67% mini-boss kill rate
- `rl/train_demo_curriculum.py` — curriculum trainer mixing user-demo
  save states + gameplay_start
- `rl/saves/user_demo/converted/` — 20 PyBoy-loadable states converted
  from mgba `.ss` files via the WRAM+HRAM+OAM injection pipeline
  (`rl/saves/user_demo/inject_to_pyboy.py`)

The RL bot is incidental to colorization but useful for autonomous
exploration when generating wide screenshot coverage for harness
calibration.

---

## Version history (recent — full chain via `git tag`)

| Tag | What changed | Status |
|-----|--------------|--------|
| `colorize-v3.00-inline-hook` | Inline BG-attr write at game tile-copy time | Current production |
| `colorize-v2.99-minimal`     | Minimal bg_table — only items + hazards colored | Backup |
| `colorize-v2.98-refined`     | Floor-edge tiles back to pal0 | Backup |
| `colorize-v2.97-fully-fixed` | Path A calibrated table + Path B viewport sweep | Backup |
| `colorize-v2.95-no-artifacts`| DMG-style title, no green-ball | Backup |
| `colorize-v2.94-three-bugs-fixed` | First merged title+phantom+BG fix | Superseded |
| `rl-v4.21-demo-curriculum`   | mgba .ss → PyBoy state injection | — |
| `rl-v4.20-reward-section-bonus` | Section-advance reward in RL trainer | — |

---

## Legal

Bring your own legally-obtained Penta Dragon (J) ROM. This repo
contains the patching tools and harnesses, not the original ROM data.

---

## Credits

- Original game: **Penta Dragon (J)** — Japan Art Media (JAM) / Yanoman, 1992
- Colorization: penta-dragon-dx project
- Tools: Python · uv · mGBA · PyBoy · MiSTer · Claude
