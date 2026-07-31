# Changelog

This project records source-level changes only. Copyrighted ROM images and
emulator save/state files are never release artifacts in this repository.

## [Unreleased]

## [v3.01-stream-rc5] - 2026-07-30

### Added

- Inventory all 19 labeled Stage 1 pickup forms from the real serialized mGBA
  VRAM states, covering 73 unique tile IDs and the alternate Health 2 tile.
- Add `verify_pickup_class_palettes.py` as release gate 16. It proves every
  inventoried tile maps to its named semantic class, checks the exact compiled
  LUT histogram, requires five byte-distinct palette rows, and renders a
  contact sheet from the real pickup graphics.

### Changed

- Split the former single red pickup class into five audience-tunable groups:
  health/restoration red, rare/life/score purple, status cures green,
  shields/navigation cyan, and attack/form powers gold-red. Exact surrounding
  font and structural gaps remain neutral.
- Generalize the scroll-transition raster audit from red-only detection to the
  exact accent colors of BG1–BG5. The 1,200-frame box route captured 1,143
  transition windows with zero mismatched cells and zero detached pickup-color
  pixels.
- Expand the deterministic release contract to 38 serial gates. Two clean
  builds produced ROM MD5 `95d98e40efa97a1882c00e5977161d5a` / SHA-256
  `5de405686c5779bc2db4df0ddc3659813e5d7d03ab39f8970f919dfec587a4eb`;
  the complete matrix passed 38/38 with source fingerprint
  `3c41da448ba794c37448a26d9878099bc928dabd9a6b4441487b6bc5ecceb048`.
- Regenerate the ROM-free 6,749-byte IPS (MD5
  `5a4f5d1a4a8f47802d654021ef4e2a8e`) so it reconstructs the exact RC5
  candidate from the supported Japanese base ROM.

## [v3.01-stream-rc4] - 2026-07-30

### Fixed

- Add a committed deterministic release suite and pre-commit receipt hook.
  `run_deterministic_suite.py` builds the candidate twice, requires identical
  bytes, runs all 37 emulator gates serially, verifies that its source inputs
  did not change, and writes `docs/release/verification/latest.json` only
  after a complete pass. The hook rejects a missing/stale receipt and any
  staged ROM, save, RAM, or savestate. The final isolated run passed 37/37
  against two byte-identical SHA-256
  `78dc24cfc8111d359d1742e1744f824b6715fd7664ea54666a1126b2700f5f7a`
  builds and source fingerprint `2cbdbfdc937ebaa1…`.
- Make the deterministic-suite preflight fail closed when any mGBA process
  already owns the host slot. It reports the exact process and exits 75 rather
  than stacking Penta verification on another project's emulator workload.
  While the matrix runs, a 50 ms host monitor permits only descendants carrying
  its random 256-bit ownership token, confirms a foreign PID/group across
  three polls to avoid `/proc` exec races, and caches the token-proven host
  group across PID namespaces. If a foreign mGBA starts later, the suite stops
  only its exact matrix and token-owned groups, leaves the foreign owner
  untouched, rejects the run, and withholds the receipt. It also fails and
  cleans up if any token-owned emulator survives a normally completed matrix.
- Terminate the three independently sessioned speed, frame-flicker, and Stage
  1 color-bleed probes by their exact `xvfb`/mGBA process groups. Stopping only
  the `xvfb-run` shell could orphan Qt; the successful 37-gate run leaves zero
  mGBA processes on the host.
- Exercise both natural title-to-Stage-1 routes as a release gate. The probe
  presses the real title controls without injecting scene, level, PC, or SRAM
  state and requires stable nonwhite gameplay before the deadline.
- Fix the true first-process, post-attract GAME START white-screen freeze.
  Stock attract teardown overwrites the 36-byte level-select trampoline at
  WRAM `$CFAA` but leaves its historical `$DF0E` sentinel set. The title
  prelude now validates the trampoline's actual `$E5` entry byte and recopies
  it when clobbered. Eight normal blank/saved × delayed/prompt × cold/reset
  routes and the exact cold post-attract route all reach 120 stable gameplay
  frames. The fix changes only three bytes versus the prior 36/36 ROM and
  preserves its sample-406 Gargoyle return.
- Keep the save-present level selector out of the title palette repair without
  borrowing a title/reel counter or stock state. Its existing 36-byte clear
  stub publishes the out-of-range palette phase `$A0`; natural Stage 1 entry
  replaces it with the normal `$11` phase. Cycle-balanced title work retains
  the proven attract cadence while GAME START no longer stalls.
- Move both title CRAM repairs 116 CPU cycles earlier inside VBlank while
  preserving the wrapper's exact total cadence and register postconditions.
  This removes the reproducible scene-01 sample whose final BG0 byte was
  `$7F` instead of `$00`, without reintroducing reel slowdown or flicker.
