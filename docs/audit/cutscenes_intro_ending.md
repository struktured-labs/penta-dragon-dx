# Audit: Cutscenes (Intro + Ending) — Render Paths & Colorization Feasibility

Base ROM: `rom/Penta Dragon (J).gb` (DMG, CGB flag 0x00). DX working ROM:
`rom/working/penta_dragon_dx_FIXED.gb`. Analysis combines `tmp/gbdis.py`
static disassembly with mGBA/PyBoy scene and CGB-attribute captures.

> **2026-07-23 correction:** The original version of this audit conflated
> three different sequences. The first title option really is a long story
> prologue (`D880=0x15`); pressing DOWN selects GAME START. The `0x54C0`
> routine is a bridge around the final battle: it presents the Penta Dragon
> transition, calls the bank-2 final-boss loop, and only after that call
> returns does it enter the ending. The corrected map below supersedes older
> “no intro” and “0x54C0 is all ending” wording.

---

## TL;DR

Current production behavior is state-independent: entering a supported story
or ending family starts a bounded loader for all eight BG rows from the YAML
palette deck before the position-aware attribute dispatcher runs. The
production gate checks the exact 64 CRAM bytes, the exact 360 visible
attributes, live tile/glyph content, and native rendered pixels. Correct
attribute indices over stale or all-white CRAM no longer count as colorized.

| Sequence | D880 / FFC1 | Render identity | Current DX behavior |
|----------|-------------|-----------------|---------------------|
| **OPENING START story prologue** (default title option) | `0x15` / `0` | Japanese text, open book, Sara portrait, dragon eye | ROM-native multi-region YAML masks: 160 art cells above 200 BG0 dialogue cells |
| GAME START | DOWN, then confirm | Skips the prologue and enters stage load | Separate path; do not use it to test the story |
| Title attract/logo/menu | `0x00/01/1B/1C` / `0` | Logo, menu, animated banner | Title-specific paths described below |
| **Penta Dragon pre-battle bridge** | `0x19`, then splash `0x18`, then arena `0x14` | Sets `FFBA=8`, shows Penta transition/speech, enters final boss | ROM-native multi-region Penta/Sara art above BG0 dialogue; 57 mGBA samples with zero layout mismatches |
| **Post-final ending** | after bank-2 loop returns: `0x1A→0x16→0x00` / `0` | Lisa/Sara ending, credits, END, epilogue | Exact arts 5/6/7 region masks, then full-screen BG1/BG2/BG3; two 154-panel inventories pass |
| Death/game-over cinematic | `0x17` / `1` | bank14 illustration, then hardware window | ROM-native neutral BG0 containment on both physical maps; six natural boss routes pass |

## 1. OPENING START story prologue (confirmed live)

The title cursor starts on **OPENING START**. Pressing A on the default option
enters `D880=0x15`; pressing DOWN first selects **GAME START** instead. The
automated capture in `scripts/diagnostics/inventory_opening_cutscene.py`
reached the prologue at frame 258 and sampled 33 panels through frame 11778.

Before the 2026-07-23 containment fix, scene dispatch treated `0x15` as a
generic high scene and loaded the Stage 1 semantic dungeon table. Story art
reuses tile IDs such as `0x80`, `0x8D`, and `0xD0` for unrelated image pieces,
so the dungeon table painted large parts of the book, Sara, and dragon-eye
panels red. This was palette-metadata collision, not corrupt graphics.

The production builder now uses panel and screen-position semantics rather
than a global tile-ID table. The uncommitted text preamble remains
`attrs={0:360}`. Once each stock panel identity commits, the visible top eight
rows use its exact multi-region YAML mask: BG5/BG6 for the book,
BG2/BG4/BG5/BG7 for Sara, and BG3/BG6/BG7 for the dragon eye. The separator,
border, and dialogue remain exactly 200 BG0 cells. All 33 sampled panels pass
with no unsafe attribute bits. One frame at an art-page boundary
may still show the complete previous art layout while `DCF0` announces the
next page; the next sample must commit it via `DD07+1==DCF0`.

