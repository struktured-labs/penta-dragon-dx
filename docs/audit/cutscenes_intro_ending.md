# Audit: Cutscenes (Intro + Ending) — Render Paths & Colorization Feasibility

Static analysis only (no emulator). Base ROM: `rom/Penta Dragon (J).gb` (DMG,
CGB flag 0x00). DX working ROM: `rom/working/penta_dragon_dx_v301.gb`.
Disassembler used: `tmp/gbdis.py` (full LR35902, written for this audit).

---

## TL;DR

| Cutscene | D880 | FFC1 | Tile gfx source | Tilemap commit path | Colorizes today? |
|----------|------|------|-----------------|---------------------|------------------|
| Title "intro" — logo/decor (D880=0x1B) | 0x1B | 0 | bank1 desc @0x4E63 → C1A0 buffer | **inline hook 0x42A7** (via `CALL 0x42A5`) | **YES** (bg_table lookup runs) |
| Title — text rows / menu (D880=0x1C, cursor) | 0x1C / 0x01 | 0 | bank1 strings | **direct VRAM** via `0x0D27`/`0x3C72` | **NO** (no attr write) |
| Victory ending (after Penta Dragon) | 0x19→0x1A→0x16 | 0 | **bank14:0x7800** → VRAM 0x9000; script **bank15:0x6F90** | **direct VRAM** via `0x3DDD`→decompress→`0x5559`→`0x2030` | **NO** (no attr write, attrs stay = palette 0) |
| Death/game-over cinematic (reference) | 0x17 | n/a | bank14 → VRAM 0x9000 | window layer, direct | NO (see `gap_bank14_death_cinematic.md`) |

There is **no separate story-intro animation** between title and gameplay. Game
start (`0x3B37`→`0x3B4D`, sets D880=0x15) jumps straight to the main loop
(`JP 0x0162`) into stage-1 dungeon. The "intro cutscene" *is* the title screen
sequence.

---

## 1. INTRO (title screen sequence)

### Entry & top-level flow (bank 0/1, all resident)
`0x39C3` is the title entry (re-entered each title loop via `JP 0x39C3` at 0x39E8):

```
39C3: XOR A; LD [DD09],A          ; clear input-block
39C7: CALL 0A0E                   ; (setup)
39CA: CALL 492B                   ; (setup)
39CE: LD A,01; LD [D880],A        ; D880 = 0x01  (title music/scene)
39D4: CALL 3AF6                   ; cursor/menu graphic setup  (sets D880 via sub)
39D7: CALL 3BA2                   ; LOGO TEXT rows  (sets D880 = 0x1C)
39DA: CALL 39EB                   ; more title graphics (PENTA banner etc)
39DD: CALL 007E
39E0: LD B,03; CALL 3A9B          ; ANIMATED title graphic ×3  (sets D880 = 0x1B)
39E5: CALL 018D
39E8: JP 39C3                     ; loop
```

### 1a. Logo text path — `0x3BA2` (sets D880 = 0x1C) — BYPASSES colorization
```
3BA3: LD A,1C; LD [D880],A
3BA9: LD A,30; LD D,90; CALL 0D27   ; draw row (tilemap base 0x90xx)
3BB0: LD A,31; LD D,94; CALL 0D27
3BB7: LD A,32; LD D,88; CALL 0D27
3BBE: LD A,33; LD D,8C; CALL 0D27
3BC5: LD BC,0000; JP 41AD
```
`0x0D27`/`0x0D33` is the **direct tilemap writer**: `DI; CALL NZ,0099 (STAT
wait); LD A,[HL+]; LD [DE],A; INC DE; ...`. It writes **tile IDs only** to the
tilemap at DE; it never touches VBK / VRAM bank 1, so no CGB attribute is
written. **Not colorized.**

