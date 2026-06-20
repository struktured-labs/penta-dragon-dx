# Level-select / high-score screen "color bleed" — root cause (2026-06-14)

## Symptom
The "STAGE 01 / STAGE LOAD / ◆ TOP 3 / 1ST 9999 SEC …" screen shown when you pick
**GAME START with a save present** has orange/red color bleed on the big "STAGE
NN" letters (same tile shows palette 0 AND palette 1 on different cells).

## Root cause (verified)
- This screen is the **level-select** routine `bank1:0x7393` (reached via
  `JP NZ 0x7393` at `0x3B47` when `DCFD != 0`). Its scene byte is **D880=0x00**
  (same as the title menu / boot / ending graphic) and **FFC1=0**.
- It draws the letters with the **direct tilemap writer (tile IDs only, no CGB
  attribute)** and runs its **own input loop (`0x73C3`) with interrupts disabled**
  for the STAT-wait draws — so the **DX VBlank colorizer never runs while it is
  on screen** (probe: cleaner sentinel `DF08` stays `0x00` for 50+ frames; only
  re-arms at ~f270 when the screen is leaving).
- Therefore the letter cells keep whatever BG attributes were last written there
  (by the title banner / prior gameplay via the inline hook) → same tile, mixed
  p0/p1 → bleed.
- **Confirmed**: manually clearing the attr plane (VBK=1, 0x9800-0x9FFF=0) on this
  screen makes the letters uniform p0. So the fix is "clear attrs here".

## Why it's hard (historical)
- The screen is colorizer-dark (own DI'd loop), so all colorize-handler /
  scene_detect-side fixes (which run in our VBlank chain) do NOT reach it. (My
  D880=0x18 splash fix and a D880=0x00 cleaner re-arm both missed it for this
  reason — the only verified win so far is the *OPENING START* brief "STAGE NN"
  splash at D880=0x18, a different screen.)
- A real fix must inject an attr-plane clear into the level-select path itself
  (e.g., repoint `JP NZ 0x7393` through an LCD-off attr-clear, then JP 0x7393).

## STATUS: FIXED (commit 2582e85, 2026-06-14)

The note below ("No free space in bank 0 or bank 1") was correct as a
constraint when this audit was first written, but a later commit
shipped the fix by putting the attr-clear stub in **bank 13** (which
has free space) and copying it to WRAM at boot. The patched `JP NZ`
at `bank1:0x3B47` (file 0x3B48) targets the WRAM stub at `0xDB28`,
which:
  1. Saves HL/BC and LCDC.
  2. Turns LCD off (one-frame glitch acceptable mid-transition).
  3. Sets VBK=1 and zeros `0x9800-0x9FFF` (BG attrs).
  4. Restores VBK=0 and LCDC.
  5. JPs to `0x7393` (the original level-select target).

The stub source is in `scripts/build_v301_teleport.py:build_levelsel_attr_clear_stub`
at ROM `bank13:0x53C2` (34 bytes). Verified live at WRAM `0xDB28`
across f=100/300/500 — bytes match the build script output.

### Verification status
The fix is **deployed and the WRAM bytes are correct**, but a true
end-to-end "screenshot the bleed gone" verification still requires
populated SRAM with actual checkpoint data (to render the full
"STAGE 01 STAGE LOAD ◆ TOP 3 …" screen). The current
`rom/Penta Dragon (J).sav` is empty (all 0xFF), so headless probes
land on a simpler stage-select grid rather than the full bleed-prone
screen. The author of commit 2582e85 confirmed the fix in their own
testing; reproducing it here needs the SRAM populated. **Filed as a
future iter task** — see `tmp/probe_lvlsel_bleed.lua` for the cold-boot
probe scaffold.

### Free space inventory (iter 94 verification, 2026-06-20)
Beyond bank 13, **bank 1 also has free space** that wasn't in the
original audit:
- Bank 1 `0x431C-0x436D` = 82 truly-free bytes (teleport zeroed the
  original STAT-wait copy loop). The 9 ROM-wide refs into `0x4326-0x4363`
  are all intra-bank from banks 2/3/7 — not bank 1.

Useful for future hot-path patches that need to live in a mapped bank
without the bank-switch dance.

## Note
OPENING START (DCFD==0) bypasses the level-select and is clean. The bleed is
only on the GAME-START/continue path.

Probes: probe_scorescreen.lua, probe_levelselect2.lua, probe_scorefix_diag.lua.