- Add a hard project-wide mGBA safety boundary. Maintained GUI, headless, live
  palette, and regression entrypoints now share one atomic nonblocking lock;
  concurrent launches fail with status 75. The wrapper execs the emulator and
  arms Linux parent-death cleanup so killing a verifier cannot leave an
  orphaned Qt process. A checked-in Claude `PreToolUse` hook rejects raw mGBA,
  unsafe `--mgba` overrides, and quarantined legacy launchers; `AGENTS.md`
  forbids parallel emulator tools and broad `pkill`/`killall` for all agents.
  The hardware-free release gate proves lock exclusion, release, hook denial,
  and parent-death cleanup without launching an emulator.
- Make the title BG0/BG7 restore and death/GAME OVER fade share bounded
  eight-byte CRAM copy paths. The title path now runs early enough in VBlank
  to commit both complete palettes; the death path retains its guarded fade
  sequencing.
- Move the bounded room-attribute repair away from the Stage 7 WRAM-copy
  source and assert both regions at build time. This removes the code/data
  overlap behind later-stage random tiles and black holes.
- Preserve the previously proven ordinary demo/gameplay instruction cadence
  byte-for-byte while keeping the death-only fade service behind its local
  dispatcher. The Gargoyle demo now returns at sample 405 of 500 without BGP
  pulses or all-white active palettes.
- Align the title-cursor pixel gate with stock hardware behavior. Both the
  original ROM and DX can expose one raster-visible partial blink frame; the
  verifier now accepts only a contiguous prefix/suffix of exact native marker
  rows while still rejecting pixels on the wrong option or malformed rows.
- Let the ordinary-gameplay OBJ verifier select bounded subsets of its combat
  anchors, so all hardware-OAM mappings can produce durable receipts without
  exceeding the outer automation window.
- Neutralize both traced sources of the stock `$90/$F9` whole-background
  pulse: keep the `$281C` gameplay-effect routine instruction-width stable and
  normalize active-play writes through `$0F5E` (including caller `$01D4`) back
  to `$E4`. The compact fade shim no longer rewrites all 64 BG CRAM bytes to
  black. The full reel still reaches Gargoyle and returns, measuring
  1,978/436 frames versus the OG's 1,856/395.
- Keep the native fade shim out of cold title/menu CRAM. It had blackened the
  spotlight background while leaving colored actors visible, erasing the
  `PENTA DRAGON` art and monster name cards. Restore title BG0/BG7 immediately
  on the first available VBlank so the CGB boot-white palette cannot flash.
- Make flicker a failing mGBA release gate: audit 500 rendered Gargoyle-demo
  frames and 240+ gameplay frames, reject `$90/$F9` pulses, all-white visible
  palettes, steady active-BG changes, and premature/overlong demo returns. The
  title-showcase gate also requires renderer-visible spotlight header/name
  pixels, so a colored actor on a black background cannot false-pass.
- Replace the broad red Stage 1 pickup mapping with six confirmed eight-tile
  bands (`$88–8F` through `$D8–DF`) plus eight exact IDs attributed from a
  headed native capture: `$A0/$A1/$B0/$B1` and `$A6/$A7/$B6/$B7`. All 56
  confirmed pickup tiles use the cherry-red BG1 accent; remaining interleaved
  font/structural tiles and `$F0–FF` stay BG0 so pickup color cannot bleed into
  unrelated art.
- Eliminate the transition-time Stage 1 pickup bleed visible in the headed
  captures, including the vertical-only failure that survived the earlier
  horizontal route. Up/Down now forces an atomic hidden-map refresh and
  invalidates that destination's `$DC00` cache for one settling pass; ordinary
  horizontal movement retains the fast future-map cache.
- Commit rows 4–23 before wrapping through rows 0–3, and store each four-cell
  attribute group from right to left after its tile IDs. A departing pickup's
  red attribute is therefore neutralized before its replacement floor reaches
  the PPU. The helper restores the stock final `HL`, `DE`, `A`, and zero-flag
  contract, while the input-blocked title demo is phase-aligned separately.
- Upgrade the cold-boot Stage 1 gate from a post-frame VRAM-only assertion to
  a rendered-raster audit. It drives 1,200+ continuous gameplay frames,
  drives a right/down/left/up route, captures 12-frame windows around every
  scroll/source transition, masks current/previous pickup and OAM rectangles,
  and requires every sampled visible cell to match the compiled LUT. The
  fixed candidate passes 1,143 transition captures with zero mismatched cells
  and zero detached red pixels.
- Make the release harness resume already-passed hash-bound gates after an
  external runner interruption. Incomplete/running results are discarded on
  resume, the isolated ROM hash is rechecked, and only proven passes survive.
- Move the livestream palette editor from the retired teleport ROM to the
  release-candidate `FIXED.gb`. Replace browser-driven SELECT+START simulation
  and raw state-byte holds with a 42-button deck of curated/generated mGBA
  states.
