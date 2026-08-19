# Ted sparse publisher production-integration audit

Date: 2026-08-15

Scope: the experimental `PENTA_TED_WRITER_MIRROR=1` architecture in
`scripts/build_v302_title_fix.py`. This is a static/offline audit. No emulator
was launched.

## Verdict

Do not promote the current layout. The sparse algorithm is plausible, but the
present integration has two direct ROM-data collisions and three unresolved
state-ownership problems:

1. The bank-13 writer runtime at `$7687-$76FE` replaces 120 bytes of Ted's
   live `$7600-$76FF` tile-to-palette table.
2. The sparse scan at `$6D4E-$6D5B` replaces `$6D50-$6D5B`, twelve bytes of
   the 32-byte title footer glyph data at `$6D50-$6D6F`.
3. The two-map invalidation latch still lives at `$C5FE`, despite the current
   architecture's own finding that Ted overwrites the `$C500` page.
4. The `$D000-$D2FF` planes publish eight padding columns per row, but the
   sparse compiler writes only the first 24 columns. Those 192 padding bytes
   per bank have no deterministic initialization in the ROM-resident tracker
   path.
5. The reserved switchable-WRAM contract stops at `$D305`; the experiment
   actually owns dirty maps at `$D300-$D323` and scratch at `$D324`.

The global `$3136` hook also maps bank 13 before rejecting non-Ted scenes. Its
non-Ted cost and ownership must be measured before this can be considered a
latency optimization.

## Receipts

The current builders report these exact lengths:

- bank-13 writer runtime: 120 bytes (`98` code bytes, padding to offset
  `$70`, then an 8-byte mask table);
- fixed writer stub: 17 bytes at `$0838-$0848`;
- bank-1 source-clear invalidator: 11 bytes at `$6FE4-$6FEE`;
- Ted post-copy wrapper: 19 bytes at `$563A-$564C`.

`tmp/ted-cache-current/writer-v4.gb` contains the current generated sparse
fragments byte-for-byte. Comparing that ROM to the generated payloads proves
that the writer runtime, rather than the Ted LUT, owns `$7687-$76FE`, and that
the sparse scan, rather than the footer glyphs, owns `$6D50-$6D5B`.

### Current sparse fragment map

| Range | Bytes | Audit result |
|---|---:|---|
| `$5340-$5350` | 17 | Safe only in writer mode; aliases cached overlay F |
| `$539E-$53A4` | 7 | Safe; writer-mode pointer advance |
| `$55D8-$55E2` | 11 | Safe; ends before Stage-1 entry helper at `$55E5` |
| `$56FF-$5715` | 23 | Safe; starts immediately after semantic compare `$56FA-$56FE` |
| `$578C-$57AB` | 32 | Safe only in writer mode; aliases retired Ted sanitizer main |
| `$5830-$5841` | 18 | Safe only in writer mode; aliases cached column wrap |
| `$5860-$5871` | 18 | Safe only in writer mode; aliases cached overlay E |
| `$5890-$589F` | 16 | Safe only in writer mode; aliases cached overlay A |
| `$5CDA-$5CE8` | 15 | Safe only in writer mode; aliases retired materializer front |
| `$5D4C-$5D5B` | 16 | Safe; immediately follows Shalamar cell `$5D3A-$5D4B` |
| `$5D7F-$5D8D` | 15 | Safe; follows arena dispatch `$5D6A-$5D74` |
| `$5E2D-$5E49` | 29 | Safe only in writer mode; retired sanitizer geometry continuation |
| `$6150-$6157` | 8 | Safe only in writer mode; cached overlay G alias |
| `$6180-$6187` | 8 | Safe; ends before Stage-1 scanner region beginning `$618F` |
| `$623C-$6248` | 13 | Safe only in writer mode; cached sparse scan alias |
| `$6250-$6253` | 4 | Safe only in writer mode; cached overlay H alias |
| `$6268-$626F` | 8 | Safe exact gap |
| `$6D4E-$6D5B` | 14 | **Unsafe: overlaps title glyph data `$6D50-$6D6F`** |
| `$7687-$76FE` | 120 | **Unsafe: inside Ted LUT `$7600-$76FF`** |

The fixed-bank ranges are tight but non-overlapping: writer stub
`$0838-$0848` ends immediately before the lava-decider entry at `$0849`, and
the bank-1 invalidator occupies 11 of the 13 native-zero bytes at
`$6FE4-$6FF0`.