### 1b. Menu/cursor static fill — `0x3BE2` — direct
`0x3BE2` fills tilemap 0x9800 directly (`DI; CALL 0099; LD A,C; LD [HL+],A …`).
The cursor handler loop is at `0x3B1C` (953 iters per MEMORY.md). Menu glyphs use
`0x3C72` (per-tile copy: loads 2bpp from 0x5400-based gfx into VRAM tile region
via `0x0061` banked copy, then writes tilemap via direct `LD [DE],A`). **Not
colorized** (tile-ID writes only).

### 1c. Animated banner — `0x3A9B` (sets D880 = 0x1B) — USES inline hook (COLORIZES)
```
3A9C: LD A,1B; LD [D880],A
3AA6: LD A,DF; LD HL,C1A0; LD BC,0240; CALL 09A8   ; fill C1A0 buf w/ tile 0xDF
3AB6: LD A,04; LDH [FF43],A; LDH [FF42],A          ; scroll
3ABC: LD DE,8800; CALL 10A1                        ; load tile gfx → VRAM 0x8800
3AC2: LD A,34; LD D,8C; CALL 0D27                  ; (direct row)
3AD2: LD HL,4E63; CALL 1238                        ; build C1A0 from desc @0x4E63
3AD8: CALL 42A5                ; <<< INLINE HOOK (LD H,0x98 → 0x42A7) — COLORIZES
3ADB: CALL 41E4 ...
3AE1: LD B,19; CALL 4068       ; 25-frame delay loop
... animation loop (B=3 outer, 0x516F frame-anim via FFF2 table @0x522A) ...
```
`0x1238` populates the WRAM tile buffer **C1A0** (`LD HL,0xC1A0` @0x124C) from
the title descriptor at bank1 **0x4E63** (tile IDs 0xE0–0xFF, 0xCE/0xCF,
0xDE/0xDF — the decorative title tiles). `CALL 0x42A5` then runs the **DX inline
tile+attr copy** (`0x42A5: LD H,0x98 → 0x42A7`). Verified in DX ROM the patched
body at 0x42AC contains `06 DA` (`LD B,0xDA`) and `0A` (`LD A,[BC]`) — i.e. it
performs the `bg_table[tile_id]` lookup at WRAM 0xDA00 and writes the attr to
VRAM bank 1. **So this path IS colorized** by whatever entries bg_table has for
tile IDs 0xE0-0xFF (today: 0x88-0xDF → pal 1; 0xE0-0xFF → pal 0 in the dungeon
table).

### Entry-point correction (vs `docs/inline_tile_attr_copy.md`)
That doc lists 0x42A4=`LD H,0x98`, 0x42A6=`RET`. The actual bytes (vanilla AND
DX) at `0x42A4` are `26 98 2E 00` = `LD H,0x98; LD L,0x00`. So **`0x42A5` is a
valid live entry** (`LD H,0x98`) that the title (0x3AD8) and the ending-path
buffer flush (0x43BA, via 0x43B8 `LD H,0x98; CALL 0x42A7`) both use. The "0x42A6
RET vestigial" claim is wrong — there is no RET there.

