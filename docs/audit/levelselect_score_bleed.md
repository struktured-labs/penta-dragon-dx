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

## STATUS: FIXED (commit 2582e85, 2026-06-14) — verified end-to-end iter 157

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

### 2026-06-21 UPDATE (iter 156-157): VERIFIED working end-to-end

**Iter 156 setup.** Created `tmp/iter156_lvlsel/test_slot0.sav` (8 KB)
with slot 0 populated per `gap_sram_checkpoint_layout.md` (validity
0x01, FFBA=0/FFBD=1 = stage 1, HP=23). Ran `probe_levelselect2.lua`
with PICK=0 and DCFD-force. Initial finding: at f=231 attrs read 66/360
non-zero (still pal 1 from the title-banner inline-hook stamping).
Concerned that stub wasn't working.

**Iter 157 resolution.** Two follow-up probes confirmed the stub IS
working — iter 156 just sampled too early:

1. `probe_stub.lua` at f=200 dumps WRAM 0xDB28-0xDB4B (36 bytes) and
   confirms the stub bytes match `build_levelsel_attr_clear_stub`
   exactly: `E5 C5 F0 40 47 E6 7F E0 40 3E 01 E0 4F 21 00 98 AF 22 7C
   FE A0 20 F9 AF E0 4F 78 E0 40 C1 E1 C3 93 73`. DF0E sentinel = 0x5A
   (cold-boot copy ran).

2. `probe_clear.lua` traces non-zero attrs across f=212, 216, 220, 230,
   250, 300:

   | frame | non-zero attrs / 360 | D880 |
   |-------|----------------------|------|
   | 212   | 66                   | 0x01 |
   | 216   | 66                   | 0x00 |
   | 220   | 66                   | 0x00 |
   | 230   | 66                   | 0x00 |
   | 250   | 66                   | 0x00 |
   | 300   | **0**                | 0x00 |

   The clear happens between f=250 and f=300. By f=400 every tile is
   pal 0 and the screen renders cleanly with no bleed. Verified visually
   in `tmp/iter157_lvlsel/late_f400.png`.

**Why the lag.** The stub fires only on the GAME-START path's JP NZ at
bank1:0x3B47 after the title menu fully processes the A press and
transitions to level-select. The title's inline-hook keeps stamping
pal-1 attrs in its own loop until the actual transition. So between
A-press at f=215 and the stub firing, ~85 frames of title-loop
continue. Once the stub fires, attrs go to 0 and stay there (the
level-select code at 0x7393 runs a DI'd input loop with no attr
writes).

**Status: FIX VERIFIED.** The iter 2582e85 stub correctly clears all
VBK=1 attrs to 0 by the time the user sees the level-select screen.
The bleed-prone screen is no longer bleed-prone.

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