- Generate ROM-matched Stage 2–7 states through the original save-present
  level-select path. They are cached outside release artifacts by ROM checksum
  and regenerated automatically before a palette session when necessary.
- Add all nine stage/final boss arenas to the livestream deck. Their temporary
  entry states patch only mGBA's documented serialized CPU/memory fields, then
  run and recapture for 240 frames on the untouched release ROM; no boss
  navigation code or diagnostic ROM is used by the stream.
- Validate generated boss states by their persistent `D880=$0C..$14` scene
  identity. `FFBA` is only an input to the stock `$1A2B` dispatcher and becomes
  runtime scratch afterward; treating it as persistent made valid states
  false-fail even though all nine scenes were stable for 240 frames.
- Add four OPENING story states generated by confirming the title's default
  first option with A only: first text, book, Sara, and dragon eye. Their route
  never presses DOWN, which remains the separate GAME START selection.
- Add five final-story art states for pre-final Penta/Sara and post-final
  dragon/Lisa/Sara. Each state is captured from the original bank-1 story
  routine, then loaded for 60 clean frames in a fresh mGBA process against the
  untouched release ROM before it is admitted to the livestream deck.
- Add guarded credits, END-page, and epilogue states captured by advancing the
  stock post-final routine. Each must retain its complete
  `D880/D889/DCE2/FFF9` phase identity and its ROM-native full-screen
  BG1/BG2/BG3 layout after a fresh mGBA reload.
- Color the eight artwork panels through their exact stock
  `D880/DCE8/DCEA/DCF0/DD07` identities. Only the top eight artwork rows use
  the matching BG1–BG7 palette; all 200 separator/dialogue cells remain on BG0.
  The production ROM writes this layout; the Lua bridge only reasserts the
  identical mapping after loading a research state.
- Apply only BG/OBJ palettes explicitly edited during the live session. This
  allows audience changes to survive normal game palette reloads without
  overwriting unrelated arena or miniboss CRAM.
- Expose every palette row consumed by the production builder: 8 BG, 8 primary
  OBJ, 8 boss overrides, 2 jet forms, and 3 projectile powerups. Boss, jet,
  and powerup edits use exact `FFBF`/`FFD0`/`FFC0` guards and save back to the
  same YAML entries the builder emits. Add stable Spiral and Shield scene
  buttons, expanding the deck to 42 states.
- Serialize threaded palette updates through a single atomic bridge writer, so
  rapid audience-driven color changes cannot race over the same temporary
  file. Give every scene-button click a monotonically increasing request ID;
  clicking the same scene again now reliably reloads it instead of being
  mistaken for unchanged bridge content.
- Preserve the exact prior palette YAML in a hash-named stream-session backup
  before a changed browser save. Identical saves leave the YAML untouched and
  create no redundant backup.
- Round RGB888/BGR555 conversion to the nearest representable channel value
  instead of flooring in both directions. The previous math biased audience
  picks darker and failed to round-trip 32,760 of the 32,768 valid CGB words.
- Make the palette-session launcher use the verified XWayland/NVIDIA command
  and stop only its recorded mGBA/editor PIDs; unrelated emulator windows are
  no longer killed.
- Stop an existing owned palette session before regenerating its cached states,
  and fail startup if the XWayland/xcb mGBA process exits immediately. A Qt
  display-device failure can no longer leave an apparently successful browser
  session backed only by the editor.
- Generate the six Stage 2–7 stream states sequentially. Starting three
  offscreen `mGBA-Qt` display contexts concurrently could terminate one capture
  with signal 11, making an otherwise valid livestream session fail
  nondeterministically.
- Publish the live-bridge smoke marker only after requesting its rendered PNG,
  keep mGBA alive for the host-side acknowledgement, and wait for the image
  before evaluating it. This removes the intermittent missing-screenshot race.
- Replace the stale title-cursor probe that hard-coded the retired teleport ROM
  and cropped copyright text. The rendered gate now follows the cursor through
  its blink cycle and proves the native triangle moves
  OPENING START → GAME START → OPENING START with DOWN/UP.
- Isolate vanilla/candidate save and savestate paths in the stage-timing,
  phantom-sound, and scroll probes. Baseline measurements can no longer rewrite
  ROM-adjacent user `.sav` files.
- Make the repository's legacy MiSTer automation fail closed before every
  status, SSH, SCP, launch, input, screenshot, or deployment action. It now
  requires an external reservation checker to validate the active lease ID
  against the exact target host before every hardware boundary, without
  logging checker output; local-only cheat listing/building remains available
  without touching the shared hardware.
- Bind the editor to loopback and preserve YAML comments/ordering when saving
  audience-selected colors instead of reserializing the entire file.