---

## Death / GAME OVER cinematic (production-contained)

The stock death route publishes `D880=0x17`, renders its bank-14 illustration
on the scrolled `0x9C00` background map, then enables a GAME OVER window backed
by `0x9800` roughly 35 frames later. It writes tile IDs but does not establish
fresh CGB attributes. Before containment, both maps therefore inherited the
last dungeon or boss-arena attributes, producing the reported red lettering
and scattered colored cells.

The production wrapper services bank 13:`0x7100` before scene detection and
skips the ordinary gameplay colorizer for `D880=0x17`. Each VBlank clears
three rows and 24 columns on **both** physical maps to exact attribute byte
zero. Seven phases cover row 31 and rows 0–19, including the scrolled
illustration edge and the complete unscrolled window, without assuming which
map LCDC currently assigns to BG or window. Exact zero selects BG0 and removes
stale VRAM-bank, flip, and priority bits as well as the palette index.

`verify_death_gameover.py` generates exact-ROM checkpoints and follows six
stock boss routes naturally into death: Shalamar, Cameo, Ted, Troop, Faze, and
Penta Dragon. It verifies the illustration, the first window-enable frame,
and settled GAME OVER state with zero displayed non-BG0 or unsafe attributes.
Riff, Crystal Dragon, and Angela use multi-phase boss-local HP semantics, so
the generic checkpoint generator does not falsely force their transition;
they share the same guarded `D880=0x17` runtime service.

---

## 2. TITLE ATTRACT / MENU (not the OPENING story)

---

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
body at 0x42AC contains `06 CC` (`LD B,0xCC`) and `0A` (`LD A,[BC]`) — i.e. it
performs the `bg_table[tile_id]` lookup at WRAM 0xC600 and writes the attr to
VRAM bank 1. **So this path IS colorized** by whatever per-scene table is
active. The release title/banner table is uniformly palette 0.

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

## 3. FINAL-BOSS BRIDGE + VICTORY ENDING

### Trigger — bank0 stage-complete dispatcher `0x1A60`
```
1A78: LDH A,[FFBA]; CP 07; JR Z,1A84      ; skip high-score if FFBA==7
1A7E: CALL 52F4 (high score); CALL 7569
1A84: XOR A; LDH [FFDA],A
1A87: LDH A,[FFBA]; CP 06
1A8B:   JR C,1AA3        ; FFBA < 6 → normal next stage (INC FFBA; CALL 746A)
1A8D:   JP Z,54C0        ; FFBA == 6 → **PENTA DRAGON bridge**
1A90:   (FFBA > 6)       → FFBA=5; FFFA=1; CALL 09CE/556C/09D6 (wrap)
```
The corridor/stage counter **FFBA == 6** means Faze / Stage 7 has just been
cleared, not that Penta Dragon has already been defeated. This matches the
published walkthrough ordering: Boss 07 Faze, then a Penta Dragon pre-battle
speech, then Boss 08 Penta Dragon, then the Lisa/Sara ending. The routine
rewrites FFBA to boss index 8 before entering the final arena.

