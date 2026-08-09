# Penta Dragon DX

**Game Boy Color colorization of Penta Dragon (ペンタドラゴン)**

Converts the original DMG ROM into a CGB build with semantically-aware
palettes for floors, walls, items, hazards, and sprites. Its OBJ path colors
the exact alternating Shadow OAM buffer immediately before the game's native
DMA, avoiding stale palette attributes without touching sprite positions.

---

## Status: ⚠️ v3.01 stream RC9 palette checkpoint — audience vote pending

The current release workflow builds `rom/working/penta_dragon_dx_FIXED.gb`
with the exact title footer `DX V3.01 STRUK LABS`. The ROM is intentionally
excluded from Git; the deterministic IPS patch, builder, probes, and
documentation are versioned.

Tag `v3.01-stream-rc9` records the current source and palette-review
checkpoint. Its unpromoted Stage 4/6 prototype builds to MD5
`e8baabaaa6b5d5073dba12985e8cfe00` and SHA-256
`32c3ab3daba362f65dde949e0b350eb65c963f8483bd491e2db76da8bf4bbf7e`.
The complete deterministic profile owns 53 mandatory gates. **53/53 pass**:
cold/warm and post-attract GAME START, the general OG speed matrix, exact
20,000-frame terrain copying, visible pickup containment, all prerecorded/live
pickup forms, the rotating spikes, the bonus room, ordinary/low-health
flicker, all 38 spotlight actors, and the opening/final cutscenes. The natural
north route reaches the byte-exact room-$01 checkpoint 93 gameplay frames
later than stock, within the same explicit 10% OG-speed policy used by the
three-stage matrix (96-frame computed budget). The ROM is not tracked.
The checked-in ROM-free IPS remains the historical RC5 artifact pending the
audience palette vote and reserved MiSTer validation.

### Current stage palette review

[![Current seven-stage palette review](artifacts/stage-collage/penta-dragon-dx-stages-current.png)](artifacts/stage-collage/index.html)

### Gameplay screenshots

<table>
  <tr>
    <td align="center"><img src="artifacts/stage-collage/panels-current/stage1.png" alt="Stage 1 rotating spike room" width="256"><br><sub>Stage 1 — rotating hazard and semantic pickups</sub></td>
    <td align="center"><img src="artifacts/stage-collage/panels-current/stage4.png" alt="Stage 4 cyan floor and blue-gray masonry" width="256"><br><sub>Stage 4 — cyan flooring, blue-gray stone, magenta accents</sub></td>
    <td align="center"><img src="artifacts/stage-collage/panels-current/stage6.png" alt="Stage 6 green chamber" width="256"><br><sub>Stage 6 — green chamber with earthy material separation</sub></td>
  </tr>
</table>

Stage 4 now separates cyan diamond flooring, blue-gray masonry, and restrained
magenta bridge accents instead of applying one magenta ramp to the whole room.
Stage 6 retains its vivid green identity but uses an earthy brown second shade
and independent red health pickups. Stage 6 is intentionally still marked for
audience tuning because the current contrast is lively. The linked gallery
contains one canonical current panel per stage plus explicit Stage 4/6
before-and-after receipts; no ROM image is stored in Git.

