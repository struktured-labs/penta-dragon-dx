# Cutscene region palettes — production implementation

Date: 2026-08-03

Status: **ROM-native and verified**, with colors intentionally left tuneable
for the livestream palette vote.

The former offline spike has been promoted into the production builder. Story
illustrations occupy the visible top 20×8 cells. Exact tile-aligned YAML masks
select multiple BG palette rows inside each illustration, while the separator,
dialogue border, and text remain 20×10 neutral BG0 cells.

The verified candidate is:

- MD5: `c4d599af736a92c5d260fa1d96380faf`
- SHA-256: `61a77022f456d1e10b74f1a276fd1ebd3ce19a02dfd34f1229e67e2bf287e5e4`
- Palette YAML SHA-256:
  `53e7a512511d4ac2c7de320ee9723e5fab069376c379f50251863f62f3dcf14b`
- Suite-source fingerprint:
  `ef5afd488683d95995fceb14b489725ef178b72e6c5a00f2dc4f33acc3654bff`

## Production source and runtime

`palettes/penta_palettes_v097.yaml` owns seven story art IDs through six
unique masks and 23 rectangles. `scripts/cutscene_region_palettes.py` validates
the complete ID set and compiles each mask to exactly 20×8 cells.

`scripts/build_v302_title_fix.py` compiles those masks into 18 unique RLE rows,
54 runs, and 110 data bytes. A five-byte bank-13 bridge calls the bounded
bank-6 classifier; the existing story scheduler writes one five-cell quarter
at a time and clears all 200 lower cells to BG0. The page key includes the art
ID, active tilemap, and aligned viewport shift, so transitions restart the
finite pass instead of leaving stale attributes.

Every written value is a palette index from 0 through 7. VRAM-bank, flip, and
priority bits remain zero.

## Region assignments

| Illustration | Production regions |
|---|---|
| Opening book (art 1) | BG6 slate surround; BG5 book/pages |
| Opening Sara (art 2) | BG7 wings; BG2 hair/body; BG5 face; BG4 costume |
| Opening dragon eye (art 3) | BG7 cavern; BG6 socket; BG3 eye |
| Pre-final Penta (art 4) | BG4 left head; BG5 center head; BG3 right head |
| Post-final dragon (art 5) | BG6 body; BG5 central crest |
| Post-final Lisa/dragon (art 6) | BG7 surround; BG2 head; BG5 horn/crest |
| Pre/post-final Sara (art 7) | BG7 wings; BG2 hair/body; BG5 face; BG4 armor |

These are semantic assignments, not final color approval. Editing the named BG
rows in `penta_palettes_v097.yaml` and rebuilding changes the presentation
without changing Python or assembly.

## Exact current evidence

The 2026-08-03 verification used the candidate, YAML, and suite-source hashes
above. The dedicated profile passed 21/21 with the source fingerprint identical
before and after the run:

- Natural OPENING: 33 panels; arts 1, 2, and 3 all reached; every committed
  160-cell illustration exactly matched its YAML mask; all 200 dialogue cells
  remained BG0; zero unsafe attributes.
- mGBA final-story pipeline: 57 pre-final and 21 post-final samples; zero
  position-mask mismatches and zero non-neutral story-LUT samples; both native
  160×144 screenshots were recorded and hashed.
- Full pre-final inventory: arts 4 and 7 reached and exactly matched.
- Two independent full endings: 154 panels each; arts 5, 6, and 7 reached and
  exactly matched; credits reached full BG1, END reached full BG2, the epilogue
  preamble reached BG0, and epilogue text reached full BG3. Both runs returned
  to the title and produced the same five-phase discriminator trajectory.

The authoritative combined receipt and artifacts from that run are:

- `/tmp/penta-live-regression-sourcebound-v4/manifest.json`
- `/tmp/penta-live-regression-sourcebound-v4/artifacts/opening-cutscene/manifest.json`
- `/tmp/penta-live-regression-sourcebound-v4/artifacts/final-cutscene-mgba/receipt.json`
- `/tmp/penta-live-regression-sourcebound-v4/artifacts/pre-final-inventory/manifest.json`
- `/tmp/penta-live-regression-sourcebound-v4/artifacts/ending-inventory-a/manifest.json`
- `/tmp/penta-live-regression-sourcebound-v4/artifacts/ending-inventory-b/manifest.json`
- `/tmp/penta-live-regression-sourcebound-v4/artifacts/ending-discriminators.json`
- `/tmp/penta-cutscene-production-contact-v3.png`

A fresh source rebuild at `/tmp/penta-final-source-rebuild.gb` is byte-for-byte
identical to the tested candidate (MD5/SHA-256 above).

The stock ending reuses WRAM `$C600` as script workspace during some direct-
written credits pages. The exact same byte patterns reproduce on the original
ROM. Therefore the neutral-LUT invariant applies only to story scenes `$19`
and `$1A`; credits/END/epilogue are instead checked by their complete visible
360-byte attribute layouts.

## Reproduction

```sh
python3 scripts/diagnostics/inventory_opening_cutscene.py \
  rom/working/penta_dragon_dx_FIXED.gb --expect-production \
  --output /tmp/penta-opening-production

python3 scripts/diagnostics/verify_final_cutscene_mgba.py \
  rom/working/penta_dragon_dx_FIXED.gb \
  --output /tmp/penta-final-production

python3 scripts/diagnostics/inventory_final_cutscene.py \
  rom/working/penta_dragon_dx_FIXED.gb --entry post-final \
  --frames 32000 --expect-production --output /tmp/penta-ending-a
```

Run the post-final inventory twice and pass both manifests to
`analyze_ending_page_discriminators.py` for the repeatability receipt.
