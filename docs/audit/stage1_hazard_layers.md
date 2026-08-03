# Stage 1 rotating-spike layer and art audit

Date: 2026-08-02

This audit answers whether the rotating cylinder in the user's Stage 1 capture
needs coordinated BG-tile and OBJ-sprite coloring. It does not. In the exact
captured state, the complete visible cylinder, rings, upright teeth, and
hanging teeth are background tiles. Hardware OAM contains Sara, clipped
actors, and a projectile, but no OAM rectangle overlaps the spike assembly.

## Reproducible receipt

The analyzer reads the embedded `gbAs` payload from the checked-in mGBA state.
It does not launch an emulator or modify a ROM/state.

```sh
python3 scripts/diagnostics/analyze_stage1_hazard_layers.py \
  --output /tmp/penta-stage1-hazard-layers
```

The receipt records:

- `LCDC=8B`, `SCX=0`, `SCY=4`, active map `$9C00`, signed BG tile mode;
- every visible `$60-$7F` spike-family cell and its screen rectangle;
- every visible hardware-OAM rectangle from the state's exact 160-byte OAM;
- zero BG-spike/OAM intersections;
- 32/32 live `$60-$7F` patterns byte-equal to the Stage 1 ROM source at
  file offset `$1D000 + tile*16`;
- all 22 proposed rotating/body VRAM-bank-1 slots blank in all 89 parsed
  saved-state fixtures; and
- the production Stage 1 LUT and candidate source art equal the shared YAML
  compiler output.

Artifacts are `receipt.json`, `bg-vs-oam-layer-map.png`,
`current-vs-semantic-art.png`, and `hazard-variant-tiles.png`.

## Why palette assignment alone is insufficient

The moving art and its floor/rail background are baked into the same opaque
2bpp BG cells. The white rotating pixels use source index 0. All current BG
ramps keep index 0 white, so assigning BG5 or BG6 can color the midtones but
cannot color those white pixels.

A blanket 2bpp remap was tested offline and rejected. It colored the rings,
but it also colored the stationary rail and the checkerboard pixels embedded
in those same tiles. The visual preview caught that failure before any ROM was
changed.

The revised prototype compares each animation tile with the exact environment
tile it overlays:

| Animation tiles | Semantic baseline |
|---|---|
| `64/66` | floor `01` |
| `65/67` | floor `02` |
| `68` | shadow `04` |
| `69` | shadow `03` |
| `6C/6D` | stationary upper rail `6E` |
| `74` | floor `01` |
| `75` | floor `02` |
| `76/78` | shadow `04` |
| `77/79` | shadow `03` |
| `7C/7D` | stationary lower rail `7E` |

Pixels equal to the baseline keep environment colors. Changed non-black tooth
pixels become one dedicated hazard index, while black outlines stay black.
That comparison alone left a few floor/shadow-colored pixels inside the tooth
tips where moving art coincidentally equaled its baseline. The final prototype
therefore traces an explicit row-span silhouette inside each of the 12 tooth
animation frames. Every span starts and ends on original black outline pixels;
all enclosed non-black pixels become gold, while every pixel outside the span
still uses the conservative baseline comparison. The receipt tests all three
properties across all 12 frames, so the fill cannot silently spread into the
checkerboard or cast shadow.
The four ring tiles also use tiny art-audited masks for their complete arcs:
`6C` rows 4-7, `7C` rows 0-3, `6D` rows 0-4, and `7D` rows 3-7. Those masks
cover ring pixels that coincidentally equal the stationary rail and would
otherwise remain gray. Ring tiles then use BG5: ring arcs map to yellow, their
embedded cylinder material maps to yellow/red, and black outlines stay black.
Six body/end-cap tiles (`61/62/6E/71/72/7E`) receive equivalent silhouette masks.
This preserves exposed floor while continuously coloring the full cylinder,
rings, end cap, and protruding teeth.

## Preferred production path

VRAM bank 1 is available and is a valid isolation fallback, but it is not
needed for this Stage 1 family. The lower-risk implementation is:

1. apply the 24 semantic 2bpp variants directly to the Stage 1-only source
   art at `$1D000 + tile*16`;
2. map the 12 floor-sharing tooth IDs to BG7 in the scene-`$02` Stage 1
   attribute table;
3. map ring IDs `6C/6D/7C/7D` and cylinder-body IDs
   `61/62/6E/71/72/7E` to fire
   BG5, while
   deliberately leaving the `63/73` vertical shadow column out of that set;