- Complete the audience-tuning round trip into the production builder.
  Independently tuned BG7 is now stored outside the title's intentional
  BG7→BG0 boot mask and restored by a one-palette-per-VBlank CRAM service when
  FFC1 enters gameplay. Each palette is copied as two LCD-mode-safe four-byte
  halves, eliminating partial old/new palette hybrids; BG0 tuning no longer
  trips a hardcoded byte assertion. The
  previously omitted Turbo projectile palette is emitted from YAML too.
- Let the production builder accept explicit palette, intermediate, and output
  paths so a tuned release can be built and tested entirely under `/tmp`
  without overwriting the working candidate.
- Preserve the previous default `FIXED.gb` as a hash-named rollback ROM before
  any audience-palette rebuild changes it. Identical rebuilds are detected and
  do not create redundant backups; an existing backup is never overwritten
  unless its bytes already match the candidate being preserved.
- Color all 40 entries in the exact Shadow OAM buffer selected by the
  immediately following native DMA. The previous helper colored only ten
  entries in each alternating buffer, leaving ordinary enemies in slots 10–23
  flat blue or only partly colored after the main loop rebuilt their palette
  attributes.
- Preserve the existing gameplay packed-tile cascade, dynamic Sara palette,
  and boss slot assignment in that complete pass. The title-idle reel remains
  a separate scene-gated consumer with its own three-identity palette table.
- Keep the save-present GAME START level-select/high-score screen on neutral
  attributes. The screen disables interrupts and bypasses the normal
  colorizer, so its existing WRAM entry stub clears both BG attribute maps
  before jumping into the original drawing loop.
- Identify the real title spotlight as `D880=0x1B`, not the ordinary
  `D880=0x0A` gameplay demo. Its stock `FFF2` identity selects Sara W → OBJ2,
  Sara D → OBJ1, or Dragonfly → OBJ4 through a three-byte table at
  bank13:`0x6BF0`; slots 0–3 in the exact next-DMA shadow buffer receive the
  selected palette.
- Leave the `D880=0x0A` Gargoyle demo on the normal boss mapping. It no longer
  enters a mislabeled reel pass or changes palette roughly once per second.
- Align the footer period glyph source to the GDMA engine's 16-byte boundary
  at bank13:`0x6D50`, so both cold and returned title screens render the exact
  `DX V3.01 STRUK LABS` string instead of a stray character.
- Route the sliding `PENTA DRAGON` banner to neutral attributes and clear
  stale hardware OAM once on the transition into it. Returning from demo play
  rearms the same cleanup, removing the remaining accidental red banner traces.
- Route the default **OPENING START** story prologue (`D880=0x15`) through a
  viewport-aware production mapper. The book, Sara, and dragon-eye panels use
  BG1/BG2/BG3 across the top 160 cells, while separator/dialogue stays on BG0.
  Pressing DOWN on the title remains the way to select the actual GAME START
  option.
- Stop applying the Stage 1 semantic background table to later dungeon
  tilesets. Penta Dragon replaces more than half of its BG character slots
  between stages, so shared tile IDs were being misclassified as metallic
  walls or items; the resulting dark palette fills looked like random tiles
  and black holes even though the underlying level data was intact.
- Route Stages 2–4 and 6 to a neutral background-attribute baseline until
  their palettes are tuned individually. Preserve the audited Stage 5 and 7
  lava IDs on palette 5 and leave all nine boss-arena tables unchanged.
- Reassert the later-stage table across the delayed stage-load cold-boot clear,
  preventing the Level 1 table from returning several frames after entry.
- Route the Penta Dragon pre-battle bridge (`D880=0x19`) and post-final
  transition (`D880=0x1A`) through the same position-aware mapper. Committed
  Penta/Sara/dragon/Lisa artwork uses BG4–BG7 above neutral BG0 dialogue.
- Add ROM-native direct-ending layouts keyed by
  `D880/D889/DCE2/FFF9`: credits are full BG1, the END page is full BG2,
  epilogue preamble clears to BG0, and epilogue text is full BG3.
- Make the story mapper finite and VBlank-bounded: five-cell quarter sweeps
  complete three 32-column artwork passes plus 40 lower-panel quarters across
  visible rows 8–17. Its
  page key includes the active tilemap and eight-pixel SCX/SCY viewport shift,
  and every written attribute has unsafe bank/flip/priority bits cleared.
- Split the six-row menu HUD reset into alternating VBlank groups 0/4/5 and
  1/2/3. This prevents the old overlong burst from leaving the HP/MEDICAL/F
  row at stale red attributes when VBlank ended mid-copy.
- Contain the stock death illustration and GAME OVER window on neutral BG0.
  A seven-phase VBlank service clears 24 columns across both physical
  tilemaps, including unsafe bank/flip/priority bits, before either map can
  become visible. A mode-safe wrapper-tail check clears the final two
  Faze-specific cells at `$9DCC/$9DCD` after the stock late draw.
