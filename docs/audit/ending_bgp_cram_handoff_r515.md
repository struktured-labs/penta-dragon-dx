# Ending BGP/CRAM handoff r515 (rejected)

## Historical result (invalidated)

r515 was the first candidate to pass the focused ending inventories, but it is
rejected: its bank-20 body overlapped the relocated Angela arena LUT. The
retained ROM and evidence below are diagnostic history only. The non-promotable
successor is documented in `docs/audit/ending_bgp_cram_handoff_r527.md`.

Its retained candidate is:

- path: `tmp/ending-bgp-handoff-r515/candidate.gb`
- SHA-256: `30f85499221a057ea80dc82f2a49f10e8857ecfa6b18d546cc169ab25c551879`
- exact base: r475, SHA-256
  `59384e3c0ea5508ade2ff8d08af2f3012c4eff1f5f9cf1cebb2f04273cd1693f`

The candidate remains experimental and non-promotable until the complete
release qualification pipeline is run. These ending-specific results are not
a Stage-1 READY claim and do not update any release or Pocket pin.

## Defect

The DMG ending constructs and hides pages with BGP values `$FF`, `$FE`, and
`$F9`. On CGB hardware, BGP does not remap palette RAM. The native sequence
therefore exposed partially updated color pages and stale attribute ownership
during story, credits, END-page, and epilogue transitions.

## Repair boundary

The checked composer is
`scripts/diagnostics/compose_ending_bgp_handoff_r515.py`. It installs a
1,746-byte bank-20 service which:

- mirrors hidden BGP transitions into all CGB BG palette rows;
- restores only the row deck owned by the page being revealed;
- synchronizes private credits and story fade callers before BGP publication;
- repairs the credits' visible 20x18 attribute page in bounded HBlank/VBlank
  writes; and
- suppresses the bank-13/bank-16 four-byte palette publisher only while the
  ending mirror owns hidden CRAM.

The native palette-loader heads at bank 13/16 `$6900..$6905` and the global
fade service at fixed `$0F5A..$0F65` remain byte-for-byte unchanged. The build
receipt records all 1,919 changed bytes, and the regression test proves every
one falls inside the declared hooks, local caves, bank-20 body, or cartridge
checksums.

## Reproducible checks

Build and deterministic boundary checks:

```sh
python3 scripts/diagnostics/compose_ending_bgp_handoff_r515.py
python3 scripts/diagnostics/verify_ending_bgp_handoff_r515_static.py
python3 -m unittest \
  tests.test_ending_bgp_handoff_r515 \
  tests.test_ending_fade_cram_oracle \
  tests.test_ending_inventory_probe_contract
```

The static verifier executes the installed LR35902 subsets for the mirror,
retry, palette guard, and scene-site paths. It also checks register/stack
handoffs, CRAM ownership, exact continuations, bounded credits publication,
and the transient `$E7` case.

## Fresh emulator evidence

Both production inventories used the exact r515 path and SHA above, with the
patched mGBA CGB-latch build and the project single-flight launcher.

- Post-final every-frame inventory:
  `tmp/r515-ending-fine-full-current239/manifest.json`
  - status `pass`; 321 panels
  - exact scene signature
    `(1A,01,00,00) -> (16,01,00,00) -> (16,01,00,01) ->`
    `(00,0C,00,01) -> (00,0C,01,01)`
  - full story arts 5, 6, and 7
  - full credits, END page, epilogue preamble, and epilogue text
  - zero unsafe attribute cells, neutral inactive story table, exact
    production discriminators, and return to title
- Pre-final every-frame inventory:
  `tmp/r515-prefinal-fine-full-current240/manifest.json`
  - status `pass`; 4,228 panels
  - exact art sequence `4 -> 7 -> 4`
  - 4,107 stable samples, 121 transition samples, and zero stale-tail samples
  - zero unsafe attribute cells and exact production discriminators

ROMs, manifests, and captures remain ignored scratch artifacts as required by
the project artifact policy.