### FFC1 during title
Title sets FFC1=0 (it's never set to 1 until gameplay). Therefore in the DX
colorize handler (bank13:0x6E00) the **FFC1 gate is closed**: bg_sweep,
shadow_main (OBJ), and OAM-DMA all skip. Only `cond_pal` (palette RAM load) and
the cold-boot attr-cleaner run. So on the title, colorization of BG comes
**solely from the inline-hook path (1c)**; the direct-write paths (1a/1b) stay
palette 0. NOTE: `build_v301_gdma.py` lines 457-473 strip bg_sweep's *internal*
FFC1 gate, but the handler still calls bg_sweep *inside* its own FFC1 gate
(lines 638-642), so bg_sweep does NOT run on the FFC1=0 title in production.

---

## 2. VICTORY ENDING (after defeating Penta Dragon)

### Trigger — bank0 stage-complete dispatcher `0x1A60`
```
1A78: LDH A,[FFBA]; CP 07; JR Z,1A84      ; skip high-score if FFBA==7
1A7E: CALL 52F4 (high score); CALL 7569
1A84: XOR A; LDH [FFDA],A
1A87: LDH A,[FFBA]; CP 06
1A8B:   JR C,1AA3        ; FFBA < 6 → normal next stage (INC FFBA; CALL 746A)
1A8D:   JP Z,54C0        ; FFBA == 6 → **VICTORY ENDING**
1A90:   (FFBA > 6)       → FFBA=5; FFFA=1; CALL 09CE/556C/09D6 (wrap)
```
The corridor/stage counter **FFBA == 6** (final stage cleared = Penta Dragon
defeated) dispatches to `JP 0x54C0`. (This FFBA is the level/corridor counter,
distinct from the boss-arena FFBA index that is rewritten per-arena; see
MEMORY.md "FFBA = level/boss counter 0-8".)

### Ending sequence — `0x54C0` (bank 1)
```
54C0: LD A,19; LD [D880],A        ; D880 = 0x19  (ending scene 1)
54C7: XOR A; LD [DCF0],A
54CB: LD A,04; CALL 34CA          ; music set 4
54D0: CALL 5016                   ; reset DMG palettes (FF47/48/49 = FF)
54D3/D6/D9: CALL 492B/40A0/0A16   ; frame sync / render
54DF: LD A,C4; LDH [FF48],A; CALL 0CF2   ; OBP0; draw status row (direct 0D33)
54E6: LD A,08; LDH [FFBA],A       ; FFBA = 8 (Penta Dragon index — final)
54EA: LD A,01; LDH [FFDA],A; LDH [FFE4],A
54F0: CALL 16FD; CALL 174E        ; entity/scroll reset
54FC: CALL 759B; CALL 1EC0; CALL 1296
5505: LD B,30; CALL 4068          ; 48-frame delay
550B: LDH [FFF4],A (=0)
5514: LD A,1A; LD [D880],A        ; D880 = 0x1A  (ending scene 2)
551E: LD A,05; CALL 34CA          ; music set 5
5526..: render syncs
5530: LD A,16; LD [D880],A        ; D880 = 0x16  (ending scene 3 / "the end")
553C: CALL 3DB5                   ; <<< ENDING GRAPHIC + TEXT RENDER
5545: LD A,06; CALL 3CAB          ; music set 6
5553: CALL 0F33
5556: JP 0150                     ; reboot → back to title
```

### Ending graphic render — `0x3DB5` (bank 1)
```
3DB5: CALL 0A16
3DB8: LD HL,C4E0; LD BC,0168; XOR A; CALL 09A8   ; clear C4E0 tile buffer
3DC2: CALL 109E                  ; copy bank14:0x7800 → VRAM 0x9000 (0x800 = 128 tiles)
3DC5: LD HL,6F90; CALL 3DDD      ; build & commit tilemap from script @ bank15:0x6F90
3DCB: LD A,0C; LD [D889],A; XOR A; LD [D880],A; CALL 0F9D
3DD7: LD A,64; CALL 4068         ; 100-frame hold
```
- `0x109E`: `LD DE,0x9000; LD HL,0x7800; LD BC,0x0800; LD A,0x0E (bank14);
  CALL 0x0061` → loads ending tile graphics from **bank 14:0x7800** into VRAM
  tile region 0x9000. (Same bank as the death cinematic, different offset; death
  uses the lower region.)
- `0x3DDD`: switches to **bank 0x0F (15)** (`LD A,0x0F; CALL 0x0061`), then reads
  the layout script at **bank15:0x6F90** (`01 03 1B 00 05 18 05 03 15 14 09 16 05
  FD …` — FD/FE/FF command stream + tile IDs forming the ending text).
  - `0x3DF6` parses (col,row) headers → DE = C4E0 + tilemap offset.
  - `0x3E10` decompresses tile IDs **into the WRAM buffer C4E0** (`LD [DE],A; INC
    DE`), NOT to VRAM. Commands: `0xFF`=terminate, `0xFE`=commit page,
    `0xFD`=newline, `0x2A`+special, `<0x2A`=literal tile.
  - On `0xFE` it calls **`0x3E68`** which calls **`0x5559`**:
    ```
    5559: LD HL,9800; LDH A,[FF40]; RES 3,A; LDH [FF40],A   ; select 0x9800 map
    5562: LD DE,C4E0; LD C,0C; LD B,12                       ; 12 cols × 18 rows
    5569: JP 2030
    ```
  - **`0x2030`** is a pure **direct tile-ID copy**: `DI; STAT-wait mode3→mode0;
    LD A,[DE]; INC DE; LD [HL+],A; … EI` — **no VBK toggle, no attr write.**

### Conclusion for the ending render path
The ending tilemap reaches VRAM through `0x3DDD → 0x3E68/0x3E9E → 0x5559 →
0x2030`, a **direct tile-ID-only copy that completely bypasses the inline hook
(0x42A7) and bg_sweep.** No CGB attribute byte is ever written for the ending
tilemap. With FFC1=0 throughout (`bg_sweep` skipped) and the cold-boot
attr-cleaner long since finished, the ending BG tiles retain whatever attr is
already in VRAM bank 1 — effectively **palette 0** (the cleaner zeroed them at
boot). **The ending is therefore NOT colorized today and will not pick up
bg_table entries** because it never flows through any attr-writing path.

(Contrast: the title banner DOES flow through 0x42A7, so a bg_table entry would
color it. The ending does NOT.)

---

## 3. Does cutscene BG flow through the inline hook / bg_sweep?

| Path | Routine chain | Writes CGB attr? | Picks up bg_table? |
|------|---------------|------------------|--------------------|
| Title banner (D880=0x1B) | `0x1238`→C1A0→`CALL 0x42A5`→`0x42A7` | YES (inline hook attr phase) | YES |
| Title logo/text (D880=0x1C) | `0x0D27`/`0x0D33` direct | NO | NO |
| Title menu glyphs | `0x3C72`/`0x3BE2` direct | NO | NO |
| **Ending tilemap** (D880=0x19/1A/16) | `0x3DDD`→`0x5559`→`0x2030` direct | **NO** | **NO** |
| bg_sweep (any scene) | bank13:0x6CD0 | YES, but **gated by FFC1==1** | YES |

Both cutscenes run with FFC1=0, so bg_sweep is disabled for them. The only
attr-writing path that touches cutscenes is the inline hook, and only the title
banner uses it; the ending uses the direct `0x2030` copy exclusively.

---

## 4. Concrete plan to colorize both cutscenes

### 4a. Intro / title
Two sub-cases:
1. **Banner (D880=0x1B)** already colorizes via inline hook → just give the
   banner tile IDs (0xE0-0xFF, 0xCE/0xCF, 0xDE/0xDF; see desc @bank1:0x4E63) the
   desired palette in the active bg_table at WRAM 0xDA00. Simplest: add a
   **per-scene table swap** keyed on D880 (see 4c) for the title states, OR just
   set those tile IDs in the dungeon bg_table (cheap but those IDs may collide
   with in-game item tiles 0x88-0xDF which are already pal 1).
2. **Logo text / menu (direct-write paths 0x0D27/0x3C72/0x3BE2)** never write
   attrs. Cheapest fix: **let bg_sweep run on the title.** The build already has
   the bg_sweep gate machinery; change the colorize handler's FFC1 gate so that
   bg_sweep (only — not OBJ/OAM) also runs when D880 ∈ {0x01,0x1B,0x1C} (title).
   bg_sweep reads 0xDA00 and will color every visible tilemap row regardless of
   which routine wrote the tile IDs. Combine with a title bg_table (4c). Cost:
   ~one row/frame sweep (~600-900T), already budgeted in v3.00/MiSTer-tested.

### 4b. Ending — bg_sweep is the right lever (inline hook is not reachable)
The ending never calls 0x42A7, so the only way to color it without invasive ROM
surgery is **bg_sweep**. Plan:
1. **Un-gate bg_sweep for ending scenes.** In `build_v301_gdma.py` colorize
   handler, replace the single `LDH A,[FFC1]; OR A; JR Z` gate around bg_sweep
   with a predicate that also passes when `D880 ∈ {0x19, 0x1A, 0x16}` (read
   D880 from WRAM 0xD880). Keep OBJ colorizer + OAM-DMA still FFC1-gated (the
   ending has no gameplay sprites to colorize and shadow_main expects gameplay
   OAM layout).
2. **Provide an ending bg_table.** Build a 256-byte table mapping the ending's
   tile IDs to palettes. The ending uses (a) the font/text tiles (script
   bank15:0x6F90 literals are < 0x4A, e.g. 0x1B/0x15/0x14/0x09/0x16/0x05 and the
   0x40-0x4A range seen in the title-string sibling at bank1:0x6F90) and (b) the
   bank14:0x7800 graphic tiles loaded to VRAM 0x9000 (VRAM tile slots 0x00-0x7F
   of the 0x9000 block → map tile IDs 0x00-0x7F). Probe the actual on-screen
   tilemap for the ending to get the exact IDs (see "probes needed").
3. **Verify bg_sweep coverage matches the ending tilemap.** The ending commits
   18 rows × 12 cols to 0x9800 (LCDC bit 3 cleared at 0x5559). bg_sweep already
   sweeps the active tilemap (it reads LCDC bit 3 → base 0x98/0x9C), and rows are
   driven by SCY/8 + DF04. The ending sets SCY=0 (FF42=0 in 0x3DDD), so rows
   0-17 align — bg_sweep will cover the whole ending. Good.

### 4c. Per-scene table swap (recommended, mirrors arena scene_detect)
Extend the teleport build's `build_scene_detect` (`scripts/build_v301_teleport.py`
line 165) — which today maps D880=0x0C..0x14 → per-boss tables at 0x7200-0x7AFF
and default → dungeon @0x7000 — to also handle cutscene states:
```
D880 == 0x01/0x1B/0x1C → TITLE  bg_table   (new, e.g. bank13:0x7B00)
D880 == 0x19/0x1A/0x16 → ENDING bg_table   (new, e.g. bank13:0x7C00)
D880 == 0x17           → DEATH  bg_table    (optional; see gap_bank14_death_cinematic.md)
else                   → existing dispatch
```
scene_detect copies the matching 256-byte table to WRAM 0xDA00 on D880 change
(~4100T one-shot, ~16T steady). Both the inline hook (title banner) and bg_sweep
(title text + ending) then read the correct palettes from 0xDA00 automatically.
Note `0x16` is reused as both "post-boss reload" and ending-scene-3; gate the
ending table on the ending entry (e.g. also check FFE4=1 or a dedicated flag set
at 0x54C0) to avoid mis-coloring mid-game stage reloads. Safer: trigger the
ending table on D880=0x19 or 0x1A (unambiguous ending states) and keep it loaded.