- Preserve every arena's selected background table across delayed stock
  cold-boot-sentinel resets. Ted triggered such a reset roughly 250 frames
  after entry and silently restored the Stage 1 table; all nine arena tables
  now remain exact throughout the verification hold.
- Replace the obsolete 274-byte distributable IPS, which reconstructed a
  months-old ROM differing from the release candidate in 5,934 bytes. The
  deterministic 6,749-byte IPS now targets the supported Japanese base and
  reconstructs the exact emulator-green RC4 ROM.
- Add a deterministic, three-file release packager that independently rebuilds
  and applies the IPS, requires the successful full emulator manifest, and
  emits four distinct, decodable, nonblank native 160x144 submission
  screenshots. Its archive allowlist excludes ROMs, saves, and savestates.
- Make public packaging fail closed: until a MiSTer hardware-pass manifest and
  livestream audience-palette approval bind the exact ROM, patch, emulator
  manifest, and palette YAML, only a conspicuous `PREHARDWARE` archive can be
  built and its readme says not to publish it.
- Add an explicit post-stream palette-approval recorder. Before signing the
  audience choice, it rebuilds entirely under a temporary directory and
  requires the approved YAML to reproduce the exact release ROM byte-for-byte.
- Add a Twitch stream runbook covering the verified xcb launcher, the
  OPENING-first title controls, a 42-scene audience-vote order, shared boss-BG
  palette caveats, safe save/recovery behavior, and the exact post-stream
  build → IPS → 37-gate matrix → approval → MiSTer → final-package sequence.
- Replace the permissive MiSTer deploy smoke test with a hash-bound physical
  release-sweep workflow. Wrong cores and failed screenshots now abort; stale
  images cannot be recycled as new evidence; every title/game/story/stage/menu/
  boss/death checkpoint needs an explicit human confirmation before
  `hardware-pass` can be sealed.
- Document Romhack Plaza as the current database submission target because
  Romhacking.net stopped accepting new database entries in August 2024. The
  prepared archive follows Plaza's patch-only ZIP/readme/native-screenshot
  requirements and never uploads anything.
- Restore near-vanilla gameplay throughput by limiting the expensive atomic
  tile-plus-attribute copy to the two audited lava scenes (`D880=0x06/0x08`).
  Other dungeon scenes keep the native tile path plus the bounded VBlank
  repair.
- Inline the central sprite emitter's exact `$1FFF=0x0A/0x00` writes instead
  of calling stock helpers that save and restore a dead accumulator 3,900+
  times per speed route. The exact promoted candidate executes 139 stock
  main-loop entries versus vanilla's 142 while moving (97.9%) and 145 versus
  148 while stationary (98.0%); it reaches gameplay at frame 308 versus 309
  and reaches the dungeon at 487 versus 489.
- Make lava-room refresh detection cover camera X, camera Y, and the packed
  tile-source byte. The compact even-valued signature shares the existing
  ready-marker byte without aliasing its odd `0xA7` value, so a changed room
  cannot display one frame of palette-5 attributes over stale tile IDs.
- Restore the title spotlight's native bank-1 four-quadrant sprite emitter.
  A title-only dispatcher now lazily loads the actor's YAML OBJ palette,
  recolors its four shadow-OAM slots, and invokes the stock OAM DMA. Sara W,
  Sara D, and Dragonfly are all visible again and use OBJ2, OBJ1, and OBJ4
  respectively.
- Extend the Gargoyle/demo miniboss override across its complete animated tile
  range (`0x30–0x7F`) and restore the ordinary gameplay LUT on boss exit. The
  palette no longer changes once per second as animation crosses the old
  `0x4F` cutoff.
- Correct the short later-stage verifier: it now follows `SCX/SCY` for the
  visible safety audit and checks both prepared tilemaps for exact Stage 5/7
  lava tile/attribute pairing. A neutral Stage 5 entry viewport is valid; its
  prepared map contains 308 audited lava cells with zero mismatches.
- Replace the timing-sensitive Stage 5/7 sparse palette-map cache keys with
  receipt-bounded raw-tile XOR keys that are injective across every captured
  layout and stable across duplicate raw variants (Stage 5: 20 layouts/22
  variants; Stage 7: 26/28). Independent metadata remains keyed by room and
  physical BG map.
- Initialize hot OAM helpers on the existing room-repair slow path when a
  legacy gameplay savestate resumes with an empty sentinel. This restores
  ordinary enemy palettes without adding the every-VBlank timing shift that
  caused excess sound-engine transitions.
- Move helper-readiness checks onto title-family branches so the returned
  banner keeps its exact native cadence while ordinary gameplay avoids the
  old unconditional VBlank cost. The production sound trace is 30 D887
  transitions versus vanilla's cached 18, below the clean hard threshold of
  36.