## Collision-free ROM relocation

### Writer tracker and mask table

Use the four writer-exclusive sanitizer/installer records below:

| Fragment | Capacity | Normal owner outside writer mode |
|---|---:|---|
| `$58E0-$5903` | 36 | sanitizer crown / incremental installer continuation |
| `$5910-$5933` | 36 | sanitizer active |
| `$5940-$5963` | 36 | sanitizer installer/special |
| `$5970-$5993` | 36 | sanitizer clear/installer middle |

They provide 144 physical bytes. Three tail jumps leave 135 usable bytes,
enough for the current 98-byte tracker, 8-byte mask table, and the branch
rewrites required by fragmentation. They are zero and untouched in the
writer-v4 build, and their owners are architecture-exclusive with writer
mirror mode.

Suggested logical partition:

1. `$58E0`: entry, scene/destination validation, and untracked exit;
2. `$5910`: offset-to-bit conversion and mask lookup;
3. `$5940`: bank-2/bank-3 dirty-bit updates and SVBK restoration;
4. `$5970`: mapper return tail plus the aligned 8-byte mask table near the
   fragment end.

Generate these as named fragments with absolute branches. Do not slice the
current monolithic byte stream: its relative branches assume contiguity.

### Sparse bitmap scan

Move the 14-byte scan from `$6D4E` to `$53A5-$53B2`. The preceding pointer
advance occupies `$539E-$53A4`; the underlying asserted-zero run continues
through `$53B5`. This leaves three guard bytes before the next resource.

## WRAM ownership and initialization

Use this writer-mode record in both SVBK 2 and 3:

| Range | Purpose |
|---|---|
| `$D000-$D2FF` | 24-row attribute publication plane, including padding |
| `$D300-$D323` | 36-byte sparse dirty bitmap |
| `$D324` | rotating bitmap-byte scratch |
| `$D325-$D326` | recommended two-byte plane-initialized signature |

Extend `verify_ted_cache_plane_reservation.py` and its Lua watchpoint range
from `$D000-$D305` through at least `$D326`. Declare only the exact tracker,
initializer, compiler, scanner, and GDMA PCs as allowed owners/readers.

On the first publication for each bank, clear that bank's 24 groups of eight
padding bytes, set its initialized signature, and force all 36 dirty bytes.
Do this lazily per selected physical map, not as two `$300` fills in the
scene-change VBlank. A full two-plane fill previously caused palette/VBlank
timing failures; only 192 padding bytes per bank require explicit clearing.

The last sparse source row (`$C3C8-$C3DF`) cannot start a complete 2x2. Keep
the current compile rejection at source `>= $C3C8`; it consumes/clears those
bits without writing beyond `$D2FF`.

## C600 reload invalidation

The current source-clear hook marks both physical maps stale, but that is not
the same contract as palette-LUT reload invalidation.

Production Ted LUT ownership is:

1. On D880 transition to `$10`, `build_scene_detect()` copies the ROM page
   `$7600-$76FF` to `$C600-$C6FF`.
2. The CRAM palette scheduler changes colors, not C600 indices, and therefore
   does not require attribute recompilation.
3. A live editor that changes C600 tile assignments must explicitly rearm both
   physical maps.

Move the persistent two-bit invalidation latch out of `$C5FE`. `$C500` is not
an owned state page in the ROM-resident design. A candidate is retired `DF03`,
but it must first receive an all-scene write canary and be added to the WRAM
allocation map. The updater must read and consume this latch while SVBK is
still 1, then select bank 2/3.

Rearm this latch on the one-time scene-change path when A is Ted's `$10`.
`build_scene_detect()` already calls `TITLE_TRANSITION_SERVICE_ADDR` before
copying C600, so marking stale there is correctly ordered: the next
publication compiles against the newly copied table. The current transition
helper is full, so trampoline its existing Crystal rearm call to a larger
writer-exclusive helper that:

- preserves A;
- sets the two-bit latch for scene `$10`;
- retains the Crystal `$0E` palette rearm behavior;
- returns without touching other scenes.

For the browser/live editor, define one explicit operation: after changing any
C600 index, write the same two-bit invalidation latch. CRAM-only color edits do
not need it. A deterministic control should mutate one referenced C600 entry,
rearm, and require each physical map to expose the new attribute on its next
alternating publication.

## Global-hook latency hazard