### Bank-13 space
Production bank13 layout (build_v301_gdma.py): tables end ~0x7100 (attr_comp);
teleport extends arena tables through 0x7AFF. **0x7B00-0x7FFF is free** for the
title + ending (+ death) 256-byte cutscene tables.

### Effort & risk
- Adding scene_detect cases + 2-3 tables + un-gating bg_sweep for ending states:
  medium effort; the scene_detect + per-arena-table machinery already exists and
  is mGBA-verified for 9 arenas.
- Risk: D880=0x16 ambiguity (ending vs post-boss reload); the ending direct-write
  to 0x9800 vs bg_sweep's active-tilemap selection (verify LCDC bit 3 state at
  ending — 0x5559 does `RES 3` so base = 0x9800, and bg_sweep computes base from
  LCDC bit3 → consistent); bg_sweep cost on the (short) ending is negligible.

---

## Addresses / banks / tile IDs (quick ref)
- Title entry: bank0 0x39C3; banner: bank1 0x3A9B (D880=0x1B); logo text: bank1
  0x3BA2 (D880=0x1C); cursor loop: bank1 0x3B1C.
- Title banner tile descriptor: bank1 **0x4E63** (tile IDs 0xE0-0xFF,
  0xCE/0xCF, 0xDE/0xDF) → WRAM C1A0 → inline hook 0x42A5/0x42A7.