| Release gate | Probe | Current result |
|--------------|-------|------------|
| Emulator process safety | `verify_mgba_singleflight_guard.py` | PASS without launching mGBA: raw commands denied, concurrent launch returns 75, parent-death cleanup works, and the suite confirms random-token ownership plus exact process-group cleanup |
| Dedicated live regression | `verify_live_regression.py` | Last standalone profile: **PASS, 25/25** on MD5 `5ab49289505bd04d7a04197f4e30cc96`. The current candidate passes the equivalent gates inside the complete matrix: terrain, rendered spike phases and containment, bleed, pickup-local chroma, bonus, flicker, spotlight, starts, every story illustration, and the complete ending pass |
| Manual low-health flicker | Headed mGBA + saved state/capture | Historical report is now covered by the deterministic low-health fixture; one final headed audience pass remains part of stream preparation |
| Deterministic low-health flicker | `verify_low_health_flicker.py` | **PASS on the current candidate**, 1,600 consecutive rendered frames: 60-frame healthy baseline, forced low-health threshold, natural Gargoyle music init at sample 586, and the complete 40→0 native pulse countdown. BGP stayed `$E4`, zero non-`E4` writes, byte-stable BG CRAM, zero unexpected attribute mismatches, and only 13.163 maximum successive mean RGB movement |
| Full deterministic suite | `run_deterministic_suite.py` | **PASS, 53/53** on MD5 `e8baabaaa6b5d5073dba12985e8cfe00`; two builds were byte-identical and the candidate plus source fingerprint `58aa788c…5ed50` are bound by the [receipt](docs/release/verification/latest.json) |
| Candidate-only IPS round trip | `verify_release_patch.py --candidate-only` | Historical **PASS** for MD5 `798a4363…`; the checked-in distributable IPS remains the historical RC5 artifact pending hardware/audience approval |
| Checked-in distributable IPS (RC5) | `verify_release_patch.py` | **PASS**: historical 6,749-byte IPS MD5 `5a4f5d1a4a8f47802d654021ef4e2a8e` reconstructs RC5 ROM MD5 `95d98e40…` from the supported Japanese base |
| MiSTer reservation guard | `verify_mister_reservation_guard.py` | PASS, unreserved hardware commands stop before SSH/SCP; local-only commands remain usable |
| Audience palette → release ROM | `verify_palette_build_roundtrip.py` | PASS, edited base BG/OBJ, both jet forms, boss overrides, and all powerup bytes bake into a fresh ROM; base colors reach live mGBA CRAM |
| Title footer and palette | `verify_title_screen_integration.py`, `verify_title_color.py` | PASS |
| Complete title/logo/banner cycle | `verify_title_showcase_mgba.py`, `verify_title_visual_receipts.py` | PASS, 399 scene samples + 9 rendered frames; exact cold/returned footer, 0 unsafe/red banner cells |
| Title cursor and option order | `verify_title_cursor_pixels.py` | PASS, native marker defaults to OPENING; DOWN moves it to GAME START; OG and DX retain the same raster-visible partial blink behavior |
| Livestream palette bridge | `verify_live_palette_session.py` | PASS, all 29 builder palettes, guarded special CRAM, serialized rapid edits, repeatable requests, and 42/42 scene buttons |
| `STAGE XX` timing/ditty | `verify_stage_intro_timing.py` | PASS, 156 frames; 232 versus vanilla's 233 timer ticks, no sound rewinds |
| Item-menu HP/MEDICAL attributes | `verify_menu_hud_and_combo.py` | PASS, 0 contaminated cells |
| Item-menu Window publish order | `verify_menu_window_order.py` | **PASS**, the native 6×20 HUD is complete on the first visible Window frame and all 77 visible frames; rejected build was 71/120 tiles wrong on its first frame, fixed build is 0/120 |
| Stale gameplay Window recovery | `verify_menu_window_order.py --inject-stale-frame 800` | **PASS**, the captured `WY=$60` lower-screen overlay is removed by the next VBlank with 0 stale frames after the grace frame |
| Save-present GAME START score screen | `verify_levelselect_screen.py` | PASS, 360/360 visible attributes on palette 0 |
| Cold-process GAME START | `verify_game_start_routes.py` | PASS, eight blank/saved × delayed/prompt × cold/reset routes plus a first-process post-attract route all reach 120 stable Stage 1 frames; live play records 0 attract-wait hits |
| Vanilla gameplay-speed parity | `verify_stage_speed_matrix.py` | **PASS on the current candidate**: Stage 1 97.9%, Stage 5 97.0%, and Stage 7 94.6% of the untouched ROM under the fixed 600-frame right-input matrix. The stricter natural north-route checkpoint passes separately |
| Adversarial speed routes | `verify_stage_speed_matrix.py` | Historical promoted baseline: stationary Stage 5/7 97.1%/100%; right 95.1%/91.6%; patrol 80.1%/91.4% (Stage 5 patrol remains the worst measured case) |
| Headed live speed comparison | Manual user playtest | **PASS**, user reports speed is good on the promoted no-bleed build |
| Ordinary gameplay enemy OBJ palettes | `verify_gameplay_obj_palettes.py` | PASS, 6,290 hardware-OAM samples / 0 mismatches across 7 active combat anchors; the eighth naturally entered its miniboss scene before sampling |
| Idle actor spotlight reel | `inventory_spotlight_roster.py`, `inventory_attract_reel.py` | PASS, all 38 roster identities use their gameplay-YAML family; Sara W/Sara D/Dragonfly travel and Gargoyle sprites have 0 palette mismatches. The natural prerecorded route measures 2,000 Stage 1 frames versus OG 1,856 and 418 Gargoyle frames versus OG 395, with a clean direct return to title |
| ROM-native OPENING story palettes | `inventory_opening_cutscene.py --expect-production` | PASS, each 20×8 illustration exactly matches its position-aware YAML mask above 200 neutral dialogue cells |
| ROM-native final-story palettes | `verify_final_cutscene_mgba.py` | PASS, 57 pre-final + 21 post-final mGBA samples; 0 position-aware layout mismatches or bad story tables |
| Complete ending phase map | `inventory_final_cutscene.py`, `analyze_ending_page_discriminators.py` | PASS, two independent 154-panel runs exactly cover arts 5/6/7 and full BG1 credits, BG2 END, BG0 preamble, and BG3 epilogue |
| ROM-native cutscene pixels and CRAM | `verify_story_attr_production.py` | **PASS on the current candidate**, every story/ending state matches the exact 64-byte YAML BG palette deck and expected 360-cell attribute mask; native captures also contain visible tiles/glyphs and nonblank, chromatic pixels |
| Stage 1 BG colorization | `verify_gameplay_palette.py` | PASS, active map uses floor BG0 + slate-wall BG6 |
| Stage 1 rotating/thrusting spikes | `verify_stage1_spike_palettes.py` | **PASS**, tracked packed-BG fixtures cover every live animation tile `$60–$7F`; 24 YAML-compiled source-art variants use scene-local BG7 teeth, BG5 rings/cylinder, and BG6 supports. Historical fixtures first import all 32 candidate source tiles, then every native capture is decoded at its exact scroll alignment: zero candidate tooth cells render through gray BG0 across all floor/ceiling phases and 400 pre/post-miniboss periodic frames. A separate 600-frame north-scroll receipt keeps room-`$05` `2A-3D` patterned floors on Dungeon BG0. The gate also proves zero tooth color outside the outlines, exact five-row publisher containment, and zero tile/attribute mismatch or red/gold floor wash. |
| Stage 1 pickup class inventory | `verify_pickup_class_palettes.py` | **PASS**, all 19 labeled pickup forms / 73 unique tile IDs resolve to five byte-distinct semantic color classes |
| Stage 1 live pickup palettes | `verify_pickup_live_palettes.py` | **PASS**, all 19 forms resume across 14 current-ROM states; both physical maps use their semantic BG attributes, BG1–BG5 exactly match candidate CRAM, and every launch/artifact is recorded with a bounded transport retry |
| Stage 1 attract-demo pickup palettes | `verify_attract_pickup_palettes.py` | **PASS**, natural cold boot with no input; 5,926/5,926 visible pickup cells use their compiled YAML palette, zero remain on BG0, all six native frames contain chroma inside the exact visible pickup rectangles, no trail survives the four hidden entry frames, and the 2,000-frame segment is within 7.8% of OG timing |
| Stage 1 bonus area | `verify_bonus_stage_live.py` | **PASS**, historical state resumes in current code, both Sara jet palettes exactly match the ROM, visible OAM uses the jet slot, BG attributes remain safe, and three native frames are chromatic |
| Stage 1 pickup color containment | `verify_stage1_no_bleed.py` | **PASS**, 1,206 continuous gameplay frames, 1,128 native transition-window raster captures, six settled receipts, zero mismatched cells, and zero detached pickup-accent pixels across a right/down/left/up route |
| Stage 1 room-map integrity | `verify_stage1_tilemap_copy.py` | **PASS**, 20,000 frames and 4,275 completed 24×24 room copies across both physical maps match the packed native source byte-for-byte with zero mismatches; the prior interrupt race that could shift a complete map by two columns is covered |
| Stage 1 natural north route | `verify_stage1_north_integrity.py` | **PASS**, cold GAME START + straight-north input reaches camera `$03A4` / room `$01`; all 576 packed room bytes, C1A0, and visible VRAM hashes exactly match the untouched ROM, with no gameplay-memory writes |
| Natural north traversal timing | same route receipt | Terrain **PASS**; identical camera `$03A4` / room `$01` takes 1,057 DX gameplay frames versus 964 stock (+93), within the computed 96-frame/10% OG-speed budget |
| Later-stage BG integrity | `verify_later_stage_integrity.py` | **PASS**, exact stage-specific pickup attributes and LUT entries, audited Stage 4 floor/bridge materials, and no unsafe attributes in Stages 2–7 |
| Later-stage 48K-frame soak | `verify_later_stage_soak.py` | **PASS**, mandatory Qt screenshot timing with no stable-frame delay; 1,650 semantic pickup-cell observations plus 32,526 Stage 4 material observations across Stages 2–7 have 0 palette mismatches, pickup-colored terrain cells, unsafe attrs, or lava bleed |
| All nine boss arenas | `verify_boss_arena_palettes.py` | PASS, 9/9 live tables exact and visibly colorized |
| Death / GAME OVER containment | `verify_death_gameover.py` | PASS, six naturally terminating boss variants; both physical maps stay exact BG0 with zero unsafe attributes |
| Phantom sound | `verify_phantom_d887.py` | PASS, 15 one-frame command/clear pairs with no chaining or unpaired writes; progress-sensitive total is 30 transitions versus vanilla's cached 18 and remains below the clean hard ceiling of 36 |
| Scroll stability | `verify_scroll_tearing.py` | PASS, 0.00 changes/s |
| `SELECT+START` safety | `verify_menu_hud_and_combo.py` | PASS, no scene change or freeze |