The fixed `$3136` tail hook runs before the ROM tracker tests D880. Therefore
every invocation currently pays `DI`, bank-13 mapping, tracker dispatch, and
bank-14 restoration even when the tracker immediately rejects a non-Ted
scene. This could introduce a systemic dungeon/demo slowdown while improving
Ted.

Before production integration, extend the writer-ownership probe across title,
attract play, Stages 1/2, minibosses, and all arena scenes. Record `$3136`
entries by D880 and caller (`$30EB` or `$3103`). Then choose one route:

- if the two call sites are receipt-proven Ted-exclusive, remove the redundant
  scene rejection and document that ownership;
- otherwise gate before the ROM-bank switch at a Ted-specific upstream call
  site; do not accept a global per-metatile bank switch as release behavior.

The existing ownership receipt proves Ted canonical and staging cells share
the `$3127` blitter, but it does not prove non-Ted scenes never use that
blitter.

## Required integration gates

1. Add a mode-aware interval registry to the builder. Reject pairwise overlap
   before any ROM writes, including overlaps with data that may contain zero
   bytes. At minimum protect `$6D50-$6D6F` and all arena LUT pages
   `$7200-$7AFF`.
2. Build twice and require byte-identical ROMs.
3. Assert every generated fragment matches its final ROM slice after all later
   writes, not merely when initially installed.
4. Extend the WRAM reservation to `$D326` and retain synthetic foreign
   reader/writer negative controls.
5. Add C600 mutation/rearm positive and missing-rearm negative controls.
6. Add non-Ted writer-hook cadence/speed controls.
7. Run the existing cold-start, Stage-1 terrain/pickup, title/footer, Ted
   determinism, publication-sequence, visual-attribute, and 2,800-frame cadence
   gates before any headed presentation.

Until items 1-6 pass, treat writer mirror as an experiment, not a release or
livestream candidate.

## Recommended <=1% replacement: stock-copy two-plane cache

This is the production recommendation after auditing
`build_ted_cached_full_plane_runtime()`.  That runtime reconstructs a
canonical 32x32 tile plane, bypasses the stock tile copier, and depends on the
unsafe `$C4F5-$C5FF`, `$6D4E`, and `$7687-$76FF` ranges above.  It should not
be repaired in place.  Retire it as a negative control.

Keep the stock `$4295` alternating tile copy byte-for-byte and append an
attribute-only cache at Ted's receipt-proven sole call site, `$028A`.  The
existing `$DB87` form of `build_ted_native_postcopy_wrapper()` already has the
right shape: call `$4295` while ROM bank 1 is mapped, save its exact AF, map
bank 13, call the attribute service, restore bank 1, restore AF, and return.
The service must also preserve BC, DE, and HL and return with SVBK=1 and VBK=0.

### Authoritative compact-key receipt

Do not qualify this design against the later v73 artifact.  That artifact's
two-plane v4 receipt fails its collision and physical-publication gates.  The
qualified source corpus is:

- ROM SHA-256
  `0665980bb158fb835b7f3f44e11ad4e4d52882964273521e7bdb40b20fcba794`;
- source trace SHA-256
  `687bc23f244cf0f9fefb0ddde8af1965676bcd046e0445f5c4248f4c355c0827`;
- 485 publications over 2,800 frames, from
  `tmp/cadence/dx/ted.sources.bin`.

For the 22 receipt-locked source indices

```
350, 230, 419, 221, 186, 151, 204, 390, 399, 196, 227,
303, 403, 431, 443, 163, 164, 185, 374, 437, 464, 564
```

the two-byte production key is exactly:

```
key[0] = sum(C1A0[index] for index in samples) & 0xff
key[1] = C1A0[221]
```

The absolute sample addresses are `$C2FE,$C286,$C343,$C27D,$C25A,$C237,
$C26C,$C326,$C32F,$C264,$C283,$C2CF,$C333,$C34F,$C35B,$C243,$C244,
$C259,$C316,$C355,$C370,$C3D4`.  On the qualified corpus the key has zero
attribute-layout collisions, 43 distinct keys for 42 layouts, and a two-entry
FIFO needs 45 compiles and serves 440 hits.  The two physical destinations
alternate on all 484 transitions.  Destination-tag comparison reduces
attribute publication to 83 GDMAs and skips 402; an exact full-layout key
would save only two additional GDMAs.