### Combined pre-battle/post-battle routine — `0x54C0` (bank 1)
```
54C0: LD A,19; LD [D880],A        ; D880 = 0x19  (final-boss bridge)
54C7: XOR A; LD [DCF0],A
54CB: LD A,04; CALL 34CA          ; music set 4
54D0: CALL 5016                   ; reset DMG palettes (FF47/48/49 = FF)
54D3/D6/D9: CALL 492B/40A0/0A16   ; frame sync / render
54DF: LD A,C4; LDH [FF48],A; CALL 0CF2   ; OBP0; draw status row (direct 0D33)
54E6: LD A,08; LDH [FFBA],A       ; FFBA = 8 (Penta Dragon index — final)
54EA: LD A,01; LDH [FFDA],A; LDH [FFE4],A
54F0: CALL 16FD; CALL 174E        ; entity/scroll reset
54FC: CALL 759B                    ; FFBA=8 boss splash; publishes D880=0x18
54FF: CALL 1EC0
5502: CALL 1296                    ; bank 2:0x4000 FINAL-BOSS LOOP
                                     (does not return until Penta is defeated)
5505: LD B,30; CALL 4068          ; post-battle 48-frame delay
550B: LDH [FFF4],A (=0)
5514: LD A,1A; LD [D880],A        ; D880 = 0x1A  (post-final transition)
551E: LD A,05; CALL 34CA          ; music set 5
5526..: render syncs
5530: LD A,16; LD [D880],A        ; D880 = 0x16  (ending render setup)
553C: CALL 3DB5                   ; <<< ENDING GRAPHIC + TEXT RENDER
5545: LD A,06; CALL 3CAB          ; music set 6
5553: CALL 0F33
5556: JP 0150                     ; reboot → back to title
```

`0x1296` is the control-flow boundary the earlier audit missed:

```
1296: LD A,02; CALL 0061          ; map ROM bank 2
129B: CALL 4000                   ; run boss engine
129E: RST 28; RET                ; restore bank only after boss loop returns
```

Within bank 2, the `FFBA=8` setup publishes `D880=0x14`, the established Penta
Dragon arena scene. The pre-battle dialogue is therefore part of the final
boss engine/transition, while `0x1A`, `0x16`, and the direct ending graphic are
post-victory. Do not color-key all of `0x54C0` as one “ending” scene.

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
(0x42A7) and bg_sweep.** No CGB attribute byte is written by the ending
tilemap routine itself.

That did not make the old DX build safe. The attribute maps survive between
screens, and the pre/post-final inline paths had already written Stage 1
palette values into them. Before containment, `D880=0x19` and `0x1A` selected
the dungeon table; the direct-written `0x16` credits and `D880=0x00` final
graphic then inherited those stale red attributes. Captures measured visible
palette-1 contamination in both branches.

The release candidate handles this without changing the original tile
renderer or story timing:

1. `scene_detect` at bank 13:`0x6F90` selects a neutral active tile-ID table
   for story scenes, preventing the Stage 1 semantic table from touching
   dialogue. The active 256-byte table remains WRAM `0xC600`.
2. The ROM-native story sweep at bank 13:`0x7E40` applies each committed
   art ID's exact 20×8 YAML region mask by screen position, always above 200
   BG0 separator/dialogue cells.
3. The finite sweep writes five cells per VBlank quarter, completing three
   32-column artwork passes plus four separator quarters. Its page key includes
   `DCF0`, the active tilemap, and the eight-pixel `SCX/SCY` viewport shift, so
   a scroll or map flip restarts the bounded pass instead of leaving stale
   cells.
4. The direct-written tail uses `D880/D889/DCE2/FFF9`, not stale portrait
   bytes: credits are full BG1, END is full BG2, the epilogue preamble clears
   to BG0, and epilogue text is full BG3.

Every written attribute is an exact palette index with bank/flip/priority bits
zero. There is no unbounded per-frame ending sweep; the original control flow
and audio timing remain intact.

During some direct-written credit pages, the stock ending reuses `$C600` as
ordinary script workspace. The original ROM reproduces the same values at the
same phases. Since `FFC1=0` disables the gameplay LUT consumer and the ending
service owns the complete attribute map directly, the neutral-LUT invariant is
required only for story scenes `$19/$1A`; credits, END, and epilogue are proved
by their exact 360 visible attribute bytes.

Earlier generated ending fixtures exposed a second failure mode: credits or
END could satisfy their BG1/BG2 attribute masks while the captured mGBA frame
was effectively all white. The fixture and production gates now require the
exact eight-row YAML CRAM deck as well as nonempty tile/glyph buffers and a
nonblank chromatic screenshot. These are fatal checks, not advisory metrics.

---

## 4. Does cutscene BG flow through the inline hook / bg_sweep?