- Direct tilemap writers (no attr): 0x0D27/0x0D33, 0x3C72, 0x3BE2, **0x2030**.
- Ending trigger: bank0 0x1A8D `JP Z,0x54C0` (FFBA==6).
- Ending sequence: bank1 0x54C0 (D880 0x19→0x1A→0x16), graphic at bank1 0x3DB5.
- Ending tile gfx: **bank14 (0x0E):0x7800** → VRAM 0x9000 (via 0x109E).
- Ending tilemap script: **bank15 (0x0F):0x6F90** (via 0x3DDD).
- Ending tilemap commit: 0x3DDD → 0x3E68/0x3E9E → 0x5559 → 0x2030 (direct, NO attr).
- DX inline hook (colorizes): bank1 0x42A7, body 0x42AC (contains `06 DA`/`0A`
  bg_table lookup). Entries: 0x42A0 (H=0x9C), 0x42A5 (H=0x98).
- DX bg_sweep: bank13 0x6CD0 (FFC1-gated in handler; reads bg_table@0xDA00).
- DX colorize handler: bank13 0x6E00; bg_table@0x7000 → WRAM 0xDA00.
- scene_detect (teleport build): bank13 0x6FB0; arena tables 0x7200-0x7AFF; free
  space 0x7B00-0x7FFF for cutscene tables.