4. keep the 10 declared support/end-shadow IDs on metallic BG6; and
5. leave hardware OAM and every OBJ palette path untouched.

This keeps the 384-byte source window the same size and changes 258 bytes. It
uses no VRAM-bank switch, WRAM art state, or runtime art rewrite, and keeps
attribute values in the supported `0..7` range instead of introducing bank
bit 3 (`$08`).

Production now provides that Stage-1-local BG7 row. Audience color tuning is
owned by `stage1_hazard_palettes.RotatingSpikeTeeth.colors` in
`palettes/penta_palettes_v097.yaml`; BG5 in the same file controls the rings
and cylinder body. The phased loader keeps the title-safe BG7 alias, selects
the hazard row only when the active `FFD0` stage flag is zero, and restores
normal YAML BG7 in the bonus and later stages. The live bonus receipt and the
alternate-YAML build round trip prove both sides of that contract.

## Bank-1 fallback

If another hazard shares a source tile with non-hazard Stage 1 art, the same
semantic variant can instead live at the corresponding VRAM-bank-1 pattern
slot. Its map attribute becomes `0x08 | palette`. The fixture corpus shows the
20 spike slots are currently blank in bank 1, but a production loader would
still need an exact stage-entry/LCD-safe load point, a later-scene teardown or
overwrite contract, and updated validators that permit bit 3 only for declared
variants.

## Active generalized hazard schema

The complete production contract is active under
`stage1_hazard_art.rotating_spike` in
`palettes/bg_tile_categories.yaml`. The following condensed excerpt documents
the shape used by the compiler; the checked-in YAML remains canonical:

```yaml
hazard_art_variants:
  stage1_rotating_spike:
    scene: 0x02
    destination_bank: 0
    tooth_palette: 7
    ring_palette: 5
    body_palette: 5
    body_tiles: [0x61, 0x62, 0x6E, 0x71, 0x72, 0x7E]
    variants:
      0x64: {baseline: 0x01}
      0x65: {baseline: 0x02}
      0x66: {baseline: 0x01}
      0x67: {baseline: 0x02}
      0x68: {baseline: 0x04}
      0x69: {baseline: 0x03}
      0x6C: {baseline: 0x6E}
      0x6D: {baseline: 0x6E}
      0x74: {baseline: 0x01}
      0x75: {baseline: 0x02}
      0x76: {baseline: 0x04}
      0x77: {baseline: 0x03}
      0x78: {baseline: 0x04}
      0x79: {baseline: 0x03}
      0x7C: {baseline: 0x7E}
      0x7D: {baseline: 0x7E}
    equal_pixel_map: {0: 0, 1: 1, 2: 1, 3: 3}
    changed_pixel_map: {0: 2, 1: 2, 2: 2, 3: 3}
    ring_regions: # x0, y0, x1, y1; end-exclusive
      0x6C: [0, 4, 8, 8]
      0x7C: [0, 0, 8, 4]
      0x6D: [0, 0, 8, 5]
      0x7D: [0, 3, 8, 8]
    tooth_row_spans: # y: [x0, x1], end-exclusive; full table is receipted
      0x64: {5: [3, 5], 6: [2, 6], 7: [1, 7]}
      0x67: {1: [3, 5], 2: [2, 6], 3: [2, 6], 4: [1, 7], 5: [1, 7], 6: [0, 8], 7: [0, 8]}
      0x77: {0: [0, 8], 1: [0, 8], 2: [1, 7], 3: [1, 7], 4: [2, 6], 5: [2, 6], 6: [3, 5]}
```

Future hazards must first produce the same layer receipt. An OBJ-backed hazard
would use the normal OBJ identity/palette pipeline; a BG-backed hazard would
use source-art semantics or the bank-1 fallback. A visual resemblance to a
sprite is not enough to choose the path.

## Promotion receipts

The hash-isolated RC7 candidate completes the focused promotion set:

1. all 24 source tiles, the exact LUT, and the approved 20-tile artifact hash;
2. 32/32 visible full-cycle cells: 10 teeth, 20 ring/body, 2 supports;
3. exact live BG5 and Stage-1 BG7 CRAM, plus ordinary BG7 in bonus play;
4. pickup-class, pickup-art, 1,200-frame rendered no-bleed, tilemap,
   low-health, speed, title/demo, opening-story, and palette-roundtrip gates;
5. a byte-identical deterministic rebuild.

The complete release matrix, audience color vote, and reservation-backed
MiSTer validation remain release-level checkpoints.