| Path | Routine chain | Writes CGB attr? | Picks up bg_table? |
|------|---------------|------------------|--------------------|
| Title banner (D880=0x1B) | `0x1238`→C1A0→`CALL 0x42A5`→`0x42A7` | YES (inline hook attr phase) | YES |
| Title logo/text (D880=0x1C) | `0x0D27`/`0x0D33` direct | NO | NO |
| Title menu glyphs | `0x3C72`/`0x3BE2` direct | NO | NO |
| OPENING story (`D880=0x15`) | mixed inline/direct writers + DX position sweep | YES | Exact arts 1–3 region masks over BG0 dialogue |
| Pre-final story (`D880=0x19`) | mixed inline/direct writers + DX position sweep | YES | Exact arts 4/7 region masks over BG0 dialogue |
| Post-final dialogue (`D880=0x1A`) | mixed inline/direct writers + DX position sweep | YES | Exact arts 5/6/7 region masks over BG0 dialogue |
| Credits/END/epilogue (`D880=0x16→0x00`, `FFE4=1`) | stock direct tile writer + DX ending sweep | Stock: **NO**; DX: **YES** | Full BG1/BG2/BG3 phase layouts |
| Death/GAME OVER (`D880=0x17`) | stock bank14/direct window render + DX two-map neutralizer | Stock: **NO**; DX: **YES** | Exact BG0 on both physical maps |
| bg_sweep | bank13:0x6CD0 | YES, but outer handler is **gated by FFC1==1** | Gameplay only |

Both cutscenes run with FFC1=0, so the gameplay `bg_sweep` is disabled. The
stock final graphic still uses the direct `0x2030` tile-ID copy exclusively;
the separate DX story/ending service runs before the gameplay gate and owns
the corresponding CGB attribute layout.

---

## 5. ROM-native production colorization

The position-aware artistic pass is now in the release ROM. It deliberately
does not derive meaning from reused story tile IDs. A compact runtime key
selects the committed panel and visible viewport, then a bounded quarter sweep
writes exact palette indices into the active attribute map:

- bank 13:`0x7E40` owns the story sweep;
- `0x6D6E` dispatches rows, `0x6C00` writes a five-cell quarter, and `0x6C80`
  handles the separator quarters;
- `0x6CC3` builds the viewport-aware key from the panel, active tilemap, and
  eight-pixel `SCX/SCY` shift;
- `0x6AB5` and `0x6AF5` handle the direct ending phase/column writes;
- `0x6FF1` remains the generic uniform clear used outside these art layouts.

Three artwork passes cover all 32 tilemap columns without an infinite
per-frame rewrite; four final quarters force the separator/dialogue boundary
to BG0. High bits are always zero, so this service cannot accidentally select
VRAM bank 1, flips, or priority.

The direct-written tail has this verified runtime phase trajectory and never
trusts the stale dialogue portrait bytes:

| Phase | Committed guard (`FFC1=0`, `FFE4=1` throughout) |
|-------|--------------------------------------------------|
| Post-final dialogue | `D880=1A`, `D889=01`, `DCE2=00`, `FFF9=00` |
| Credits | `D880=16`, `D889=01`, `DCE2=00`, `FFF9=00` |
| `END` page | `D880=16`, `D889=01`, `DCE2=00`, `FFF9=01` |
| Epilogue preamble | `D880=00`, `D889=0C`, `DCE2=00`, `FFF9=01` |
| Epilogue text | `D880=00`, `D889=0C`, `DCE2=01`, `FFF9=01` |

Two independent full inventories completed the stock ending naturally and
captured 154 panels each: 68 post-final dialogue, 39 credits, 2 END, 3
epilogue-preamble, and 42 epilogue-text samples. The discriminator gate
requires full BG1 credits, full BG2 END, a neutral BG0 epilogue preamble, and
full BG3 epilogue text, while allowing only bounded two-phase transitions.

The fallback remains BG0 for any unclassified or uncommitted panel. The
`D880=0x00` epilogue additionally requires `FFC1=0`, `FFE4=1`, `D889=0x0C`,
and `FFF9=1`, because title/boot reuse `D880=0x00`.