Compute the key on every stock publication, then check the selected physical
map's resident tag *before* touching either switchable cache bank.  If its
key and generation match, return immediately.  Otherwise look for the key in
bank 2 and bank 3.  Hits do not reorder the FIFO.  A miss replaces the bank
selected by the FIFO cursor and toggles the cursor.

### Exact WRAM record ABI

Both switchable banks use only the already reserved `$D000-$D305` record:

| Address | Purpose |
|---|---|
| `$D000-$D2FF` | 24 rows x 32 attribute bytes; compile 24 C600 lookups and write eight zero padding bytes per row |
| `$D300` | compact-key sum |
| `$D301` | raw source byte `$C27D` (`C1A0[221]`) |
| `$D302` | palette-LUT generation; write this last as the record commit |
| `$D303` | miss-path generation scratch while fixed bank-1 DFxx is hidden |
| `$D304-$D305` | reserved/canary |

Use scene-exclusive fixed-bank metadata already allocated to Stage 1/5 when
Ted is not active:

| Address | Ted-scene purpose |
|---|---|
| `$DF53-$DF55` | `$9800` resident sum, discriminator, generation |
| `$DF56` | nonzero palette-LUT generation |
| `$DF57-$DF59` | `$9C00` resident sum, discriminator, generation |
| `$DF5A` | FIFO replacement bank, always 2 or 3 |

On entry to scene `$10`, increment `$DF56`, skipping zero, initialize `$DF5A`
to 2, and invalidate the two physical tags by clearing `$DF55/$DF59`.  Old
bank-2/3 records invalidate automatically because their `$D302` generation
no longer matches; scene entry never needs a large WRAM clear.  A live editor
that changes C600 tile-to-palette assignments performs the same nonzero
generation increment.  CRAM-only RGB edits need no cache invalidation because
the published palette indices remain correct.

### Compile and publication order

1. Preserve the complete post-`$4295` register/flag ABI.
2. Form the two-byte key from the 22 direct source reads.
3. Select `$9800` or `$9C00` from `(H & $FC)` and compare its fixed-WRAM tag.
4. On a physical hit, restore state and return without SVBK switching or GDMA.
5. On a physical miss, probe bank 2 then bank 3 by generation and key.
6. On a cache miss, select `$DF5A`, toggle 2/3, compile C1A0-C3DF into
   D000-D2FF, store D300/D301, then commit D302 last.
7. Set VBK=1 and perform one 48-block GDMA from D000 to the selected map.
8. Only after GDMA completion, store the selected physical resident tag.
9. Restore VBK=0, SVBK=1, BC/DE/HL, interrupt state, and the exact AF returned
   by `$4295`; restore ROM bank 1 in the outer wrapper.

The 24x24 compiler must consume every source byte and deterministically emit
all eight padding zeroes in every row.  It must not scan for a crown, generate
numbered limbs, alter DC0B, synthesize tiles, or add a cadence delay.  Those
operations are exactly what made the cached full-plane prototype diverge and
flicker.

### Collision-free ROM placement

Keep the existing 26-byte `$563A` source copied to `$DB80`, with `$028A`
calling its `$DB87` stock-alternating entry.  Rebuild the cache service as
absolute-jump fragments in the architecture-exclusive asserted-zero bank-13
sanitizer records:

`$578C-$57AF`, `$57BC-$57DF`, `$58E0-$5903`, `$5910-$5933`,
`$5940-$5963`, `$5970-$5993`, `$5DCC-$5DEF`, `$5DFC-$5E1F`,
`$5E2C-$5E4F`, and `$5E5C-$5E7F`, with the smaller existing `$54F2`,
`$55D8`, and `$56FF` records available for compact continuations.  Generate
each fragment independently and assert both its original zero/cave ownership
and final-ROM identity.  Do not place any part of the service in
`$7600-$76FF`, `$6D50-$6D6F`, `$C400-$C5FF`, or beyond `$D305`.

The prior every-publication 24x24 post-copy pass measured 5.76% slow.  Scaling
its dominant compile work to 45/485 publications and its GDMA work to 83/485
puts this design plausibly in the 0.6-0.9% range, but this is a sizing estimate,
not a receipt.  Promotion still requires a fresh deterministic 2,800-frame
cadence receipt at <=1%, zero compact-key collisions, exactly 45-or-fewer
compiles, 83-or-fewer attribute GDMAs, and the existing Ted geometry,
publication-sequence, cold-start, footer, and live-palette gates.
