# Continue during a miniboss leaves death-fade BG palettes (792319cb)

Status: diagnostic prototype only. This is not production builder integration.

## Repro
Stage 1 Gargoyle (FFBF=01, scene D880=0A). Die with one credit and accept
Continue. The game resumes in D880=0A with the miniboss still present. All 8 BG
palettes keep the death/white-fade set (`7FFF7FFF7FFF7F29 ...`) until the
miniboss dies, so the room and HUD render flat pink. OBJ CHR and OBJ CRAM
match OG. Confirmed on the corrected r454 CGB-latch runtime and on the
installed library.

## Root cause
The bank13 VBlank commit gate at $7703 (r443e dealias) requires D880==02 and
DF5D==1 before it jumps to $740F (BG pal0 + DF4C=0x11 sequencer restart).
Only scene hook $7CFC/$7D18 raises DF5D, and only for scene 02. Resume into
0A never raises or consumes the request, so palettes are never reloaded.
The sequencer BG writer at $71B6 already folds 0A onto 02 (`AND F7`).
rc11 cannot reach this path because it never accepts Continue (#28).

## Prototype
`scripts/diagnostics/build_continue_miniboss_reload.py` patches 792319cb:
- the gate accepts D880 in {02,0A}
- a bank-0x27 helper raises DF5D for 02, or for 0A when the previous scene
  (DF0D) is 17 (death/continue)

After Continue, BG CRAM equals the pre-death gameplay CRAM by +30f. The
no-boss continue is unchanged. Residual: a pre-existing sequencer 4-byte
burst ($71E4-71EC) can land in STAT mode 3 and drop one byte. The same
signature appeared in the #28 "stale 4A29". Identity pins in
stage_card_palette_handoff.py, crystal_transition_contract.py and
menu_commit_protocol.py must be updated before a production integration.