Every artistic revision must rerun the mGBA pixel-pipeline gate in
`verify_final_cutscene_mgba.py`, the story-production and ending-discriminator
gates, plus the title, stage-timing, menu/HUD, later-stage, and boss-arena
gates. The current exact ROM passes both the dedicated 21-gate live profile
and the broader source-bound 51-gate release matrix. PyBoy
remains useful for deterministic inventory and control-flow coverage,
but it is not the final timing/flicker authority.

The title-idle actor spotlight is a separate OBJ problem and is already mapped
from `palettes/monster_palette_map.yaml`; it should not be conflated with the
background story panels.

---

## Addresses / banks / tile IDs (quick ref)
- Title entry: bank0 0x39C3; banner: bank1 0x3A9B (D880=0x1B); logo text: bank1
  0x3BA2 (D880=0x1C); cursor loop: bank1 0x3B1C.
- Title banner tile descriptor: bank1 **0x4E63** (tile IDs 0xE0-0xFF,
  0xCE/0xCF, 0xDE/0xDF) → WRAM C1A0 → inline hook 0x42A5/0x42A7.
- Direct tilemap writers (no attr): 0x0D27/0x0D33, 0x3C72, 0x3BE2, **0x2030**.
- Death/GAME OVER attribute service: bank13 **0x7100**, first in the release
  VBlank wrapper; clears both `0x9800` and `0x9C00` maps.
- Final bridge trigger: bank0 0x1A8D `JP Z,0x54C0` after Faze (FFBA==6).
- Pre-final: bank1 0x54C0 sets FFBA=8, calls splash 0x759B, then `0x1296`
  enters bank2:0x4000 (Penta Dragon, D880=0x14).
- Post-final: when bank2 returns, D880 goes 0x1A→0x16; graphic at bank1
  0x3DB5 resets D880 to 0x00 while FFE4 remains 1.
- Ending tile gfx: **bank14 (0x0E):0x7800** → VRAM 0x9000 (via 0x109E).
- Ending tilemap script: **bank15 (0x0F):0x6F90** (via 0x3DDD).
- Ending tilemap commit: 0x3DDD → 0x3E68/0x3E9E → 0x5559 → 0x2030 (direct, NO attr).
- DX inline hook (colorizes): bank1 0x42A7, body 0x42AC (contains `06 CC`/`0A`
  bg_table lookup). Entries: 0x42A0 (H=0x9C), 0x42A5 (H=0x98).
- DX bg_sweep: bank13 0x6CD0 (outer FFC1 gate; reads active table at WRAM
  0xC600).
- DX colorize handler: bank13 0x6E00; per-scene ROM table → WRAM 0xC600.
- Release `scene_detect`: bank13 0x6F90; uniform clear 0x6FF1; arena tables
  0x7200-0x7AFF.
- ROM-native story service: bank13 0x7E40; row dispatcher 0x6D6E; five-cell
  quarter writer 0x6C00; separator quarter 0x6C80; viewport key 0x6CC3.
- Direct-ending helpers: bank13 0x6AB5 and per-column writer 0x6AF5.

---

## 6. ADDENDUM (2026-07-23): deterministic headless verification — RESOLVED

An ending save state is no longer required for regression coverage. Both
harnesses enter the game's original bank-1 routines only after a normal title
boot has initialized VRAM, CRAM, WRAM, interrupts, and the DX VBlank hook.
They do not fabricate story frames or patch the ROM file.

- **PyBoy inventory:** `inventory_final_cutscene.py` can set the emulated CPU
  register file directly. After 600 normal boot frames it maps bank 1, supplies
  the state that surrounds the chosen branch, and starts the original
  `0x54C0` pre-final or `0x5514` post-final routine. The pre-final path reached
  `0x19→0x18→0x14`. Two full post-final runs covered `0x1A→0x16→0x00`
  and captured 154 panels apiece across the ROM-native dialogue, credits, END,
  epilogue-preamble, and epilogue-text layouts.