The current stream-focused candidate ROM is SHA-256
`32c3ab3daba362f65dde949e0b350eb65c963f8483bd491e2db76da8bf4bbf7e`.
Its Stage 1/bonus scope is green, including the rotating-spike material pass,
the repaired natural north route, and the dedicated low-health fixture. The
Local emulator state and raw diagnostic captures remain excluded from Git. A
small curated seven-panel palette-review gallery is versioned for GitHub and
livestream color voting; the ROM itself remains excluded.
The current candidate passes the complete 53-gate release matrix, including
the dedicated live-profile coverage, and rebuilds byte-identically. The checked-in
[full-suite receipt](docs/release/verification/latest.json) binds that ROM to
the exact source fingerprint. Reservation-backed MiSTer hardware and the
audience palette vote remain pending. Historical promoted RC5
receipts remain in
[`docs/release/receipts/c0a29419`](docs/release/receipts/c0a29419), while the
prior `67cf1235` folder retains the six 8,000-frame soak reports and 48-panel
stable-versus-candidate sheet.

---

## Key features

### Emulator process safety

- All maintained headed and automated entrypoints execute mGBA through one
  project-wide nonblocking lock. A second launch fails immediately with status
  75 instead of competing for CPU/GPU resources.
- The wrapper becomes the real emulator process and arms Linux
  `PR_SET_PDEATHSIG`. Killing or timing out its verifier therefore terminates
  that exact emulator and releases the lock instead of stranding `mgba-qt`.