- Make the later-stage soak trace record the exact `$9800/$9C00` destination
  selected by the two native tile-copy entries, retain first-mismatch source,
  map, attribute, and shadow dumps, and support immediate screenshots for
  very brief room routes.
- Make the ending inventory key captures on VRAM attributes and tile state as
  well as rendered pixels. The static END page can commit BG2 without changing
  its framebuffer checksum; the old sampler skipped the full phase it later
  required.
- Replace the stale frame-script speed release gate with the exact-scene
  matrix: each route waits for 120 consecutive stable gameplay frames and
  counts the stock main-loop entry at `$016C` for both vanilla and DX.

### Current validation candidate (2026-07-30)

- Two independent source builds reproduced MD5
  `4f20b0cb7ab206c0216282a2f8fd113d` (SHA-256
  `78dc24cfc8111d359d1742e1744f824b6715fd7664ea54666a1126b2700f5f7a`)
  byte-for-byte. The isolated 37/37 receipt binds it to source fingerprint
  `2cbdbfdc937ebaa1e7486e390699b407a2ea821b4cf84e1b753b34a8a34250f6`.
  The deterministic checked-in IPS reconstructs this exact candidate without
  committing or distributing the copyrighted ROM.
- Title/footer/banner and all 38 spotlight actors pass with zero unsafe/red
  title cells and YAML-derived actor palettes. The spotlight name cards remain
  visible.
- Stage 1 completed 1,206 continuous frames with 1,143 transition-window
  raster captures, six settled receipts, zero tile/attribute mismatches, and
  zero detached red pixels across horizontal and vertical movement. The
  ordinary OBJ audit sampled 6,290 hardware-OAM entries across seven active
  combat anchors with zero mismatches; the Gargoyle miniboss and all nine boss
  arenas pass separately.
- Stages 2–7 completed 48,000 aggregate soak frames across rooms 1, 3, 5, and
  7 with zero unexpected attributes, unsafe bits, or lava mismatches.
- All six natural death carryover shapes reach neutral fades and GAME OVER
  with zero chromatic pixels or unsafe attributes. Opening, pre-final,
  post-final, credits, END, and epilogue anchors retain their production
  BG1–BG7 layouts.
- Controlled speed routes pass the ten-percent release tolerance: Stage 1
  136/141 (96.5%), Stage 5 160/164 (97.6%), and Stage 7 153/167 (91.6%) stock
  main-loop entries. Gameplay/demo flicker, scroll, menu/input, stage-card
  timing, sound pulse shape, deterministic palette rebuild, and all 42
  livestream scene buttons pass.

### Resolved release blocker

- The retired `3c0bef5d37ae178504b00823314e467c` build ran only 56 stock
  main-loop entries versus vanilla's 120 and felt 25–50% slower in headed
  play. RC4 reaches 136/141 Stage 1 loop entries (96.5%), 160/164 in Stage 5
  (97.6%), and 153/167 in Stage 7 (91.6%) over identical 600-frame rightward
  routes. The older stationary and patrol matrix remains recorded as an
  adversarial baseline.

### Verified

- A one-command release harness copies the candidate to `/tmp`, runs all
  current emulator gates sequentially, retains per-gate logs and rendered
  artifacts, and checks both ROM hashes after every gate. All 37 serial gates
  pass with source and isolated-copy MD5
  `4f20b0cb7ab206c0216282a2f8fd113d`. MiSTer remains the separate
  reservation-backed hardware requirement.
- The deterministic 6,749-byte IPS (MD5
  `f32b2293dd3cd5d63852fbb08ebb13a7`) reconstructs exact candidate
  `4f20b0cb…` from supported base MD5
  `df43e0adfdc74b2829c7e95e91c71a28`.
- Two independent packaging runs produced the same archive SHA-256, contained
  only IPS/readme/checksum files, preserved fixed ZIP timestamps, and rejected
  `--final` without both hardware and audience approval manifests.
- A hardware-free regression exercises the release-sweep state machine:
  non-GBC launch aborts, stale screenshots are rejected, incomplete checkpoint
  sets cannot seal, and only an intact fully confirmed manifest reaches
  `hardware-pass`. It makes no MiSTer connection.
- The current production palette YAML rebuilt twice through independent
  temporary outputs to MD5 `4f20b0cb7ab206c0216282a2f8fd113d`,
  byte-for-byte equal to the promoted working candidate, validating
  deterministic reproduction without falsely recording an audience vote.
- A tuned-YAML build gate changes BG0, BG7, OBJ2/Sara Witch, both jet forms,
  Gargoyle/Boss3, and all three powerup colors on a temporary copy, builds a
  fresh release ROM, checks their exact bank-13 bytes, and boots that ROM in
  mGBA. It proves the title retains the BG7 boot mask while gameplay restores
  tuned BG7 and exposes tuned BG0/OBJ2 through live CGB CRAM, without changing
  the workspace candidate. The same gate verifies the hash-named rollback
  contract and unchanged-build no-op.
