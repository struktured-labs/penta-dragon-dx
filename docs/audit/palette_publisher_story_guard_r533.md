# Palette publisher and story neutral-row guard r533

## Result

r533 is the current experimental candidate:

- path: `tmp/story-neutral-guard-r533/candidate.gb`
- SHA-256:
  `4fc5028a50250130c87d6a84414b409e050e55407e9fb2ac0e05af7ce288a4ba`
- MD5: `0111d6d3042647cf78e97527478717f1`
- direct parent: r532, SHA-256
  `055a2754355439b60e4e310adf89854f4db16e70a27182edad8ed902e3c43821`
- ending-handoff ancestor: r527, SHA-256
  `13beaa1b0867dc71153538531838e00c101b355c2b3bdb8823184784ea78cc6b`
- exact base: r475, SHA-256
  `59384e3c0ea5508ade2ff8d08af2f3012c4eff1f5f9cf1cebb2f04273cd1693f`

It remains explicitly experimental and non-promotable. These selected passes
are not the complete release matrix, do not constitute a Stage-1 READY claim,
and do not update a release or Analogue Pocket pin.

## Palette-byte defect and atomic repair

The native bank-13/bank-16 palette loader publishes eight-byte CRAM rows as
two four-byte calls through `$71DB`. Calls that straddled an LCD phase or an
interrupt could silently lose bytes or resume with incoherent mapper shadows.

r532 installs a 47-byte bank-20 router at `$7320` and a 14-byte source writer
at bank 13/16 `$71E3`. The route:

- saves caller DE and the source bank;
- saves IE and masks interrupt sources without changing IME;
- writes immediately with LCD off or during VBlank;
- otherwise acquires mode 3 followed by its fresh HBlank;
- switches back through full mapper `$0061`, keeping DC09, FF99, and hardware
  bank selection coherent; and
- restores caller DE and IE immediately before returning.

BC and DE are restored, HL advances exactly four source bytes, and A returns
the saved IE. The complete static call graph proves A is dead: bank 13/16
`$71DB` is called only by `$7FE0`, and `$7FE0` is called only at `$717C`, whose
continuation uses D rather than A.

## Story-row defect exposed by the safer timing

r532 fixed the palette byte loss, but its timing exposed an inherited story
attribute routing error. Story art rows 0 through 7 retained a bit-7 family
marker and used the bank-6 per-cell VRAM guard. Neutral dialogue rows 8 through
17 instead loaded `C=$00`. That selected BG0 as intended, but also cleared the
bit-7 dispatch marker and sent all twenty writes through the unguarded ending
fast path.

The exact post-final trace retained palette 6 at visible row 9, column 15
(physical VBK1 `$9950`). The failed r532 report measured 161 nonzero cells and
one layout mismatch after a completed row cursor `$12`.

r533 changes only the neutral marker at bank 13 `$6D7A` from `$00` to `$80`.
The low three bits still select BG0, while bit 7 routes the entire row through
the existing bank-6 per-cell STAT guard. Including the cartridge checksum, the
exact r532 parent delta is two bytes: file offsets `$014F` and `$036D7A`.

## Rejected iterations

- r528 restored stack registers in the wrong order.
- r529 used the low-level mapper at `$09C0`, leaving DC09 and FF99 incoherent.
- r530 always waited through a complete frame for calls already in VBlank,
  causing palette-gate timeouts and severe throughput loss.
- r531 restored the VBlank fast path but forced EI for IME-clear callers,
  corrupting Stage 1 attributes and CRAM.
- r532 preserves IME and passes the palette-byte gates, but fails the complete
  story deck because neutral dialogue rows still use the unguarded path.

## Reproducible static checks

```sh
python3 scripts/diagnostics/compose_palette_publisher_atomic_r532.py
python3 scripts/diagnostics/verify_palette_publisher_atomic_r532_static.py
python3 scripts/diagnostics/compose_story_neutral_guard_r533.py
python3 scripts/diagnostics/verify_story_neutral_guard_r533_static.py
python3 -m unittest \
  tests.test_palette_publisher_atomic_r532 \
  tests.test_story_neutral_guard_r533 \
  tests.test_r527_inherited_profiles
```

The r533 verifier pins the exact digest, two-byte parent delta, canonical
builder output, `$80` marker semantics, bank-6 classifier mask, and per-cell
STAT guard. The combined focused suite passes 16 tests.

## Fresh exact-ROM emulator evidence

All runs used the r533 SHA above, the patched mGBA CGB-latch build, and the
checked project single-flight launcher. Each release manifest records an
isolated tested-ROM copy plus current source and runtime-tool identities.

- `tmp/r533-palette-gates-current298/manifest.json`: all four selected gates
  pass: current pickup state, all 19 current host palettes, visible pickup art,
  and 2,400 consecutive rendered frames in each flicker mode.
- `tmp/r533-story-release-gates-current296/manifest.json`: `live_palette_deck`
  and dependent `story_attr_production` both pass after regenerating and
  clean-loading the complete story-state deck.
- `tmp/r533-ending-release-gates-current297/manifest.json`: all five selected
  ending gates pass: short final-cutscene sampler, pre-final inventory, both
  post-final inventories, and independent discriminator analysis.
- `tmp/r533-post-final-current295/post_final.report`: the focused clean reload
  has 160 target art cells, 200 neutral dialogue cells, zero wrong attributes,
  and a neutral story table.

ROMs, savestates, manifests, traces, and captures remain ignored scratch
artifacts.