- Deterministic-suite children publish a random-token ownership marker before
  `exec`, bound to their host-visible namespace PID and kernel start time.
  Forked children are identified by the same token in the exact inherited
  single-flight lock descriptor. This prevents rewritten `/proc` environments,
  PID namespaces, or post-exec forks from looking foreign while a stale marker
  or reused PID still cannot claim another emulator.
- The checked-in Claude `PreToolUse` hook rejects raw emulator commands,
  unguarded `--mgba` overrides, and quarantined legacy launchers. `AGENTS.md`
  applies the same no-parallel/no-broad-kill rule to other project agents.
- `scripts/launch_mgba.sh` is the only headed-play entrypoint. It never uses
  broad `pkill` or `killall`.

### Stream-safe title, transitions, and HUD (post-RC5)

- Exact `DX V3.01 STRUK LABS` release footer with a native-style period glyph.
- Intentional white-to-blue-gray title palette with no accidental red text.
- Vanilla-length `STAGE XX` card: the colorizer yields during the stock
  frame-synchronized wait, preventing the intro ditty from repeating.
- Cold GAME START now survives a complete attract-demo cycle. Stock attract
  teardown overwrites the 36-byte level-select trampoline at WRAM `$CFAA`
  without clearing its old `$DF0E` sentinel. Title/level-select frames validate
  the actual executable entry byte (`PUSH HL`, `$E5`) and recopy it when
  necessary; gameplay never touches `$CFAA`, because Stage 1 legitimately
  reuses that address while generating northern rooms.
- The active-play fade shim normalizes the stock `$90/$F9` whole-background
  mappings to `$E4`, eliminating the white checker pulse without blackening
  CGB palette RAM. The complete gameplay/Gargoyle/title return remains within
  10.4% of the measured OG segment timing.
- Clean item-menu HP bar, `MEDICAL` separator, and full-health `F` marker on
  either hardware window map. The VBlank service alternates rows 0/4/5 and
  1/2/3 so the timing-critical HP row cannot be stranded red.
- Both stock item-menu entries copy the complete native 6×20 HUD before
  publishing LCDC's hardware Window. This closes the interrupt-sized gap that
  could expose the prior room map as false walls, black gaps, and an apparent
  extra pickup for one rendered frame.
- Live dungeon VBlank also rejects an already-stale hardware Window whenever
  the stock item-menu flag is clear. This specifically repairs the captured
  persistent split at scanline 96 (`WY=$60`) without touching legitimate menu,
  death/game-over, or story Windows and without adding work to normal gameplay
  frames where LCDC.5 is already clear.
- Neutral death and GAME OVER artwork on either physical tilemap. A bounded
  seven-phase service clears stale arena palette, bank, flip, and priority
  bits before the stock window appears; a mode-safe late check contains the
  final two Faze illustration cells.
- The unstable IRQ-stack `SELECT+START` teleport is removed from production.
- CRAM restores are split into one palette per VBlank and each four-byte half
  is written only with the LCD off, in VBlank, or during a fresh HBlank. This
  keeps audience-tuned palettes exact instead of producing mixed old/new rows.

### Stage and pickup palette containment (post-RC5)

- Stage 1 keeps its tuned floor/wall table and now maps every inventoried
  pickup by meaning: health/restoration uses red BG1; rare/life/score uses
  purple BG2; status cures use green BG3; shields/arrows/teleport use cyan
  BG4; and attack/form powers use gold-red BG5. The inventory covers all 19
  labeled forms and 73 unique tile IDs, including the alternate Health 2
  lower-right tile.
- Exact neutral gaps around those blocks remain BG0, so adjacent font,
  structural art, and `$F0–FF` cannot inherit a pickup palette. Hidden-map
  cache misses retain the native row order so all 24 rows use one coherent
  packed room source.
- Stage 1 room copies initialize their packed-source pointer only after a
  bounded DI closes the setup race. Changed live maps copy in three-tile
  groups, admitting only the Timer/audio interrupt between groups and saving
  its `DE` state outside the interrupted stack. The source pointer therefore
  cannot shift while the stock music timer continues on schedule.
- The Stage 1 raster gate captures 12-frame windows around every scroll/source
  transition, masks hardware OAM, and rejects exact BG1–BG5 pickup accents
  outside raster-aligned pickup cells. This catches rendered bleed that a
  post-frame VRAM comparison cannot see.
- The rotating cylinder is a BG-tile assembly, not an OBJ sprite. Its 32 live
  `$60–$7F` animation IDs are partitioned into 12 teeth on scene-local BG7,
  10 ring/body IDs on BG5, and 10 metallic support/shadow IDs on BG6. The
  builder compiles 24 exact source-art variants from the semantic masks in
  `palettes/bg_tile_categories.yaml`; no runtime art rewrite or OBJ hook is
  involved. The room-aware live publisher covers both the ceiling-mounted
  room-`$02` layout and the floor-mounted room-`$12` layout; their cylinder is
  shifted four packed cells, so each uses its own audited phase sample.