- The MiSTer reservation regression gate proves an unreserved `status` call
  exits before its handler and before any network subprocess, exercises both
  checker rejection and acceptance against an exact lease/host pair, and
  confirms local-only commands remain usable. The test never contacts MiSTer.
- A new full-cycle mGBA title gate covers `D880=0x01`, logo animation
  `0x1C`, and the complete `0x1B` PENTA DRAGON showcase instead of sampling
  only the first menu frame. Across 399 scene samples and nine
  rendered screenshots, it finds zero nonzero/unsafe attributes, zero
  red-dominant pixels, exact blue-gray BG0 CRAM, and a neutral active table
  throughout the animated banner.
- The end-to-end stream gate drives the browser HTTP API, serializes 64
  concurrent edits without loss, proves two identical scene-button clicks
  remain separately observable, exhaustively round-trips all 32,768 CGB color
  words, confirms selective BG3/OBJ4 edits in mGBA's actual CGB CRAM, saves
  through a temporary YAML copy with seven targeted color lines changed,
  verifies exact guarded boss/jet/Spiral/Shield/Turbo CRAM, an exact pre-save
  backup plus an unchanged-save no-op, and loads/renders all 42 scene-deck
  states—including 12 freshly generated story/ending states, Stages 2–7, and
  all nine release-ROM boss arenas. Every artwork state passes its
  committed-panel guard and 160-art/200-dialogue attribute split; the three
  ending-tail states pass exact phase guards and 360-cell BG1/BG2/BG3
  previews. No production ROM-state or teleport directive is emitted.
- Eight checked-in combat states reproduced the old defect with 3,816 wrong
  hardware-OAM samples out of 6,456. The repaired build checks 6,562 ordinary
  enemy samples over 120 consecutive frames per state with zero mismatches,
  including actors through Shadow OAM slot 23.
- The exact promoted build passes the title reel, gameplay OBJ, stage-intro
  audio/timing, Stage 1 palette, menu HUD, `SELECT+START`, speed, later-stage
  integrity/soak, scroll stability, both story paths, both ending inventories,
  live palette deck, deterministic rebuild, and IPS reconstruction in one
  coherent 37/37 manifest.
- The title-default menu semantics are exercised explicitly: DOWN moves from
  OPENING START to GAME START, `DCFD=1` enters the original colorizer-dark
  level-select path, and all 360 visible cells are palette 0 after its 55 score
  tiles are drawn.
- A 14,000-frame cold-boot trace reached the complete title-idle spotlight and
  checked 448 Sara W, 442 Sara D, and 444 Dragonfly samples across X=2–158
  with zero palette mismatches. The same trace observed 4,889 ordinary demo
  miniboss sprites with zero deviations from its fixed boss palette.
- The default title choice reaches `D880=0x15`. Across all 33 sampled OPENING
  panels through frame 11,779, every committed art page reaches an exact
  160-cell BG1/BG2/BG3 top region above 200 BG0 dialogue cells, with no unsafe
  attributes. The capture tolerates only the single verified one-sample
  previous-page handoff immediately before a newly announced art page commits.
- Corrected the cutscene map: the `0x54C0` path begins after Faze, sets
  `FFBA=8`, enters the bank-2 Penta Dragon loop, and continues into the ending
  only after the final boss returns. The pre-battle speech and post-final
  ending are captured independently with their ROM-native position-aware
  BG4–BG7 artwork and BG0 dialogue layouts.
- Original final-story routines pass the mGBA pixel-pipeline gate: the
  pre-final branch sampled 50 panels through `0x19→0x18→0x14`, and the
  post-final branch sampled 15 panels through `0x1A→0x16`, with zero layout
  mismatches or bad active tables. Two full PyBoy inventories each captured
  154 post-final panels through the `D880=0x00` epilogue with the required
  BG5/BG6/BG7 dialogue art and full BG1/BG2/BG3 ending layouts.
- The complete post-final trace now proves independent guards for the
  direct-written tail: `D880/D889/DCE2/FFF9` distinguish dialogue, credits,
  the `END` page, epilogue preamble, and epilogue text in that exact order.
  This avoids reusing stale `DCE8/DCF0/DD07` portrait identities after the
  dialogue renderer has exited. Two full 154-panel inventories reproduced the
  same five-phase trajectory.
- Paired vanilla/DX captures found identical VBK0 tile graphics throughout
  Stages 2–7 and intact active tilemaps, proving this was palette metadata
  corruption rather than deleted or overwritten level art.
- Automated live captures show 360/360 neutral visible attributes in Stages
  2, 3, 4, and 6. Stage 5 and 7 contain only neutral attributes plus their
  vetted lava palette; all stages have zero tile-bank/flip/priority leakage.
