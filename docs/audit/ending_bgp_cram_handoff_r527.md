# Ending BGP/CRAM handoff r527

## Result

r527 is the current experimental ending-handoff candidate:

- path: `tmp/ending-bgp-handoff-r527/candidate.gb`
- SHA-256: `13beaa1b0867dc71153538531838e00c101b355c2b3bdb8823184784ea78cc6b`
- exact base: r475, SHA-256
  `59384e3c0ea5508ade2ff8d08af2f3012c4eff1f5f9cf1cebb2f04273cd1693f`
- direct parent: r524, SHA-256
  `e2ffa7e6c91cb630066524c49c00b56243f9bc61b137bab367b97a441c95224a`

It remains explicitly experimental and non-promotable. The selected gates in
this audit are not the complete release matrix, do not constitute a Stage-1
READY claim, and do not update a release or Analogue Pocket pin.

## Defects and repair

The stock ending changes DMG BGP while constructing story, credits, END, and
epilogue pages. On CGB, BGP does not remap CRAM, so a colorized ROM must commit
the corresponding CRAM rows before exposing each BGP state.

r518 supplies the page-aware mirror and synchronized private fade paths. r524
adds a CRAM-black prepublication at the stock epilogue `$554A -> $0A16` reset,
while retaining the native BGP/OBP reset result `AF=$FFA0`. r527 keeps those
repairs and widens r518's final repeated-row retry from byte `$3F` to the whole
color at bytes `$3E/$3F`.

The r527 addition is deliberately narrow:

- bank 20 `$79D5` changes from the inherited wait-loop entry to `JP $7380`;
- the 25-byte erased cave at bank 20 `$7380` repeats the inherited LCD-phase
  wait, selects BCPS `$FE`, and rewrites source bytes 6 and 7;
- `RST $10` still receives `A=$07`; flag-neutral `DEC HL` selects byte 6, so
  the successful path retains the inherited final A/F and restored HL;
- DI/EI are absent, so the caller's interrupt state is unchanged; and
- the exact r524 parent delta is 30 bytes including cartridge checksums.

The native global fade at fixed `$0F5A..$0F65`, the bank-13/bank-16 native
palette-loader heads, and all relocated arena tables remain byte-for-byte
inherited.

## Rejected iterations

- r515 passed focused ending runs but overlapped the Angela arena LUT.
- r516 read palette source bytes from the wrong bank.
- r517 retained black CRAM through the visible `$E7` epilogue page.
- r518 fixed that reveal but exposed the stock late `$FF` reset at one-frame
  resolution.
- r519/r520 double-popped HL in the shared credits dispatcher.
- r521-r524 fixed the dispatcher/reset path but exposed a rejected CRAM byte
  at repeated-row index `$3E` on a mode edge.
- r525 delayed the whole 64-byte publisher and regressed visible ownership.
- r526 retried the final pair at a fresh scanline edge; its accumulated delay
  missed the fixed 32,000-frame return-to-title bound.

## Reproducible static checks

```sh
python3 scripts/diagnostics/compose_ending_bgp_handoff_r527.py
python3 scripts/diagnostics/verify_ending_bgp_handoff_r527_static.py
python3 -m unittest \
  tests.test_ending_bgp_handoff_r527 \
  tests.test_story_attr_cram_equivalence
```

The static verifier pins the exact digest, erased-cave provenance, 30-byte
parent delta, instruction bytes, interrupt neutrality, r524 handoff, and
untouched native fade. Twelve focused unit tests pass.

## One-frame emulator evidence

Both inventories used `ENDING_INVENTORY_SAMPLE_INTERVAL=1`, the exact r527 ROM,
the patched mGBA CGB-latch build, and the checked single-flight launcher.

- `tmp/r527-ending-fine-full-current272/manifest.json`: pass; 322 distinct
  post-final panels; full story arts 5/6/7; full credits, END page, epilogue
  preamble, and epilogue text; zero unsafe attribute cells; exact production
  discriminators; return to title.
- `tmp/r527-prefinal-fine-full-current273/manifest.json`: pass; 4,149 distinct
  pre-final panels; exact `4 -> 7 -> 4` art trajectory; zero unsafe attribute
  cells; exact production discriminators.

## Fresh release-harness evidence

Both isolated tested-ROM copies match the source SHA-256 above. Their manifests
report intact ROM hashes, source inputs, and runtime tool identities.

- `tmp/r527-story-release-gates-current274/manifest.json`: selected pass for
  `live_palette_deck` and dependent `story_attr_production`. The story oracle
  validates every CRAM row actually referenced by visible attributes; unused
  aliased rows are not mistaken for visual mismatches.
- `tmp/r527-ending-release-gates-current275/manifest.json`: selected pass for
  `final_cutscene_mgba`, `pre_final_inventory`, `ending_inventory_a`,
  `ending_inventory_b`, and `ending_discriminators`.

ROMs, savestates, manifests, and captures remain ignored scratch artifacts.