- Audience tuning requires no code edit. Change
  `stage1_hazard_palettes.RotatingSpikeTeeth.colors` in
  `palettes/penta_palettes_v097.yaml` for the tooth/drill row. Change
  `bg_palettes.BG5.colors` for the Stage 1 rings and cylinder body; BG5 is also
  shared by attack/form pickups, so those colors should be judged together on
  stream. Rebuilding selects the hazard BG7 only for Stage 1 and restores the
  ordinary YAML BG7 in the bonus and later stages.
- Stages 2–7 publish only pickup families
  proven by the 24-room capture corpus: Stage 2 rare/life, Stage 3 health,
  Stage 5 health plus rare/life, Stage 6 health, and Stage 7 arrows plus
  rare/life. Stage 4 keeps its ambiguous pickup-looking components out of the
  semantic pickup table, but assigns collision-free diamond-floor IDs to BG4
  and bridge IDs to BG2 over a BG6 stone base. Stage 6 uses the YAML BG3
  green/earth duotone as its base while retaining red BG1 health pickups. The
  shared structural aliases `$A5/$B9/$CF` are never recolored.
- Stages 5 and 7 retain their captured and verified lava-field mappings. The
  pickup rows remain the normal audience-tuneable YAML BG1 (health), BG2
  (rare/life), and BG4 (arrows/navigation), independent of the stage BG0 row.
- Later-stage room publication caches two independent layout signatures plus
  the room ID. A changed layout uses the coherent tile+attribute path; an
  unchanged layout retains the fast native tile path. The bounded repair
  prioritizes the pickup-bearing seam rows before completing every row once.
- Boss arenas remain independently colorized by their nine arena tables.
- The selected table is protected every VBlank after arena entry, including
  Ted's delayed stock sentinel reset that previously restored the Stage 1
  table roughly 250 frames into the fight.
- `probe_stage_integrity.lua` captures both VRAM banks and both map planes;
  `render_stage_integrity.py` reconstructs the background for visual review.

### Title-idle reel and story prologue (unreleased)

- The title cursor defaults to **OPENING START**; press DOWN before confirming
  to select **GAME START**.
- The real title spotlight is scene `D880=0x1B`. Its stock `FFF2` identity
  indexes a packed 38-entry map at bank13:`0x6BE8`; every actor uses the same
  YAML OBJ family as its matching gameplay graphics. Sara W → OBJ2,
  Sara D → OBJ1, and Dragonfly → OBJ4 are explicit roster examples.
- Only spotlight shadow-OAM slots 0–3 are recolored immediately before native
  DMA. The ordinary `D880=0x0A` gameplay demo remains on its normal boss
  mapping, so its Gargoyle palette no longer changes once per second.
- The release ROM now colorizes the OPENING book, Sara, and dragon-eye panels
  from their committed story identities. Each 20×8 illustration uses its exact
  multi-region YAML mask while the separator, border, and 20×10 dialogue area
  remain neutral BG0. The first title option enters this intro; DOWN selects
  GAME START.
- The Penta Dragon pre-battle speech and the Lisa/Sara post-final ending are
  separate paths. Their committed art uses exact Penta, Sara, dragon, and
  Lisa/dragon region masks above neutral dialogue; credits, END, and epilogue
  use full-screen BG1, BG2, and BG3. The scene deck loads ROM-matched states so
  audience edits preview the same mappings that the builder bakes into release.
  Their corrected control-flow map and verification evidence are in
  `docs/audit/cutscenes_intro_ending.md`.

### DMA-ordered Shadow OAM palette pass (unreleased)

The old helper colored ten entries in each Shadow OAM buffer. That missed
ordinary enemies in slots 10–23, and the main loop could rebuild the future
DMA buffer with palette 0 after it had already been colored.

The release builder now predicts which of `C000`/`C100` the immediately
following `FF80` DMA will select, colors all 40 entries in that one buffer,
then lets the native DMA run. Sara's dynamic palette and boss-slot semantics
are preserved. An mGBA hardware-OAM gate checks every stable ordinary enemy
tile on every frame rather than inferring success from WRAM.

The title-idle reel and ordinary gameplay intentionally use separate maps:

| Context | Mapping |
|---------|---------|
| Title-idle reel | Packed 38-entry `FFF2` identity map at bank13:`0x6BE8`, compiled from gameplay YAML families |
| Ordinary gameplay | Packed runtime ranges: `30–3F→3`, `40–4F→4`, `50–5F→5`, `60–6F→6`, `70–7F→7` |
| Sara | Dynamic `FFBE`: Witch palette 2, Dragon palette 1 |
| Bosses | Existing boss-specific OBJ slot table |

### Arena-Dispatched Inline Hook
The inline hook at bank1:0x42A7 dispatches based on scene:

- `D880=0x02`, `DCFD=0` (the main prerecorded Stage 1 demo) → stock-width
  tile-only copying; the native room-expander seam stamps only actual pickup
  metatiles into both attribute maps before they become visible
- `D880=0x0A`, `DCFD=0` (the later Gargoyle miniboss demo) → stock-width
  tile-only copying with its separate bounded Shield-row repair