- Three independent 48,000-frame mGBA soaks covered Stages 2–7 for 8,000
  frames each, including rooms 1, 3, 5, and 7, with zero unexpected/unsafe
  attributes or lava-table mismatches.
- Fresh-boot diagnostic entry through the original boss dispatcher verified
  all nine boss arenas, with each live WRAM table byte-for-byte equal to its
  dedicated bank-13 table and each arena retaining visible color.
- Six stock boss routes naturally reach `D880=0x17` in exact-ROM mGBA
  captures. The death illustration, first window-enable frame, and settled
  GAME OVER screen all have zero displayed non-BG0 or unsafe attributes on
  both physical tilemaps.
- Title, stage-intro timing, Stage 1 colorization, item-menu HUD,
  `SELECT+START`, scroll stability, and phantom-sound regressions still pass;
  the phantom trace is 30 transitions versus vanilla's cached 18 (threshold
  36).
- Repaired output MD5: `4f20b0cb7ab206c0216282a2f8fd113d`
  (informational only; the ROM itself is not committed).

## [v3.01-stream-rc3] - 2026-07-22

### Fixed

- Restore the original `STAGE XX` splash duration by bypassing the expensive
  background/object colorizer while the all-palette-0 stage card is active.
  The stock LCD-mode wait now observes every VBlank, so the intro ditty plays
  once instead of repeating while stage loading stalls.
- Keep the item-menu HUD clean with either hardware window map. While gameplay
  is paused in the menu, the color sweep and inline attribute writer are gated
  off and the six visible window rows are reset directly to palette 0. This
  removes the timing-dependent red HP/separator artifacts exposed by the
  shorter stage transition.
- Run the title-color screenshot probe on Qt's headless offscreen platform so
  it no longer depends on the desktop display cookie.

### Verified

- Frame-matched mGBA comparison: both the original ROM and DX remain on the
  stage card for exactly 156 frames and receive 233 timer ticks; neither sound
  pointer rewinds nor stage-card attribute contamination occur in DX.
- Title integration/color, gameplay palette, menu HUD, `SELECT+START` safety,
  scrolling stability, and phantom-sound regressions all pass.
- Repaired output MD5: `9c41db6cc7839136459c84078435d89f`
  (informational only; the ROM itself is not committed).

## [v3.01-stream-rc2] - 2026-07-22

### Fixed

- Keep title-screen text on palette 0 instead of inheriting the dungeon font's
  red palette, and refresh the intended white-to-blue-gray palette safely at
  the start of each title VBlank.
- Clear the six visible item-menu window attribute rows in both hardware
  window maps when the menu opens, removing the red palette bleed from the HP
  bar, `MEDICAL` separator, and full-health `F` marker.
- Remove the unstable `SELECT+START` teleport and IRQ stack redirect that could
  freeze gameplay. Scene-aware palettes, lava overrides, and level-select
  setup remain enabled.
- Make the gameplay palette probe wait for a real dungeon scene rather than
  accepting the earlier all-palette-0 stage splash as gameplay.

### Verified

- Combined cold-boot mGBA release gate: exact title palette bytes, zero
  contaminated title attributes, and zero contaminated menu HUD attributes.
- Live `SELECT+START` regression through frame 1300: gameplay continued, the
  scene and boss indices stayed unchanged, and shadow OAM kept advancing.
- Title integration/color, gameplay background palette, miniboss object
  palette, and boot/menu-transition probes.
- Repaired output MD5: `bd2bd354dbf5393fbc8d37cee79595cc`
  (informational only; the ROM itself is not committed).

## [v3.01-stream-rc1] - 2026-07-22

### Fixed

- Render the exact title footer `DX V3.01 STRUK LABS` independently of the
  current Git tag or detached-head state.
- Use the title screen's signed VRAM tile-addressing mode correctly. The
  native `3`, `0`, and `1` glyphs are reused, while a one-block GDMA transfer
  installs the period and restores the displaced native `9` after the title.
- Move footer glyph data out of the live palette/colorizer routines it had
  overwritten, with explicit collision and free-space assertions in the
  builder.
- Restore reliable title-menu input through the proven joypad sampler and
  keep the title-safe tile-only inline colorizer path.
- Restore the correct level-select WRAM target and remove the duplicate sound
  engine call from the VBlank wrapper.
- Preserve cold-boot title palette timing so the title no longer appears
  completely white.

### Verified

- Exact footer tilemap and period glyph in live mGBA memory.
- Title integration and title-color probes through 600 frames.
- Gameplay background palettes, miniboss object palettes, scrolling attribute
  stability, boot/menu transitions, and menu input in PyBoy and mGBA.
- Repaired output MD5: `2809fe9005b17441c83078d921128685`
  (informational only; the ROM itself is not committed).

### Known issues

- The in-game menu HUD has red pixels on the HP bar, `MEDICAL` separator text,
  and the full-health `F` marker. This is captured for the next palette pass.