---

## 5. ADDENDUM (2026-06-14): headless reach/verify of the ending — BLOCKED

Empirical follow-up while implementing the lava + ending polish. Goal: reach the
victory ending headlessly to capture tile IDs and verify a colorization.

Findings:
- **mgba Lua `emu:setRegister`/`readRegister` is NOT available** in this build —
  cannot redirect PC directly.
- **Cold-jumping to `0x54C0` does not run the ending.** Hijacking the title entry
  `0x39C3` with `XOR A; LD[0x6000],A; LD[0x4000],A; LD A,1; LD[0x2100],A;
  JP 0x54C0` (MBC1 forced to clean bank 1) fires when the title loops back to
  `0x39C3` (~f2046, after the banner animation), but D880 then goes to **0x00**,
  never `0x19/0x1A/0x16`, and FFE4 stays 0. So `0x54C0` entered outside the
  natural stage-complete dispatcher (`0x1A60`→`0x1A8D`) does **not** execute the
  ending sequence — it depends on game state the dispatcher sets up first.
- **D880=0x00 ambiguity (showstopper for clean scene-keying):** the ending
  *graphic* displays at **D880=0x00** (set by `0x3DB5`: `XOR A; LD [D880],A`),
  which is the SAME scene byte as the title menu / boot / uninitialized state.
  FFE4=1 (set at `0x54EA`) is the only discriminator. Any palette table keyed on
  D880 alone for the ending would also recolor the title.
- **Colorize-handler space:** the handler (build_v301_gdma.py) is exactly 128
  bytes ending at 0x6E80 (teleport routine start in the teleport build); bg_sweep
  is FFC1-gated there (lines 644-650) so it is skipped during the ending
  (FFC1=0). Adding an ending bg_sweep gate needs space the handler doesn't have.
  A workable but unverified path exists (per-frame `CALL` from the teleport
  routine, like lava_override, gated on FFE4=1 + D880=0x00, loading an ending
  table to 0xDA00 and calling bg_sweep) — but it cannot be verified without a way
  to reach the ending.

Conclusion: colorizing the ending safely needs an **ending save state** (.ss0
captured at the real victory) as an anchor — both to capture the exact tile IDs
and to verify the change without risking the title screen (shared D880=0x00).
Deferred pending that anchor. The ending currently renders via pal0 (the Dungeon
palette: white/light-blue/teal), so it is monochrome-blue, not grayscale.