- `D880=0x02`, `DCFD=1` (live Stage 1) → the stock `$DC00` future-map phase selects the
  per-map cache; changed maps copy tile+attribute atomically in native row
  order, while steady maps retain the exact stock-width tile-only path
- D880 `0x06`/`0x08` (Stage 5/7 lava) → atomic tile+attribute copy when
  the packed tile source or camera signature changes
- Other dungeon scenes → native tile copy with their neutral scene baseline
- Title, story, and boss scenes → tile-only here; their dedicated bounded
  services own attributes
- Hardware window enabled (item menu) → tile-only, preserving palette-0 HUD attrs

### Legacy teleport debugging

The older `penta_dragon_dx_teleport.gb` debug build contains the retired
IRQ-stack teleport experiment. It is not a release artifact and must not be
used for livestream/release validation. A safe main-loop browser teleport can
be added later without restoring the stack redirect.

---

## Quick start

### Build

#### Stream release candidate (`FIXED.gb`)

```bash
python3 scripts/build_v302_title_fix.py
# → rom/working/penta_dragon_dx_FIXED.gb
```

Generate and verify the distributable patch:

```bash
uv run penta-colorize build-patch \
  --original "rom/Penta Dragon (J).gb" \
  --modified rom/working/penta_dragon_dx_FIXED.gb \
  --out rom/penta_dragon_dx.ips
python3 scripts/diagnostics/verify_release_patch.py
```

The patch accepts only the verified Japanese base ROM with MD5
`df43e0adfdc74b2829c7e95e91c71a28`. The checked-in 6,749-byte IPS has MD5
`5a4f5d1a4a8f47802d654021ef4e2a8e` and reconstructs the RC5 ROM MD5
`95d98e40efa97a1882c00e5977161d5a`; copyrighted source and output ROMs are
not distribution artifacts.

### Build the ROM-free pre-hardware bundle

After a full matrix pass, build the deterministic IPS/readme/checksum archive
and four native 160x144 submission screenshots:

```bash
python3 scripts/build_release_bundle.py \
  --emulator-manifest /tmp/penta-release-candidate/manifest.json
```

Without a hash-bound MiSTer pass and audience palette approval, the script
emits only `Penta_Dragon_DX_v3.01_PREHARDWARE.zip`; its bundled readme says
not to publish it. `--final` fails closed unless both approvals match the exact
ROM, patch, emulator manifest, and production palette YAML. No ROM, save, or
savestate can enter the archive allowlist. See `docs/release/README.md`.
After the livestream vote, `scripts/record_palette_approval.py` independently
rebuilds the ROM from the approved YAML before it writes that approval.

Romhacking.net's database stopped accepting new submissions in August 2024.
The current packaging target is Romhack Plaza, whose rules permit IPS/ZIP
patch releases, forbid ROM files, and require native-resolution screenshots:

- https://community.romhackplaza.org/help/terms/
- https://romhackplaza.org/news/many-new-things-on-the-plaza/

### Test in mGBA

```bash
# Verified human-testing launch (KDE Wayland + NVIDIA):
scripts/launch_mgba.sh rom/working/penta_dragon_dx_FIXED.gb
```

Do not pipe, redirect, background, or bypass this launcher. It uses the
project's xcb display setup, holds the single-flight lock, and remains the
exact parent guardian of mGBA. If another emulator owns the slot, wait for it;
never use a broad `pkill` or `killall`.

### Run verification probes

The pre-stream live profile is one command. It runs 25 historically fragile
emulator paths serially—including exact prerecorded/live pickup palettes,
rotating spikes, the bonus room, Stage 1 tile-copy integrity, and visible color
bleed—and writes a hash-bound manifest plus every gate's screenshots and JSON
receipts below the requested output directory. The prerecorded pickup gate
binds six native screenshots to exact visible pickup rectangles and requires
chromatic pixels inside each rectangle; unrelated screen color cannot make it
pass. Any failing gate leaves the profile red:

```bash
python3 scripts/diagnostics/verify_live_regression.py \
  rom/working/penta_dragon_dx_FIXED.gb \
  --output /tmp/penta-live-regression
```

The authoritative deterministic suite refuses an occupied emulator slot,
builds the candidate twice under `/tmp`, requires byte-identical output, runs
all current gates sequentially, and writes a source-bound receipt only after
the complete matrix passes:

```bash
python3 scripts/diagnostics/run_deterministic_suite.py
```

Passing all 53 emulator/local-tooling gates does not replace the
reservation-backed MiSTer FPGA sweep required before release. The historical
`scripts/probes/full_verification_loop*.sh` scripts target the retired
teleport build and are not release evidence.

The repository's legacy `scripts/mister.py` entry point fails closed before
all MiSTer status, SSH, SCP, input, launch, screenshot, or deployment work.
After acquiring a reservation through the shared service, expose its lease ID
and trusted local checker:

```bash
MISTER_RESERVATION_ID='<active lease>' \
MISTER_RESERVATION_CHECKER='<reservation-service check command>' \
python3 scripts/mister.py reservation_check
```