- **mGBA pixel pipeline:** `probe_final_cutscene_mgba.lua` modifies emulated
  memory only: after the first title pass has begun, it replaces the
  already-executed instruction at bank-0 `0x39C3` with a jump to a diagnostic
  WRAM stub. The untouched title/attract loop initializes normally and takes
  that branch when it returns around frame 2,046. The stub maps bank 1 and
  jumps to `0x54C0` or the stack-balanced post-final entry at `0x5513`; the ROM
  on disk is unchanged.
- **Gate result:** `verify_final_cutscene_mgba.py` sampled 57 pre-final panels
  and 21 post-final panels. Both branches had zero position-aware layout
  mismatches, zero bad active-table samples, and valid 160×144 screenshots.

This is deterministic original-control-flow coverage, not a claim that a human
playthrough defeated Penta Dragon. A natural victory save state remains useful
for future artistic panel timing, but it is no longer a blocker for the
containment fix.

### Livestream research states

`generate_stream_story_states.py` now turns that deterministic coverage into
12 release-ROM-compatible palette-research states:

| State | Stock identity | Live preview |
|-------|----------------|--------------|
| `opening.ss0` | Default first title option, initial text | neutral |
| `opening_book.ss0` | `15/02/01/01/00` | OpeningBook region mask |
| `opening_sara.ss0` | `15/02/01/02/01` | SaraPortrait region mask |
| `opening_dragon_eye.ss0` | `15/02/01/03/02` | DragonEye region mask |
| `pre_final.ss0` | `19/04/01/04/03` | PreFinalPenta region mask |
| `pre_final_sara.ss0` | `19/04/01/07/06` | SaraPortrait region mask |
| `post_final.ss0` | `1A/05/01/05/04` | PostFinalDragon region mask |
| `post_final_lisa.ss0` | `1A/05/01/06/05` | LisaDragonPortrait region mask |
| `post_final_sara.ss0` | `1A/05/01/07/06` | SaraPortrait region mask |
| `ending_credits.ss0` | `16/01/00/00` | full-screen BG1 |
| `ending_end.ss0` | `16/01/00/01` | full-screen BG2 |
| `ending_epilogue.ss0` | `00/0C/01/01` | full-screen BG3 |

For the eight artwork rows, the five-byte identity is
`D880/DCE8/DCEA/DCF0/DD07`. `DCE8` distinguishes OPENING (`2`), pre-final
(`4`), and post-final (`5`); `DCEA=1` means the story engine is initialized;
and `DD07+1==DCF0` proves the requested artwork has actually committed rather
than merely beginning a page transition. The OPENING route sends A only on the
default first option and never sends DOWN, because DOWN selects GAME START.

After capture, every final-story state is opened in a fresh mGBA process on
the untouched `FIXED.gb` and must retain that complete identity and its exact
160-art/200-dialogue production layout for 60 frames. They are safe one-click
panels in the 42-button livestream scene deck.

The ROM assigns the matching 20×8 YAML region mask to screen tile rows 0–7
(160 cells). Rows 8–17 (200 cells)—including the separator, dialogue border,
and text—are explicitly held on BG0. Lua reasserts this identical mapping after
research-state loads. A rendered audit caught and corrected the earlier row-8
boundary before release: row 8 is already part of the dialogue frame, not
artwork.

Repeated full inventories produced the exact stock art sequences
`[1,2,3]`, `[4,7,4]`, and `[5,7,6,7]`. This discriminator is valid only while
`D880` remains in the corresponding dialogue scene. The bytes remain stale
afterward, so the direct-written tail uses the independent
`D880/D889/DCE2/FFF9` identity shown in the final three table rows. Each tail
state is captured by advancing the stock post-final routine, then must retain
its guard and production layout for 60 frames in a fresh mGBA process.
Credits, END, and epilogue assign all 360 visible cells to BG1, BG2, or BG3;
Lua only reasserts that same layout after loading the state.