Probes: scripts/diagnostics/probe_ending_trigger.lua, probe_ending_capture.lua.

## 6. ADDENDUM (2026-06-20, iter 97): death-cinematic-trigger investigation

Goal: reach the death cinematic (D880=0x17) headlessly to test
colorization. Status: **same showstopper as the ending — D880 transition
not triggerable from arbitrary state.**

Findings:
- Forcing `DCBB=0` (via Lua emu:write8) for 300 consecutive frames after
  reaching gameplay (D880=0x02) does **NOT** transition D880 to 0x17.
  The death check is in the game's natural decrement paths (0x1024 and
  0x4200, per MEMORY.md), and just writing 0 to DCBB without the
  decrement-then-check sequence apparently doesn't satisfy the death
  trigger predicate.
- Also tried zeroing `DCDD` (HP) and `DCDC` (sub-counter) simultaneously
  with DCBB=0 — no transition either.
- The existing `death_uses_dungeon_table` test uses
  `force_d880: 0x17` to test the bg_table dispatch, but it does NOT
  trigger the actual death cinematic visual sequence (the screenshot
  shows the original savestate's dungeon room, not the death window
  layer + bank14 graphics).

Reachability options not yet tried:
1. Let the game's natural time-based decrement at 0x4200 fire by waiting
   in gameplay long enough (~minutes? per the per-DCDF/DCDE tick rate).
2. Force `JP 0x4A44` directly via a ROM patch (no Lua PC redirect
   available in mGBA).
3. Trigger via damage path: spawn an enemy with high attack on top of
   Sara at low HP, let collision do the SUB B at 0x1024.

Conclusion: death cinematic colorization is gated on the same
"natural game state" requirement as the ending. Filed for future
iter with proper damage simulation. Probes:
`tmp/probe_death_cinematic.lua` (deleted).

## 7. ADDENDUM (2026-06-20, iter 114-115): RESOLVED — death cinematic IS reachable and IS colorized

The iter-97 conclusion ("death cinematic not triggerable") was based
on trying to force DCBB=0 against a healthy savestate. Iter 114
found the actual reachability path: **level-select with no save data**.

In `tmp/probe_death_capture.lua` (level-select to FFBA=6 with empty
SRAM), Sara naturally dies because:
1. Level-select copies a 0x20-byte checkpoint slot (all 0xFF) into
   gameplay state. DCDD (HP) gets initialized OK but DCBB starts
   low and decrements past 0 quickly.
2. D880 cycles naturally: splash 0x18 → dungeon 0x08 → **death 0x17**
   → title 0x01 → boot 0x00 → splash 0x18 → ... (saved log captured
   at f=538, 1707, 3594, 5217, 6833, 8841 — Sara dies repeatedly).

Savestate captured at `save_states_for_claude/death_cinematic_native.ss0`
(D880=0x17, FFE4=01, FFBA=06).

### iter 115 visual finding — already colorized
The audit's TL;DR claim "Death/game-over cinematic ... NO (see
gap_bank14_death_cinematic.md)" is **WRONG for current builds**.
Iter 115 probed the actual render via the captured savestate:

  f=180 colors: #FF3900=8232, #00C6FF=3191, #A5A5FF=108

The **"GAME OVER" text renders in lava pal 5 colors** (red+cyan)!
The window-layer text picks up BG-pal-5 from surrounding tile attrs
that the dispatch already applied. Visual: the "GAME OVER" splash
shows red GAME OVER letters against red background with cyan accents.

Regression test added: `death_cinematic_game_over_colorized`
(pixel guards #FF3900 ≥ 6500, #00C6FF ≥ 2500, 5/5 zero-jitter).

**The TL;DR table at the top of this doc is OUT OF DATE.** Death
cinematic IS colorized via the existing dispatch chain. The
`gap_bank14_death_cinematic.md` reference predates the current
colorize chain that handles this via BG-pal-5 (lava) bleeding into
the window layer's text region.