The checker receives `MISTER_RESERVATION_ID` and
`MISTER_RESERVATION_HOST`; it must exit zero only while that exact lease owns
that exact host. It is re-run before every SSH/SCP boundary so an expired lease
cannot remain cached during a long command. No checker is bundled, because
reservation ownership belongs to the external shared service. MiSTerClaw MCP
calls must follow the same reservation rule.

Once reserved, start the physical release sweep from the exact successful
emulator manifest:

```bash
python3 scripts/mister.py release_sweep_start \
  /tmp/penta-release-candidate/manifest.json
```

Navigate with the physical controller. At each state, capture and explicitly
confirm the live output:

```bash
python3 scripts/mister.py release_checkpoint \
  tmp/mister_release_sweeps/.../manifest.json title confirm
```

The required visual checkpoints are title, default OPENING route, DOWN→GAME
START route, STAGE card, Stage 1 gameplay, item menu, a later stage, a boss
arena, and death/GAME OVER. `release_sweep_finish` refuses to emit
`hardware-pass` until every checkpoint is confirmed, the live core is still
GBC, the deployed/local ROM hashes still match, and every screenshot remains
intact. A failed capture cannot reuse an older screenshot.

Individual gates remain useful while developing:

```bash
# Title screen (must show 2+ colors, >5% non-white)
python3 scripts/probes/verify_title_color.py rom/working/penta_dragon_dx_FIXED.gb

# Entire title/logo/animated-banner cycle must stay artifact-free
python3 scripts/diagnostics/verify_title_showcase_mgba.py rom/working/penta_dragon_dx_FIXED.gb

# Default marker is OPENING; DOWN moves it to GAME START
python3 scripts/diagnostics/verify_title_cursor_pixels.py rom/working/penta_dragon_dx_FIXED.gb

# Exact STAGE XX/ditty duration versus the original ROM
python3 scripts/probes/verify_stage_intro_timing.py rom/working/penta_dragon_dx_FIXED.gb

# Title, menu HUD, and retired SELECT+START safety
python3 scripts/probes/verify_menu_hud_and_combo.py rom/working/penta_dragon_dx_FIXED.gb

# First and every visible item-menu Window frame must match its native HUD
python3 scripts/diagnostics/verify_menu_window_order.py \
  rom/working/penta_dragon_dx_FIXED.gb \
  --output /tmp/penta-menu-window/report.txt

# DOWN selects GAME START; its save-present score screen must remain clean
python3 scripts/diagnostics/verify_levelselect_screen.py rom/working/penta_dragon_dx_FIXED.gb

# Gameplay palette (must show 10+ distinct BG palette words)
python3 scripts/probes/verify_gameplay_palette.py rom/working/penta_dragon_dx_FIXED.gb

# Long Stage 1 room-map test (tile IDs, not only palette attributes)
python3 scripts/diagnostics/verify_stage1_tilemap_copy.py \
  rom/working/penta_dragon_dx_FIXED.gb --frames 20000 --timeout 60

# Ordinary enemy tiles must match the production map in hardware OAM
python3 scripts/diagnostics/verify_gameplay_obj_palettes.py rom/working/penta_dragon_dx_FIXED.gb

# Later-stage neutral baseline + Stage 5/7 lava containment
python3 scripts/diagnostics/verify_later_stage_integrity.py rom/working/penta_dragon_dx_FIXED.gb

# Long-run containment across Stages 2-7
python3 scripts/diagnostics/verify_later_stage_soak.py rom/working/penta_dragon_dx_FIXED.gb --frames 8000

# Every boss arena must load its exact dedicated table
python3 scripts/probes/verify_boss_arena_palettes.py rom/working/penta_dragon_dx_FIXED.gb

# Stock death illustration and GAME OVER window must remain neutral
python3 scripts/diagnostics/verify_death_gameover.py rom/working/penta_dragon_dx_FIXED.gb

# Title-idle Sara W/Sara D/Dragonfly identities must select OBJ2/OBJ1/OBJ4
python3 scripts/diagnostics/inventory_attract_reel.py rom/working/penta_dragon_dx_FIXED.gb --frames 14000

# Default OPENING option: exact ROM-native art/dialogue palette split
python3 scripts/diagnostics/inventory_opening_cutscene.py rom/working/penta_dragon_dx_FIXED.gb --expect-production

# Both original final-story branches through the mGBA pixel pipeline
python3 scripts/diagnostics/verify_final_cutscene_mgba.py rom/working/penta_dragon_dx_FIXED.gb

# Miniboss colorization
python3 scripts/probes/verify_miniboss_color.py rom/working/penta_dragon_dx_FIXED.gb

# Scroll tearing (must be ≤0.50 changes/s)
python3 scripts/probes/verify_scroll_tearing.py rom/working/penta_dragon_dx_FIXED.gb

# Phantom sound (must be ≤1.5× vanilla baseline)
python3 scripts/probes/verify_phantom_d887.py rom/working/penta_dragon_dx_FIXED.gb

# Cold-boot title menu semantics and Stage 1 entry
python3 scripts/diagnostics/verify_hardware_gate.py rom/working/penta_dragon_dx_FIXED.gb
```

## Live palette editing session

```bash
scripts/palette_session.sh start
```

