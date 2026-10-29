# Post-ending soft reset: re-run DX cold init

## Symptom
After the ending, pressing GAME START on the returned title hangs (RST38 storm).

## Root cause
The ending resets through `01:5553 CALL $428F` / `01:5556 JP $0150`. Boot at
`$0150` clears `$C000-$DEFF` only. DX cold init (`13:6E00`, `13:6E2D`) is
skipped when `$DF02 = $5A` / `$DF08 = $5A`, which survive the soft reset, so the
`$DBC0-$DBFC` runtime installed by cold init is never rebuilt and
`CALL $DBF3` at `01:42F5` executes zeros.

## Fix (stage `soft-reset-cold-init`, `scripts/diagnostics/build_soft_reset_cold_init.py`)
- `01:5556`: `C3 50 01` -> `C3 E2 00`. `CALL $428F` and its return address
  (`$5556`, dispatched by 14:746C on the low byte) are untouched.
- `00:00E2-00EF`: `F3 21 00 DF 06 F0 AF 22 05 20 FC C3 50 01`
  (DI; zero `$DF00-$DFEF`; `JP $0150`). Fill `$00E2-$00FF` was stock and
  unreferenced (#54 uses `$00D0-$00E1`). `$DFF0-$DFFF` is left for the live stack.
- Deterministic single pass, no marker register, no new bank.

## Why clearing `$DF00-$DFEF` is safe
- OG: `$DFxx` is stack only (`LD SP,$DFFF` at `$0155` before any pop).
- DX: SVBK-1 `$DF00-$DFEF` holds only cold-boot state (hash, magic sentinels),
  which power-on presents as zero. Experimental menu state in SVBK7:DF00 is a
  different bank and is not touched.
- Evidence: 30 frames after title entry, power-on vs post-reset dumps of
  `$DBC0-$DBFF` and `$C600-$C6FF` are identical; every byte DX writes in
  `$DF00-$DFEF` matches; the only differences are never-written bytes
  (emulator power-on pattern vs zero) and stack residue at `$DFE0+`.

## Equivalence
Attract lockstep frames 0-26000, cold boot, per-frame WRAM (32 KiB), VRAM,
OAM, HRAM and CPU registers: byte-identical to parent 05020905. Stage-7 patrol
identical. Natural ending -> title -> GAME START reaches Stage 1 (scenes
14,00,1A,16,00,01,00,15,18,02,0A,0B).
