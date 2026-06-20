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

## Why it's hard
- The screen is colorizer-dark (own DI'd loop), so all colorize-handler /
  scene_detect-side fixes (which run in our VBlank chain) do NOT reach it. (My
  D880=0x18 splash fix and a D880=0x00 cleaner re-arm both missed it for this
  reason — the only verified win so far is the *OPENING START* brief "STAGE NN"
  splash at D880=0x18, a different screen.)
- A real fix must inject an attr-plane clear into the level-select path itself
  (e.g., repoint `JP NZ 0x7393` through an LCD-off attr-clear, then JP 0x7393).

## Free space update (iter 94, 2026-06-20)
The earlier "no free space" claim is **out of date** for the teleport ROM. Bank
1 `0x431C-0x436D` is 82 truly-free bytes:
- Original ROM had a STAT-wait copy loop here; teleport zeroed all 82 bytes.
- The 9 ROM-wide refs that point into `0x4326-0x4363` are all intra-bank from
  banks 2/3/7 (those banks have their own code at those addresses, since
  `0x4326` etc. is in the switchable-bank window). Bank 1 is NOT being called
  there.
- Verified by diffing `rom/Penta Dragon (J).gb` vs
  `rom/working/penta_dragon_dx_teleport.gb` at `0x431C-0x436D`: 81 of 82 bytes
  differ (all zeroed in teleport).

## Teleport dispatch redirection
The teleport ROM already redirects `JP NZ 0x7393` at `0x3B48` to `JP NZ 0xDB28`
(WRAM stub). Any attr-clear injection should hook at the DB28 WRAM stub source
OR inject a new bank-1 attr-clear routine and repoint `0x3B48` to it (then JP
to `0xDB28` from the new routine to preserve the existing redirection chain).

## Reproduction note
Headless cold-boot probes (force DCFD=1 + auto DOWN+A from title) do reach a
level-select-like screen at f≥320 but the rendered letters are uniform
lavender — no obvious bleed at this entry path. The audit's bleed likely
requires populated SRAM checkpoint data (a real save with prior gameplay)
because that's what causes the "STAGE 01 STAGE LOAD ◆ TOP 3 …" full screen.
See `tmp/probe_lvlsel_bleed.lua`.

## Note
OPENING START (DCFD==0) bypasses the level-select and is clean. The bleed is
only on the GAME-START/continue path.

Probes: probe_scorescreen.lua, probe_levelselect2.lua, probe_scorefix_diag.lua.