This boots the verified `FIXED.gb` through the correct XWayland/NVIDIA launch,
attaches `live_palettes.lua`, serves the color picker on loopback port 8077,
and opens the browser UI. Its 42-button Stream Scene Deck loads 15 curated
emulator states, 12 ROM-matched story/ending states, six Stage 2–7 states, and
all nine boss arenas without changing release-ROM control flow. The group
includes the intro's first text/book/Sara/dragon-eye panels, pre-final
Penta/Sara, post-final dragon/Lisa/Sara, credits, the END page, and the
epilogue. Generated stage/story/boss states are refreshed automatically when
the ROM checksum changes.

The boss-state generator starts from a freshly generated Stage 1 state,
modifies only a temporary copy of mGBA's serialized CPU/memory state to enter
the original boss dispatcher, and then runs and recaptures every arena for 240
frames on `FIXED.gb`. The browser never writes PC, stack, `D880`, or `FFBA`.
The five final-story states are likewise recaptured from the original routines,
then loaded in fresh mGBA processes against the untouched ROM before they can
enter the deck. Their artwork previews use the exact stock
`D880/DCE8/DCEA/DCF0/DD07` discriminator; the separator, dialogue border, and
text remain on neutral BG0. These are ROM-native attributes, not an emulator
overlay. Credits, END, and epilogue use independent complete ending-phase
guards and all 360 visible cells on BG1, BG2, and BG3, respectively.

Stop with `scripts/palette_session.sh stop`.

Only palettes actually changed in the browser are reapplied, so unrelated
boss/scene CRAM is preserved. All 29 production palette rows are exposed:
eight BG, eight primary OBJ, eight guarded boss overrides, two guarded jet
forms, and three guarded powerup projectiles. Saving updates those exact YAML
arrays without reformatting commentary and creates a hash-named pre-save
backup; rebuild with `build_v302_title_fix.py`. The title keeps its proven
BG7→BG0 boot mask. The phased CRAM service then restores independently tuned
BG7 for gameplay, one palette per VBlank with LCD-mode-safe four-byte writes.
When the default `FIXED.gb` would change, the builder
first preserves its previous bytes as
`penta_dragon_dx_FIXED.prebuild_<md5>.backup.gb`; rebuilding identical bytes
creates no redundant backup. The session stop command tracks its own PIDs and
does not kill unrelated mGBA windows.

```bash
python3 scripts/diagnostics/verify_live_palette_session.py \
  rom/working/penta_dragon_dx_FIXED.gb
```

The retired SELECT+START teleport and raw state-byte holds are absent from this
workflow.

For the show order, title-control explanation, audience-vote sequence,
post-stream rebuild, approval, and recovery steps, use
`docs/stream_runbook.md`.

---

## Architecture

```
scripts/
├── build_v301_gdma.py           # Base production ROM builder
├── build_v301_teleport.py       # Teleport ROM builder (extends gdma)
├── build_v302_title_fix.py       # v3.01 stream RC builder
├── build_release_bundle.py       # Deterministic ROM-free guarded packager
├── record_palette_approval.py    # Explicit post-stream palette hash lock
├── patch_oam_intercept.py       # Retired experimental intercept (not release path)
├── palette_session.sh           # Release-safe headed stream launcher
├── live_palette_editor.py       # Loopback browser palette UI
├── lua/live_palettes.lua        # Selective live CRAM + scene-deck bridge
├── bg_experiment.py             # Colorizer codegen utilities
├── probes/                      # Verification probes (5 main + extras)
│   ├── verify_title_color.py
│   ├── verify_gameplay_palette.py
│   ├── verify_miniboss_color.py
│   ├── verify_scroll_tearing.py
│   └── verify_phantom_d887.py
└── diagnostics/                 # Diagnostic harnesses
    ├── inventory_opening_cutscene.py
    ├── inventory_final_cutscene.py
    ├── verify_gameplay_obj_palettes.py
    ├── generate_stream_stage_states.py
    ├── generate_stream_boss_states.py
    ├── generate_stream_story_states.py
    ├── verify_live_palette_session.py
    ├── verify_mister_release_workflow.py
    ├── verify_live_regression.py
    ├── verify_release_candidate.py
    ├── verify_levelselect_screen.py
    ├── verify_final_cutscene_mgba.py
    ├── verify_later_stage_soak.py
    ├── verify_sprite_flicker.py
    └── verify_title_cursor_pixels.py

palettes/
├── bg_tile_categories.yaml      # BG tile category → palette mapping
├── monster_palette_map.yaml     # Per-monster-type palette assignments
└── penta_palettes_v097.yaml     # CGB palette color definitions

docs/
├── release/                      # Public readme template + packaging contract
├── o1_oam_intercept_plan.md     # Historical intercept design
├── per_monster_palette_plan_v2.md  # Per-monster palette design
├── VBLANK_HOOK_LIMITATIONS.md   # VBlank hook constraint documentation
└── inline_hook_analysis_v300.md # Inline hook design analysis
```

---

## Toolchain

- Python 3.12+
- `pyboy` (headless emulation for probes)
- `Pillow` (screenshot capture and analysis)
- GBDK-2020 / SDCC (for future C-based features)
